"""Orchestrator dry-run with mocked search."""
import json
from unittest.mock import patch

from agent.config import Settings
from agent.observability.run_report import ScraperStat
from agent.orchestrator import run
from agent.search.base import JobListing


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


def _settings_for(ws):
    db_path = (ws / "tracker" / "test.db").as_posix()
    return Settings(
        openrouter_api_key="test-key",
        workspace_dir=str(ws),
        database_url=f"sqlite:///{db_path}",
    )


def test_run_dry_run_with_listing(tmp_path):
    ws = _seed_workspace(tmp_path)
    settings = _settings_for(ws)
    listing = JobListing(
        title="AI Intern",
        company="Co",
        location="Cairo",
        source="wuzzuf",
        apply_url="https://example.com/j/1",
        description="Python ML intern",
    )
    score = {
        "score": 75,
        "tier": "strong",
        "fit_summary": "Good",
        "key_matches": ["Python"],
        "gaps": [],
        "role_family": "ai_intern",
    }

    import agent.config as config_mod

    config_mod._settings = settings

    with patch("agent.orchestrator._collect_all_listings") as mock_collect:
        mock_collect.return_value = (
            [listing],
            {"wuzzuf": ScraperStat(count=1, status="ok", message="healthy")},
        )
        with patch("agent.orchestrator.deduplicate", return_value=[listing]):
            with patch("agent.orchestrator.score_listing", return_value=score):
                run(manual=True, dry_run=True)

    runs = list((ws / "logs" / "runs").glob("*.json"))
    assert runs
    report = json.loads(runs[0].read_text(encoding="utf-8"))
    assert report["scrapers"]["wuzzuf"]["status"] == "ok"
    assert report["scrapers"]["wuzzuf"]["message"] == "healthy"
    config_mod._settings = None


def test_run_returns_before_tracker_save_when_all_scores_skip(tmp_path):
    ws = _seed_workspace(tmp_path)
    settings = _settings_for(ws)
    listing = JobListing(
        title="Generic Engineer",
        company="Co",
        location="Cairo",
        source="indeed_eg",
        apply_url="https://example.com/j/skip",
        description="General software role",
    )
    skip_score = {
        "score": 20,
        "tier": "skip",
        "fit_summary": "Not relevant.",
        "key_matches": [],
        "gaps": ["No AI focus"],
        "role_family": "irrelevant",
    }

    import agent.config as config_mod

    config_mod._settings = settings

    try:
        with patch("agent.orchestrator._collect_all_listings") as mock_collect:
            mock_collect.return_value = (
                [listing],
                {"indeed_eg": ScraperStat(count=1, status="ok")},
            )
            with patch("agent.orchestrator.deduplicate", return_value=[listing]):
                with patch("agent.orchestrator.score_listing", return_value=skip_score):
                    with patch("agent.tracker.sql.SqlTracker.save") as mock_save:
                        run(manual=True, dry_run=False)

        mock_save.assert_not_called()
        assert (ws / "memory" / "applications-log.md").read_text(encoding="utf-8") == "# Log\n"
        runs = list((ws / "logs" / "runs").glob("*.json"))
        assert runs
        report = json.loads(runs[0].read_text(encoding="utf-8"))
        assert report["fresh_listings"] == 1
        assert report["scored"] == 0
    finally:
        config_mod._settings = None
