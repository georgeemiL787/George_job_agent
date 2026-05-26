"""Tests for run ETA estimation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.config import Settings
from agent.desktop.run_estimator import RunEstimator
from agent.run_control import RunProgress


def _settings(tmp_path: Path) -> Settings:
    ws = tmp_path / "workspace"
    runs = ws / "logs" / "runs"
    runs.mkdir(parents=True)
    return Settings(
        openrouter_api_key="test-key",
        workspace_dir=str(ws),
        database_url=f"sqlite:///{(ws / 'tracker' / 'job_agent.db').as_posix()}",
    )


def test_estimate_without_history_uses_fallback(tmp_path):
    settings = _settings(tmp_path)
    estimator = RunEstimator(settings)
    progress = RunProgress(
        phase="score",
        started_at=1000.0,
        score_target=10,
        scored=3,
    )
    import time

    progress.started_at = time.monotonic() - 60
    est = estimator.estimate(progress, mode="fast")
    assert est.elapsed_sec >= 50
    assert est.remaining_sec > 0
    assert "Score" in est.phase_detail
    assert est.confidence == "low"


def test_estimate_from_history(tmp_path):
    settings = _settings(tmp_path)
    runs = settings.runs_log_path
    for i in range(6):
        report = {
            "status": "complete",
            "phase_timings": {
                "collect": 120.0,
                "dedup": 20.0,
                "score": 60.0,
                "tailor": 90.0,
            },
            "scrapers": {"wuzzuf": {"count": 5}, "linkedin": {"count": 3}},
            "scored": 5,
            "tailored": 3,
        }
        (runs / f"run_{i}.json").write_text(json.dumps(report), encoding="utf-8")

    estimator = RunEstimator(settings)
    assert estimator._confidence == "high"

    progress = RunProgress(
        phase="collect",
        sources_total=2,
        sources_done=0,
    )
    est = estimator.estimate(progress, mode="fast")
    assert est.remaining_sec > 0
    assert "Collect" in est.phase_detail


def test_format_line(tmp_path):
    settings = _settings(tmp_path)
    estimator = RunEstimator(settings)
    progress = RunProgress(phase="tailor", tailor_target=5, tailored=2)
    import time

    progress.started_at = time.monotonic() - 120
    est = estimator.estimate(progress, mode="fast")
    line = est.format_line()
    assert "Elapsed" in line
    assert "left" in line or "Finishing" in line
