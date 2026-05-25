"""FastAPI route tests with an offline SQLite tracker."""

import json

import pytest
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
    cv = tmp_path / "public-cv.pdf"
    cv.write_bytes(b"%PDF-1.4\n% test public cv\n")
    return Settings(
        openrouter_api_key="test-key",
        workspace_dir=str(ws),
        database_url=f"sqlite:///{(ws / 'tracker' / 'web.db').as_posix()}",
        web_token="test-token",
        public_cv_path=str(cv),
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
            response = client.get(
                "/api/status",
                headers={"Authorization": "Bearer test-token"},
            )
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
            response = client.post(
                "/api/run?dry_run=true",
                headers={"Authorization": "Bearer test-token"},
            )
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
            response = client.get(
                "/api/status",
                headers={"Authorization": "Bearer test-token"},
            )
        assert response.status_code == 200
        scrapers = response.json()["latest_run"]["scrapers"]
        assert scrapers["bayt"]["status"] == "empty"
        assert scrapers["indeed_eg"]["status"] == "ok"
        assert scrapers["blocked"]["status"] == "error"
        assert scrapers["blocked"]["message"] == "HTTP 403 Forbidden"
    finally:
        config_mod._settings = None


def test_public_pages_and_cv_do_not_require_auth(tmp_path):
    settings = _settings(tmp_path)
    config_mod._settings = settings

    try:
        with TestClient(create_app()) as client:
            home = client.get("/")
            cv = client.get("/cv/george-emil-sadek.pdf")
            login = client.get("/login")
            health = client.get("/healthz")
            docs = client.get("/docs")
        assert home.status_code == 200
        assert "George Emil Sadek" in home.text
        assert "Applied AI engineer" in home.text
        assert "george-cv-preview.png" in home.text
        for private_text in [
            "Ahmed Basha",
            "Rod El Farag",
            "11632",
            "applications-log",
            "tracker-priorities",
        ]:
            assert private_text not in home.text
        assert cv.status_code == 200
        assert cv.headers["content-type"] == "application/pdf"
        assert login.status_code == 200
        assert health.status_code == 200
        assert docs.status_code == 404
    finally:
        config_mod._settings = None


def test_admin_pages_and_private_apis_require_auth(tmp_path):
    settings = _settings(tmp_path)
    config_mod._settings = settings

    try:
        with TestClient(create_app(), follow_redirects=False) as client:
            admin = client.get("/admin")
            api = client.get("/api/status")
        assert admin.status_code == 303
        assert admin.headers["location"].startswith("/login")
        assert api.status_code == 401
    finally:
        config_mod._settings = None


def test_token_login_allows_admin_and_logout_removes_access(tmp_path):
    settings = _settings(tmp_path)
    config_mod._settings = settings
    tracker = PostgresTracker(settings)
    tracker.load_or_create()

    try:
        with TestClient(create_app(), follow_redirects=False) as client:
            bad = client.post("/api/auth/login", json={"token": "wrong"})
            assert bad.status_code == 401

            login = client.post("/api/auth/login", json={"token": "test-token"})
            assert login.status_code == 200
            assert "george_job_agent_admin" in login.headers["set-cookie"]

            admin = client.get("/admin")
            status = client.get("/api/status")
            assert admin.status_code == 200
            assert status.status_code == 200

            logout = client.post("/api/auth/logout")
            assert logout.status_code == 200
            denied = client.get("/api/status")
            assert denied.status_code == 401
    finally:
        config_mod._settings = None


def test_production_requires_web_token(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    settings.web_token = ""
    settings.environment = "production"
    config_mod._settings = settings
    monkeypatch.delenv("RENDER", raising=False)

    try:
        with pytest.raises(RuntimeError, match="WEB_TOKEN"):
            with TestClient(create_app()):
                pass
    finally:
        config_mod._settings = None


def test_startup_seeds_missing_workspace_memory(tmp_path):
    source_settings = _settings(tmp_path / "source")
    target_ws = tmp_path / "persistent" / "workspace"
    source_settings.workspace_dir = str(target_ws)
    config_mod._settings = source_settings

    try:
        with TestClient(create_app()) as client:
            assert client.get("/healthz").status_code == 200
        assert (target_ws / "memory" / "cv-facts.md").exists()
        assert (target_ws / "memory" / "job-search-profile.md").exists()
    finally:
        config_mod._settings = None
