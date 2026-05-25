"""Bundle apply-ready PDFs for a role slug."""
from __future__ import annotations

import shutil
from pathlib import Path

from agent.config import Settings
from agent.tracker.workbook import TrackerWorkbook


def package_role(slug: str, settings: Settings) -> Path:
    tracker = TrackerWorkbook(settings)
    tracker.load_or_create()
    row = tracker.get_row_by_slug(slug)
    if not row:
        raise ValueError(f"Slug not found in tracker: {slug}")

    company = str(row[1] or "")
    title = str(row[2] or "")
    apply_url = str(row[9] or "")
    fit = str(row[8] or "")

    out_dir = settings.packages_path / slug
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    cv_pdf = settings.cv_tailored_path / f"{slug}.pdf"
    cv_tex = settings.cv_tailored_path / f"{slug}.tex"
    letter_pdf = settings.cover_letters_path / f"{slug}_letter.pdf"
    letter_tex = settings.cover_letters_path / f"{slug}_letter.tex"

    copied: list[str] = []
    for src in (cv_pdf, cv_tex, letter_pdf, letter_tex):
        if src.exists():
            dest = out_dir / src.name
            shutil.copy2(src, dest)
            copied.append(src.name)

    readme = out_dir / "README.txt"
    readme.write_text(
        f"Company: {company}\n"
        f"Role: {title}\n"
        f"Apply: {apply_url}\n"
        f"Slug: {slug}\n\n"
        f"Fit summary:\n{fit}\n\n"
        f"Files: {', '.join(copied) or 'none — run tailor first'}\n",
        encoding="utf-8",
    )
    return out_dir
