"""Tests for artifact queue ordering."""
from agent.orchestrator import TIER_ORDER, _sort_for_artifacts


def test_sort_for_artifacts_tier_priority():
    scored = [
        (None, {"tier": "medium", "score": 80}),
        (None, {"tier": "top", "score": 70}),
        (None, {"tier": "strong", "score": 60}),
    ]
    ordered = _sort_for_artifacts(scored)  # type: ignore[arg-type]
    tiers = [r[1]["tier"] for r in ordered]
    assert tiers == ["top", "strong", "medium"]
    assert TIER_ORDER["top"] < TIER_ORDER["medium"]
