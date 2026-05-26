"""Tests for run lock and cancellation."""
import pytest

from agent.run_control import RunCancelled, RunOptions, RunStatus, get_coordinator


@pytest.fixture(autouse=True)
def reset_coordinator():
    get_coordinator().reset()
    yield
    get_coordinator().reset()


def test_lock_rejects_second_start():
    c = get_coordinator()
    assert c.try_start_run(RunOptions()) is True
    assert c.try_start_run(RunOptions()) is False
    c.finish_run(RunStatus.COMPLETE)


def test_cancel_sets_flag_and_raises():
    c = get_coordinator()
    c.try_start_run(RunOptions())
    c.request_cancel()
    assert c.is_cancelled()
    with pytest.raises(RunCancelled):
        c.check_cancelled()
    c.finish_run(RunStatus.CANCELLED)
