"""Tests for extended run progress and events."""
import time

import pytest

from agent.run_control import RunOptions, RunStatus, get_coordinator


@pytest.fixture(autouse=True)
def reset_coordinator():
    get_coordinator().reset()
    yield
    get_coordinator().reset()


def test_events_ring_buffer():
    c = get_coordinator()
    c.try_start_run(RunOptions())
    for i in range(250):
        c.append_event(f"event-{i}")
    events = c.get_events()
    assert len(events) == 200
    assert events[0].message == "event-50"
    c.finish_run(RunStatus.COMPLETE)


def test_set_phase_records_timing():
    c = get_coordinator()
    c.try_start_run(RunOptions())
    c.set_phase("collect")
    time.sleep(0.05)
    c.set_phase("dedup")
    progress = c.get_progress()
    assert "collect" in progress.phase_timings
    assert progress.phase_timings["collect"] >= 0.04
    c.finish_run(RunStatus.COMPLETE)


def test_extended_progress_fields():
    c = get_coordinator()
    c.try_start_run(RunOptions())
    c.update_progress(sources_total=3, sources_done=1, score_target=10, scored=2)
    data = c.get_progress().to_dict()
    assert data["sources_total"] == 3
    assert data["score_target"] == 10
    c.finish_run(RunStatus.COMPLETE)
