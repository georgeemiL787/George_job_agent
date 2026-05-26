"""Orchestrator scoring cap and queued overflow persistence."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from agent.config import Settings
from agent.observability.run_report import ScraperStat
from agent.orchestrator import run
from agent.run_control import get_coordinator
from agent.search.base import JobListing
from agent.tracker import get_tracker


@pytest.fixture(autouse=True)
def reset_coordinator():
    get_coordinator().reset()
    yield
    get_coordinator().reset()


def _seed_workspace(tmp_path):
    ws = tmp_path / "workspace"
    mem = ws / "memory"
    mem.mkdir(parents=True)
    (mem / "job-search-profile.md").write_text("# Profile\nGeorge", encoding="utf-8")
    (mem / "cv-facts.md").write_text("# CV Facts\nPython", encoding="utf-8")
    (mem / "cv-role-playbook.md").write_text("# Playbook\n", encoding="utf-8")
    (mem / "applications-log.md").write_text("# Log\n", encoding="utf-8")
    (ws / "tracker").mkdir(parents=True)
    return ws


def _listing(n: int) -> JobListing:
    return JobListing(
        title=f"AI Engineer {n}",
        company=f"Co{n}",
        location="Cairo, Egypt",
        source="wuzzuf",
        apply_url=f"https://example.com/j/{n}",
        description="machine learning python pytorch cairo",
        card_snippet="machine learning python",
    )


def test_queued_overflow_persisted_when_over_cap(tmp_path):
    ws = _seed_workspace(tmp_path)
    settings = Settings(
        openrouter_api_key="test-key",
        workspace_dir=str(ws),
        database_url=f"sqlite:///{(ws / 'tracker' / 'test.db').as_posix()}",
        fast_run_max_scoring_candidates=1,
        max_scoring_candidates=1,
    )
    listings = [_listing(1), _listing(2)]

    import agent.config as config_mod

    config_mod._settings = settings
    try:
        with patch("agent.orchestrator._collect_all_listings") as mock_collect:
            mock_collect.return_value = (
                listings,
                {"wuzzuf": ScraperStat(count=2, status="ok")},
                {},
            )
            with patch("agent.orchestrator._fetch_details_for_shortlist"):
                with patch("agent.orchestrator.score_listing") as mock_score:
                    mock_score.return_value = {
                        "score": 80,
                        "tier": "strong",
                        "fit_summary": "ok",
                        "key_matches": [],
                        "gaps": [],
                        "role_family": "ai_engineer",
                    }
                    run(manual=True, dry_run=True)

        tracker = get_tracker(settings)
        tracker.load_or_create()
        roles = {r.slug: r for r in tracker.list_pipeline_rows()}
        assert len(roles) == 2
        statuses = {r.scoring_status for r in roles.values()}
        assert "queued" in statuses
        assert "scored" in statuses
    finally:
        config_mod._settings = None
