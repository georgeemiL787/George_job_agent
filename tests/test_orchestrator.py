"""Orchestrator dry-run with mocked search."""
from unittest.mock import patch

from agent.config import Settings
from agent.observability.run_report import ScraperStat
from agent.orchestrator import run
from agent.search.base import JobListing


def test_run_dry_run_with_listing(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    mem = ws / "memory"
    mem.mkdir(parents=True)
    (mem / "job-search-profile.md").write_text("# Profile\nGeorge", encoding="utf-8")
    (mem / "cv-facts.md").write_text("# CV Facts\nPython", encoding="utf-8")
    (mem / "cv-role-playbook.md").write_text("# Playbook\n", encoding="utf-8")
    (mem / "applications-log.md").write_text("# Log\n", encoding="utf-8")
    (ws / "tracker").mkdir(parents=True)

    settings = Settings(openrouter_api_key="test-key", workspace_dir=str(ws))
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
        mock_collect.return_value = ([listing], {"wuzzuf": ScraperStat(count=1)})
        with patch("agent.orchestrator.deduplicate", return_value=[listing]):
            with patch("agent.orchestrator.score_listing", return_value=score):
                run(manual=True, dry_run=True)

    runs = list((ws / "logs" / "runs").glob("*.json"))
    assert runs
    config_mod._settings = None
