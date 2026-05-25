"""LLM-based CV tailorer — generates per-role ATS-optimized LaTeX CV."""
from __future__ import annotations

from pathlib import Path

from loguru import logger
from openai import OpenAI

from agent.config import Settings, get_settings
from agent.cv.variations import style_hint_for_role_family
from agent.search.base import JobListing
from agent.validation.latex import validate_latex_cv

SYSTEM_PROMPT = """\
You are an expert CV writer specializing in ATS-optimized resumes for AI/ML engineering roles.

RULES (never violate):
1. Use ONLY facts listed in the MASTER FACTS section. Never invent employers, degrees, certifications, dates, skills, or metrics.
2. Reorder sections and rewrite bullet points to emphasize the most relevant experience for this specific role and company.
3. Inject the most important truthful keywords from the JOB DESCRIPTION naturally into bullets and the summary. Do not keyword-stuff.
4. Rewrite the Summary section to address this exact role title and company specifically.
5. Include ALL quantifiable results from MASTER FACTS that are genuinely relevant to this role.
6. Keep the CV ATS-safe: single column, standard section headings (Summary, Skills, Experience, Projects, Education, Highlights), no icons, no tables, no graphics, no colored boxes.
7. The CV MUST fit on one page. Use \\vspace{} and font size adjustments if needed.
8. Output ONLY the complete compilable LaTeX source. No explanation, no markdown fences, no preamble text.
9. Use hands-on, built, developed, applied, contributed language. Never imply senior ownership or multi-year full-time experience.
10. Follow the Style reference section order when provided.
"""


def _build_tailor_prompt(
    listing: JobListing,
    score_result: dict,
    master_facts: str,
    base_template: str,
) -> str:
    key_matches = ", ".join(score_result.get("key_matches", []))
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
Key JD Keywords to include (truthfully): {key_matches}

JOB DESCRIPTION:
{listing.description[:4000] if listing.description else 'No description available.'}

BASE LATEX TEMPLATE (adapt this structure, keep all packages and commands):
{base_template}

Produce the tailored LaTeX CV now. Output ONLY the complete LaTeX source.
"""


def _normalize_latex(content: str) -> str | None:
    content = content.strip()
    if "```" in content:
        for part in content.split("```"):
            if "\\documentclass" in part:
                content = part.lstrip("latex").lstrip("tex").strip()
                break
    if "\\documentclass" not in content:
        return None
    return content


def tailor_cv(
    listing: JobListing,
    score_result: dict,
    master_facts: str,
    settings: Settings | None = None,
) -> Path | None:
    """
    Generate a tailored LaTeX CV for the given listing.
    Saves .tex file and returns its path (PDF compiled separately by renderer).
    Returns None on failure.
    """
    if settings is None:
        settings = get_settings()

    base_template_path = Path(__file__).parent / "templates" / "ats_base.tex"
    if not base_template_path.exists():
        logger.error(f"Base template not found: {base_template_path}")
        return None

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
                max_tokens=3000,
            )
            content = _normalize_latex(response.choices[0].message.content or "")
            if content is None:
                logger.warning(f"CV tailor: response does not look like LaTeX ({model})")
                return None
            errors = validate_latex_cv(content)
            if errors:
                logger.warning(f"CV tailor validation ({model}): {errors}")
                return None
            return content
        except Exception as e:
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
        return None

    out_dir = settings.cv_tailored_path
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / f"{listing.slug}.tex"
    tex_path.write_text(latex_content, encoding="utf-8")
    logger.info(f"CV tailored: {tex_path}")
    return tex_path
