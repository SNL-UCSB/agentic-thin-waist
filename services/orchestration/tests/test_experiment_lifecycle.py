"""Unit tests for experiment lifecycle helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.engine.experiment_lifecycle import (
    ExperimentLifecycleSession,
    ExperimentLifecycleStatus,
    is_terminal_experiment_poll_status,
    is_terminal_status,
    transition_allowed,
)
from app.engine.executor import DownstreamClients


def test_transition_pending_to_running_allowed():
    assert transition_allowed(
        ExperimentLifecycleStatus.PENDING, ExperimentLifecycleStatus.RUNNING
    )


def test_transition_complete_to_running_blocked():
    assert not transition_allowed(
        ExperimentLifecycleStatus.COMPLETE, ExperimentLifecycleStatus.RUNNING
    )


def test_is_terminal_experiment_poll_status():
    assert is_terminal_experiment_poll_status("completed")
    assert is_terminal_experiment_poll_status("complete")
    assert is_terminal_experiment_poll_status("failed")
    assert not is_terminal_experiment_poll_status("pending")


def test_is_terminal_status():
    assert is_terminal_status("complete")
    assert is_terminal_status("failed")
    assert not is_terminal_status("running")


def test_lifecycle_session_traces_phases_and_patches():
    clients = DownstreamClients()
    clients.patch_experiment = MagicMock(return_value={})
    s = ExperimentLifecycleSession(clients, "exp-1", enable_intermediate_patches=False)
    s.on_registered_pending()
    s.mark_running()
    s.mark_collecting()
    s.mark_complete()
    assert any(p.get("phase") == "dispatch_done" for p in s.phases)
    assert any(p.get("phase") == "complete" for p in s.phases)
    # Intermediate PATCHes off: only terminal complete
    assert clients.patch_experiment.call_count == 1
    clients.patch_experiment.assert_called_with("exp-1", {"status": "complete"})
