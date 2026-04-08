"""Orchestration workflow runner: preflight, per-iteration dispatch, aggregation.

Centralizes all orchestration policy so that ``process_intent`` (and tests)
call a single entrypoint rather than reimplementing sequencing inline.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.engine.connectivity import ConnectivityManager, WorkerInfo

logger = logging.getLogger(__name__)

from app.engine.ctp_resolver import resolve_ctp
from app.engine.executor import DownstreamClients
from app.engine.experiment_lifecycle import (
    ExperimentLifecycleSession,
    OrchestrationRunRecorder,
    OrchestrationStage,
    is_terminal_experiment_poll_status,
)
from app.engine.experiment_generator import ExperimentGenerator
from app.engine.orchestration_store import save_orchestration

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def _env_float(key: str, default: str) -> float:
    return float(os.getenv(key, default))


def _env_int(key: str, default: str) -> int:
    return int(os.getenv(key, default))


def _truthy_env(key: str, default: str = "0") -> bool:
    return os.getenv(key, default).strip().lower() in ("1", "true", "yes", "on")


def netgent_execution_enabled() -> bool:
    """When True, orchestration calls NetGent ``/workflows/generate`` and polls to completion.

    Default is **off** until NetGent is ready for real NFA runs; set ``ORCH_NETGENT_EXECUTION_ENABLED=1`` to enable.
    """
    return _truthy_env("ORCH_NETGENT_EXECUTION_ENABLED", "0")


def ctp_service_preflight_enabled() -> bool:
    """When True, preflight also calls CTP ``POST /ctps/validate`` for each ``ctp_cluster``."""
    return _truthy_env("ORCH_CTP_SERVICE_PREFLIGHT", "0")


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------


class PreflightResult:
    """Aggregated outcome of all pre-dispatch checks."""

    def __init__(self) -> None:
        self.ctp: dict[str, Any] = {}
        self.netgent: dict[str, Any] = {}
        self.worker: dict[str, Any] = {}
        self.passed = True
        self.failure_reason: str | None = None

    def fail(self, reason: str) -> None:
        self.passed = False
        self.failure_reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failure_reason": self.failure_reason,
            "ctp": self.ctp,
            "netgent": self.netgent,
            "worker": self.worker,
        }


def run_preflight(
    clients: DownstreamClients,
    experiment_specs: list[dict[str, Any]],
    recorder: OrchestrationRunRecorder,
) -> PreflightResult:
    result = PreflightResult()

    # 1. CTP replay readiness
    _check_ctp_readiness(clients, experiment_specs, recorder, result)
    if not result.passed:
        return result

    # 2. NetGent application support
    _check_application_support(clients, experiment_specs, recorder, result)
    if not result.passed:
        return result

    # 3. Substrate worker availability
    _check_worker_availability(clients, recorder, result)

    return result


def _check_ctp_readiness(
    clients: DownstreamClients,
    specs: list[dict[str, Any]],
    recorder: OrchestrationRunRecorder,
    result: PreflightResult,
) -> None:
    """Verify CTP PCAP corpus exists on disk for every cluster in the specs."""
    recorder.record(OrchestrationStage.VALIDATING_CTP_SERVICE)
    recorder.record(OrchestrationStage.CHECKING_CTP_REPLAY_READINESS)

    ctp_clusters = {s.get("ctp_cluster") for s in specs if s.get("ctp_cluster")}
    if not ctp_clusters:
        result.ctp = {"status": "no_ctp_cluster_requested", "ready": True}
        recorder.record(
            OrchestrationStage.CTP_REPLAY_READY, detail="no ctp_cluster in specs"
        )
        return

    for cluster_id in ctp_clusters:
        resolution = resolve_ctp(cluster_id)
        if resolution.ready:
            result.ctp = {
                "status": "ready",
                "cluster_id": resolution.cluster,
                "resolution": resolution.to_dict(),
            }
            recorder.record(
                OrchestrationStage.CTP_REPLAY_READY, detail=resolution.cluster
            )
        else:
            result.ctp = {
                "status": "not_ready",
                "cluster_id": resolution.cluster,
                "resolution": resolution.to_dict(),
            }
            result.fail(
                f"CTP cluster '{resolution.cluster}' has no PCAP files on disk "
                f"(looked in {resolution.to_dict().get('download_pcap', 'N/A')})"
            )
            recorder.record(
                OrchestrationStage.ITERATION_FAILED,
                detail=f"CTP '{resolution.cluster}' no PCAPs on disk",
            )
            return

    # Optional: CTP Service corpus validation (PostgreSQL / replay-export readiness)
    if ctp_service_preflight_enabled() and ctp_clusters:
        recorder.record(OrchestrationStage.VALIDATING_CTP_SERVICE)
        ctp_http: dict[str, Any] = {}
        for cluster_id in ctp_clusters:
            try:
                vr = clients.validate_ctp_spec({"ctp_cluster": cluster_id})
            except Exception as exc:
                logger.warning(
                    "CTP preflight validate failed for %s: %s", cluster_id, exc
                )
                result.ctp = {
                    **result.ctp,
                    "ctp_service_validate": {
                        "cluster_id": cluster_id,
                        "error": str(exc),
                    },
                }
                result.fail(f"CTP Service unreachable or validate failed: {exc}")
                recorder.record(
                    OrchestrationStage.ITERATION_FAILED,
                    detail=f"CTP service validate error: {exc}",
                )
                return
            ctp_http[cluster_id] = vr
            if not vr.get("valid"):
                result.ctp = {
                    **result.ctp,
                    "ctp_service_validate": ctp_http,
                }
                result.fail(
                    f"CTP Service reports cluster/id '{cluster_id}' is not in the corpus "
                    f"(replay export not available). Onboarding is out-of-band."
                )
                recorder.record(
                    OrchestrationStage.ITERATION_FAILED,
                    detail=f"CTP service: invalid {cluster_id}",
                )
                return
        result.ctp = {**result.ctp, "ctp_service_validate": ctp_http}


def _check_application_support(
    clients: DownstreamClients,
    specs: list[dict[str, Any]],
    recorder: OrchestrationRunRecorder,
    result: PreflightResult,
) -> None:
    recorder.record(OrchestrationStage.CHECKING_APPLICATION_SUPPORT)
    requested_apps = {s.get("application") for s in specs if s.get("application")}
    if not requested_apps:
        result.netgent = {"status": "no_applications_requested", "supported": True}
        recorder.record(OrchestrationStage.APPLICATION_SUPPORTED)
        return

    try:
        available = clients.get_available_workflows()
    except Exception as exc:
        result.netgent = {"status": "netgent_unreachable", "error": str(exc)}
        result.fail(f"NetGent service unreachable: {exc}")
        recorder.record(OrchestrationStage.APPLICATION_UNSUPPORTED, detail=str(exc))
        return

    supported_apps = {item["application"] for item in available.get("applications", [])}
    unsupported = requested_apps - supported_apps
    if unsupported:
        result.netgent = {
            "status": "unsupported_applications",
            "unsupported": sorted(unsupported),
            "available": sorted(supported_apps),
        }
        result.fail(
            f"Application(s) not supported by NetGent: {', '.join(sorted(unsupported))}. "
            "Application onboarding is out-of-band."
        )
        recorder.record(
            OrchestrationStage.APPLICATION_UNSUPPORTED,
            detail=f"unsupported: {sorted(unsupported)}",
        )
        return

    result.netgent = {"status": "all_supported", "applications": sorted(requested_apps)}
    recorder.record(OrchestrationStage.APPLICATION_SUPPORTED)


def _check_worker_availability(
    clients: DownstreamClients,
    recorder: OrchestrationRunRecorder,
    result: PreflightResult,
) -> None:
    recorder.record(OrchestrationStage.CHECKING_WORKER_AVAILABILITY)
    try:
        health = clients.get_substrate_health()
    except Exception as exc:
        result.worker = {"status": "unreachable", "error": str(exc)}
        result.fail(f"Substrate worker unreachable: {exc}")
        recorder.record(OrchestrationStage.WORKER_UNAVAILABLE, detail=str(exc))
        return

    if health.get("status") not in ("ok", "healthy"):
        result.worker = {"status": "degraded", "health": health}
        result.fail(f"Substrate worker degraded: {health.get('status')}")
        recorder.record(OrchestrationStage.WORKER_UNAVAILABLE, detail=str(health))
        return

    required_caps = ["tc_available", "tshark_available", "tcpreplay_available"]
    missing = [c for c in required_caps if not health.get(c)]
    if missing:
        result.worker = {
            "status": "missing_capabilities",
            "missing": missing,
            "health": health,
        }
        result.fail(f"Substrate worker missing capabilities: {missing}")
        recorder.record(
            OrchestrationStage.WORKER_UNAVAILABLE, detail=f"missing: {missing}"
        )
        return

    result.worker = {"status": "available", "health": health}
    recorder.record(OrchestrationStage.WORKER_AVAILABLE)


# ---------------------------------------------------------------------------
# Per-iteration dispatch
# ---------------------------------------------------------------------------


def _build_shape_payload(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "upstream_iface": os.getenv("SUBSTRATE_UPSTREAM_IFACE", "veth4"),
        "downstream_iface": os.getenv("SUBSTRATE_DOWNSTREAM_IFACE", "veth2"),
        "download_mbps": float(spec["capacity_mbps"]),
        "upload_mbps": float(spec.get("upload_mbps", spec["capacity_mbps"])),
        "latency_ms": float(spec["latency_ms"]),
        "latency_location": spec.get("latency_location", "both"),
        "qdisc": spec.get("aqm_policy", "fq_codel"),
        "buffer_packets": int(spec.get("buffer_packets", 1000)),
        "qdisc_params": spec.get(
            "qdisc_params", {"target": "5ms", "interval": "100ms"}
        ),
    }


def _build_capture_payload(spec: dict[str, Any]) -> dict[str, Any]:
    exp_id = spec["experiment_id"]
    capture_iface = os.getenv("SUBSTRATE_CAPTURE_IFACE", "veth2")
    capture_seconds = int(
        os.getenv(
            "ORCH_CAPTURE_DURATION_SECONDS",
            str(min(int(spec.get("duration_seconds", 60)), 30)),
        )
    )
    return {
        "interface": capture_iface,
        "capture_filter": "",
        "filename": exp_id,
        "duration_seconds": capture_seconds,
    }


def _build_replay_payload(
    spec: dict[str, Any], ctp_file: str | None = None
) -> dict[str, Any]:
    resolved_file = ctp_file or spec.get("ctp_cluster", "")
    return {
        "ctp_file": resolved_file,
        "interface": os.getenv("SUBSTRATE_REPLAY_IFACE", "veth1"),
        "rate": str(int(spec.get("capacity_mbps", 10))),
        "loop": False,
        "duration_seconds": int(spec.get("duration_seconds", 60)),
    }


def _intensity_range_for_spec(spec: dict[str, Any]) -> list[float]:
    capacity = float(spec.get("capacity_mbps", 0) or 0)
    ratio = _env_float("ORCH_CTP_INTENSITY_TOLERANCE_RATIO", "0.5")
    low = max(0.01, capacity * (1 - ratio))
    high = max(low, capacity * (1 + ratio))
    return [round(low, 4), round(high, 4)]


def _global_ctp_service_url(clients: DownstreamClients) -> str:
    return os.getenv("CTP_SERVICE_GLOBAL", clients.ctp_service_url).rstrip("/")


def _build_replay_data_pointer(clients: DownstreamClients, ctp_id: str) -> str:
    base = _global_ctp_service_url(clients)
    replay_dir = quote(
        os.getenv("ORCH_CTP_REPLAY_DIR", "/home/netreplica/output_test"), safe="/._-"
    )
    users_root = quote(
        os.getenv("ORCH_CTP_USERS_ROOT", "/home/netreplica/output_test/users"),
        safe="/._-",
    )
    return (
        f"{base}/ctps/{ctp_id}/replay-data"
        f"?replay_dir={replay_dir}&users_root={users_root}&direction={{direction}}"
    )


def _resolve_ctp_pointer_for_spec(
    clients: DownstreamClients, spec: dict[str, Any]
) -> tuple[str | None, dict[str, Any]]:
    query = {
        "is_transformed": True,
        "intensity_range_mbps": _intensity_range_for_spec(spec),
    }
    limit = _env_int("ORCH_CTP_SELECT_LIMIT", "10")
    selection = clients.select_ctps(
        {"query": query, "limit": limit, "order_by": "intensity"}
    )
    ctps = selection.get("ctps") or []
    if not ctps:
        return None, {"query": query, "selection": selection, "selected": None}
    selected = ctps[0]
    ctp_id = selected.get("ctp_id")
    if not ctp_id:
        return None, {"query": query, "selection": selection, "selected": selected}
    pointer = _build_replay_data_pointer(clients, ctp_id)
    return pointer, {
        "query": query,
        "selection": selection,
        "selected": selected,
        "ctp_id": ctp_id,
    }


def _build_telemetry_result_payload(
    spec: dict[str, Any],
    orch_id: str,
    shape_result: dict[str, Any],
    capture_status: dict[str, Any],
    netgent_result: dict[str, Any] | None,
    dynamic_state: dict[str, Any] | None,
) -> dict[str, Any]:
    live = netgent_execution_enabled()
    netgent_meta = {
        "execution_mode": "live" if live else "skipped",
        "skipped": not live,
        "env_flag": "ORCH_NETGENT_EXECUTION_ENABLED",
        "env_value": os.getenv("ORCH_NETGENT_EXECUTION_ENABLED", "0"),
    }
    if isinstance(netgent_result, dict):
        netgent_meta["result_status"] = netgent_result.get("status")

    return {
        "experiment_id": spec["experiment_id"],
        "status": "complete",
        "trial_number": spec.get("num_trials", 1),
        "bottleneck_state": {
            "configured_capacity": spec.get("capacity_mbps"),
            "configured_latency": spec.get("latency_ms"),
            "measured_throughput": (dynamic_state or {})
            .get("bottleneck_state", {})
            .get("download_mbps"),
            "measured_rtt": (dynamic_state or {})
            .get("bottleneck_state", {})
            .get("latency_ms"),
        },
        "contextual_tree": {
            "c_app": {"application": spec.get("application")},
            "c_bottleneck": shape_result.get("bottleneck_state", {}),
            "c_ctp": {"ctp_cluster": spec.get("ctp_cluster")},
            "orchestration_id": orch_id,
            "netgent_execution": netgent_meta,
        },
        "qoe_metrics": netgent_result if netgent_result else {},
        "pcap_path": capture_status.get("pcap_path", ""),
        "transport_state": {},
    }


def _is_duplicate_experiment_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "409" in msg and "experiment_id already exists" in msg


def _is_missing_ctp_replay_file_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "ctp file not found" in msg


def _with_unique_experiment_id(
    spec: dict[str, Any], orch_id: str, iteration_index: int
) -> dict[str, Any]:
    out = dict(spec)
    base = str(spec.get("experiment_id", "experiment")).strip() or "experiment"
    suffix = f"{orch_id[-6:]}-{iteration_index}-{int(time.time())}"
    out["experiment_id"] = f"{base}-{suffix}"[:160]
    return out


def run_single_iteration(
    clients: DownstreamClients,
    spec: dict[str, Any],
    orch_id: str,
    iteration_index: int,
    recorder: OrchestrationRunRecorder,
) -> dict[str, Any]:
    """Execute one experiment iteration through the full service pipeline.

    Returns a per-iteration result dict suitable for aggregation.
    """
    run_spec = dict(spec)
    exp_id = run_spec.get("experiment_id", "unknown")
    item: dict[str, Any] = {"experiment_id": exp_id, "iteration": iteration_index}
    lifecycle = ExperimentLifecycleSession(clients, exp_id)

    recorder.record(
        OrchestrationStage.STARTING_ITERATION, iteration=iteration_index, detail=exp_id
    )

    try:
        # 1. Resolve CTP PCAP pointer from CTP service (fallback to local corpus)
        lifecycle.on_ctp_validation_start()
        recorder.record(
            OrchestrationStage.REQUESTING_CTP_EXPORT, iteration=iteration_index
        )
        ctp_fetch_result: dict[str, Any] | None = None
        ctp_pointer, ctp_meta = _resolve_ctp_pointer_for_spec(clients, run_spec)
        item["ctp_pointer"] = ctp_meta

        ctp_resolution = None
        replay_ctp_file: str | None = None

        if ctp_pointer:
            ctp_fetch_result = clients.fetch_ctp_substrate({"ctp_pointer": ctp_pointer})
            replay_ctp_file = ctp_fetch_result.get("name")
            item["ctp_fetch"] = ctp_fetch_result
            lifecycle.on_ctp_validation_done(True)
            recorder.record(
                OrchestrationStage.CTP_PCAP_READY, iteration=iteration_index
            )
        else:
            ctp_resolution = resolve_ctp(spec.get("ctp_cluster"))
            item["ctp_resolution"] = ctp_resolution.to_dict()
            replay_ctp_file = ctp_resolution.replay_ctp_file
            lifecycle.on_ctp_validation_done(
                bool(getattr(ctp_resolution, "ready", False))
            )
            recorder.record(
                OrchestrationStage.CTP_PCAP_READY, iteration=iteration_index
            )

        # 2. Register experiment via Experiment API
        experiment_payload = dict(run_spec)
        experiment_payload["orchestration_id"] = orch_id
        try:
            experiment_result = clients.run_experiment(experiment_payload)
        except Exception as exc:
            if not _is_duplicate_experiment_error(exc):
                raise
            run_spec = _with_unique_experiment_id(run_spec, orch_id, iteration_index)
            exp_id = run_spec.get("experiment_id", exp_id)
            item["experiment_id"] = exp_id
            item["experiment_id_rewritten"] = True
            item["original_experiment_id"] = spec.get("experiment_id")
            recorder.record(
                OrchestrationStage.STARTING_ITERATION,
                iteration=iteration_index,
                detail=f"rewrote duplicate id -> {exp_id}",
            )
            lifecycle = ExperimentLifecycleSession(clients, exp_id)
            experiment_payload = dict(run_spec)
            experiment_payload["orchestration_id"] = orch_id
            experiment_result = clients.run_experiment(experiment_payload)
        item["experiment"] = experiment_result
        lifecycle.on_registered_pending()

        # 3. Shape bottleneck via substrate
        recorder.record(
            OrchestrationStage.CONFIGURING_BOTTLENECK, iteration=iteration_index
        )
        shape_payload = _build_shape_payload(run_spec)
        shape_result = clients.shape_substrate(shape_payload)
        item["shape"] = shape_result
        recorder.record(
            OrchestrationStage.BOTTLENECK_CONFIGURED, iteration=iteration_index
        )
        lifecycle.mark_running()

        # 4. Start capture + replay
        recorder.record(
            OrchestrationStage.STARTING_CAPTURE_AND_REPLAY, iteration=iteration_index
        )
        capture_payload = _build_capture_payload(run_spec)
        capture_result = clients.capture_substrate(capture_payload)
        item["capture"] = capture_result

        replay_payload = _build_replay_payload(run_spec, ctp_file=replay_ctp_file)
        try:
            replay_result = clients.replay_substrate(replay_payload)
        except Exception as exc:
            if not _is_missing_ctp_replay_file_error(exc):
                raise
            replay_result = {
                "status": "replay_skipped_missing_ctp_file",
                "error": str(exc)[:2000],
                "ctp_file": replay_payload.get("ctp_file"),
            }
            logger.warning(
                "Replay skipped due to missing CTP file: %s",
                replay_payload.get("ctp_file"),
            )
        item["replay"] = replay_result
        recorder.record(
            OrchestrationStage.CAPTURE_IN_PROGRESS, iteration=iteration_index
        )

        # 5. NetGent (NFA / QoE) — stage is always reached; execution optional via env
        skip_reason = (
            "NetGent NFA execution is disabled for this deployment phase "
            "(set ORCH_NETGENT_EXECUTION_ENABLED=1 when the service is ready)."
        )
        if netgent_execution_enabled():
            recorder.record(
                OrchestrationStage.RUNNING_NETGENT_WORKFLOW, iteration=iteration_index
            )
            netgent_result = _run_netgent_workflow(clients, run_spec)
            item["netgent"] = netgent_result
            recorder.record(
                OrchestrationStage.NETGENT_WORKFLOW_COMPLETE, iteration=iteration_index
            )
            logger.info(
                "NetGent workflow finished for experiment_id=%s iteration=%s status=%s",
                exp_id,
                iteration_index,
                (netgent_result or {}).get("status"),
            )
        else:
            netgent_result = {
                "status": "netgent_execution_skipped",
                "skipped": True,
                "reason": skip_reason,
                "application": run_spec.get("application"),
                "orchestration_flag": "ORCH_NETGENT_EXECUTION_ENABLED=0",
            }
            item["netgent"] = netgent_result
            logger.warning(
                "NetGent execution skipped (intentional; ORCH_NETGENT_EXECUTION_ENABLED=0) "
                "experiment_id=%s iteration=%s",
                exp_id,
                iteration_index,
            )
            recorder.record(
                OrchestrationStage.NETGENT_EXECUTION_SKIPPED,
                iteration=iteration_index,
                detail=skip_reason[:240],
            )
            lifecycle.mark_netgent_skipped(skip_reason)

        # 6. Stop capture / stop replay, measure state
        recorder.record(OrchestrationStage.STOPPING_CAPTURE, iteration=iteration_index)
        capture_id = capture_result.get("capture_id")
        replay_id = replay_result.get("replay_id")

        capture_status = _wait_and_stop_capture(clients, capture_id)
        item["capture_status"] = capture_status
        recorder.record(OrchestrationStage.CAPTURE_COMPLETE, iteration=iteration_index)

        if replay_id:
            try:
                clients.stop_replay(replay_id)
            except Exception:
                pass

        recorder.record(
            OrchestrationStage.MEASURING_DYNAMIC_STATE, iteration=iteration_index
        )
        try:
            dynamic_state = clients.get_substrate_state()
        except Exception:
            dynamic_state = {}
        item["dynamic_state"] = dynamic_state

        lifecycle.mark_collecting()

        # 7. Telemetry persistence
        recorder.record(
            OrchestrationStage.SAVING_TO_TELEMETRY, iteration=iteration_index
        )
        telemetry_payload = _build_telemetry_result_payload(
            run_spec,
            orch_id,
            shape_result,
            capture_status,
            netgent_result,
            dynamic_state,
        )
        telemetry_save = clients.post_result(telemetry_payload)
        item["telemetry"] = telemetry_save

        if telemetry_save.get("error"):
            recorder.record(
                OrchestrationStage.TELEMETRY_SAVE_FAILED,
                iteration=iteration_index,
                detail=str(telemetry_save.get("error")),
            )
            item["telemetry_saved"] = False
        else:
            recorder.record(
                OrchestrationStage.TELEMETRY_SAVE_COMPLETE, iteration=iteration_index
            )
            item["telemetry_saved"] = True

        item["status"] = "success"
        lifecycle.mark_complete()
        recorder.record(
            OrchestrationStage.ITERATION_SUCCEEDED, iteration=iteration_index
        )

    except Exception as exc:
        item["status"] = "failed"
        item["error"] = str(exc)
        lifecycle.mark_failed(str(exc))
        recorder.record(
            OrchestrationStage.ITERATION_FAILED,
            iteration=iteration_index,
            detail=str(exc)[:500],
        )

    item["lifecycle"] = {
        "phases": lifecycle.phases,
        "last_status": lifecycle.last_status.value if lifecycle.last_status else None,
    }
    item["netgent_execution_enabled"] = netgent_execution_enabled()
    return item


def _run_netgent_workflow(
    clients: DownstreamClients, spec: dict[str, Any]
) -> dict[str, Any] | None:
    """Submit a workflow to NetGent, poll until terminal, return result."""
    application = spec.get("application", "")
    try:
        gen_resp = clients.generate_workflow(
            {
                "query": f"Run {application} experiment",
                "parameters": {},
                "application": application,
            }
        )
    except Exception as exc:
        return {"status": "netgent_generate_failed", "error": str(exc)}

    workflow_id = gen_resp.get("workflow_id")
    if not workflow_id:
        return {"status": "no_workflow_id", "response": gen_resp}

    timeout = _env_float("ORCH_NETGENT_WORKFLOW_TIMEOUT_SECONDS", "120")
    poll_interval = _env_float("ORCH_NETGENT_POLL_SECONDS", "2")
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            status_resp = clients.get_workflow_status(workflow_id)
        except Exception:
            time.sleep(poll_interval)
            continue
        wf_status = status_resp.get("status", "")
        if wf_status in ("completed", "failed", "timeout"):
            break
        time.sleep(poll_interval)

    try:
        result = clients.get_workflow_result(workflow_id)
    except Exception as exc:
        result = {"status": "result_fetch_failed", "error": str(exc)}
    result["workflow_id"] = workflow_id
    return result


def _wait_and_stop_capture(
    clients: DownstreamClients, capture_id: str | None
) -> dict[str, Any]:
    if not capture_id:
        return {"status": "missing_capture_id"}

    timeout = _env_int("ORCH_CAPTURE_TIMEOUT_SECONDS", "120")
    poll_interval = _env_float("ORCH_POLL_INTERVAL_SECONDS", "2")
    deadline = time.time() + timeout
    last: dict[str, Any] = {}

    while time.time() < deadline:
        try:
            last = clients.get_capture(capture_id)
        except Exception:
            time.sleep(poll_interval)
            continue
        if last.get("status") == "finished":
            return last
        time.sleep(poll_interval)

    # Timed out — force stop
    try:
        clients.stop_capture(capture_id)
        last = clients.get_capture(capture_id)
    except Exception:
        pass
    last.setdefault("status", "timeout")
    return last


# ---------------------------------------------------------------------------
# Top-level orchestration entrypoint
# ---------------------------------------------------------------------------


def _run_iteration_on_worker(
    base_clients: DownstreamClients,
    spec: dict[str, Any],
    orch_id: str,
    idx: int,
    connectivity_manager: "ConnectivityManager",
) -> dict[str, Any]:
    """Create an ephemeral worker, run one iteration, then destroy the worker.

    Used by the parallel execution path in :func:`run_orchestration`.
    Each call has its own :class:`OrchestrationRunRecorder` so iteration stages
    don't race with the shared recorder.
    """
    from app.engine.connectivity import ConnectivityManager as _CM  # noqa: F401

    worker_info: WorkerInfo | None = None
    iter_recorder = OrchestrationRunRecorder()
    try:
        worker_info = connectivity_manager.create_worker({})
        iter_clients = DownstreamClients(substrate_worker_url=worker_info.endpoint)
        result = run_single_iteration(iter_clients, spec, orch_id, idx, iter_recorder)
        result["worker_id"] = worker_info.worker_id
        result["_iteration_stages"] = iter_recorder.stages
        return result
    finally:
        if worker_info is not None:
            try:
                connectivity_manager.destroy_worker(worker_info.worker_id)
            except Exception as exc:
                logger.warning(
                    "Failed to destroy worker %s: %s", worker_info.worker_id, exc
                )


def run_orchestration(
    orch_id: str,
    intent: str,
    parsed_intent: dict[str, Any],
    *,
    clients: DownstreamClients | None = None,
    connectivity_manager: "ConnectivityManager | None" = None,
    max_parallel_workers: int = 1,
) -> dict[str, Any]:
    """Full orchestration workflow: spec generation → preflight → iterations → aggregation.

    Returns a UI-friendly result dict that is also persisted to the orchestration store.
    """
    clients = clients or DownstreamClients()
    recorder = OrchestrationRunRecorder()
    recorder.record(OrchestrationStage.RECEIVED_INTENT, detail=intent[:200])

    # --- A. Intent → experiment specs ---
    generator = ExperimentGenerator()
    experiments = generator.generate(parsed_intent)
    experiment_specs = [e.model_dump() for e in experiments]
    recorder.record(
        OrchestrationStage.GENERATED_EXPERIMENT_SPEC,
        detail=f"{len(experiment_specs)} experiment(s)",
    )

    orch_record: dict[str, Any] = {
        "orchestration_id": orch_id,
        "intent": intent,
        "status": "executing",
        "experiments": experiment_specs,
        "lifecycle_stages": recorder.stages,
        "reasoning_steps": [],
        "results": [],
        "netgent_execution": {
            "execution_enabled": netgent_execution_enabled(),
            "env": "ORCH_NETGENT_EXECUTION_ENABLED",
            "note": (
                "When execution_enabled is false, the pipeline still reaches the NetGent stage "
                "but does not call /workflows/generate; re-enable with ORCH_NETGENT_EXECUTION_ENABLED=1."
            ),
        },
    }
    save_orchestration(orch_record)

    # --- B. Preflight ---
    preflight = run_preflight(clients, experiment_specs, recorder)
    orch_record["preflight"] = preflight.to_dict()
    orch_record["lifecycle_stages"] = recorder.stages
    save_orchestration(orch_record)

    if not preflight.passed:
        recorder.record(
            OrchestrationStage.EXPERIMENT_FAILED, detail=preflight.failure_reason
        )
        orch_record["status"] = "failed"
        orch_record["error"] = preflight.failure_reason
        orch_record["lifecycle_stages"] = recorder.stages
        save_orchestration(orch_record)
        return _build_final_result(
            orch_id, intent, experiment_specs, [], preflight, recorder, "failed"
        )

    # --- C. Cluster / topology (pass-through for now) ---
    recorder.record(OrchestrationStage.CHECKING_CLUSTER)
    recorder.record(OrchestrationStage.CLUSTER_READY, detail="substrate-only path")

    # --- D. Per-iteration dispatch ---
    iteration_results: list[dict[str, Any]] = []

    use_parallel = (
        connectivity_manager is not None
        and max_parallel_workers > 1
        and len(experiment_specs) > 1
    )

    if use_parallel:
        # Parallel path: each iteration gets its own ephemeral worker.
        # Iterations run concurrently; the shared recorder only sees top-level stages.
        with ThreadPoolExecutor(max_workers=max_parallel_workers) as pool:
            futures = [
                pool.submit(
                    _run_iteration_on_worker,
                    clients,
                    spec,
                    orch_id,
                    idx,
                    connectivity_manager,
                )
                for idx, spec in enumerate(experiment_specs)
            ]
            # Preserve original order
            iteration_results = [f.result() for f in futures]
        orch_record["results"] = iteration_results
        orch_record["lifecycle_stages"] = recorder.stages
        save_orchestration(orch_record)
    else:
        # Sequential path (default): optionally provision a per-iteration worker.
        for idx, spec in enumerate(experiment_specs):
            worker_info: "WorkerInfo | None" = None
            iter_clients = clients
            if connectivity_manager is not None:
                worker_info = connectivity_manager.create_worker({})
                iter_clients = DownstreamClients(
                    substrate_worker_url=worker_info.endpoint
                )
            try:
                iter_result = run_single_iteration(
                    iter_clients, spec, orch_id, idx, recorder
                )
                if worker_info is not None:
                    iter_result["worker_id"] = worker_info.worker_id
            finally:
                if worker_info is not None and connectivity_manager is not None:
                    try:
                        connectivity_manager.destroy_worker(worker_info.worker_id)
                    except Exception as exc:
                        logger.warning(
                            "Failed to destroy worker %s: %s",
                            worker_info.worker_id,
                            exc,
                        )
            iteration_results.append(iter_result)

            orch_record["results"] = iteration_results
            orch_record["lifecycle_stages"] = recorder.stages
            save_orchestration(orch_record)

    # --- E + F. Aggregate ---
    successful = sum(1 for r in iteration_results if r.get("status") == "success")
    final_status = (
        "complete"
        if successful == len(iteration_results)
        else ("failed" if successful == 0 else "partial")
    )

    if final_status in ("complete", "partial"):
        recorder.record(OrchestrationStage.EXPERIMENT_SUCCEEDED)
    else:
        recorder.record(OrchestrationStage.EXPERIMENT_FAILED)

    orch_record["status"] = final_status
    orch_record["lifecycle_stages"] = recorder.stages
    save_orchestration(orch_record)

    return _build_final_result(
        orch_id,
        intent,
        experiment_specs,
        iteration_results,
        preflight,
        recorder,
        final_status,
    )


def _build_final_result(
    orch_id: str,
    intent: str,
    specs: list[dict[str, Any]],
    iteration_results: list[dict[str, Any]],
    preflight: PreflightResult,
    recorder: OrchestrationRunRecorder,
    final_status: str,
) -> dict[str, Any]:
    successful = sum(1 for r in iteration_results if r.get("status") == "success")
    return {
        "orchestration_id": orch_id,
        "intent": intent,
        "status": final_status,
        "experiment_specs": specs,
        "preflight": preflight.to_dict(),
        "lifecycle_stages": recorder.stages,
        "iteration_results": iteration_results,
        "netgent_execution": {
            "execution_enabled": netgent_execution_enabled(),
            "env": "ORCH_NETGENT_EXECUTION_ENABLED",
        },
        "summary": {
            "total_experiments": len(specs),
            "iterations_run": len(iteration_results),
            "successful": successful,
            "failed": len(iteration_results) - successful,
        },
    }
