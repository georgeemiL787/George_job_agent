"""Compact live run progress for the dashboard."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QProgressBar, QVBoxLayout

from agent.desktop.run_estimator import RunEstimate
from agent.desktop.widgets.phase_stepper import PhaseStepper
from agent.desktop.widgets.run_waiting_view import RunWaitingView


class _MetricChip(QFrame):
    def __init__(self, title: str, parent: QFrame | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MetricChip")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        self.value = QLabel("0")
        self.value.setObjectName("MetricValue")
        self.title = QLabel(title)
        self.title.setObjectName("MetricTitle")
        layout.addWidget(self.value)
        layout.addWidget(self.title)

    def set_value(self, n: int) -> None:
        self.value.setText(str(n))


class RunLiveStrip(QFrame):
    def __init__(self, parent: QFrame | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RunLiveStrip")
        root = QVBoxLayout(self)
        root.setSpacing(10)

        self.status_label = QLabel("Idle")
        self.status_label.setObjectName("RunStatusLabel")
        self.eta_label = QLabel("")
        self.eta_label.setObjectName("RunEtaLabel")

        self.stepper = PhaseStepper(self)
        self.overall_bar = QProgressBar()
        self.overall_bar.setObjectName("RunOverallBar")
        self.overall_bar.setRange(0, 100)
        self.overall_bar.setValue(0)
        self.overall_bar.setTextVisible(False)
        self.overall_bar.setFixedHeight(8)

        chips = QGridLayout()
        chips.setSpacing(8)
        self.chip_collected = _MetricChip("Collected")
        self.chip_fresh = _MetricChip("Fresh")
        self.chip_scored = _MetricChip("Scored")
        self.chip_tailored = _MetricChip("Tailored")
        self.chip_failed = _MetricChip("Failed")
        for i, chip in enumerate(
            (
                self.chip_collected,
                self.chip_fresh,
                self.chip_scored,
                self.chip_tailored,
                self.chip_failed,
            )
        ):
            chips.addWidget(chip, 0, i)

        root.addWidget(self.status_label)
        self.waiting_panel = RunWaitingView(self, compact=True)
        root.addWidget(self.waiting_panel)
        root.addWidget(self.stepper)
        root.addWidget(self.overall_bar)
        root.addLayout(chips)
        root.addWidget(self.eta_label)
        self.set_idle()

    def set_idle(self) -> None:
        self.waiting_panel.set_running(False)
        self.status_label.setText("Idle — ready to run")
        self.eta_label.setText("")
        self.overall_bar.setValue(0)
        self.stepper.set_phase("")
        for chip in (
            self.chip_collected,
            self.chip_fresh,
            self.chip_scored,
            self.chip_tailored,
            self.chip_failed,
        ):
            chip.set_value(0)

    def update_state(
        self,
        *,
        active: bool,
        progress: dict[str, Any],
        estimate: RunEstimate | None,
        status_text: str = "",
    ) -> None:
        if not active and not progress.get("phase"):
            self.set_idle()
            return

        self.waiting_panel.set_running(True)
        phase = progress.get("phase", "")
        self.stepper.set_phase(phase)
        self.chip_collected.set_value(int(progress.get("collected", 0)))
        self.chip_fresh.set_value(int(progress.get("fresh", 0)))
        self.chip_scored.set_value(int(progress.get("scored", 0)))
        self.chip_tailored.set_value(int(progress.get("tailored", 0)))
        self.chip_failed.set_value(int(progress.get("failed", 0)))

        self.status_label.setText(status_text or f"Running — {phase or 'starting'}")
        if estimate:
            self.eta_label.setText(estimate.format_line())
        else:
            self.eta_label.setText("")

        self.overall_bar.setValue(self._overall_percent(progress))

    @staticmethod
    def _overall_percent(progress: dict[str, Any]) -> int:
        phase = (progress.get("phase") or "").lower()
        if phase == "complete":
            return 100
        phase_weights = {"collect": 25, "dedup": 35, "score": 70, "tailor": 95}
        base = 0
        for p, w in phase_weights.items():
            if p == phase:
                base = w - 15
                break
            base = w

        if phase == "collect" and progress.get("sources_total"):
            done = progress.get("sources_done", 0)
            total = progress["sources_total"]
            return min(35, base + int(15 * done / max(1, total)))
        if phase == "score" and progress.get("score_target"):
            done = progress.get("scored", 0)
            total = progress["score_target"]
            return min(85, base + int(20 * done / max(1, total)))
        if phase == "tailor" and progress.get("tailor_target"):
            done = progress.get("tailored", 0)
            total = progress["tailor_target"]
            return min(99, base + int(15 * done / max(1, total)))
        return base
