"""Seed runtime workspace files from bundled private source data."""
from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger

from agent.config import Settings


def seed_workspace(settings: Settings) -> list[Path]:
    """Copy missing memory files into a persistent runtime workspace."""
    source_memory = settings.repo_root / "workspace" / "memory"
    target_memory = settings.memory_path
    if not source_memory.exists() or source_memory.resolve() == target_memory.resolve():
        return []

    target_memory.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for source in source_memory.glob("*"):
        if not source.is_file():
            continue
        target = target_memory / source.name
        if target.exists():
            continue
        shutil.copy2(source, target)
        copied.append(target)
        logger.info(f"Seeded workspace memory file: {target}")
    return copied
