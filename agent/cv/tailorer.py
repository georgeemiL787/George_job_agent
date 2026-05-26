"""LLM-based CV tailorer — generates per-role ATS-optimized LaTeX CV."""
from __future__ import annotations

import re
from pathlib import Path

from loguru import logger
from openai import OpenAI

from agent.config import Settings, get_settings
from agent.cv.variations import style_hint_for_role_family
from agent.llm_retry import call_with_model_and_key_pool, strip_think_block
from agent.search.base import JobListing

from agent.validation.latex import validate_latex_cv

SYSTEM_PROMPT = """\
You are an expert CV writer specializing in ATS-optimized resumes for AI/ML engineering roles.
You have exceptional attention to detail and guarantee 100% valid, compilable LaTeX code perfectly matching the exact structure requested.

RULES (never violate):
1. Use ONLY facts listed in the MASTER FACTS section. Never invent employers, degrees, certifications, dates, skills, or metrics.
2. Reorder sections and rewrite bullet points to emphasize the most relevant experience for this specific role and company.
3. Inject the most important truthful keywords from the JOB DESCRIPTION naturally into bullets and the summary. Do not keyword-stuff.
4. Rewrite the Summary section to address this exact role title and company specifically.
5. Include ALL quantifiable results from MASTER FACTS that are genuinely relevant to this role.
6. Keep the CV perfectly ATS-safe: single column, standard section headings (Summary, Skills, Experience, Projects, Education, Highlights), no icons, no tables, no graphics, no colored boxes.
7. The CV MUST fit on one page. Use \\vspace{} and font size adjustments if needed.
8. Output ONLY the complete compilable LaTeX source. Do not output conversational text or markdown fences before or after the latex document.
9. Use hands-on, built, developed, applied, contributed language. Never imply senior ownership or multi-year full-time experience.
10. Follow the exact LaTeX structure of the BASE LATEX TEMPLATE. Never change the preamble.
"""



def _build_tailor_prompt(
    listing: JobListing,
    score_result: dict,
    master_facts: str,
    base_template: str,
) -> str:
    key_matches = ", ".join(score_result.get("key_matches", []))
    ats_keywords = score_result.get("ats_keywords", [])
    ats_block = (
        "\n".join(f"  • {kw}" for kw in ats_keywords)
        if ats_keywords
        else "  (none extracted — use key_matches above)"
    )
    role_family = score_result.get("role_family", "adjacent")
    style = style_hint_for_role_family(role_family)
    style_block = f"\n{style}\n" if style else ""
    return f"""MASTER FACTS:
{master_facts}
{style_block}
TARGET ROLE:
Title: {listing.title}
Company: {listing.company}
Location: {listing.location}
Role Family: {role_family}

ATS KEYWORDS — inject ALL of these verbatim into bullets, summary, or skills \
(only where truthfully applicable):
{ats_block}

Key JD keyword matches to also include (high-level): {key_matches}

JOB DESCRIPTION:
{listing.description[:4000] if listing.description else 'No description available.'}

BASE LATEX TEMPLATE (adapt this structure, keep all packages and commands):
{base_template}

Produce the tailored LaTeX CV now. Output ONLY the complete LaTeX source.
"""

def _normalize_latex(content: str) -> str | None:
    content = strip_think_block(content)

    if "```" in content:
        for part in content.split("```"):
            if "\\documentclass" in part:
                content = part.lstrip("latex").lstrip("tex").strip()
                break

    if "\\documentclass" not in content:
        return None

    # Extract just the latex block
    start = content.find("\\documentclass")
    end = content.rfind("\\end{document}")
    if start != -1 and end != -1:
        return content[start:end + 14]

    return content


def tailor_cv(
    listing: JobListing,
    score_result: dict,
    master_facts: str,
    settings: Settings | None = None,
) -> tuple[Path | None, list[str]]:
    """
    Generate a tailored LaTeX CV for the given listing.
    Saves .tex file and returns its path (PDF compiled separately by renderer).
    Returns (path, errors); path is None on failure.
    """
    if settings is None:
        settings = get_settings()

    if not (settings.openrouter_api_key or "").strip():
        return None, ["OpenRouter API key is not configured"]

    base_template_path = Path(__file__).parent / "templates" / "ats_base.tex"
    if not base_template_path.exists():
        logger.error(f"Base template not found: {base_template_path}")
        return None, [f"CV template missing: {base_template_path}"]

    base_template = base_template_path.read_text(encoding="utf-8")

    prompt = _build_tailor_prompt(listing, score_result, master_facts, base_template)

    def _call(api_key: str, model: str, validation_feedback: str = "") -> str | None:
        """Single attempt — raises retryable errors, returns None for non-retryable."""
        user = prompt
        if validation_feedback:
            user += f"\n\nPrevious output failed validation:\n{validation_feedback}\nFix and output ONLY valid LaTeX."
        
        # Instantiate a new client for the specific API key
        current_client = OpenAI(
            api_key=api_key,
            base_url=settings.openrouter_base_url,
            default_headers={
                "HTTP-Referer": "https://github.com/george-job-agent",
                "X-Title": "George Job Agent",
            },
        )
        
        # NOTE: RateLimitError / APIStatusError(429/5xx) are intentionally NOT
        # caught here — call_with_model_and_key_pool handles them with back-off.
        response = current_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=3000,  # CVs are never >2000 tokens; smaller = higher free-tier priority
        )
        try:
            content = _normalize_latex(response.choices[0].message.content or "")
        except Exception as parse_exc:
            logger.warning(f"CV tailor parse error ({model}): {parse_exc}")
            return None
        if content is None:
            logger.warning(f"CV tailor: response does not look like LaTeX ({model})")
            return None
        errors = validate_latex_cv(content)
        if errors:
            logger.warning(f"CV tailor validation ({model}): {errors}")
            return None
        return content

    # Build ordered model list from pool setting
    pool_models = [m.strip() for m in settings.model_pool.split(",") if m.strip()]
    # Ensure primary and fallback appear first (deduplicated)
    ordered_models: list[str] = []
    seen: set[str] = set()
    for m in [settings.cv_model, settings.fallback_model, *pool_models]:
        if m and m not in seen:
            ordered_models.append(m)
            seen.add(m)

    # Get all available API keys
    api_keys = settings.get_api_keys()

    label = f"CV tailor '{listing.title}' @ {listing.company}"

    # First pass: clean prompt
    latex_content = call_with_model_and_key_pool(
        lambda k, m: _call(k, m),
        models=ordered_models,
        api_keys=api_keys,
        max_retries_per_combination=settings.tailor_max_retries,
        base_seconds=settings.tailor_backoff_base_seconds,
        label=label,
    )

    # Second pass: add validation hint if first pass failed
    if latex_content is None:
        logger.info(f"CV tailor: retrying all models/keys with validation hint for '{listing.title}'")
        latex_content = call_with_model_and_key_pool(
            lambda k, m: _call(k, m, "Must include \\documentclass; no tables or images."),
            models=ordered_models,
            api_keys=api_keys,
            max_retries_per_combination=max(1, settings.tailor_max_retries // 2),
            base_seconds=settings.tailor_backoff_base_seconds,
            label=f"{label} [hint-retry]",
        )

    if latex_content is None:
        logger.error(f"CV tailor: all models and retries exhausted for '{listing.title}' @ {listing.company}")
        return None, ["CV tailoring failed after all model attempts and retries"]

    out_dir = settings.cv_tailored_path
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / f"{listing.slug}.tex"
    tex_path.write_text(latex_content, encoding="utf-8")
    logger.info(f"CV tailored: {tex_path}")
    return tex_path, []
