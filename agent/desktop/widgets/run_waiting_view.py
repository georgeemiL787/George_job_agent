"""Double-pendulum waiting animation while an agent run is active."""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView

    _HAS_WEBENGINE = True
except ImportError:
    QWebEngineView = None  # type: ignore[misc, assignment]
    _HAS_WEBENGINE = False

_CANVAS_W = 680
_CANVAS_H = 480
_N = 12
_L1 = 115.0
_L2 = 90.0
_G = 9.8
_DT = 0.038
_TRAIL = 380
_OY = 170.0

_MESSAGES = [
    "12 pendulums — one grain of difference each",
    "watch them drift apart: the butterfly effect, live",
    "deterministic chaos: known rules, unknowable futures",
    "this is how the universe works behind the curtain",
    "some things just take time to unfold",
]


def _waiting_html_path() -> Path:
    bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return bundle / "assets" / "run_waiting.html"


@dataclass
class _Pendulum:
    t1: float
    t2: float
    w1: float = 0.0
    w2: float = 0.0
    trail: list[tuple[float, float, float, float]] = field(default_factory=list)
    hue: float = 0.0


class _NativeWaitingCanvas(QWidget):
    """Qt fallback matching run_waiting.html physics."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RunWaitingCanvas")
        self.setMinimumHeight(280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._frame = 0
        self._msg_index = 0
        self._msg_tick = 0
        self._pends = [
            _Pendulum(
                t1=math.pi * 0.88 + i * 0.00025,
                t2=math.pi * 0.52,
                hue=(i / _N) * 360.0,
            )
            for i in range(_N)
        ]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._fade = QColor(5, 5, 18, 23)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start(16)

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._frame += 1
        self._msg_tick += 1
        if self._msg_tick > 260:
            self._msg_tick = 0
            self._msg_index = (self._msg_index + 1) % len(_MESSAGES)
        self.update()

    def _step(self, p: _Pendulum, ox: float) -> tuple[float, float, float, float]:
        for _ in range(5):
            d = p.t1 - p.t2
            denom = 3.0 - math.cos(2 * d)
            a1 = (
                -3 * _G * math.sin(p.t1)
                - _G * math.sin(p.t1 - 2 * p.t2)
                - 2
                * math.sin(d)
                * (p.w2 * p.w2 * _L2 + p.w1 * p.w1 * _L1 * math.cos(d))
            ) / (_L1 * denom)
            a2 = (
                2
                * math.sin(d)
                * (2 * p.w1 * p.w1 * _L1 + 2 * _G * math.cos(p.t1) + p.w2 * p.w2 * _L2 * math.cos(d))
            ) / (_L2 * denom)
            p.w1 += a1 * _DT
            p.w2 += a2 * _DT
            p.t1 += p.w1 * _DT
            p.t2 += p.w2 * _DT
        x1 = ox + _L1 * math.sin(p.t1)
        y1 = _OY + _L1 * math.cos(p.t1)
        x2 = x1 + _L2 * math.sin(p.t2)
        y2 = y1 + _L2 * math.cos(p.t2)
        p.trail.append((x2, y2, x1, y1))
        if len(p.trail) > _TRAIL:
            p.trail.pop(0)
        return x1, y1, x2, y2

    def paintEvent(self, _event) -> None:  # noqa: N802
        w, h = self.width(), self.height()
        if w < 10 or h < 10:
            return
        sx, sy = w / _CANVAS_W, h / _CANVAS_H
        scale = min(sx, sy)
        ox = w / 2
        oy = _OY * sy

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(0, 0, w, h, self._fade)

        positions: list[tuple[float, float, float, float]] = []
        for p in self._pends:
            x1, y1, x2, y2 = self._step(p, _CANVAS_W / 2)
            positions.append((x1, y1, x2, y2))

        def tx(x: float) -> float:
            return (x - _CANVAS_W / 2) * scale + ox

        def ty(y: float) -> float:
            return y * sy

        for p in self._pends:
            if len(p.trail) < 2:
                continue
            pen = QPen(QColor.fromHslF(p.hue / 360.0, 0.82, 0.65, 0.7))
            pen.setWidthF(max(1.0, 1.4 * scale))
            painter.setPen(pen)
            path_pts = [(tx(t[0]), ty(t[1])) for t in p.trail]
            for i in range(1, len(path_pts)):
                painter.drawLine(path_pts[i - 1][0], path_pts[i - 1][1], path_pts[i][0], path_pts[i][1])
            lx, ly = path_pts[-1]
            painter.setBrush(QColor.fromHslF(p.hue / 360.0, 0.9, 0.78))
            painter.drawEllipse(lx - 3 * scale, ly - 3 * scale, 6 * scale, 6 * scale)

        arm_pen = QPen(QColor(255, 255, 255, 20))
        arm_pen.setWidthF(max(1.0, scale))
        painter.setPen(arm_pen)
        for i, p in enumerate(self._pends):
            if i >= len(positions):
                continue
            x1, y1, x2, y2 = positions[i]
            painter.drawLine(ox, oy, tx(x1), ty(y1))
            painter.drawLine(tx(x1), ty(y1), tx(x2), ty(y2))

        painter.setBrush(QColor(255, 255, 255, 140))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(ox - 4.5 * scale, oy - 4.5 * scale, 9 * scale, 9 * scale)

        mt = self._msg_tick
        raw = mt / 28 if mt < 28 else (260 - mt) / 28 if mt > 232 else 1.0
        painter.setPen(QColor(255, 255, 255, int(255 * raw * 0.38)))
        painter.drawText(0, h - int(18 * sy), w, 20, Qt.AlignmentFlag.AlignHCenter, _MESSAGES[self._msg_index])

        dot = (self._frame // 22) % 5
        for d in range(5):
            r = (3 if dot == d else 1.8) * scale
            alpha = 200 if dot == d else 36
            painter.setBrush(QColor(255, 255, 255, alpha))
            painter.drawEllipse(w / 2 - 24 * scale + d * 12 * scale - r, h - 36 * sy - r, 2 * r, 2 * r)
        painter.end()


class RunWaitingView(QWidget):
    """Container shown while a run is in progress."""

    def __init__(self, parent: QWidget | None = None, *, compact: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("RunWaitingPanel")
        self._compact = compact
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        height = 300 if compact else 480
        self.setMinimumHeight(height)

        self._view: QWidget
        html_path = _waiting_html_path()
        if _HAS_WEBENGINE and html_path.exists():
            assert QWebEngineView is not None
            web = QWebEngineView(self)
            web.setObjectName("RunWaitingWeb")
            web.setUrl(QUrl.fromLocalFile(str(html_path.resolve())))
            web.page().setBackgroundColor(QColor(5, 5, 15))
            self._view = web
        else:
            self._view = _NativeWaitingCanvas(self)

        layout.addWidget(self._view)
        self.setVisible(False)

    def set_running(self, running: bool) -> None:
        self.setVisible(running)
        if isinstance(self._view, _NativeWaitingCanvas):
            if running:
                self._view.start()
            else:
                self._view.stop()
