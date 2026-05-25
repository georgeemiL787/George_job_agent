"""FastAPI route tests with an offline SQLite tracker."""

import json

from fastapi.testclient import TestClient

import agent.config as config_mod
from agent.config import Settings
from agent.search.base import JobListing
from agent.tracker.postgres import PostgresTracker
from agent.web.app import create_app


def _settings(tmp_path):
    ws = tmp_path / "workspace"
    (ws / "memory").mkdir(parents=True)
    (ws / "tracker").mkdir(parents=True)
    return Settings(
        openrouter_api_key="test-key",
        workspace_dir=str(ws),
        database_url=f"sqlite:///{(ws / 'tracker' / 'web.db').as_posix()}",
    )


def test_status_route_lists_roles(tmp_path):
    settings = _settings(tmp_path)
    config_mod._settings = settings
    tracker = PostgresTracker(settings)
    tracker.load_or_create()
    tracker.upsert_role(
        JobListing(
            title="AI Intern",
            company="Co",
            location="Cairo",
            source="manual",
            apply_url="https://example.com",
            slug="co-ai-intern-manual",
        ),
        {
            "score": 75,
            "tier": "strong",
            "role_family": "ai_intern",
            "fit_summary": "Good fit",
        },
    )
    tracker.rerank()

    try:
        with TestClient(create_app()) as client:
            response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["roles"][0]["slug"] == "co-ai-intern-manual"
        assert data["roles"][0]["score"] == 75
    finally:
        config_mod._settings = None


def test_run_route_returns_conflict_when_busy(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    config_mod._settings = settings
    monkeypatch.setattr("agent.web.jobs.start_run", lambda **kwargs: False)

    try:
        with TestClient(create_app()) as client:
            response = client.post("/api/run?dry_run=true")
        assert response.status_code == 409
    finally:
        config_mod._settings = None


def test_status_route_normalizes_legacy_scraper_health(tmp_path):
    settings = _settings(tmp_path)
    config_mod._settings = settings
    tracker = PostgresTracker(settings)
    tracker.load_or_create()
    settings.runs_log_path.mkdir(parents=True)
    (settings.runs_log_path / "2026-05-25_00-00.json").write_text(
        json.dumps(
            {
                "scrapers": {
                    "bayt": {"count": 0, "error": None},
                    "indeed_eg": {"count": 1, "error": None},
                    "blocked": {"count": 0, "error": "HTTP 403 Forbidden"},
                }
            }
        ),
        encoding="utf-8",
    )

    try:
        with TestClient(create_app()) as client:
            response = client.get("/api/status")
        assert response.status_code == 200
        scrapers = response.json()["latest_run"]["scrapers"]
        assert scrapers["bayt"]["status"] == "empty"
        assert scrapers["indeed_eg"]["status"] == "ok"
        assert scrapers["blocked"]["status"] == "error"
        assert scrapers["blocked"]["message"] == "HTTP 403 Forbidden"
    finally:
        config_mod._settings = None
