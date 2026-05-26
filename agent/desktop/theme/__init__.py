"""Desktop theme assets."""
from __future__ import annotations

import sys
from pathlib import Path


def theme_path(name: str = "dark") -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return bundle_root / "agent" / "desktop" / "theme" / f"{name}.qss"


def load_theme(name: str = "dark") -> str:
    path = theme_path(name)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""
