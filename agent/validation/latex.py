"""LaTeX output validation for CVs and cover letters."""
from __future__ import annotations

import re

_CV_FORBIDDEN = [
    r"\\begin\{tabular\}",
    r"\\includegraphics",
    r"\\begin\{tikzpicture\}",
    r"\\fa[A-Z]",
    r"\\emoji",
]

_LETTER_FORBIDDEN = _CV_FORBIDDEN


def validate_latex_cv(text: str) -> list[str]:
    errors: list[str] = []
    if "\\documentclass" not in text:
        errors.append("Missing \\documentclass")
    for pattern in _CV_FORBIDDEN:
        if re.search(pattern, text):
            errors.append(f"Forbidden pattern: {pattern}")
    if len(text) < 200:
        errors.append("LaTeX content too short")
    return errors


def validate_latex_letter(text: str) -> list[str]:
    errors: list[str] = []
    if "\\documentclass" not in text:
        errors.append("Missing \\documentclass")
    for pattern in _LETTER_FORBIDDEN:
        if re.search(pattern, text):
            errors.append(f"Forbidden pattern: {pattern}")
    if len(text) < 100:
        errors.append("LaTeX content too short")
    return errors
