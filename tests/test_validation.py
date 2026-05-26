"""Tests for validation helpers."""
from agent.validation.latex import sanitize_latex_source, validate_latex_cv, validate_latex_letter
from agent.validation.models import validate_score_result


def test_validate_score_result_ok():
    data, errors = validate_score_result(
        {
            "score": 80,
            "tier": "strong",
            "fit_summary": "Good fit",
            "key_matches": ["Python"],
            "gaps": [],
            "role_family": "ai_engineer",
        }
    )
    assert errors == []
    assert data is not None
    assert data["tier"] == "strong"


def test_validate_score_result_bad_tier():
    data, errors = validate_score_result({"score": 50, "tier": "invalid"})
    assert data is None
    assert errors


def test_validate_latex_cv_rejects_table():
    errors = validate_latex_cv(
        "\\documentclass{article}\\begin{document}\\begin{tabular}{c}c\\end{tabular}\\end{document}"
    )
    assert any("tabular" in e for e in errors)


_MIN_TEX = "\\documentclass{article}\\begin{document}" + ("x" * 200) + "\\end{document}"


def test_validate_latex_cv_ok():
    errors = validate_latex_cv(_MIN_TEX)
    assert errors == []


def test_sanitize_latex_source_makes_model_unicode_pdftex_safe():
    raw = (
        "\\documentclass{article}\\begin{document}"
        "Hands\u2011on RAG \u2014 improved accuracy by 12\u202f% and George\u2019s notes."
        "\\end{document}"
    )

    sanitized = sanitize_latex_source(raw)

    assert sanitized == (
        "\\documentclass{article}\\begin{document}"
        "Hands-on RAG --- improved accuracy by 12\\% and George's notes."
        "\\end{document}"
    )
    assert all(ord(ch) < 128 for ch in sanitized)


def test_sanitize_latex_source_replaces_hyperref_with_href_fallback():
    raw = (
        "\\documentclass{article}\n"
        "\\usepackage{hyperref}\n"
        "\\begin{document}\\href{https://example.com}{example.com}\\end{document}"
    )

    sanitized = sanitize_latex_source(raw)

    assert "\\usepackage{hyperref}" not in sanitized
    assert "\\newcommand{\\href}[2]{#2}" in sanitized


def test_sanitize_latex_source_compacts_cv_template():
    raw = (
        "\\documentclass[11pt,a4paper]{article}\n"
        "\\usepackage[top=1.8cm, bottom=1.8cm, left=1.8cm, right=1.8cm]{geometry}\n"
        "\\newcommand{\\cvsection}[1]{\\vspace{4pt}%#1\\vspace{4pt}%}\n"
        "\\setlist[itemize]{leftmargin=*, nosep, topsep=2pt, parsep=0pt, partopsep=0pt}\n"
        "\\begin{document}Body\\end{document}"
    )

    sanitized = sanitize_latex_source(raw)

    assert "\\documentclass[10pt,a4paper]{article}" in sanitized
    assert "top=1.25cm" in sanitized
    assert "topsep=1pt" in sanitized
    assert "\\begin{document}\n\\small" in sanitized


def test_validate_latex_cv_rejects_unsupported_unicode():
    errors = validate_latex_cv(_MIN_TEX + "\u202f")
    assert any("Unsupported Unicode" in e for e in errors)


def test_validate_latex_letter_ok():
    errors = validate_latex_letter(_MIN_TEX.replace("article", "letter"))
    assert errors == []
