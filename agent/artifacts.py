"""Compile and validate CV / cover letter artifacts."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from agent.config import Settings
from agent.cover_letter.writer import write_cover_letter
from agent.cv.renderer import compile_latex, latex_failure_summary
from agent.cv.tailorer import tailor_cv
from agent.search.base import JobListing
from agent.validation.pdf import validate_pdf


@dataclass
class ArtifactResult:
    tex_path: Path | None = None
    pdf_path: Path | None = None
    ok: bool = False
    errors: list[str] | None = None


def _pdflatex_available(latex_bin: str) -> bool:
    return bool(shutil.which(latex_bin))


def build_cv_artifact(
    listing: JobListing,
    score_result: dict,
    master_facts: str,
    settings: Settings,
) -> ArtifactResult:
    tex_path, tailor_errors = tailor_cv(listing, score_result, master_facts, settings)
    if not tex_path:
        return ArtifactResult(errors=tailor_errors or ["CV tailoring failed"])

    if not _pdflatex_available(settings.latex_bin):
        logger.warning("pdflatex not available — CV saved as .tex only")
        return ArtifactResult(tex_path=tex_path, ok=True)

    pdf_path = compile_latex(tex_path, tex_path.parent, settings.latex_bin)
    if not pdf_path:
        detail = latex_failure_summary(tex_path, tex_path.parent)
        message = "CV PDF compilation failed"
        if detail:
            message = f"{message}: {detail}"
        return ArtifactResult(tex_path=tex_path, errors=[message])

    pdf_errors = validate_pdf(pdf_path, latex_bin=settings.latex_bin)
    if pdf_errors:
        return ArtifactResult(tex_path=tex_path, pdf_path=pdf_path, errors=pdf_errors)

    return ArtifactResult(tex_path=tex_path, pdf_path=pdf_path, ok=True)


def build_letter_artifact(
    listing: JobListing,
    score_result: dict,
    master_facts: str,
    settings: Settings,
) -> ArtifactResult:
    tex_path = write_cover_letter(listing, score_result, master_facts, settings)
    if not tex_path:
        return ArtifactResult(errors=["Cover letter generation failed"])

    if not _pdflatex_available(settings.latex_bin):
        return ArtifactResult(tex_path=tex_path, ok=True)

    pdf_path = compile_latex(tex_path, tex_path.parent, settings.latex_bin)
    if not pdf_path:
        detail = latex_failure_summary(tex_path, tex_path.parent)
        message = "Letter PDF compilation failed"
        if detail:
            message = f"{message}: {detail}"
        return ArtifactResult(tex_path=tex_path, errors=[message])

    pdf_errors = validate_pdf(pdf_path, max_pages=2, latex_bin=settings.latex_bin)
    if pdf_errors:
        return ArtifactResult(tex_path=tex_path, pdf_path=pdf_path, errors=pdf_errors)

    return ArtifactResult(tex_path=tex_path, pdf_path=pdf_path, ok=True)
