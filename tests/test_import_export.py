"""Excel tracker import/export round-trip."""
from __future__ import annotations

from openpyxl import Workbook

from agent.config import Settings
from agent.tracker import get_tracker
from agent.tracker.import_export import export_tracker, import_tracker
from agent.tracker.workbook import PIPELINE_HEADERS


def _settings(tmp_path) -> Settings:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)
    return Settings(
        openrouter_api_key="k",
        workspace_dir=str(ws),
        database_url=f"sqlite:///{(ws / 'tracker' / 't.db').as_posix()}",
    )


def test_export_import_preserves_scoring_columns(tmp_path):
    settings = _settings(tmp_path)
    tracker = get_tracker(settings)
    tracker.load_or_create()
    from agent.search.base import JobListing

    tracker.upsert_role(
        JobListing(
            title="AI Intern",
            company="Co",
            location="Cairo",
            source="manual",
            apply_url="https://example.com",
            slug="co-ai-intern-manual",
        ),
        {"score": 70, "tier": "strong", "role_family": "ai_intern", "fit_summary": "ok"},
        scoring_status="scored",
        artifact_status="cv_done",
    )
    tracker.rerank()

    out = export_tracker(settings, tmp_path / "roundtrip.xlsx")
    assert out.exists()

    tracker2 = get_tracker(settings)
    tracker2.load_or_create()
    # Clear and re-import
    import_tracker(settings, out)
    role = tracker2.get_row_by_slug("co-ai-intern-manual")
    assert role is not None
    assert role.score == 70
    assert role.scoring_status == "scored"
    assert role.artifact_status == "cv_done"
