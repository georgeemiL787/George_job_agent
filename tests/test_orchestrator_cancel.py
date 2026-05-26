"""Orchestrator cancellation and checkpoint tests."""
import json
from unittest.mock import patch

import pytest

from agent.config import Settings
from agent.observability.run_report import ScraperStat
from agent.orchestrator import run
from agent.run_control import get_coordinator
from agent.search.base import JobListing


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


def test_cancel_mid_score_writes_partial_report(tmp_path):
    ws = _seed_workspace(tmp_path)
    db_path = (ws / "tracker" / "test.db").as_posix()
    settings = Settings(
        openrouter_api_key="test-key",
        workspace_dir=str(ws),
        database_url=f"sqlite:///{db_path}",
    )
    listing_a = JobListing(
        title="AI Intern",
        company="Co",
        location="Cairo",
        source="wuzzuf",
        apply_url="https://example.com/j/1",
        description="Python ML intern",
        card_snippet="AI intern python cairo",
    )
    listing_b = JobListing(
        title="ML Engineer",
        company="Other",
        location="Cairo",
        source="wuzzuf",
        apply_url="https://example.com/j/2",
        description="machine learning pytorch",
        card_snippet="ML engineer python cairo",
    )

    import agent.config as config_mod

    config_mod._settings = settings
    calls = {"n": 0}

    def score_side_effect(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            get_coordinator().request_cancel()
        return {
            "score": 70,
            "tier": "strong",
            "fit_summary": "ok",
            "key_matches": [],
            "gaps": [],
            "role_family": "ai_intern",
        }

    with patch("agent.orchestrator._collect_all_listings") as mock_collect:
        mock_collect.return_value = (
            [listing_a, listing_b],
            {"wuzzuf": ScraperStat(count=2, status="ok")},
            {},
        )
        with patch("agent.orchestrator._fetch_details_for_shortlist"):
            with patch("agent.orchestrator.deduplicate", return_value=[listing_a, listing_b]):
                with patch("agent.orchestrator.score_listing", side_effect=score_side_effect):
                    run(manual=True, dry_run=True)

    latest = ws / "logs" / "runs" / "latest.json"
    assert latest.exists()
    report = json.loads(latest.read_text(encoding="utf-8"))
    assert report.get("status") == "cancelled"
    config_mod._settings = None
