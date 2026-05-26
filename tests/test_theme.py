"""Desktop theme path resolution."""
from __future__ import annotations

from agent.desktop.theme import theme_path


def test_theme_path_resolves_for_dev():
    path = theme_path("dark")
    assert path.name == "dark.qss"
    assert path.exists()
