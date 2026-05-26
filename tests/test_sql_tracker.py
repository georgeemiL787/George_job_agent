"""Tests for the local SQL tracker."""

from agent.config import Settings
from agent.search.base import JobListing
from agent.tracker.sql import SqlTracker


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


def test_sql_tracker_upsert_and_status(tmp_path):
    tracker = SqlTracker(_settings(tmp_path))
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


def test_start_run_and_role_status_columns(tmp_path):
    tracker = SqlTracker(_settings(tmp_path))
    tracker.load_or_create()
    run_id = tracker.start_run(True, False, {"mode": "fast"})
    assert run_id == 1
    tracker.upsert_role(
        _listing(),
        {"score": 70, "tier": "strong", "role_family": "ai_intern", "fit_summary": "ok"},
        run_id=run_id,
        scoring_status="scored",
        artifact_status="none",
    )
    role = tracker.get_row_by_slug("co-ai-intern-manual")
    assert role is not None
    assert role.run_id == 1
    assert role.scoring_status == "scored"
    tracker.set_artifact_status("co-ai-intern-manual", "cv_done")
    role = tracker.get_row_by_slug("co-ai-intern-manual")
    assert role.artifact_status == "cv_done"
    tracker.finish_run(run_id, "complete", {"status": "complete"})
