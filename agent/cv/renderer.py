"""pdflatex renderer — compiles .tex files to PDF."""
from __future__ import annotations

import subprocess
import shutil
from pathlib import Path

from loguru import logger


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
                    "-interaction=nonstopmode",
                    "-output-directory", str(output_dir),
                    str(tex_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.error(
                    f"pdflatex run {run_num} failed for {tex_path.name}:\n"
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
