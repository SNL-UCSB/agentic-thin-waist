"""Experiment lifecycle: canonical statuses, transitions, and PATCH helpers.

Orchestration drives Experiment API (and Telemetry-backed) experiment rows through
discrete phases. This module centralizes status strings and optional intermediate
PATCHes so ``ExecutionManager`` is not ad-hoc string soup.

Also contains the **orchestration run stage** recorder used by the workflow runner
to track coarse-grained progress across the entire run (preflight, iterations,
aggregation) — distinct from per-experiment row statuses.
"""

from __future__ import annotations

import os
import time
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.executor import DownstreamClients


# ---------------------------------------------------------------------------
# Orchestration run stages (coarse-grained, UI-facing)
# ---------------------------------------------------------------------------


class OrchestrationStage(str, Enum):
    """Stages for an orchestration run's lifecycle (not per-experiment)."""

    RECEIVED_INTENT = "RECEIVED_INTENT"
    GENERATED_EXPERIMENT_SPEC = "GENERATED_EXPERIMENT_SPEC"

    # Pre-flight
    VALIDATING_CTP_SERVICE = "VALIDATING_CTP_SERVICE"
    CHECKING_CTP_REPLAY_READINESS = "CHECKING_CTP_REPLAY_READINESS"
    PREPARING_CTP_REPLAY = "PREPARING_CTP_REPLAY"
    CTP_REPLAY_READY = "CTP_REPLAY_READY"

    CHECKING_APPLICATION_SUPPORT = "CHECKING_APPLICATION_SUPPORT"
    APPLICATION_SUPPORTED = "APPLICATION_SUPPORTED"
    APPLICATION_UNSUPPORTED = "APPLICATION_UNSUPPORTED"

    CHECKING_WORKER_AVAILABILITY = "CHECKING_WORKER_AVAILABILITY"
    WORKER_AVAILABLE = "WORKER_AVAILABLE"
    WORKER_UNAVAILABLE = "WORKER_UNAVAILABLE"

    CHECKING_CLUSTER = "CHECKING_CLUSTER"
    CLUSTER_READY = "CLUSTER_READY"

    # Per-iteration
    STARTING_ITERATION = "STARTING_ITERATION"
    REQUESTING_CTP_EXPORT = "REQUESTING_CTP_EXPORT"
    CTP_PCAP_READY = "CTP_PCAP_READY"
    CONFIGURING_BOTTLENECK = "CONFIGURING_BOTTLENECK"
    BOTTLENECK_CONFIGURED = "BOTTLENECK_CONFIGURED"
    STARTING_CAPTURE_AND_REPLAY = "STARTING_CAPTURE_AND_REPLAY"
    CAPTURE_IN_PROGRESS = "CAPTURE_IN_PROGRESS"
    RUNNING_NETGENT_WORKFLOW = "RUNNING_NETGENT_WORKFLOW"
    NETGENT_EXECUTION_SKIPPED = "NETGENT_EXECUTION_SKIPPED"
    NETGENT_WORKFLOW_COMPLETE = "NETGENT_WORKFLOW_COMPLETE"
    STOPPING_CAPTURE = "STOPPING_CAPTURE"
    CAPTURE_COMPLETE = "CAPTURE_COMPLETE"
    MEASURING_DYNAMIC_STATE = "MEASURING_DYNAMIC_STATE"
    SAVING_TO_TELEMETRY = "SAVING_TO_TELEMETRY"
    TELEMETRY_SAVE_COMPLETE = "TELEMETRY_SAVE_COMPLETE"
    TELEMETRY_SAVE_FAILED = "TELEMETRY_SAVE_FAILED"
    ITERATION_SUCCEEDED = "ITERATION_SUCCEEDED"
    ITERATION_FAILED = "ITERATION_FAILED"

    # Terminal
    EXPERIMENT_SUCCEEDED = "EXPERIMENT_SUCCEEDED"
    EXPERIMENT_FAILED = "EXPERIMENT_FAILED"


class OrchestrationRunRecorder:
    """Append-only stage log for an orchestration run.

    Each entry is ``{stage, timestamp, detail?, iteration?}`` and accumulates
    in memory during the run.  The workflow runner persists the list into the
    orchestration record via ``save_orchestration`` at checkpoints.
    """

    def __init__(self) -> None:
        self.stages: list[dict[str, Any]] = []

    def record(
        self,
        stage: OrchestrationStage | str,
        *,
        detail: str | None = None,
        iteration: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "stage": stage.value if isinstance(stage, OrchestrationStage) else stage,
            "timestamp": time.time(),
        }
        if detail is not None:
            entry["detail"] = detail
        if iteration is not None:
            entry["iteration"] = iteration
        if extra:
            entry.update(extra)
        self.stages.append(entry)

    @property
    def last_stage(self) -> str | None:
        return self.stages[-1]["stage"] if self.stages else None


class ExperimentLifecycleStatus(str, Enum):
    """Persisted experiment ``status`` field (Experiment API / Telemetry DB)."""

    PENDING = "pending"
    VALIDATING = "validating"
    RUNNING = "running"
    COLLECTING = "collecting"
    COMPLETE = "complete"
    FAILED = "failed"


# After create, POST typically yields PENDING; orchestrator may then PATCH forward.
_ALLOWED_FROM: dict[ExperimentLifecycleStatus, frozenset[ExperimentLifecycleStatus]] = {
    ExperimentLifecycleStatus.PENDING: frozenset(
        {
            ExperimentLifecycleStatus.VALIDATING,
            ExperimentLifecycleStatus.RUNNING,
            ExperimentLifecycleStatus.FAILED,
        }
    ),
    ExperimentLifecycleStatus.VALIDATING: frozenset(
        {
            ExperimentLifecycleStatus.RUNNING,
            ExperimentLifecycleStatus.FAILED,
        }
    ),
    ExperimentLifecycleStatus.RUNNING: frozenset(
        {
            ExperimentLifecycleStatus.COLLECTING,
            ExperimentLifecycleStatus.COMPLETE,
            ExperimentLifecycleStatus.FAILED,
        }
    ),
    ExperimentLifecycleStatus.COLLECTING: frozenset(
        {
            ExperimentLifecycleStatus.COMPLETE,
            ExperimentLifecycleStatus.FAILED,
        }
    ),
    ExperimentLifecycleStatus.COMPLETE: frozenset(),
    ExperimentLifecycleStatus.FAILED: frozenset(),
}


def is_terminal_status(status: str | None) -> bool:
    """Whether the experiment record should accept no further orchestration PATCHes."""
    if status is None:
        return False
    s = str(status).lower().strip()
    return s in {ExperimentLifecycleStatus.COMPLETE, ExperimentLifecycleStatus.FAILED}


def is_terminal_experiment_poll_status(status: str | None) -> bool:
    """Experiment API GET ``status`` while polling (may use synonyms)."""
    if status is None:
        return False
    s = str(status).lower().strip()
    return s in {"complete", "completed", "failed"}


def transition_allowed(
    current: ExperimentLifecycleStatus | str | None,
    target: ExperimentLifecycleStatus,
) -> bool:
    """Best-effort check: whether ``target`` is a normal next step from ``current``."""
    if current is None:
        return True
    if isinstance(current, ExperimentLifecycleStatus):
        cur = current
    else:
        cur_s = str(current).lower().strip()
        try:
            cur = ExperimentLifecycleStatus(cur_s)
        except ValueError:
            return not is_terminal_status(cur_s)
    if cur not in _ALLOWED_FROM:
        return not is_terminal_status(cur.value)
    return target in _ALLOWED_FROM[cur]


class ExperimentLifecycleSession:
    """Per-experiment lifecycle: phase trace + PATCH orchestration status."""

    def __init__(
        self,
        clients: DownstreamClients,
        experiment_id: str,
        *,
        enable_intermediate_patches: bool | None = None,
    ) -> None:
        self.clients = clients
        self.experiment_id = experiment_id
        self.phases: list[dict[str, Any]] = []
        if enable_intermediate_patches is None:
            enable_intermediate_patches = (
                os.getenv("ORCH_EXPERIMENT_LIFECYCLE_PATCHES", "1").lower() != "0"
            )
        self._intermediate = enable_intermediate_patches
        self._last_status: ExperimentLifecycleStatus | None = ExperimentLifecycleStatus.PENDING

    @property
    def last_status(self) -> ExperimentLifecycleStatus | None:
        return self._last_status

    def _trace(self, phase: str, **extra: Any) -> None:
        entry: dict[str, Any] = {"phase": phase, **extra}
        self.phases.append(entry)

    def _patch(
        self,
        status: ExperimentLifecycleStatus,
        *,
        spec: dict[str, Any] | None = None,
        optional: bool = True,
    ) -> None:
        payload: dict[str, Any] = {"status": status.value}
        if spec:
            payload["spec"] = spec
        try:
            self.clients.patch_experiment(self.experiment_id, payload)
            self._last_status = status
        except Exception:
            if not optional:
                raise

    def on_ctp_validation_start(self) -> None:
        """CTP validate runs before POST /experiments; optional PATCH if row already exists."""
        self._trace("ctp_validation_start")

    def on_ctp_validation_done(self, valid: bool) -> None:
        self._trace("ctp_validation_done", valid=valid)

    def on_registered_pending(self) -> None:
        """Experiment row created (API returns pending)."""
        self._trace("registered", experiment_status=ExperimentLifecycleStatus.PENDING.value)
        self._last_status = ExperimentLifecycleStatus.PENDING

    def mark_validating(self) -> None:
        """Optional: CTP path when you pre-create rows; no-op if intermediate PATCHes off."""
        self._trace("mark_validating")
        if not self._intermediate:
            return
        if transition_allowed(self._last_status, ExperimentLifecycleStatus.VALIDATING):
            self._patch(ExperimentLifecycleStatus.VALIDATING, optional=True)

    def mark_running(self) -> None:
        """Substrate pipeline dispatched (POST + shape + capture returned)."""
        self._trace("dispatch_done")
        if not self._intermediate:
            return
        if transition_allowed(self._last_status, ExperimentLifecycleStatus.RUNNING):
            self._patch(ExperimentLifecycleStatus.RUNNING, optional=True)

    def mark_collecting(self) -> None:
        """Awaiting capture/experiment completion and/or pulling telemetry."""
        self._trace("collecting")
        if not self._intermediate:
            return
        if transition_allowed(self._last_status, ExperimentLifecycleStatus.COLLECTING):
            self._patch(ExperimentLifecycleStatus.COLLECTING, optional=True)

    def mark_netgent_skipped(self, reason: str) -> None:
        """NetGent stage reached but NFA execution was intentionally skipped (phase gate)."""
        self._trace("netgent_execution_skipped", reason=reason[:2000])
        try:
            self.clients.patch_experiment(
                self.experiment_id,
                {
                    "spec": {
                        "netgent_execution": {
                            "skipped": True,
                            "reason": reason[:2000],
                        }
                    }
                },
            )
        except Exception:
            pass

    def mark_complete(self) -> None:
        self._trace("complete")
        self._patch(ExperimentLifecycleStatus.COMPLETE, optional=True)

    def mark_failed(self, error: str) -> None:
        self._trace("failed", error=error[:2000])
        self._patch(
            ExperimentLifecycleStatus.FAILED,
            spec={"error": error},
            optional=True,
        )
