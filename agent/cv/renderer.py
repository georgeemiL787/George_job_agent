"""pdflatex renderer — compiles .tex files to PDF."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from loguru import logger


def latex_failure_summary(tex_path: Path, output_dir: Path | None = None) -> str:
    """Return the first useful LaTeX error from the compiler log, if present."""
    log_dir = output_dir or tex_path.parent
    log_path = log_dir / tex_path.with_suffix(".log").name
    if not log_path.exists():
        return ""

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        is_error = (
            stripped.startswith("!")
            or "LaTeX Error:" in stripped
            or ("Package " in stripped and " Error:" in stripped)
            or "Fatal error" in stripped
        )
        if is_error:
            context = " ".join(part.strip() for part in lines[idx : idx + 3] if part.strip())
            return context[:500]
    return ""


def compile_latex(tex_path: Path, output_dir: Path, latex_bin: str = "pdflatex") -> Path | None:
    """
    Run pdflatex twice (for cross-references), return path to compiled PDF.
    Returns None if pdflatex is not available or compilation fails.
    Keeps the .tex file even if PDF compilation fails.
    """
    if not shutil.which(latex_bin):
        logger.warning(
            f"'{latex_bin}' not found on PATH. "
            "Install TeX Live or MiKTeX to enable PDF output. "
            f"Keeping .tex file: {tex_path}"
        )
        return None

    output_dir.mkdir(parents=True, exist_ok=True)

    for run_num in range(1, 3):
        try:
            result = subprocess.run(
                [
                    latex_bin,
                    "-file-line-error",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-output-directory", str(output_dir),
                    str(tex_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                summary = latex_failure_summary(tex_path, output_dir)
                logger.error(
                    f"pdflatex run {run_num} failed for {tex_path.name}:\n"
                    f"SUMMARY: {summary}\n"
                    f"STDOUT: {result.stdout[-800:]}\n"
                    f"STDERR: {result.stderr[-400:]}"
                )
                return None
        except subprocess.TimeoutExpired:
            logger.error(f"pdflatex timed out for {tex_path.name}")
            return None
        except Exception as e:
            logger.error(f"pdflatex unexpected error: {e}")
            return None

    pdf_path = output_dir / tex_path.with_suffix(".pdf").name
    if pdf_path.exists():
        logger.info(f"PDF compiled: {pdf_path}")
        return pdf_path

    logger.warning(f"PDF not found after compilation: {pdf_path}")
    return None
