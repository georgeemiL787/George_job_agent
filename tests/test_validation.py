"""Tests for validation helpers."""
from agent.validation.latex import validate_latex_cv, validate_latex_letter
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


def test_validate_latex_letter_ok():
    errors = validate_latex_letter(_MIN_TEX.replace("article", "letter"))
    assert errors == []
