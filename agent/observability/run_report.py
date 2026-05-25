"""Structured JSON run reports under workspace/logs/runs/."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import pytz

from agent.config import Settings


@dataclass
class ScraperStat:
    count: int = 0
    error: str | None = None


@dataclass
class RunReport:
    timestamp: str
    manual: bool
    dry_run: bool
    scrapers: dict[str, ScraperStat] = field(default_factory=dict)
    raw_listings: int = 0
    fresh_listings: int = 0
    scored: int = 0
    tailored: int = 0
    letters: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)

    def add_failure(self, slug: str, step: str, message: str) -> None:
        self.failures.append({"slug": slug, "step": step, "message": message})


def write_run_report(report: RunReport, settings: Settings) -> Path:
    settings.runs_log_path.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=pytz.timezone(settings.timezone)).strftime("%Y-%m-%d_%H-%M")
    path = settings.runs_log_path / f"{ts}.json"
    data = asdict(report)
    data["scrapers"] = {k: asdict(v) for k, v in report.scrapers.items()}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_latest_run_report(settings: Settings) -> dict | None:
    runs_dir = settings.runs_log_path
    if not runs_dir.is_dir():
        return None
    files = sorted(runs_dir.glob("*.json"), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))
