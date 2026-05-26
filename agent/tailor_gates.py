"""Shared gates for CV and cover letter generation."""
from __future__ import annotations

from agent.config import Settings

LETTER_TIERS = frozenset({"top", "strong"})


def should_tailor_cv(score: int, settings: Settings) -> bool:
    return score >= settings.min_score_to_tailor


def should_tailor_letter(tier: str) -> bool:
    return tier in LETTER_TIERS
