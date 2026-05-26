"""Tests for tracker display helpers."""
from __future__ import annotations

import json

from agent.tracker.models import RoleRecord, effective_score, format_added_date


def test_effective_score_prefers_db_column():
    role = RoleRecord(slug="a", score=72, source_payload=json.dumps({"prefilter_score": 40}))
    assert effective_score(role) == 72


def test_effective_score_from_prefilter_payload():
    role = RoleRecord(
        slug="a",
        score=0,
        tier="skip",
        source_payload=json.dumps({"prefilter_score": 48, "reason": "Low AI relevance"}),
    )
    assert effective_score(role) == 48


def test_effective_score_from_llm_payload():
    role = RoleRecord(
        slug="a",
        score=0,
        score_payload=json.dumps({"score": 61, "tier": "medium"}),
    )
    assert effective_score(role) == 61


def test_format_added_date():
    role = RoleRecord(slug="a", first_seen="2026-05-20T14:30:00+00:00")
    assert format_added_date(role) == "2026-05-20"
