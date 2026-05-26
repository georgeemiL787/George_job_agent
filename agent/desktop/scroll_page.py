"""Scrollable tab page wrapper for the desktop app."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLayout, QScrollArea, QSizePolicy, QWidget


def make_scroll_page(content: QWidget) -> QScrollArea:
    """Wrap tab content so it keeps natural height and scrolls when needed."""
    scroll = QScrollArea()
    scroll.setObjectName("TabScrollArea")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    lay = content.layout()
    if lay is not None:
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(12)
        lay.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)

    content.setSizePolicy(
        QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum),
    )
    scroll.setWidget(content)
    return scroll
