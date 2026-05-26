"""PySide6 desktop application."""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import agent.config as config_mod
from agent.config import Settings, get_settings
from agent.desktop.config_io import (
    desktop_defaults,
    read_run_sources,
    setup_is_missing,
    sqlite_url_for_workspace,
    write_env_values,
    write_run_sources,
)
from agent.desktop.run_estimator import RunEstimator
from agent.desktop.scroll_page import make_scroll_page
from agent.desktop.schedule import read_schedule, write_schedule
from agent.desktop.theme import load_theme
from agent.desktop.services import (
    DesktopService,
    artifact_paths,
    check_pdflatex,
    check_playwright,
    install_miktex,
    install_playwright_chromium,
)
from agent.desktop.widgets import RunDashboard, RunLiveStrip
from agent.run_control import RunProgress
from agent.version import __version__


def app_icon_path() -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return bundle_root / "agent" / "desktop" / "assets" / "app.png"


def app_icon() -> QIcon:
    icon_path = app_icon_path()
    return QIcon(str(icon_path)) if icon_path.exists() else QIcon()


def set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GeorgeJobAgent.Desktop")
    except Exception:
        pass


class FunctionWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, func: Callable[[], Any]) -> None:
        super().__init__()
        self.func = func

    def run(self) -> None:
        try:
            self.succeeded.emit(self.func())
        except Exception as exc:
            if isinstance(exc, ValueError):
                self.failed.emit(str(exc))
            else:
                self.failed.emit(traceback.format_exc())


class SetupDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("George Job Agent Setup")
        self.setMinimumWidth(620)

        self.key = QLineEdit(settings.openrouter_api_key)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.scoring_model = QLineEdit(settings.scoring_model)
        self.cv_model = QLineEdit(settings.cv_model)
        self.letter_model = QLineEdit(settings.letter_model)
        self.fallback_model = QLineEdit(settings.fallback_model)
        self.workspace = QLineEdit(settings.workspace_dir)
        self.latex_bin = QLineEdit(settings.latex_bin)
        self.schedule_hours = QSpinBox()
        self.schedule_hours.setRange(1, 24)
        self.schedule_hours.setValue(settings.schedule_interval_hours)
        self.max_roles = QSpinBox()
        self.max_roles.setRange(1, 100)
        self.max_roles.setValue(settings.max_roles_per_run)
        self.min_score = QSpinBox()
        self.min_score.setRange(0, 100)
        self.min_score.setValue(settings.min_score_to_tailor)
        self.status = QTextEdit()
        self.status.setReadOnly(True)
        self.status.setMinimumHeight(130)

        form = QFormLayout()
        form.addRow("OpenRouter API key", self.key)
        form.addRow("Scoring model", self.scoring_model)
        form.addRow("CV model", self.cv_model)
        form.addRow("Letter model", self.letter_model)
        form.addRow("Fallback model", self.fallback_model)
        form.addRow("Workspace", self.workspace)
        form.addRow("LaTeX binary", self.latex_bin)
        form.addRow("Schedule interval hours", self.schedule_hours)
        form.addRow("Max roles per run", self.max_roles)
        form.addRow("Minimum tailor score", self.min_score)

        browse = QPushButton("Browse workspace")
        browse.clicked.connect(self.choose_workspace)
        check = QPushButton("Check setup")
        check.clicked.connect(self.check_setup)
        install = QPushButton("Install Chromium")
        install.clicked.connect(self.install_chromium)
        install_latex = QPushButton("Install MiKTeX")
        install_latex.clicked.connect(self.install_miktex)
        save = QPushButton("Save and continue")
        save.clicked.connect(self.save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(browse)
        buttons.addWidget(check)
        buttons.addWidget(install)
        buttons.addWidget(install_latex)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Configure the local Windows desktop app."))
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addLayout(buttons)

    def choose_workspace(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose workspace", self.workspace.text())
        if selected:
            self.workspace.setText(selected)

    def check_setup(self) -> None:
        playwright_ok, playwright_msg = check_playwright()
        latex_ok, latex_msg = check_pdflatex(self.latex_bin.text().strip() or "pdflatex")
        key_msg = "OpenRouter key is set." if self.key.text().strip() else "OpenRouter key is missing."
        self.status.setPlainText(
            "\n".join(
                [
                    key_msg,
                    playwright_msg,
                    latex_msg,
                    f"Workspace: {self.workspace.text().strip() or 'workspace'}",
                    f"Playwright ready: {playwright_ok}",
                    f"LaTeX ready: {latex_ok}",
                ]
            )
        )

    def install_chromium(self) -> None:
        self.status.setPlainText("Installing Playwright Chromium. This can take a few minutes...")
        QApplication.processEvents()
        try:
            self.status.setPlainText(install_playwright_chromium())
        except Exception as exc:
            self.status.setPlainText(str(exc))

    def install_miktex(self) -> None:
        self.status.setPlainText(
            "Installing MiKTeX via winget. This can take several minutes...\n"
            "Please wait — do not close this dialog."
        )
        QApplication.processEvents()
        try:
            self.status.setPlainText(install_miktex())
        except Exception as exc:
            self.status.setPlainText(str(exc))

    def save(self) -> None:
        workspace = self.workspace.text().strip() or "workspace"
        values = {
            "OPENROUTER_API_KEY": self.key.text().strip(),
            "SCORING_MODEL": self.scoring_model.text().strip(),
            "CV_MODEL": self.cv_model.text().strip(),
            "LETTER_MODEL": self.letter_model.text().strip(),
            "FALLBACK_MODEL": self.fallback_model.text().strip(),
            "WORKSPACE_DIR": workspace,
            "CV_VARIATIONS_DIR": self.settings.cv_variations_dir,
            "LATEX_BIN": self.latex_bin.text().strip() or "pdflatex",
            "LOG_LEVEL": self.settings.log_level,
            "TIMEZONE": self.settings.timezone,
            "SCHEDULE_INTERVAL_HOURS": str(self.schedule_hours.value()),
            "MAX_ROLES_PER_RUN": str(self.max_roles.value()),
            "MIN_SCORE_TO_TAILOR": str(self.min_score.value()),
            "DATABASE_URL": sqlite_url_for_workspace(workspace),
            "NOTIFY_ENABLED": str(self.settings.notify_enabled).lower(),
            "NOTIFY_MIN_TIER": self.settings.notify_min_tier,
            "NOTIFY_WEBHOOK_URL": self.settings.notify_webhook_url,
        }
        defaults = desktop_defaults(self.settings)
        defaults.update(values)
        write_env_values(defaults)
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, *, auto_setup: bool = True) -> None:
        super().__init__()
        self.settings = settings
        self.service = DesktopService(settings)
        self.run_estimator = RunEstimator(settings)
        self.worker: FunctionWorker | None = None
        self.selected_slug = ""
        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self.run_scheduled_cycle)
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.refresh_run_progress)

        self.setWindowTitle(f"George Job Agent v{__version__}")
        self.setWindowIcon(app_icon())
        self.resize(1440, 920)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self._build_dashboard()
        self._build_roles()
        self._build_detail()
        self._build_add_role()
        self._build_run_monitor()
        self._build_artifacts()
        self._build_logs()
        self._build_settings()

        if auto_setup and setup_is_missing(settings):
            QTimer.singleShot(0, self.show_setup_dialog)
        else:
            self.initialize_app()

    def _build_dashboard(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)

        run_box = QGroupBox("Run")
        run_layout = QGridLayout(run_box)
        self.run_status = QLabel("Idle")
        self.run_fast_btn = QPushButton("Fast run")
        self.run_fast_btn.setObjectName("PrimaryButton")
        self.run_deep_btn = QPushButton("Deep run")
        self.run_dry_btn = QPushButton("Dry-run")
        self.run_stop_btn = QPushButton("Stop Run")
        self.run_stop_btn.setObjectName("DangerButton")
        self.run_stop_btn.setEnabled(False)
        self.run_stop_btn.clicked.connect(self.stop_run)
        self.run_fast_btn.clicked.connect(
            lambda: self.start_run_worker("Fast run active", mode="fast", dry_run=False)
        )
        self.run_deep_btn.clicked.connect(
            lambda: self.start_run_worker("Deep run active", mode="deep", dry_run=False)
        )
        self.run_dry_btn.clicked.connect(
            lambda: self.start_run_worker("Dry-run active", mode="fast", dry_run=True)
        )
        run_layout.addWidget(self.run_fast_btn, 0, 0)
        run_layout.addWidget(self.run_deep_btn, 0, 1)
        run_layout.addWidget(self.run_dry_btn, 0, 2)
        run_layout.addWidget(self.run_stop_btn, 1, 0, 1, 3)
        run_layout.addWidget(QLabel("Status"), 2, 0)
        run_layout.addWidget(self.run_status, 2, 1, 1, 2)

        sources_box = QGroupBox("Sources")
        sources_layout = QHBoxLayout(sources_box)
        self.src_wuzzuf = QCheckBox("Wuzzuf")
        self.src_linkedin = QCheckBox("LinkedIn")
        self.src_bayt = QCheckBox("Bayt")
        self.src_gulftalent = QCheckBox("GulfTalent")
        self.src_indeed = QCheckBox("Indeed")
        for cb in (
            self.src_wuzzuf,
            self.src_linkedin,
            self.src_bayt,
            self.src_gulftalent,
            self.src_indeed,
        ):
            cb.setChecked(True)
        self.src_indeed.setChecked(False)
        for cb in (
            self.src_wuzzuf,
            self.src_linkedin,
            self.src_bayt,
            self.src_gulftalent,
            self.src_indeed,
        ):
            sources_layout.addWidget(cb)
        save_sources = QPushButton("Save sources as default")
        save_sources.clicked.connect(self.save_source_defaults)
        sources_layout.addWidget(save_sources)

        schedule_box = QGroupBox("Scheduler")
        schedule_layout = QGridLayout(schedule_box)
        self.schedule_mode = QComboBox()
        self.schedule_mode.addItems(["Off", "1 hour", "2 hours", "4 hours"])
        self.schedule_save = QPushButton("Save schedule")
        self.schedule_save.clicked.connect(self.save_schedule)
        self.next_run = QLabel("Not scheduled")
        schedule_layout.addWidget(self.schedule_mode, 0, 0)
        schedule_layout.addWidget(self.schedule_save, 0, 1)
        schedule_layout.addWidget(QLabel("Next run"), 1, 0)
        schedule_layout.addWidget(self.next_run, 1, 1)

        top = QHBoxLayout()
        top.addWidget(run_box)
        top.addWidget(sources_box)
        top.addWidget(schedule_box)
        layout.addLayout(top)

        self.run_live_strip = RunLiveStrip()
        layout.addWidget(self.run_live_strip)

        self.scraper_health = QTextEdit()
        self.scraper_health.setReadOnly(True)
        self.scraper_health.setMinimumHeight(120)
        layout.addWidget(QLabel("Latest scraper health"))
        layout.addWidget(self.scraper_health)

        self.top_roles = self._new_roles_table()
        self.top_roles.setMinimumHeight(280)
        layout.addWidget(QLabel("Top roles"))
        layout.addWidget(self.top_roles)
        self._add_scroll_tab(page, "Dashboard")

    def _build_roles(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        self.drafts_only = QCheckBox("Drafts only")
        self.include_applied = QCheckBox("Include applied")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_roles)
        export = QPushButton("Export Excel")
        export.clicked.connect(self.export_tracker)
        import_btn = QPushButton("Import Excel")
        import_btn.clicked.connect(self.import_tracker)
        retry_failed = QPushButton("Retry failed scores")
        retry_failed.clicked.connect(self.retry_failed_scores)
        controls.addWidget(self.drafts_only)
        controls.addWidget(self.include_applied)
        controls.addWidget(refresh)
        controls.addWidget(export)
        controls.addWidget(import_btn)
        controls.addWidget(retry_failed)
        controls.addStretch()
        layout.addLayout(controls)
        self.roles_table = self._new_roles_table()
        self.roles_table.setMinimumHeight(420)
        layout.addWidget(self.roles_table)
        self._add_scroll_tab(page, "Roles")

    def _build_detail(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.detail_title = QLabel("Select a role from the Roles tab.")
        self.detail_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail_meta = QLabel("")
        self.detail_fit = QTextEdit()
        self.detail_fit.setReadOnly(True)
        self.detail_fit.setMinimumHeight(320)
        self.apply_url = QLabel("")
        self.apply_url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.detail_title)
        layout.addWidget(self.detail_meta)
        layout.addWidget(self.apply_url)
        layout.addWidget(self.detail_fit)

        actions = QHBoxLayout()
        for label, handler in [
            ("Tailor CV", self.tailor_selected),
            ("Approve", self.approve_selected),
            ("Package", self.package_selected),
            ("Open CV folder", lambda: self.open_path(self.settings.cv_tailored_path)),
            ("Open letters folder", lambda: self.open_path(self.settings.cover_letters_path)),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            actions.addWidget(btn)
        actions.addStretch()
        layout.addLayout(actions)

        applied = QHBoxLayout()
        self.applied_date = QDateEdit()
        self.applied_date.setCalendarPopup(True)
        self.applied_date.setDate(dt_today_qdate())
        applied_btn = QPushButton("Mark applied")
        applied_btn.clicked.connect(self.mark_selected_applied)
        applied.addWidget(QLabel("Applied date"))
        applied.addWidget(self.applied_date)
        applied.addWidget(applied_btn)
        applied.addStretch()
        layout.addLayout(applied)
        self._add_scroll_tab(page, "Role Detail")

    def _build_add_role(self) -> None:
        page = QWidget()
        layout = QFormLayout(page)
        self.add_title = QLineEdit()
        self.add_company = QLineEdit()
        self.add_location = QLineEdit()
        self.add_url = QLineEdit()
        self.add_source = QComboBox()
        self.add_source.addItems(["manual", "linkedin"])
        self.add_description = QTextEdit()
        self.add_description.setMinimumHeight(360)
        submit = QPushButton("Process role")
        submit.clicked.connect(self.submit_role)
        layout.addRow("Title", self.add_title)
        layout.addRow("Company", self.add_company)
        layout.addRow("Location", self.add_location)
        layout.addRow("Apply URL", self.add_url)
        layout.addRow("Source", self.add_source)
        layout.addRow("Description", self.add_description)
        layout.addRow(submit)
        self._add_scroll_tab(page, "Add Role")

    def _build_run_monitor(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_run_monitor)
        open_runs = QPushButton("Open run reports")
        open_runs.clicked.connect(lambda: self.open_path(self.settings.logs_path / "runs"))
        controls.addWidget(refresh)
        controls.addWidget(open_runs)
        controls.addStretch()
        layout.addLayout(controls)
        self.run_dashboard = RunDashboard()
        self.run_dashboard.setMinimumHeight(900)
        layout.addWidget(self.run_dashboard)
        self._add_scroll_tab(page, "Run")

    def _build_artifacts(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        actions = [
            ("Open CVs", lambda: self.open_path(self.settings.cv_tailored_path)),
            ("Open letters", lambda: self.open_path(self.settings.cover_letters_path)),
            ("Open packages", lambda: self.open_path(self.settings.packages_path)),
            ("Open tracker", lambda: self.open_path(self.settings.tracker_path)),
            ("Export Excel", self.export_tracker),
            ("Refresh", self.refresh_artifacts),
        ]
        for label, handler in actions:
            button = QPushButton(label)
            button.clicked.connect(handler)
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        self.artifacts_text = QTextEdit()
        self.artifacts_text.setReadOnly(True)
        self.artifacts_text.setMinimumHeight(400)
        layout.addWidget(self.artifacts_text)
        self._add_scroll_tab(page, "Artifacts")

    def _build_logs(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        refresh = QPushButton("Refresh logs")
        refresh.clicked.connect(self.refresh_logs)
        open_logs = QPushButton("Open logs folder")
        open_logs.clicked.connect(lambda: self.open_path(self.settings.logs_path))
        controls.addWidget(refresh)
        controls.addWidget(open_logs)
        controls.addStretch()
        layout.addLayout(controls)
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMinimumHeight(500)
        layout.addWidget(self.logs)
        self._add_scroll_tab(page, "Logs")

    def _build_settings(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.settings_text = QTextEdit()
        self.settings_text.setReadOnly(True)
        self.settings_text.setMinimumHeight(400)
        open_setup = QPushButton("Open setup wizard")
        open_setup.clicked.connect(self.show_setup_dialog)
        sync_master = QPushButton("Sync master CV")
        sync_master.clicked.connect(lambda: self.start_worker("Syncing master CV", self.service.sync_master))
        open_workspace = QPushButton("Open workspace")
        open_workspace.clicked.connect(lambda: self.open_path(self.settings.workspace_path))
        layout.addWidget(self.settings_text)
        buttons = QHBoxLayout()
        buttons.addWidget(open_setup)
        buttons.addWidget(sync_master)
        buttons.addWidget(open_workspace)
        buttons.addStretch()
        layout.addLayout(buttons)
        self._add_scroll_tab(page, "Settings")

    def _add_scroll_tab(self, page: QWidget, title: str) -> None:
        self.tabs.addTab(make_scroll_page(page), title)

    def _new_roles_table(self) -> QTableWidget:
        table = QTableWidget(0, 9)
        table.setHorizontalHeaderLabels(
            ["Rank", "Score", "Tier", "Status", "ScoreSt", "ArtSt", "Company", "Role", "Source"]
        )
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setDefaultSectionSize(32)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.itemDoubleClicked.connect(self.table_role_opened)
        return table

    def initialize_app(self) -> None:
        try:
            self.service.initialize()
            self.apply_saved_sources()
            self.load_schedule()
            self.refresh_all()
            self.run_status.setText("Idle")
        except Exception as exc:
            self.show_error(str(exc))

    def refresh_all(self) -> None:
        self.refresh_dashboard()
        self.refresh_roles()
        self.refresh_run_monitor()
        self.refresh_artifacts()
        self.refresh_logs()
        self.refresh_settings()

    def refresh_dashboard(self) -> None:
        rows = self.service.list_roles(include_applied=False)
        self.populate_table(self.top_roles, rows[:5])
        report = self.service.active_run_report() or self.service.latest_run_report()
        if not report:
            self.scraper_health.setPlainText("No run report yet.")
            return
        lines = []
        for name, stat in (report.get("scrapers") or {}).items():
            status = stat.get("status") or ("error" if stat.get("error") else "empty")
            message = stat.get("message") or stat.get("error") or ""
            lines.append(f"{name}: {stat.get('count', 0)} listings [{status}] {message}".strip())
        self.scraper_health.setPlainText("\n".join(lines) or "No scraper stats.")

    def refresh_roles(self) -> None:
        rows = self.service.list_roles(
            drafts_only=self.drafts_only.isChecked(),
            include_applied=self.include_applied.isChecked(),
        )
        self.populate_table(self.roles_table, rows)

    def refresh_logs(self) -> None:
        self.logs.setPlainText("\n".join(self.service.tail_log()))

    def refresh_run_monitor(self) -> None:
        self._apply_run_ui_state()

    def _apply_run_ui_state(self) -> None:
        active = self.service.is_run_active()
        progress = self.service.get_run_progress()
        events = self.service.get_run_events()
        report = self.service.active_run_report() or self.service.latest_run_report()
        opts = self.service.get_run_options()
        mode = opts.get("mode", "fast") if opts else "fast"

        estimate = None
        if active or progress.get("phase"):
            fields = RunProgress.__dataclass_fields__
            estimate = self.run_estimator.estimate(
                RunProgress(**{k: progress[k] for k in fields if k in progress}),
                mode=mode,
            )

        status_text = self.run_status.text()
        if active:
            status_text = f"Running — {progress.get('phase', '')}"
        elif not progress.get("phase"):
            self.run_live_strip.set_idle()

        if active or progress.get("phase"):
            self.run_live_strip.update_state(
                active=active,
                progress=progress,
                estimate=estimate,
                status_text=status_text,
            )
        self.run_dashboard.update_state(
            active=active,
            progress=progress,
            estimate=estimate,
            events=events,
            report=report,
            status_text=status_text,
        )

    def refresh_artifacts(self) -> None:
        lines = [
            f"Tailored CVs: {self.settings.cv_tailored_path}",
            f"Cover letters: {self.settings.cover_letters_path}",
            f"Packages: {self.settings.packages_path}",
            f"Tracker: {self.settings.tracker_path}",
        ]
        if self.selected_slug:
            lines.extend(["", f"Selected role: {self.selected_slug}"])
            for name, path in artifact_paths(self.settings, self.selected_slug).items():
                state = "ready" if path.exists() else "missing"
                lines.append(f"{name}: {state} - {path}")
        self.artifacts_text.setPlainText("\n".join(lines))

    def refresh_settings(self) -> None:
        playwright_ok, playwright_msg = check_playwright()
        latex_ok, latex_msg = check_pdflatex(self.settings.latex_bin)
        self.settings_text.setPlainText(
            "\n".join(
                [
                    f"Workspace: {self.settings.workspace_path}",
                    f"Database: {self.settings.database_url}",
                    f"OpenRouter key: {'set' if self.settings.openrouter_api_key else 'missing'}",
                    f"Schedule interval: {self.settings.schedule_interval_hours}h",
                    "",
                    self.service.resolved_config_summary(),
                    "",
                    playwright_msg,
                    latex_msg,
                    f"Playwright ready: {playwright_ok}",
                    f"LaTeX ready: {latex_ok}",
                ]
            )
        )

    def populate_table(self, table: QTableWidget, rows: list[dict[str, Any]]) -> None:
        table.setRowCount(len(rows))
        for row_index, role in enumerate(rows):
            values = [
                role.get("rank") or "",
                role.get("score") or 0,
                role.get("tier") or "",
                role.get("status") or "",
                role.get("scoring_status") or "",
                role.get("artifact_status") or "",
                role.get("company") or "",
                role.get("title") or "",
                role.get("source") or "",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, role.get("slug"))
                table.setItem(row_index, col, item)

    def table_role_opened(self, item: QTableWidgetItem) -> None:
        slug = item.data(Qt.ItemDataRole.UserRole)
        if slug:
            self.load_role_detail(str(slug))
            self.tabs.setCurrentIndex(2)

    def load_role_detail(self, slug: str) -> None:
        role = self.service.get_role(slug)
        if not role:
            self.show_error(f"Role not found: {slug}")
            return
        self.selected_slug = slug
        self.detail_title.setText(f"{role['company']} - {role['title']}")
        fr = role.get("failure_reason") or ""
        self.detail_meta.setText(
            f"Score {role['score']}/100 | {role['tier']} | {role['status']} | "
            f"{role.get('scoring_status', '')} | {role.get('artifact_status', '')} | {role['source']}"
            + (f" | Error: {fr[:60]}" if fr else "")
        )
        self.apply_url.setText(role.get("apply_url") or "")
        fit = role.get("fit_summary") or ""
        if fr:
            fit += f"\n\nFailure: {fr}"
        self.detail_fit.setPlainText(fit)
        self.refresh_artifacts()

    def _selected_sources(self) -> set[str] | None:
        mapping = {
            "wuzzuf": self.src_wuzzuf,
            "linkedin": self.src_linkedin,
            "bayt": self.src_bayt,
            "gulftalent": self.src_gulftalent,
            "indeed_eg": self.src_indeed,
        }
        selected = {key for key, cb in mapping.items() if cb.isChecked()}
        return selected or None

    def start_run_worker(self, status: str, *, mode: str, dry_run: bool) -> None:
        sources = self._selected_sources()
        self.start_worker(
            status,
            lambda: self.service.run_cycle(dry_run=dry_run, mode=mode, sources=sources),
            is_run=True,
        )

    def stop_run(self) -> None:
        self.service.cancel_run()
        self.run_status.setText("Stopping…")

    def refresh_run_progress(self) -> None:
        if not self.service.is_run_active():
            self.progress_timer.stop()
            self.run_stop_btn.setEnabled(False)
            self._apply_run_ui_state()
            return
        p = self.service.get_run_progress()
        self.run_status.setText(f"Running — {p.get('phase', '')}")
        self._apply_run_ui_state()

    def apply_saved_sources(self) -> None:
        saved = read_run_sources(self.settings)
        if not saved:
            return
        mapping = {
            "wuzzuf": self.src_wuzzuf,
            "linkedin": self.src_linkedin,
            "bayt": self.src_bayt,
            "gulftalent": self.src_gulftalent,
            "indeed_eg": self.src_indeed,
        }
        for key, cb in mapping.items():
            cb.setChecked(key in saved or ("linkedin_jobs" in saved and key == "linkedin"))

    def retry_failed_scores(self) -> None:
        self.start_worker(
            "Retrying failed scores",
            lambda: self.service.retry_failed_scores(),
            on_success=lambda n: self.show_info(f"Retried {n} role(s)."),
        )

    def save_source_defaults(self) -> None:
        path = write_run_sources(self.settings, self._selected_sources() or set())
        self.show_info(f"Saved source defaults to {path}")

    def show_info(self, message: str) -> None:
        QMessageBox.information(self, "George Job Agent", message)

    def start_worker(
        self,
        status: str,
        func: Callable[[], Any],
        on_success: Callable[[Any], None] | None = None,
        *,
        is_run: bool = False,
    ) -> None:
        if self.worker and self.worker.isRunning():
            self.show_error("Another job is already running.")
            return
        self.run_status.setText(status)
        if is_run:
            self.run_stop_btn.setEnabled(True)
            self.progress_timer.start(250)
        self.worker = FunctionWorker(func)
        self.worker.succeeded.connect(lambda result: self.worker_succeeded(result, on_success, is_run=is_run))
        self.worker.failed.connect(lambda msg: self.worker_failed(msg, is_run=is_run))
        self.worker.start()

    def worker_succeeded(
        self,
        result: Any,
        on_success: Callable[[Any], None] | None,
        *,
        is_run: bool = False,
    ) -> None:
        if is_run:
            self.progress_timer.stop()
            self.run_stop_btn.setEnabled(False)
            self.refresh_run_progress()
            report = self.service.latest_run_report()
            terminal = (report or {}).get("status", "complete")
            self.run_status.setText(terminal.capitalize())
        else:
            self.run_status.setText("Succeeded")
        if on_success:
            on_success(result)
        self.refresh_all()

    def worker_failed(self, message: str, *, is_run: bool = False) -> None:
        if is_run:
            self.progress_timer.stop()
            self.run_stop_btn.setEnabled(False)
        self.run_status.setText("Failed")
        self.show_error(message)
        self.refresh_logs()

    def run_scheduled_cycle(self) -> None:
        self.start_run_worker("Scheduled run active", mode="fast", dry_run=False)

    def load_schedule(self) -> None:
        config = read_schedule(self.settings)
        label = "Off"
        if config["enabled"]:
            label = f"{config['interval_hours']} hour" if config["interval_hours"] == 1 else f"{config['interval_hours']} hours"
        self.schedule_mode.setCurrentText(label)
        self.apply_schedule_timer(config["enabled"], config["interval_hours"])

    def save_schedule(self) -> None:
        text = self.schedule_mode.currentText()
        enabled = text != "Off"
        interval = int(text.split()[0]) if enabled else 4
        write_schedule(self.settings, enabled, interval)
        self.apply_schedule_timer(enabled, interval)

    def apply_schedule_timer(self, enabled: bool, interval_hours: int) -> None:
        self.schedule_timer.stop()
        if enabled:
            self.schedule_timer.start(interval_hours * 60 * 60 * 1000)
            self.next_run.setText(f"Every {interval_hours}h while app is open")
        else:
            self.next_run.setText("Not scheduled")

    def submit_role(self) -> None:
        body = {
            "title": self.add_title.text().strip(),
            "company": self.add_company.text().strip(),
            "location": self.add_location.text().strip(),
            "apply_url": self.add_url.text().strip(),
            "source": self.add_source.currentText(),
            "description": self.add_description.toPlainText().strip(),
        }
        if not body["title"] or not body["company"] or not body["apply_url"] or not body["description"]:
            self.show_error("Title, company, apply URL, and description are required.")
            return
        self.start_worker(
            "Processing manual role",
            lambda: self.service.add_manual_role(body),
            lambda result: self.load_role_detail(result["role"]["slug"]) if result.get("role") else None,
        )

    def tailor_selected(self) -> None:
        def on_success(result: dict[str, str | None]) -> None:
            if result.get("pdf_path"):
                self.show_info(f"CV ready.\nPDF: {result['pdf_path']}")
            elif result.get("tex_path"):
                self.show_info(
                    f"CV TeX saved (install MiKTeX to compile PDF).\n{result['tex_path']}"
                )
            else:
                self.show_info("CV tailored successfully.")

        self.require_selected(
            lambda slug: self.start_worker(
                "Tailoring CV",
                lambda: self.service.tailor_role(slug),
                on_success=on_success,
            )
        )

    def approve_selected(self) -> None:
        self.require_selected(lambda slug: self.start_worker("Approving role", lambda: self.service.approve_role(slug)))

    def package_selected(self) -> None:
        self.require_selected(
            lambda slug: self.start_worker(
                "Packaging role",
                lambda: self.service.package_role(slug),
                lambda path: self.open_path(Path(path)),
            )
        )

    def mark_selected_applied(self) -> None:
        date = self.applied_date.date().toString("yyyy-MM-dd")
        self.require_selected(lambda slug: self.start_worker("Marking applied", lambda: self.service.mark_applied(slug, date)))

    def require_selected(self, callback: Callable[[str], None]) -> None:
        if not self.selected_slug:
            self.show_error("Select a role first.")
            return
        callback(self.selected_slug)

    def export_tracker(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export tracker",
            str(self.settings.tracker_path / "george_emil_job_tracker.xlsx"),
            "Excel files (*.xlsx)",
        )
        if path:
            self.start_worker("Exporting tracker", lambda: self.service.export_tracker(Path(path)))

    def import_tracker(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import tracker",
            str(self.settings.tracker_path),
            "Excel files (*.xlsx)",
        )
        if path:
            self.start_worker("Importing tracker", lambda: self.service.import_tracker(Path(path)))

    def open_path(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True) if not path.suffix else None
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def show_setup_dialog(self) -> None:
        dialog = SetupDialog(self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config_mod._settings = None
            self.settings = get_settings()
            self.service = DesktopService(self.settings)
            self.initialize_app()

    def show_error(self, message: str) -> None:
        QMessageBox.warning(self, "George Job Agent", message)


def dt_today_qdate():
    from PySide6.QtCore import QDate

    return QDate.currentDate()


def run_desktop(argv: list[str] | None = None) -> int:
    set_windows_app_id()
    app = QApplication.instance() or QApplication(argv or sys.argv)
    theme = load_theme("dark")
    if theme:
        app.setStyleSheet(theme)
    app.setWindowIcon(app_icon())
    window = MainWindow(get_settings())
    window.show()
    return app.exec()
