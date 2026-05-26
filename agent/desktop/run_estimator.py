"""ETA estimation for active agent runs."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.config import Settings
from agent.run_control import RunProgress

PHASES = ("collect", "dedup", "score", "tailor")

DEFAULT_PHASE_SECONDS = {
    "collect": 90.0,
    "dedup": 30.0,
    "score": 12.0,
    "tailor": 45.0,
}


@dataclass
class RunEstimate:
    elapsed_sec: float
    remaining_sec: float
    remaining_label: str
    confidence: str  # low | medium | high
    phase_detail: str

    def format_line(self) -> str:
        elapsed = _fmt_duration(self.elapsed_sec)
        if self.remaining_sec <= 0:
            return f"Elapsed {elapsed} · Finishing… · {self.phase_detail}"
        remaining = _fmt_duration(self.remaining_sec)
        return f"Elapsed {elapsed} · ~{remaining} left · {self.phase_detail}"


def _fmt_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}:{secs:02d}"
    return f"{secs}s"


def _load_history(settings: Settings, limit: int = 20) -> list[dict[str, Any]]:
    runs_dir = settings.runs_log_path
    if not runs_dir.is_dir():
        return []
    files = sorted(
        (p for p in runs_dir.glob("*.json") if p.name not in ("latest.json",)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    reports: list[dict[str, Any]] = []
    for path in files:
        if len(reports) >= limit:
            break
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("status") not in ("complete", "cancelled", "failed"):
            continue
        reports.append(data)
    return reports


def _averages_from_history(reports: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, list[float]] = {p: [] for p in PHASES}
    per_source: list[float] = []
    per_score: list[float] = []
    per_tailor: list[float] = []

    for report in reports:
        timings = report.get("phase_timings") or report.get("progress", {}).get("phase_timings") or {}
        for phase in PHASES:
            val = timings.get(phase)
            if isinstance(val, (int, float)) and val > 0:
                totals[phase].append(float(val))

        scrapers = report.get("scrapers") or {}
        n_sources = max(1, len(scrapers))
        collect_t = timings.get("collect")
        if isinstance(collect_t, (int, float)) and collect_t > 0:
            per_source.append(float(collect_t) / n_sources)

        scored = report.get("scored") or report.get("progress", {}).get("scored") or 0
        score_t = timings.get("score")
        if scored and isinstance(score_t, (int, float)) and score_t > 0:
            per_score.append(float(score_t) / scored)

        tailored = report.get("tailored") or report.get("progress", {}).get("tailored") or 0
        tailor_t = timings.get("tailor")
        if tailored and isinstance(tailor_t, (int, float)) and tailor_t > 0:
            per_tailor.append(float(tailor_t) / tailored)

    def avg(values: list[float], fallback: float) -> float:
        return sum(values) / len(values) if values else fallback

    return {
        "collect": avg(totals["collect"], DEFAULT_PHASE_SECONDS["collect"]),
        "dedup": avg(totals["dedup"], DEFAULT_PHASE_SECONDS["dedup"]),
        "score": avg(per_score, DEFAULT_PHASE_SECONDS["score"]),
        "tailor": avg(per_tailor, DEFAULT_PHASE_SECONDS["tailor"]),
        "per_source": avg(per_source, DEFAULT_PHASE_SECONDS["collect"] / 3),
    }


class RunEstimator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        reports = _load_history(settings)
        self._averages = _averages_from_history(reports)
        self._confidence = "high" if len(reports) >= 5 else ("medium" if reports else "low")

    def estimate(
        self,
        progress: RunProgress | dict[str, Any],
        *,
        mode: str = "fast",
    ) -> RunEstimate:
        if isinstance(progress, dict):
            p = RunProgress(**{k: v for k, v in progress.items() if k in RunProgress.__dataclass_fields__})
        else:
            p = progress

        now = time.monotonic()
        started = p.started_at or now
        elapsed = max(0.0, now - started)
        remaining = self._remaining_seconds(p, mode=mode)
        phase_detail = self._phase_detail(p)
        label = _fmt_duration(remaining) if remaining > 0 else "0s"
        return RunEstimate(
            elapsed_sec=elapsed,
            remaining_sec=remaining,
            remaining_label=label,
            confidence=self._confidence,
            phase_detail=phase_detail,
        )

    def _remaining_seconds(self, p: RunProgress, *, mode: str) -> float:
        phase = (p.phase or "collect").lower()
        avgs = self._averages
        total = 0.0

        if phase == "collect":
            left_sources = max(0, p.sources_total - p.sources_done)
            total += left_sources * avgs["per_source"]
            if p.detail_fetches_total:
                done = p.detail_fetches_done
                total += max(0, p.detail_fetches_total - done) * 3.0
            total += avgs["dedup"] + self._score_remaining(p, mode, avgs) + self._tailor_remaining(p, avgs)
            return total

        if phase == "dedup":
            total += avgs["dedup"] * 0.5
            total += self._score_remaining(p, mode, avgs) + self._tailor_remaining(p, avgs)
            return total

        if phase == "score":
            total += self._score_remaining(p, mode, avgs) + self._tailor_remaining(p, avgs)
            return total

        if phase == "tailor":
            return self._tailor_remaining(p, avgs)

        return 0.0

    def _score_remaining(self, p: RunProgress, mode: str, avgs: dict[str, float]) -> float:
        cap = (
            self.settings.deep_run_max_scoring_candidates
            if mode == "deep"
            else self.settings.fast_run_max_scoring_candidates
        )
        target = p.score_target or cap
        left = max(0, target - p.scored)
        per_item = avgs["score"] + self.settings.scorer_delay_seconds
        return left * per_item

    def _tailor_remaining(self, p: RunProgress, avgs: dict[str, float]) -> float:
        target = p.tailor_target or max(p.scored, 1)
        left = max(0, target - p.tailored)
        return left * avgs["tailor"]

    def _phase_detail(self, p: RunProgress) -> str:
        phase = (p.phase or "starting").capitalize()
        if p.phase == "collect" and p.sources_total:
            return f"{phase} {p.sources_done}/{p.sources_total} sources"
        if p.phase == "score" and p.score_target:
            return f"{phase} {p.scored}/{p.score_target}"
        if p.phase == "tailor" and p.tailor_target:
            return f"{phase} {p.tailored}/{p.tailor_target}"
        if p.phase == "collect" and p.detail_fetches_total:
            return f"{phase} details {p.detail_fetches_done}/{p.detail_fetches_total}"
        return phase
