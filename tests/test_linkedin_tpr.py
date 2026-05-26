"""LinkedIn time filter mapping."""
from __future__ import annotations

from agent.search.linkedin_jobs import _linkedin_tpr


def test_linkedin_tpr_none_when_disabled():
    assert _linkedin_tpr(0) is None


def test_linkedin_tpr_day_and_week():
    assert _linkedin_tpr(24) == "r86400"
    assert _linkedin_tpr(168) == "r604800"
