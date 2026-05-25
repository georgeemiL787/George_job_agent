"""Index of historical CV PDFs in cv_variations/ for tailoring context."""
from __future__ import annotations

from agent.config import Settings

# Filename hints for LLM context when cv-variations.md is missing
_VARIANT_HINTS: dict[str, str] = {
    "george_emil_aiml_engineer_cv.pdf": "Applied AI / LLM engineer (RAG, LangChain, FastAPI)",
    "george_emil_cv.pdf": "General ATS one-pager",
    "George_Emil_Sadek_cv.pdf": "Formal full CV",
    "George Emil cv.pdf": "Extended portfolio-style CV",
}


def _hint_for(name: str) -> str:
    if name in _VARIANT_HINTS:
        return _VARIANT_HINTS[name]
    if name.startswith("george_emil_cv-") and name.endswith(".pdf"):
        return "Role-specific tailored iteration"
    if name.startswith("george_emil_aiml_engineer"):
        return "Applied AI / LLM engineer (duplicate filename)"
    return "Historical variant"


def build_cv_variations_context(settings: Settings) -> str:
    """
    Build a compact listing of PDFs under cv_variations/ plus memory index text.
    Included in MASTER FACTS for scoring-adjacent CV/letter generation.
    """
    parts: list[str] = []

    index_path = settings.memory_path / "cv-variations.md"
    if index_path.exists():
        parts.append(index_path.read_text(encoding="utf-8"))

    var_dir = settings.cv_variations_path
    if not var_dir.is_dir():
        if parts:
            return "\n\n".join(parts)
        return ""

    pdfs = sorted(var_dir.glob("*.pdf"), key=lambda p: p.name.lower())
    if pdfs:
        lines = ["## CV variation files (live index)", ""]
        for pdf in pdfs:
            rel = f"{settings.cv_variations_dir}/{pdf.name}"
            abs_path = pdf.resolve()
            size_kb = pdf.stat().st_size // 1024
            hint = _hint_for(pdf.name)
            lines.append(
                f"- **{pdf.name}** ({size_kb} KB) — {hint}\n"
                f"  - Relative: `{rel}`\n"
                f"  - Absolute: `{abs_path}`"
            )
        parts.append("\n".join(lines))

    return "\n\n".join(parts).strip()


_ROLE_FAMILY_PDF: dict[str, str] = {
    "ai_engineer": "george_emil_aiml_engineer_cv.pdf",
    "ml_engineer": "george_emil_cv.pdf",
    "cv_engineer": "george_emil_cv.pdf",
    "data_scientist": "george_emil_cv.pdf",
    "ai_intern": "george_emil_cv.pdf",
    "adjacent": "george_emil_cv.pdf",
}


_SECTION_ORDER: dict[str, str] = {
    "ai_engineer": "Summary → Skills (LLM/RAG/APIs first) → Experience → Projects → Education",
    "ml_engineer": "Summary → Skills (PyTorch/TF/deployment) → Experience → Projects → Education",
    "cv_engineer": "Summary → Experience (Cellula first) → Skills → Projects → Education",
    "data_scientist": "Summary → Skills (Python/SQL/Pandas) → Experience → Projects → Education",
    "ai_intern": "Summary (final-year first) → Skills → Experience → Projects → Education",
}


def style_hint_for_role_family(role_family: str) -> str:
    """Short hint for tailor prompt: reference PDF and section order."""
    if not role_family:
        return ""
    pdf = _ROLE_FAMILY_PDF.get(role_family, "george_emil_cv.pdf")
    order = _SECTION_ORDER.get(role_family, _SECTION_ORDER["ai_engineer"])
    return (
        f"Reference archive PDF: `{pdf}` (style only; use MASTER FACTS for content).\n"
        f"Section order: {order}."
    )
