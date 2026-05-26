"""Shared run lock, cancellation, and live progress for CLI, scheduler, and desktop."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_MAX_EVENTS = 200


class RunStatus(str, Enum):
    RUNNING = "running"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETE = "complete"


class RunCancelled(Exception):
    """Raised when a cooperative cancel check finds the run was stopped."""


@dataclass
class RunOptions:
    mode: str = "fast"  # "fast" | "deep"
    sources: set[str] | None = None  # override enabled_sources when set
    dry_run: bool = False


@dataclass
class RunEvent:
    timestamp: float
    level: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
        }


@dataclass
class RunProgress:
    run_id: int | None = None
    phase: str = ""
    collected: int = 0
    fresh: int = 0
    scored: int = 0
    tailored: int = 0
    failed: int = 0
    started_at: float = 0.0
    phase_started_at: float = 0.0
    current_source: str = ""
    sources_done: int = 0
    sources_total: int = 0
    score_target: int = 0
    tailor_target: int = 0
    detail_fetches_done: int = 0
    detail_fetches_total: int = 0
    llm_calls: int = 0
    prefilter_rejected: int = 0
    phase_timings: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "phase": self.phase,
            "collected": self.collected,
            "fresh": self.fresh,
            "scored": self.scored,
            "tailored": self.tailored,
            "failed": self.failed,
            "started_at": self.started_at,
            "phase_started_at": self.phase_started_at,
            "current_source": self.current_source,
            "sources_done": self.sources_done,
            "sources_total": self.sources_total,
            "score_target": self.score_target,
            "tailor_target": self.tailor_target,
            "detail_fetches_done": self.detail_fetches_done,
            "detail_fetches_total": self.detail_fetches_total,
            "llm_calls": self.llm_calls,
            "prefilter_rejected": self.prefilter_rejected,
            "phase_timings": dict(self.phase_timings),
        }


def _copy_progress(p: RunProgress) -> RunProgress:
    return RunProgress(
        run_id=p.run_id,
        phase=p.phase,
        collected=p.collected,
        fresh=p.fresh,
        scored=p.scored,
        tailored=p.tailored,
        failed=p.failed,
        started_at=p.started_at,
        phase_started_at=p.phase_started_at,
        current_source=p.current_source,
        sources_done=p.sources_done,
        sources_total=p.sources_total,
        score_target=p.score_target,
        tailor_target=p.tailor_target,
        detail_fetches_done=p.detail_fetches_done,
        detail_fetches_total=p.detail_fetches_total,
        llm_calls=p.llm_calls,
        prefilter_rejected=p.prefilter_rejected,
        phase_timings=dict(p.phase_timings),
    )


class RunCoordinator:
    """Process-wide singleton for single-run enforcement and cancellation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._status: RunStatus | None = None
        self._progress = RunProgress()
        self._options: RunOptions | None = None
        self._events: list[RunEvent] = []

    def try_start_run(self, options: RunOptions | None = None) -> bool:
        if not self._run_lock.acquire(blocking=False):
            return False
        now = time.monotonic()
        with self._lock:
            self._cancel_event.clear()
            self._status = RunStatus.RUNNING
            self._progress = RunProgress(started_at=now, phase_started_at=now)
            self._options = options or RunOptions()
            self._events = []
        self.append_event("Run started", level="info")
        return True

    def finish_run(self, status: RunStatus) -> None:
        with self._lock:
            self._status = status
            self._progress.phase = ""
            self._progress.current_source = ""
        try:
            self._run_lock.release()
        except RuntimeError:
            pass

    def reset(self) -> None:
        """Release lock and clear state (for tests)."""
        self._cancel_event.clear()
        with self._lock:
            self._status = None
            self._progress = RunProgress()
            self._options = None
            self._events = []
        try:
            while self._run_lock.locked():
                self._run_lock.release()
        except RuntimeError:
            pass

    def request_cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            if self._status == RunStatus.RUNNING:
                self._status = RunStatus.CANCELLED
        self.append_event("Cancel requested", level="warning")

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def check_cancelled(self) -> None:
        if self._cancel_event.is_set():
            raise RunCancelled()

    def get_status(self) -> RunStatus | None:
        return self._status

    def is_active(self) -> bool:
        return self._status == RunStatus.RUNNING and self._run_lock.locked()

    def get_progress(self) -> RunProgress:
        with self._lock:
            return _copy_progress(self._progress)

    def get_options(self) -> RunOptions | None:
        return self._options

    def get_events(self) -> list[RunEvent]:
        with self._lock:
            return list(self._events)

    def append_event(self, message: str, *, level: str = "info") -> None:
        event = RunEvent(timestamp=time.monotonic(), level=level, message=message)
        with self._lock:
            self._events.append(event)
            if len(self._events) > _MAX_EVENTS:
                self._events = self._events[-_MAX_EVENTS:]

    def set_run_id(self, run_id: int) -> None:
        with self._lock:
            self._progress.run_id = run_id

    def set_phase(self, phase: str, *, message: str | None = None) -> None:
        now = time.monotonic()
        with self._lock:
            prev = self._progress.phase
            if prev and prev != phase:
                elapsed = now - self._progress.phase_started_at
                self._progress.phase_timings[prev] = (
                    self._progress.phase_timings.get(prev, 0.0) + elapsed
                )
            self._progress.phase = phase
            self._progress.phase_started_at = now
        if message:
            self.append_event(message, level="info")
        elif phase:
            self.append_event(f"Phase: {phase}", level="info")

    def update_progress(self, **kwargs: Any) -> None:
        with self._lock:
            for key, value in kwargs.items():
                if key == "phase":
                    continue
                if hasattr(self._progress, key):
                    setattr(self._progress, key, value)


_coordinator = RunCoordinator()


def get_coordinator() -> RunCoordinator:
    return _coordinator
