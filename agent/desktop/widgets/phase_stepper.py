"""Horizontal phase indicator for agent runs."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

PHASES = ("collect", "dedup", "score", "tailor")
PHASE_LABELS = {
    "collect": "Collect",
    "dedup": "Dedup",
    "score": "Score",
    "tailor": "Tailor",
}


class PhaseStepper(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PhaseStepper")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._labels: dict[str, QLabel] = {}
        for i, phase in enumerate(PHASES):
            label = QLabel(PHASE_LABELS[phase])
            label.setObjectName("PhasePill")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setProperty("phase", phase)
            label.setProperty("state", "pending")
            self._labels[phase] = label
            layout.addWidget(label)
            if i < len(PHASES) - 1:
                arrow = QLabel("›")
                arrow.setObjectName("PhaseArrow")
                layout.addWidget(arrow)

    def set_phase(self, current: str) -> None:
        current = (current or "").lower()
        if current == "complete":
            current = "tailor"
        seen_current = False
        for phase in PHASES:
            label = self._labels[phase]
            if phase == current:
                label.setProperty("state", "active")
                seen_current = True
            elif not seen_current:
                label.setProperty("state", "done")
            else:
                label.setProperty("state", "pending")
            label.style().unpolish(label)
            label.style().polish(label)
