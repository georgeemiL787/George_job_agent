"""LaTeX output validation for CVs and cover letters."""
from __future__ import annotations

import re
import unicodedata

_CV_FORBIDDEN = [
    r"\\begin\{tabular\}",
    r"\\includegraphics",
    r"\\begin\{tikzpicture\}",
    r"\\fa[A-Z]",
    r"\\emoji",
]

_LETTER_FORBIDDEN = _CV_FORBIDDEN

_UNICODE_REPLACEMENTS = str.maketrans(
    {
        "\ufeff": "",
        "\u00a0": " ",
        "\u2009": " ",
        "\u202f": " ",
        "\u200b": "",
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "--",
        "\u2014": "---",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2026": "...",
        "\u2022": "-",
    }
)

_METRIC_PERCENT_RE = re.compile(r"(?<!\\)(\d+(?:\.\d+)?)[ \t]*%")
_HYPERREF_PACKAGE_RE = re.compile(
    r"^[ \t]*\\usepackage(?:\[[^\]]*\])?\{hyperref\}[ \t]*$",
    re.MULTILINE,
)


def _ensure_href_fallback(text: str) -> str:
    if "\\href" not in text or "\\newcommand{\\href}" in text:
        return text

    fallback = "\\newcommand{\\href}[2]{#2}"
    if "\\begin{document}" in text:
        return text.replace("\\begin{document}", f"{fallback}\n\n\\begin{{document}}", 1)
    return f"{fallback}\n{text}"


def _compact_cv_template(text: str) -> str:
    if "\\cvsection" not in text:
        return text

    replacements = {
        "\\documentclass[11pt,a4paper]{article}": "\\documentclass[10pt,a4paper]{article}",
        "\\usepackage[top=1.8cm, bottom=1.8cm, left=1.8cm, right=1.8cm]{geometry}": (
            "\\usepackage[top=1.25cm, bottom=1.25cm, left=1.3cm, right=1.3cm]{geometry}"
        ),
        "\\setlist[itemize]{leftmargin=*, nosep, topsep=2pt, parsep=0pt, partopsep=0pt}": (
            "\\setlist[itemize]{leftmargin=*, nosep, topsep=1pt, parsep=0pt, partopsep=0pt}"
        ),
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.replace("\\vspace{4pt}%", "\\vspace{2pt}%")
    if not re.search(r"\\begin\{document\}\s*\\small", text):
        text = text.replace("\\begin{document}", "\\begin{document}\n\\small", 1)
    return text


def sanitize_latex_source(text: str) -> str:
    """Normalize model-generated LaTeX to a conservative pdfLaTeX-safe form."""
    text = _HYPERREF_PACKAGE_RE.sub(r"\\newcommand{\\href}[2]{#2}", text)
    text = text.translate(_UNICODE_REPLACEMENTS)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = _METRIC_PERCENT_RE.sub(r"\1\\%", text)
    text = _compact_cv_template(text)
    return _ensure_href_fallback(text)


def _unsupported_unicode(text: str) -> list[str]:
    chars = sorted({ch for ch in text if ord(ch) > 127})
    return [f"U+{ord(ch):04X}" for ch in chars]


def validate_latex_cv(text: str) -> list[str]:
    errors: list[str] = []
    if "\\documentclass" not in text:
        errors.append("Missing \\documentclass")
    if unsupported := _unsupported_unicode(text):
        errors.append(f"Unsupported Unicode for pdfLaTeX: {', '.join(unsupported[:8])}")
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
    if unsupported := _unsupported_unicode(text):
        errors.append(f"Unsupported Unicode for pdfLaTeX: {', '.join(unsupported[:8])}")
    for pattern in _LETTER_FORBIDDEN:
        if re.search(pattern, text):
            errors.append(f"Forbidden pattern: {pattern}")
    if len(text) < 100:
        errors.append("LaTeX content too short")
    return errors
