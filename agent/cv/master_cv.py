"""Load composed CV facts for tailoring and cover letters."""
from __future__ import annotations

import re

from agent.config import Settings
from agent.cv.variations import build_cv_variations_context, style_hint_for_role_family

_ROLE_FAMILY_PLAYBOOK_HEADINGS: dict[str, str] = {
    "ai_engineer": "Junior AI Engineer",
    "ml_engineer": "Machine Learning Engineer",
    "cv_engineer": "Computer Vision Engineer",
    "data_scientist": "Data Scientist",
    "ai_intern": "AI internship",
}


def load_cv_facts(settings: Settings) -> str:
    """Core facts only (no tracker journal)."""
    path = settings.memory_path / "cv-facts.md"
    if not path.exists():
        legacy = settings.memory_path / "cv-notes.md"
        if legacy.exists():
            return legacy.read_text(encoding="utf-8")
        raise FileNotFoundError(f"CV facts not found at {path}")
    return path.read_text(encoding="utf-8")


def load_role_playbook_hint(
    settings: Settings,
    role_family: str = "",
    company: str = "",
    max_chars: int = 4000,
) -> str:
    """Return matching playbook sections for company or role family."""
    path = settings.memory_path / "cv-role-playbook.md"
    if not path.exists():
        return ""

    text = path.read_text(encoding="utf-8")
    sections = [s for s in re.split(r"(?=^## )", text, flags=re.M) if s.strip().startswith("##")]
    if not sections:
        return ""

    company_lower = company.lower().strip()
    matched: list[str] = []

    for sec in sections:
        heading = sec.split("\n", 1)[0].lower()
        if company_lower and company_lower in heading:
            matched.append(sec)

    if not matched and role_family:
        hint = _ROLE_FAMILY_PLAYBOOK_HEADINGS.get(role_family, "")
        if hint:
            for sec in sections:
                if hint.lower() in sec.split("\n", 1)[0].lower():
                    matched.append(sec)
                    break

    if not matched and sections:
        matched = sections[:2]

    combined = "\n\n".join(matched)
    if len(combined) > max_chars:
        return combined[:max_chars] + "\n\n...(playbook truncated)"
    return combined


def load_master_cv_facts(
    settings: Settings,
    role_family: str = "",
    company: str = "",
) -> str:
    """Compose facts + playbook slice + variations index for LLM prompts."""
    parts = [load_cv_facts(settings)]

    playbook = load_role_playbook_hint(settings, role_family, company)
    if playbook:
        parts.append(f"## Role-specific playbook\n\n{playbook}")

    style = style_hint_for_role_family(role_family)
    if style:
        parts.append(f"## Style reference\n\n{style}")

    variations = build_cv_variations_context(settings)
    if variations:
        parts.append(variations)

    return "\n\n---\n\n".join(parts)


def load_profile(settings: Settings) -> str:
    """Return full text of job-search-profile.md."""
    profile_path = settings.memory_path / "job-search-profile.md"
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found at {profile_path}")
    return profile_path.read_text(encoding="utf-8")
