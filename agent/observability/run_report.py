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
    status: str = "ok"
    message: str = ""
    error: str | None = None


@dataclass
class RunReport:
    timestamp: str
    manual: bool
    dry_run: bool
    run_id: int | None = None
    status: str = "running"
    phase: str = ""
    progress: dict = field(default_factory=dict)
    error: str = ""
    scrapers: dict[str, ScraperStat] = field(default_factory=dict)
    raw_listings: int = 0
    fresh_listings: int = 0
    scored: int = 0
    tailored: int = 0
    letters: int = 0
    llm_calls: int = 0
    prefilter_rejected: int = 0
    detail_fetches: int = 0
    phase_timings: dict[str, float] = field(default_factory=dict)
    failures: list[dict[str, str]] = field(default_factory=list)

    def add_failure(self, slug: str, step: str, message: str) -> None:
        self.failures.append({"slug": slug, "step": step, "message": message})


def prune_old_run_reports(settings: Settings) -> int:
    days = settings.run_report_retention_days
    if days <= 0:
        return 0
    runs_dir = settings.runs_log_path
    if not runs_dir.is_dir():
        return 0
    cutoff = datetime.now(tz=pytz.timezone(settings.timezone)).timestamp() - days * 86400
    removed = 0
    for path in runs_dir.glob("*.json"):
        if path.name == "latest.json":
            continue
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def _report_to_dict(report: RunReport) -> dict:
    data = asdict(report)
    data["scrapers"] = {k: asdict(v) for k, v in report.scrapers.items()}
    return data


def write_run_report(report: RunReport, settings: Settings, *, final: bool = False) -> Path:
    settings.runs_log_path.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=pytz.timezone(settings.timezone)).strftime("%Y-%m-%d_%H-%M")
    path = settings.runs_log_path / f"{ts}.json"
    if report.run_id is not None:
        path = settings.runs_log_path / f"run_{report.run_id}.json"
    data = _report_to_dict(report)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    active = settings.runs_log_path / "latest.json"
    active.write_text(json.dumps(data, indent=2), encoding="utf-8")
    if final:
        archive = settings.runs_log_path / f"{ts}_final.json"
        archive.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_latest_run_report(settings: Settings) -> dict | None:
    runs_dir = settings.runs_log_path
    if not runs_dir.is_dir():
        return None
    active = runs_dir / "latest.json"
    if active.exists():
        return json.loads(active.read_text(encoding="utf-8"))
    files = sorted(runs_dir.glob("*.json"), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))


def load_active_run_report(settings: Settings) -> dict | None:
    """Return in-progress run report if status is running."""
    report = load_latest_run_report(settings)
    if report and report.get("status") == "running":
        return report
    return None
