"""Full-screen live run monitor tab."""
from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from agent.desktop.run_estimator import RunEstimate
from agent.desktop.widgets.phase_stepper import PhaseStepper
from agent.desktop.widgets.run_waiting_view import RunWaitingView


class RunDashboard(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        self.status_label = QLabel("No active run")
        self.status_label.setObjectName("RunStatusLabel")
        self.eta_label = QLabel("")
        self.eta_label.setObjectName("RunEtaLabel")
        header.addWidget(self.status_label)
        header.addStretch()
        header.addWidget(self.eta_label)
        layout.addLayout(header)

        self.stepper = PhaseStepper(self)
        layout.addWidget(self.stepper)

        self.waiting_panel = RunWaitingView(self, compact=False)
        layout.addWidget(self.waiting_panel)

        bars = QGroupBox("Phase progress")
        bars.setObjectName("Card")
        bars_layout = QGridLayout(bars)
        self._phase_bars: dict[str, QProgressBar] = {}
        for row, (key, label) in enumerate(
            [
                ("collect", "Collect"),
                ("dedup", "Dedup"),
                ("score", "Score"),
                ("tailor", "Tailor"),
            ]
        ):
            bars_layout.addWidget(QLabel(label), row, 0)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setObjectName("PhaseProgressBar")
            self._phase_bars[key] = bar
            bars_layout.addWidget(bar, row, 1)
        layout.addWidget(bars)

        mid = QHBoxLayout()
        scrapers_box = QGroupBox("Sources")
        scrapers_box.setObjectName("Card")
        scrapers_layout = QVBoxLayout(scrapers_box)
        self.scrapers_text = QTextEdit()
        self.scrapers_text.setReadOnly(True)
        self.scrapers_text.setMinimumHeight(160)
        scrapers_layout.addWidget(self.scrapers_text)
        mid.addWidget(scrapers_box)

        activity_box = QGroupBox("Live activity")
        activity_box.setObjectName("Card")
        activity_layout = QVBoxLayout(activity_box)
        self.activity_list = QListWidget()
        self.activity_list.setObjectName("ActivityList")
        self.activity_list.setMinimumHeight(280)
        activity_layout.addWidget(self.activity_list)
        mid.addWidget(activity_box, stretch=2)
        layout.addLayout(mid)

        failures_box = QGroupBox("Failures this run")
        failures_box.setObjectName("Card")
        failures_layout = QVBoxLayout(failures_box)
        self.failures_text = QTextEdit()
        self.failures_text.setReadOnly(True)
        self.failures_text.setMinimumHeight(120)
        failures_layout.addWidget(self.failures_text)
        layout.addWidget(failures_box)

        self.show_json = QCheckBox("Show raw JSON report")
        layout.addWidget(self.show_json)
        self.json_report = QTextEdit()
        self.json_report.setReadOnly(True)
        self.json_report.setMinimumHeight(280)
        self.json_report.setVisible(False)
        self.show_json.toggled.connect(self.json_report.setVisible)
        layout.addWidget(self.json_report)

    def update_state(
        self,
        *,
        active: bool,
        progress: dict[str, Any],
        estimate: RunEstimate | None,
        events: list[dict[str, Any]],
        report: dict[str, Any] | None,
        status_text: str = "",
    ) -> None:
        phase = (progress.get("phase") or "").lower()
        self.waiting_panel.set_running(active)
        self.stepper.set_phase(phase)
        self.status_label.setText(status_text or ("Idle" if not active else f"Running — {phase}"))
        if estimate:
            self.eta_label.setText(estimate.format_line())
        else:
            self.eta_label.setText("")

        self._update_phase_bars(progress)
        self._update_scrapers(report)
        self._update_activity(events, progress.get("started_at", 0.0))
        self._update_failures(report)

        if report and self.show_json.isChecked():
            self.json_report.setPlainText(json.dumps(report, indent=2))
        elif not self.show_json.isChecked():
            self.json_report.clear()

    def _update_phase_bars(self, progress: dict[str, Any]) -> None:
        phase = (progress.get("phase") or "").lower()
        values = {
            "collect": self._ratio(
                progress.get("sources_done", 0),
                progress.get("sources_total", 0),
            ),
            "dedup": 100 if phase in ("dedup", "score", "tailor", "complete") else 0,
            "score": self._ratio(progress.get("scored", 0), progress.get("score_target", 0)),
            "tailor": self._ratio(progress.get("tailored", 0), progress.get("tailor_target", 0)),
        }
        order = list(self._phase_bars.keys())
        phase_idx = order.index(phase) if phase in order else -1
        for i, (key, bar) in enumerate(self._phase_bars.items()):
            pct = values.get(key, 0)
            if phase_idx < 0:
                bar.setValue(0)
            elif i < phase_idx:
                bar.setValue(100)
            elif i == phase_idx:
                bar.setValue(max(pct, 5 if pct == 0 and phase else pct))
            else:
                bar.setValue(0)

    @staticmethod
    def _ratio(done: int, total: int) -> int:
        if not total:
            return 0
        return min(100, int(100 * done / total))

    def _update_scrapers(self, report: dict[str, Any] | None) -> None:
        if not report:
            self.scrapers_text.setPlainText("No scraper data yet.")
            return
        lines = []
        for name, stat in (report.get("scrapers") or {}).items():
            status = stat.get("status", "ok")
            count = stat.get("count", 0)
            message = stat.get("message") or stat.get("error") or ""
            lines.append(f"{name}: {count} [{status}] {message}".strip())
        self.scrapers_text.setPlainText("\n".join(lines) if lines else "Collecting…")

    def _update_activity(
        self,
        events: list[dict[str, Any]],
        run_started: float,
    ) -> None:
        self.activity_list.clear()
        for event in events[-80:]:
            ts = event.get("timestamp", 0.0)
            rel = max(0.0, ts - run_started) if run_started else 0.0
            minutes, seconds = divmod(int(rel), 60)
            stamp = f"{minutes:02d}:{seconds:02d}"
            level = event.get("level", "info")
            item = QListWidgetItem(f"[{stamp}] {event.get('message', '')}")
            if level == "error":
                item.setForeground(Qt.GlobalColor.red)
            elif level == "warning":
                item.setForeground(Qt.GlobalColor.yellow)
            self.activity_list.addItem(item)
        if self.activity_list.count():
            self.activity_list.scrollToBottom()

    def _update_failures(self, report: dict[str, Any] | None) -> None:
        if not report:
            self.failures_text.clear()
            return
        failures = report.get("failures") or []
        if not failures:
            self.failures_text.setPlainText("None")
            return
        lines = [
            f"{f.get('step', '?')}: {f.get('slug', '?')} — {f.get('message', '')}"
            for f in failures[-20:]
        ]
        self.failures_text.setPlainText("\n".join(lines))
