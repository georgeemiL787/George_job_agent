"""LLM cover letter writer — generates per-role professional cover letters."""
from __future__ import annotations

from pathlib import Path

from loguru import logger
from openai import OpenAI

from agent.config import Settings, get_settings
from agent.search.base import JobListing
from agent.validation.latex import validate_latex_letter

SYSTEM_PROMPT = """\
You are a professional cover letter writer for AI/ML engineering job applications.

RULES (never violate):
1. Write exactly 3 paragraphs, under 320 words total.
2. Paragraph 1: Express genuine, specific interest in the role and company. Mention the role title explicitly. Do not open with "I am writing to apply" or any cliche opener.
3. Paragraph 2: Draw on 2-3 specific truthful highlights from MASTER FACTS that directly address the JD requirements. Use exact numbers from the facts when available.
4. Paragraph 3: Close with a confident but not arrogant ask for an interview.
5. Professional but natural tone. No buzzwords, no padding.
6. Never invent qualifications. Use ONLY facts from MASTER FACTS.
7. Output ONLY the complete LaTeX letter source using the provided template. No markdown fences, no explanation.
"""


def _build_letter_prompt(
    listing: JobListing,
    score_result: dict,
    master_facts: str,
    base_template: str,
) -> str:
    key_matches = ", ".join(score_result.get("key_matches", []))
    fit_summary = score_result.get("fit_summary", "")
    return f"""MASTER FACTS:
{master_facts}

TARGET ROLE:
Title: {listing.title}
Company: {listing.company}
Location: {listing.location}
Key JD Requirements: {key_matches}
Fit Summary: {fit_summary}

JOB DESCRIPTION:
{listing.description[:3000] if listing.description else 'No description available.'}

LETTER TEMPLATE (fill in the placeholder sections):
{base_template}

Produce the complete tailored cover letter LaTeX source now. Output ONLY the LaTeX.
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


def write_cover_letter(
    listing: JobListing,
    score_result: dict,
    master_facts: str,
    settings: Settings | None = None,
) -> Path | None:
    """Generate a tailored cover letter .tex file. Returns path or None on failure."""
    if settings is None:
        settings = get_settings()

    base_template_path = Path(__file__).parent / "templates" / "letter_base.tex"
    if not base_template_path.exists():
        logger.error(f"Letter template not found: {base_template_path}")
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

    prompt = _build_letter_prompt(listing, score_result, master_facts, base_template)

    def _call(model: str, validation_feedback: str = "") -> str | None:
        user = prompt
        if validation_feedback:
            user += f"\n\nValidation errors: {validation_feedback}\nFix and output ONLY LaTeX."
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
                max_tokens=1500,
            )
            content = _normalize_latex(response.choices[0].message.content or "")
            if content is None:
                logger.warning(f"Cover letter: response does not look like LaTeX ({model})")
                return None
            errors = validate_latex_letter(content)
            if errors:
                logger.warning(f"Cover letter validation ({model}): {errors}")
                return None
            return content
        except Exception as e:
            logger.warning(f"Cover letter API error ({model}): {e}")
            return None

    latex_content = _call(settings.letter_model)
    if latex_content is None:
        latex_content = _call(settings.letter_model, "Must include \\documentclass.")
    if latex_content is None:
        logger.info(f"Cover letter: retrying fallback for '{listing.title}'")
        latex_content = _call(settings.fallback_model)

    if latex_content is None:
        logger.error(f"Cover letter: failed for '{listing.title}' @ {listing.company}")
        return None

    out_dir = settings.cover_letters_path
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / f"{listing.slug}_letter.tex"
    tex_path.write_text(latex_content, encoding="utf-8")
    logger.info(f"Cover letter saved: {tex_path}")
    return tex_path
