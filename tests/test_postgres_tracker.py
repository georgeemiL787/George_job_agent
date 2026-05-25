"""Tests for SQL tracker using SQLite as an offline stand-in."""

from agent.config import Settings
from agent.search.base import JobListing
from agent.tracker.postgres import PostgresTracker


def _settings(tmp_path):
    db_path = (tmp_path / "tracker.db").as_posix()
    return Settings(openrouter_api_key="test-key", database_url=f"sqlite:///{db_path}")


def _listing():
    return JobListing(
        title="AI Intern",
        company="Co",
        location="Cairo",
        source="manual",
        apply_url="https://example.com/apply",
        description="Python ML",
        slug="co-ai-intern-manual",
    )


def test_postgres_tracker_upsert_and_status(tmp_path):
    tracker = PostgresTracker(_settings(tmp_path))
    tracker.load_or_create()
    tracker.upsert_role(
        _listing(),
        {
            "score": 82,
            "tier": "strong",
            "role_family": "ai_intern",
            "fit_summary": "Good fit",
        },
    )
    tracker.rerank()
    tracker.mark_cv_ready("co-ai-intern-manual")
    tracker.mark_draft("co-ai-intern-manual")

    role = tracker.get_row_by_slug("co-ai-intern-manual")
    assert role is not None
    assert role.rank == 1
    assert role.score == 82
    assert role.cv_ready is True
    assert role.status == "Draft"
    assert tracker.get_all_slugs() == {"co-ai-intern-manual"}
    assert tracker.list_events()
