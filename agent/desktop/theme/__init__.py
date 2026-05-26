"""Desktop theme assets."""
from __future__ import annotations

import sys
from pathlib import Path


def theme_path(name: str = "dark") -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundle_root = Path(sys._MEIPASS)
        return bundle_root / "agent" / "desktop" / "theme" / f"{name}.qss"
    return Path(__file__).resolve().parent / f"{name}.qss"


def load_theme(name: str = "dark") -> str:
    path = theme_path(name)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""
