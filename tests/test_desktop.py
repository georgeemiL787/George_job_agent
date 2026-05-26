"""Desktop app service and GUI smoke tests."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from openpyxl import Workbook
from PySide6.QtWidgets import QApplication

from agent.config import Settings
from agent.desktop.app import MainWindow
from agent.desktop.widgets import RunDashboard, RunLiveStrip
from agent.run_control import RunOptions, RunStatus, get_coordinator
from agent.desktop.config_io import setup_is_missing, sqlite_url_for_workspace, write_env_values
from agent.desktop.schedule import read_schedule, write_schedule
from agent.desktop.services import DesktopService, initialize_local_tracker
from agent.search.base import JobListing
from agent.tracker import get_tracker
from agent.tracker.workbook import PIPELINE_HEADERS


def _settings(tmp_path: Path, *, key: str = "test-key") -> Settings:
    ws = tmp_path / "workspace"
    return Settings(
        openrouter_api_key=key,
        workspace_dir=str(ws),
        database_url=f"sqlite:///{(ws / 'tracker' / 'job_agent.db').as_posix()}",
    )


def _seed_memory(settings: Settings) -> None:
    settings.memory_path.mkdir(parents=True, exist_ok=True)
    (settings.memory_path / "job-search-profile.md").write_text("# Profile\nGeorge", encoding="utf-8")
    (settings.memory_path / "cv-facts.md").write_text("# CV Facts\nPython", encoding="utf-8")
    (settings.memory_path / "cv-role-playbook.md").write_text("# Playbook\n", encoding="utf-8")
    (settings.memory_path / "applications-log.md").write_text("# Log\n", encoding="utf-8")


def _seed_workbook(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Pipeline"
    ws.append(PIPELINE_HEADERS)
    ws.append(
        [
            1,
            "Co",
            "AI Intern",
            "Cairo",
            "manual",
            80,
            "strong",
            "ai_intern",
            "Good fit",
            "https://example.com",
            "No",
            "No",
            "Not Applied",
            "",
            "slug:co-ai-intern-manual",
            "",
            "",
        ]
    )
    log = wb.create_sheet("Log")
    log.append(["Timestamp", "Event", "Detail"])
    wb.save(path)


def test_settings_default_to_local_sqlite():
    settings = Settings(openrouter_api_key="test-key")
    assert settings.database_url == "sqlite:///workspace/tracker/job_agent.db"


def test_setup_missing_without_openrouter_key(tmp_path):
    settings = _settings(tmp_path, key="")
    assert setup_is_missing(settings)
    assert sqlite_url_for_workspace("workspace") == "sqlite:///workspace/tracker/job_agent.db"


def test_env_writer_preserves_existing_values(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("FOO=bar\nOPENROUTER_API_KEY=old\n", encoding="utf-8")
    write_env_values(
        {
            "OPENROUTER_API_KEY": "new",
            "WORKSPACE_DIR": "workspace",
            "DATABASE_URL": "sqlite:///workspace/tracker/job_agent.db",
        },
        env_path,
    )
    text = env_path.read_text(encoding="utf-8")
    assert "FOO=bar" in text
    assert "OPENROUTER_API_KEY=new" in text
    assert "DATABASE_URL=sqlite:///workspace/tracker/job_agent.db" in text


def test_desktop_initializes_sqlite_and_imports_workbook(tmp_path):
    settings = _settings(tmp_path)
    _seed_memory(settings)
    _seed_workbook(settings.tracker_path / "george_emil_job_tracker.xlsx")

    result = initialize_local_tracker(settings)
    service = DesktopService(settings)
    roles = service.list_roles()

    assert result["imported"] == 1
    assert roles[0]["slug"] == "co-ai-intern-manual"
    assert (settings.tracker_path / "job_agent.db").exists()


def test_desktop_service_status_and_export(tmp_path):
    settings = _settings(tmp_path)
    _seed_memory(settings)
    initialize_local_tracker(settings)
    tracker = get_tracker(settings)
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
        {"score": 70, "tier": "strong", "role_family": "ai_intern", "fit_summary": "Good"},
    )
    tracker.rerank()

    service = DesktopService(settings)
    service.approve_role("co-ai-intern-manual")
    service.mark_applied("co-ai-intern-manual", "2026-05-25")
    exported = service.export_tracker(tmp_path / "export.xlsx")

    role = service.get_role("co-ai-intern-manual")
    assert role is not None
    assert role["status"] == "Applied"
    assert exported.exists()


def test_schedule_config_round_trip(tmp_path):
    settings = _settings(tmp_path)
    config = write_schedule(settings, True, 2)
    assert config == {"enabled": True, "interval_hours": 2}
    assert read_schedule(settings) == config


def test_desktop_main_window_renders(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = _settings(tmp_path)
    window = MainWindow(settings, auto_setup=False)

    try:
        tab_names = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert "Dashboard" in tab_names
        assert "Roles" in tab_names
        assert "Role Detail" in tab_names
        assert "Add Role" in tab_names
        assert "Run" in tab_names
        assert hasattr(window, "run_live_strip")
        assert hasattr(window, "run_dashboard")
        assert "Artifacts" in tab_names
        assert "Logs" in tab_names
        assert "Settings" in tab_names
    finally:
        window.close()
        app.processEvents()


def test_run_widgets_update_from_coordinator(tmp_path):
    app = QApplication.instance() or QApplication([])
    get_coordinator().reset()
    settings = _settings(tmp_path)
    strip = RunLiveStrip()
    dashboard = RunDashboard()

    get_coordinator().try_start_run(RunOptions(mode="fast"))
    get_coordinator().set_phase("score")
    get_coordinator().update_progress(score_target=5, scored=2)

    progress = get_coordinator().get_progress().to_dict()
    events = [e.to_dict() for e in get_coordinator().get_events()]

    strip.update_state(active=True, progress=progress, estimate=None, status_text="Running — score")
    dashboard.update_state(
        active=True,
        progress=progress,
        estimate=None,
        events=events,
        report={"scrapers": {"wuzzuf": {"count": 3, "status": "ok"}}},
        status_text="Running — score",
    )

    assert strip.chip_scored.value.text() == "2"
    assert dashboard.activity_list.count() >= 1
    get_coordinator().finish_run(RunStatus.COMPLETE)
    get_coordinator().reset()
    app.processEvents()
