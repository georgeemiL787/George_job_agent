"""LLM-based CV tailorer — generates per-role ATS-optimized LaTeX CV."""
from __future__ import annotations

import re
from pathlib import Path

from loguru import logger
from openai import OpenAI

from agent.config import Settings, get_settings
from agent.cv.variations import style_hint_for_role_family
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
    content = content.strip()
    # Strip <think>...</think> block if present
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

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

    client = OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers={
            "HTTP-Referer": "https://github.com/george-job-agent",
            "X-Title": "George Job Agent",
        },
    )

    prompt = _build_tailor_prompt(listing, score_result, master_facts, base_template)
    last_errors: list[str] = []

    def _call(model: str, validation_feedback: str = "") -> str | None:
        user = prompt
        if validation_feedback:
            user += f"\n\nPrevious output failed validation:\n{validation_feedback}\nFix and output ONLY valid LaTeX."
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=8000,
            )
            content = _normalize_latex(response.choices[0].message.content or "")
            if content is None:
                last_errors[:] = [f"Model {model} did not return valid LaTeX"]
                logger.warning(f"CV tailor: response does not look like LaTeX ({model})")
                return None
            errors = validate_latex_cv(content)
            if errors:
                last_errors[:] = [f"LaTeX validation ({model}): " + "; ".join(errors)]
                logger.warning(f"CV tailor validation ({model}): {errors}")
                return None
            return content
        except Exception as e:
            last_errors[:] = [f"API error ({model}): {e}"]
            logger.warning(f"CV tailor API error ({model}): {e}")
            return None

    latex_content = _call(settings.cv_model)
    if latex_content is None:
        latex_content = _call(settings.cv_model, "Must include \\documentclass; no tables or images.")
    if latex_content is None:
        logger.info(f"CV tailor: retrying with fallback model for '{listing.title}'")
        latex_content = _call(settings.fallback_model)

    if latex_content is None:
        logger.error(f"CV tailor: failed for '{listing.title}' @ {listing.company}")
        if not last_errors:
            last_errors.append("CV tailoring failed after all model attempts")
        return None, last_errors

    out_dir = settings.cv_tailored_path
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / f"{listing.slug}.tex"
    tex_path.write_text(latex_content, encoding="utf-8")
    logger.info(f"CV tailored: {tex_path}")
    return tex_path, []
