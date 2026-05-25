"""PDF artifact validation."""
from __future__ import annotations

from pathlib import Path

import shutil


def validate_pdf(
    pdf_path: Path,
    *,
    max_pages: int = 1,
    latex_bin: str = "pdflatex",
) -> list[str]:
    errors: list[str] = []
    if not pdf_path.exists():
        errors.append(f"PDF not found: {pdf_path}")
        return errors

    if pdf_path.stat().st_size < 1000:
        errors.append("PDF file suspiciously small")

    if not shutil.which(latex_bin):
        return errors

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        pages = len(reader.pages)
        if pages > max_pages:
            errors.append(f"PDF has {pages} pages; expected at most {max_pages}")
    except ImportError:
        pass
    except Exception as e:
        errors.append(f"Could not read PDF: {e}")

    return errors
