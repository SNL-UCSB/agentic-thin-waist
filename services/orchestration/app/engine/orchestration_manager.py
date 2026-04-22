"""Orchestration Manager: connectivity-centric experiment dispatch.

How it works
------------
1. Generate experiment specs from parsed intent (apps × capacities × latencies × CCs).
2. For each spec, sequentially (or in parallel):
   a. Provision an ephemeral substrate worker via ConnectivityManager.
   b. Query the global CTP service for a transformed background-traffic profile
      using the experiment's explicit ctp_capacity_range (Mbps).
   c. Tell the worker to fetch that CTP's download + upload PCAPs (POST /ctp/fetch).
   d. Compute the next whole-minute boundary, then fire three threads simultaneously:
      - POST /capture  — start tshark pcap recording on the worker
      - POST /replay   — start CTP background traffic replay (skipped if no CTP)
      - POST /run      — shape + congestion + execute application workflow
   e. After all threads complete: stop replay, wait/stop capture, record pcap_path.
   f. Destroy the worker.
3. Return aggregated results.

Environment variables
---------------------
CTP_SERVICE_GLOBAL               Global CTP service URL  (default: http://128.111.5.236:8001)
ORCH_CTP_SELECT_LIMIT            Max CTPs returned by /ctps/select  (default: 10)
ORCH_CTP_INTENSITY_DIRECTION     Optional: pass ``download`` or ``upload`` on /ctps/select query
ORCH_CTP_POINTER_MODE            ``export`` (default) = HTTP URL ``.../ctps/{id}/export`` ZIP fetch
                                 on the worker; ``local_path`` = use ``download_pcap`` from select
ORCH_WORKER_STARTUP_WAIT_SECONDS Seconds to wait for a new container to be ready  (default: 3)
CONNECTIVITY_BACKEND             Worker backend: local_docker / aws / gcp / remote  (default: local_docker)
SUBSTRATE_CAPTURE_IFACE          Interface to capture on (default: veth2)
ORCH_CAPTURE_DURATION_SECONDS    Max capture duration in seconds (default: min(spec.duration, 60))
ORCH_CAPTURE_TIMEOUT_SECONDS     How long to wait for capture to finish (default: 120)
ORCH_POLL_INTERVAL_SECONDS       Polling interval for capture status (default: 2)
SUBSTRATE_REPLAY_PNAT            PNAT rewrite rule for tcpreplay-edit --pnat
                                 (default: 169.231.0.0/16:172.16.1.1,128.111.0.0/16:172.16.1.1)
ORCH_PCAP_DOWNLOAD_TIMEOUT_SECONDS   Seconds for GET /capture/.../pcap -> POST /artifacts bridge (default: 600).
                                 Finished PCAPs are streamed to telemetry when
                                 TELEMETRY_SERVICE_URL is set and POST /results returns result_id.
CAPTURE_DOWNLOAD_TOKEN           Optional; if set on worker, orchestrator must send same value
                                 in X-Capture-Download-Token for PCAP download.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote

from app.engine.connectivity import ConnectivityManager, WorkerInfo
from app.engine.executor import DownstreamClients
from app.engine.experiment_generator import ExperimentGenerator
from app.engine.telemetry_capture_pull import stream_capture_pcap_to_telemetry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CTP selection
# ---------------------------------------------------------------------------


def _global_ctp_url() -> str:
    return os.getenv("CTP_SERVICE_GLOBAL", "http://128.111.5.236:8001").rstrip("/")


def _select_ctp(
    ctp_capacity_range: Any, experiment_id: str
) -> dict[str, Any] | None:
    """Query the global CTP service and return the first matching transformed CTP.

    Returns the raw CTP object (which contains download_pcap, upload_pcap, ctp_id, etc.)
    or None if nothing matched or the request failed.
    """
    default_range = [1.0, 10.0]
    if isinstance(ctp_capacity_range, dict):
        try:
            low = float(ctp_capacity_range["lower_value"])
            high = float(ctp_capacity_range["higher_value"])
            if high < low:
                low, high = high, low
            low = max(0.01, low)
            high = max(low + 0.01, high)
            intensity_range_mbps = [round(low, 4), round(high, 4)]
        except Exception:
            intensity_range_mbps = default_range
    else:
        intensity_range_mbps = default_range

    query: dict[str, Any] = {
        "is_transformed": True,
        "intensity_range_mbps": intensity_range_mbps,
        "intensity_direction": "download",
    }
    limit = int(os.getenv("ORCH_CTP_SELECT_LIMIT", "10"))

    ctp_url = _global_ctp_url()
    print(
        f"[CTP SELECT] Querying {ctp_url} for intensity range "
        f"{query['intensity_range_mbps']} Mbps (experiment={experiment_id})"
    )
    try:
        client = DownstreamClients(ctp_service_url=ctp_url)
        response = client.select_ctps(
            {"query": query, "limit": limit, "order_by": "intensity"}
        )
    except Exception as exc:
        logger.warning("CTP select failed for %s: %s", experiment_id, exc)
        print(f"[CTP SELECT] FAILED: {exc}")
        return None

    ctps = response.get("ctps") or []
    if not ctps:
        print(query)
        print(
            "No transformed CTPs found for %s (intensity range %s Mbps)",
            experiment_id,
            query["intensity_range_mbps"],
        )
        print(
            f"[CTP SELECT] No matching CTPs found — will run without background traffic"
        )
        return None

    selected = ctps[0]
    logger.info(
        "Selected CTP %s for %s (intensity range %s Mbps)",
        selected.get("ctp_id"),
        experiment_id,
        query["intensity_range_mbps"],
    )
    print(
        f"[CTP SELECT] Selected ctp_id={selected.get('ctp_id')} "
        f"intensity={selected.get('intensity', {}).get('mean_mbps')} Mbps"
    )
    return selected


def global_ctp_export_pointer(ctp_id: str) -> str:
    """Build the HTTP URL the substrate worker uses to download a CTP export ZIP.

    The worker's ``ctp_fetcher`` treats URLs whose path ends in ``/export`` as a
    single ZIP containing ``download/*.pcap`` and ``upload/*.pcap``.  This works
    when the worker cannot see the CTP server's filesystem (orchestrator and
    worker on different machines).
    """
    safe_id = quote(ctp_id, safe="")
    return f"{_global_ctp_url()}/ctps/{safe_id}/export"


def _ctp_pointer_for_worker(ctp: dict[str, Any]) -> str | None:
    """Resolve how the worker should obtain PCAPs: HTTP export ZIP or local path."""
    mode = os.getenv("ORCH_CTP_POINTER_MODE", "export").strip().lower()
    ctp_id = ctp.get("ctp_id")
    if mode == "local_path":
        path = ctp.get("download_pcap")
        return str(path) if path else None
    if not ctp_id:
        return None
    return global_ctp_export_pointer(str(ctp_id))


_DEFAULT_WORKFLOW: dict[str, Any] = {
    "specification": "default",
    "states": [
        {
            "checks": [],
            "actions": [{"type": "ping", "params": {"host": "8.8.8.8", "count": 3}}],
            "end_state": "done",
        }
    ],
}


# ---------------------------------------------------------------------------
# Synchronized-start helpers
# ---------------------------------------------------------------------------


def _next_minute_epoch() -> float:
    """Return the POSIX timestamp of the start of the next whole minute."""
    return math.ceil(time.time() / 60) * 60


def _wait_until(target_epoch: float) -> None:
    """Sleep until *target_epoch* (a POSIX timestamp)."""
    remaining = target_epoch - time.time()
    if remaining > 0:
        time.sleep(remaining)


def _build_capture_payload(exp_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Build the POST /capture request body for one experiment."""
    iface = os.getenv("SUBSTRATE_CAPTURE_IFACE", "veth2")
    duration = int(
        os.getenv(
            "ORCH_CAPTURE_DURATION_SECONDS",
            str(min(int(spec.get("duration_seconds", 60)), 60)),
        )
    )
    return {
        "interface": iface,
        "capture_filter": "",
        "filename": exp_id,
        "duration_seconds": duration,
    }


def _build_replay_payload(ctp_file: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Build the POST /replay request body for one experiment.

    The *pnat* rule rewrites internal CTP source IPs to the worker's internal
    address so replayed packets traverse the shaped link.  Configurable via
    SUBSTRATE_REPLAY_PNAT (default matches the test cluster subnets).
    """
    pnat = os.getenv(
        "SUBSTRATE_REPLAY_PNAT",
        "169.231.0.0/16:172.16.1.1,128.111.0.0/16:172.16.1.1",
    )
    duration = int(spec.get("duration_seconds", 60))
    return {
        "ctp_file": ctp_file,
        "pnat": pnat,
        "duration_seconds": duration,
    }


def _wait_and_stop_capture(
    worker_client: DownstreamClients,
    capture_id: str | None,
) -> dict[str, Any]:
    """Poll GET /capture/{id} until finished, then force-stop if timed out."""
    if not capture_id:
        return {"status": "missing_capture_id"}

    timeout = int(os.getenv("ORCH_CAPTURE_TIMEOUT_SECONDS", "120"))
    poll = float(os.getenv("ORCH_POLL_INTERVAL_SECONDS", "2"))
    deadline = time.time() + timeout
    last: dict[str, Any] = {}

    while time.time() < deadline:
        try:
            last = worker_client.get_capture(capture_id)
        except Exception:
            time.sleep(poll)
            continue
        if last.get("status") == "finished":
            return last
        time.sleep(poll)

    try:
        worker_client.stop_capture(capture_id)
        last = worker_client.get_capture(capture_id)
    except Exception:
        pass
    last.setdefault("status", "timeout")
    return last


# ---------------------------------------------------------------------------
# Running one experiment on a provisioned worker
# ---------------------------------------------------------------------------


def _run_experiment_on_worker(
    spec: dict[str, Any],
    worker: WorkerInfo,
    manager: ConnectivityManager,
) -> dict[str, Any]:
    """CTP select → worker fetch → synchronized capture + replay + workflow.

    Capture (tshark), background CTP replay (tcpreplay), and the application
    workflow (POST /run) are all fired simultaneously at the next whole-minute
    boundary so their packet timestamps are tightly aligned in the pcap file.
    """
    exp_id = spec.get("experiment_id", "unknown")
    result: dict[str, Any] = {
        "experiment_id": exp_id,
        "worker_id": worker.worker_id,
        "worker_endpoint": worker.endpoint,
        "backend": worker.backend,
    }

    print(f"\n{'─'*60}")
    print(f"[EXPERIMENT] Starting experiment={exp_id}")
    print(
        f"[EXPERIMENT]   capacity={spec.get('capacity_mbps')} Mbps  "
        f"latency={spec.get('latency_ms')} ms  "
        f"cc={spec.get('cc_algorithm')}"
    )
    print(f"[EXPERIMENT]   worker={worker.worker_id}  endpoint={worker.endpoint}")
    print(f"{'─'*60}")

    worker_client = DownstreamClients(substrate_worker_url=worker.endpoint)
    capacity = float(spec.get("capacity_mbps", 10))

    # Step 1: Pick a background-traffic profile from the global CTP service.
    print(f"\n[STEP 1/4] Selecting CTP background-traffic profile …")
    ctp = _select_ctp(spec.get("ctp_capacity_range"), exp_id)
    result["ctp_selected"] = ctp

    # Step 2: Tell the worker to fetch download + upload PCAPs (HTTP /export ZIP by default).
    print(f"\n[STEP 2/4] Fetching CTP PCAPs onto worker …")
    ctp_pointer = _ctp_pointer_for_worker(ctp) if ctp else None
    result["ctp_pointer"] = ctp_pointer
    replay_ctp_file: str | None = None
    if ctp_pointer:
        print(f"[STEP 2/4] CTP pointer → {ctp_pointer}")
        try:
            fetch_result = worker_client.fetch_ctp_substrate(
                {"ctp_pointer": ctp_pointer}
            )
            result["ctp_fetch"] = fetch_result
            replay_ctp_file = fetch_result.get("name")
            logger.info(
                "Worker %s: fetched CTP '%s'",
                worker.worker_id,
                fetch_result.get("name"),
            )
            print(
                f"[STEP 2/4] CTP fetch OK: name={fetch_result.get('name')}  "
                f"fetched={fetch_result.get('fetched')}"
            )
        except Exception as exc:
            logger.warning("Worker %s: CTP fetch failed: %s", worker.worker_id, exc)
            result["ctp_fetch"] = {"error": str(exc)}
            print(f"[STEP 2/4] CTP fetch FAILED (continuing without CTP): {exc}")
    else:
        reason = (
            "no matching CTP found"
            if not ctp
            else "could not build ctp_pointer (missing ctp_id for export, or download_pcap in local_path mode)"
        )
        result["ctp_fetch"] = {"skipped": True, "reason": reason}
        logger.warning(
            "Worker %s: no CTP pointer for %s at %.1f Mbps (%s)",
            worker.worker_id,
            exp_id,
            capacity,
            reason,
        )
        print(f"[STEP 2/4] Skipping CTP fetch: {reason}")

    # Step 3: Fire capture, CTP replay, and application workflow simultaneously
    #         at the next whole-minute boundary for tight temporal alignment.
    workflow = spec.get("workflow") or _DEFAULT_WORKFLOW
    raw_params = spec.get("workflow_parameters")
    workflow_parameters = (
        {k: str(v) for k, v in raw_params.items()} if raw_params else None
    )
    telemetry_url = os.getenv("TELEMETRY_SERVICE_URL", "http://telemetry-service:8004")
    capture_payload = _build_capture_payload(exp_id, spec)
    replay_payload = (
        _build_replay_payload(replay_ctp_file, spec) if replay_ctp_file else None
    )

    start_at = _next_minute_epoch()
    secs_until = max(0.0, start_at - time.time())
    print(
        f"\n[STEP 3/4] Synchronizing to next minute boundary in {secs_until:.1f}s — "
        f"then firing capture + {'replay + ' if replay_payload else ''}workflow simultaneously …"
    )
    print(
        f"[STEP 3/4]   workflow={workflow.get('specification')}  "
        f"download={capacity} Mbps  upload={spec.get('upload_mbps') or capacity} Mbps  "
        f"latency={spec.get('latency_ms', 0)} ms  qdisc={spec.get('aqm_policy', 'pfifo')}"
    )
    print(f"[STEP 3/4]   workflow_parameters={workflow_parameters}")
    print(
        f"[STEP 3/4]   capture iface={capture_payload['interface']}  "
        f"duration={capture_payload['duration_seconds']}s  "
        f"telemetry_url={telemetry_url}"
    )

    thread_results: dict[str, Any] = {}
    thread_errors: dict[str, str] = {}

    def _fire_capture() -> None:
        _wait_until(start_at)
        try:
            r = worker_client.capture_substrate(capture_payload)
            thread_results["capture"] = r
            print(
                f"[CAPTURE] Started — capture_id={r.get('capture_id')}  "
                f"pcap_path={r.get('pcap_path')}"
            )
        except Exception as exc:
            thread_errors["capture"] = str(exc)
            print(f"[CAPTURE] FAILED: {exc}")

    def _fire_replay() -> None:
        if replay_payload is None:
            thread_results["replay"] = {
                "skipped": True,
                "reason": "no CTP file available",
            }
            print("[REPLAY] Skipped — no CTP file available")
            return
        _wait_until(start_at)
        try:
            r = worker_client.replay_substrate(replay_payload)
            thread_results["replay"] = r
            print(f"[REPLAY] Started — replay_id={r.get('replay_id')}")
        except Exception as exc:
            thread_errors["replay"] = str(exc)
            print(f"[REPLAY] FAILED: {exc}")

    def _fire_workflow() -> None:
        _wait_until(start_at)
        try:
            r = manager.run_experiment(
                worker_id=worker.worker_id,
                workflow=workflow,
                download_mbps=capacity,
                upload_mbps=float(spec.get("upload_mbps") or capacity),
                latency_ms=float(spec.get("latency_ms", 0)),
                latency_location=spec.get("latency_location"),
                qdisc=spec.get("aqm_policy", "pfifo"),
                buffer_packets=int(spec.get("buffer_packets", 1000)),
                qdisc_params=spec.get("qdisc_params"),
                cca=spec.get("cc_algorithm", "cubic"),
                runtime=spec.get("runtime") or spec.get("application_type", "shell"),
                parameters=workflow_parameters,
                experiment_id=exp_id,
                application=workflow.get("specification", ""),
                telemetry_url=telemetry_url,
            )
            thread_results["run"] = r
            print(f"[WORKFLOW] Completed")
        except Exception as exc:
            thread_errors["run"] = str(exc)
            print(f"[WORKFLOW] FAILED: {exc}")

    threads = [
        threading.Thread(target=_fire_capture, name="fire-capture", daemon=True),
        threading.Thread(target=_fire_replay, name="fire-replay", daemon=True),
        threading.Thread(target=_fire_workflow, name="fire-workflow", daemon=True),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    result["capture"] = thread_results.get(
        "capture", {"error": thread_errors.get("capture", "thread_not_run")}
    )
    result["replay"] = thread_results.get(
        "replay", {"error": thread_errors.get("replay", "thread_not_run")}
    )

    # Step 4: Cleanup — stop replay + wait/stop capture, then report pcap path.
    print(f"\n[STEP 4/4] Cleanup — stopping replay, waiting for capture to finish …")

    replay_id: str | None = None
    replay_r = thread_results.get("replay")
    if isinstance(replay_r, dict):
        replay_id = replay_r.get("replay_id")
    if replay_id:
        try:
            worker_client.stop_replay(replay_id)
            print(f"[CLEANUP] Replay {replay_id} stopped")
        except Exception as exc:
            print(f"[CLEANUP] Stop replay failed (non-fatal): {exc}")

    capture_id: str | None = None
    capture_r = thread_results.get("capture")
    if isinstance(capture_r, dict):
        capture_id = capture_r.get("capture_id")
    capture_status = _wait_and_stop_capture(worker_client, capture_id)
    result["capture_status"] = capture_status
    result["pcap_path"] = capture_status.get("pcap_path", "")
    print(
        f"[CLEANUP] Capture: status={capture_status.get('status')}  "
        f"pcap_path={capture_status.get('pcap_path', 'N/A')}"
    )

    if telemetry_url.strip():
        run_tr = thread_results.get("run")
        telemetry_result_id: str | None = None
        if isinstance(run_tr, dict):
            tel = run_tr.get("telemetry")
            if isinstance(tel, dict) and tel.get("result_id"):
                telemetry_result_id = str(tel["result_id"])
        if (
            telemetry_result_id
            and capture_id
            and capture_status.get("status") == "finished"
        ):
            pcap_fn = os.path.basename(capture_status.get("pcap_path") or "") or (
                f"{exp_id}.pcap"
            )
            try:
                pull_out = stream_capture_pcap_to_telemetry(
                    worker_base_url=worker.endpoint,
                    capture_id=capture_id,
                    telemetry_base_url=telemetry_url.strip().rstrip("/"),
                    result_id=telemetry_result_id,
                    pcap_filename=pcap_fn,
                )
                result["telemetry_pcap_artifact"] = pull_out
                if pull_out.get("status") == "stored":
                    print(
                        f"[TELEMETRY] PCAP artifact stored for result_id={telemetry_result_id}"
                    )
                else:
                    print(
                        f"[TELEMETRY] PCAP artifact upload failed: {pull_out.get('detail', pull_out)}"
                    )
            except Exception as exc:
                logger.warning("PCAP pull to telemetry failed: %s", exc, exc_info=True)
                result["telemetry_pcap_artifact"] = {
                    "status": "error",
                    "detail": str(exc),
                }
                print(f"[TELEMETRY] PCAP pull exception: {exc}")
        elif not telemetry_result_id:
            logger.info(
                "Skipping PCAP pull to telemetry: no telemetry result_id (telemetry disabled or POST /results failed)"
            )

    # Keep experiment success criteria aligned with previous behavior:
    # workflow completion determines success/failure, while replay/capture/telemetry
    # issues are retained as warnings in the result payload.
    if "run" in thread_results:
        result["run"] = thread_results["run"]
        result["status"] = "success"
        logger.info("Worker %s: experiment %s succeeded", worker.worker_id, exp_id)
        print(f"[STEP 3/4] Experiment {exp_id} → SUCCESS")
    else:
        err = thread_errors.get("run", "workflow thread did not complete")
        result["run"] = {"error": err}
        result["status"] = "failed"
        result["error"] = err
        logger.error(
            "Worker %s: experiment %s failed: %s", worker.worker_id, exp_id, err
        )
        print(f"[STEP 3/4] Experiment {exp_id} → FAILED: {err}")

    warnings: list[str] = []
    replay_issue = (result.get("replay") or {}).get("error")
    if replay_issue:
        warnings.append(f"replay_issue: {replay_issue}")
    if capture_status.get("status") != "finished":
        warnings.append(
            f"capture_issue: status={capture_status.get('status', 'unknown')}"
        )
    telemetry_r = (result.get("run") or {}).get("telemetry")
    if isinstance(telemetry_r, dict) and telemetry_r.get("error"):
        warnings.append(f"telemetry_issue: {telemetry_r.get('error')}")
    artifact_r = result.get("telemetry_pcap_artifact") or {}
    if artifact_r and artifact_r.get("status") != "stored":
        warnings.append(
            f"pcap_artifact_issue: {artifact_r.get('detail', artifact_r.get('status'))}"
        )
    if warnings:
        result["warnings"] = warnings

    return result


# ---------------------------------------------------------------------------
# OrchestrationManager (public API)
# ---------------------------------------------------------------------------


class OrchestrationManager:
    """Runs experiments using the connectivity-backend model.

    For each experiment spec:
      - spins up an ephemeral worker (local Docker by default)
      - selects a matching CTP background-traffic profile
      - sends the CTP to the worker
      - runs the experiment on the worker
      - tears down the worker

    Args:
        connectivity_manager: ConnectivityManager to use. Defaults to one
            created from the CONNECTIVITY_BACKEND env var.
        max_parallel_workers: How many experiments to run at once (default 1).
    """

    def __init__(
        self,
        connectivity_manager: ConnectivityManager | None = None,
        max_parallel_workers: int = 1,
    ) -> None:
        self.manager = connectivity_manager or ConnectivityManager()
        self.max_parallel = max_parallel_workers

    def run(
        self,
        orch_id: str,
        intent: str,
        parsed_intent: dict[str, Any],
        workflow: dict[str, Any] | None = None,
        workflow_parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Full pipeline: generate specs → dispatch → aggregate results.

        Args:
            orch_id: Unique ID for this orchestration run.
            intent: Original natural language intent (kept for provenance).
            parsed_intent: Structured output from IntentParser.
            workflow: NetGent workflow dict (state-machine JSON) to execute
                      on each experiment. Falls back to a default ping workflow.

        Returns:
            Dict with orchestration_id, status, experiment_specs, results, summary.
        """
        # Generate the experiment specs from parsed intent
        print(f"\n{'='*60}")
        print(f"[ORCH] Generating experiment specs from parsed intent …")
        experiments = ExperimentGenerator().generate(parsed_intent)
        experiment_specs = [e.model_dump() for e in experiments]

        if workflow:
            for spec in experiment_specs:
                spec["workflow"] = workflow
                if workflow_parameters:
                    spec["workflow_parameters"] = workflow_parameters

        logger.info(
            "OrchestrationManager: %d experiment(s) for orch_id=%s via backend=%s",
            len(experiment_specs),
            orch_id,
            self.manager.backend_name,
        )
        print(
            f"[ORCH] Generated {len(experiment_specs)} experiment spec(s) "
            f"for orch_id={orch_id} via backend={self.manager.backend_name}"
        )
        for i, s in enumerate(experiment_specs):
            print(
                f"[ORCH]   spec[{i}] id={s.get('experiment_id')}  "
                f"capacity={s.get('capacity_mbps')} Mbps  "
                f"latency={s.get('latency_ms')} ms"
            )
        print(f"{'='*60}")

        if not experiment_specs:
            return {
                "orchestration_id": orch_id,
                "intent": intent,
                "status": "failed",
                "error": "No experiment specs generated from parsed intent.",
                "experiment_specs": [],
                "results": [],
                "summary": {"total_experiments": 0, "successful": 0, "failed": 0},
            }

        # Dispatch experiments (sequential or parallel)
        mode = (
            "parallel"
            if (self.max_parallel > 1 and len(experiment_specs) > 1)
            else "sequential"
        )
        print(
            f"\n[ORCH] Dispatching {len(experiment_specs)} experiment(s) in {mode} mode …"
        )
        if self.max_parallel > 1 and len(experiment_specs) > 1:
            results = self._run_parallel(experiment_specs, orch_id)
        else:
            results = self._run_sequential(experiment_specs, orch_id)

        # Summarise
        successful = sum(1 for r in results if r.get("status") == "success")
        total = len(results)
        status = (
            "complete"
            if successful == total
            else ("failed" if successful == 0 else "partial")
        )
        print(f"\n{'='*60}")
        print(
            f"[ORCH] All experiments done: {successful}/{total} succeeded  status={status}"
        )
        print(f"{'='*60}\n")

        return {
            "orchestration_id": orch_id,
            "intent": intent,
            "status": status,
            "experiment_specs": experiment_specs,
            "results": results,
            "summary": {
                "total_experiments": total,
                "successful": successful,
                "failed": total - successful,
            },
        }

    def _run_sequential(
        self, specs: list[dict[str, Any]], orch_id: str
    ) -> list[dict[str, Any]]:
        return [
            self._dispatch_one(spec, idx, orch_id) for idx, spec in enumerate(specs)
        ]

    def _run_parallel(
        self, specs: list[dict[str, Any]], orch_id: str
    ) -> list[dict[str, Any]]:
        with ThreadPoolExecutor(max_workers=self.max_parallel) as pool:
            futures = [
                pool.submit(self._dispatch_one, spec, idx, orch_id)
                for idx, spec in enumerate(specs)
            ]
            return [f.result() for f in futures]

    def _dispatch_one(
        self, spec: dict[str, Any], idx: int, orch_id: str
    ) -> dict[str, Any]:
        """Create worker → run experiment → destroy worker."""
        worker: WorkerInfo | None = None
        exp_id = spec.get("experiment_id", "unknown")
        try:
            print(
                f"\n[DISPATCH spec[{idx}]] Provisioning ephemeral worker for {exp_id} …"
            )
            worker = self.manager.create_worker({})
            logger.info(
                "Provisioned worker %s at %s for spec[%d] %s",
                worker.worker_id,
                worker.endpoint,
                idx,
                exp_id,
            )
            print(
                f"[DISPATCH spec[{idx}]] Worker provisioned: "
                f"worker_id={worker.worker_id}  endpoint={worker.endpoint}"
            )

            # Give the container a moment to be ready
            startup_wait = float(os.getenv("ORCH_WORKER_STARTUP_WAIT_SECONDS", "3"))
            if startup_wait > 0:
                print(
                    f"[DISPATCH spec[{idx}]] Waiting {startup_wait}s for container startup …"
                )
                time.sleep(startup_wait)

            result = _run_experiment_on_worker(spec, worker, self.manager)
            result["iteration"] = idx
            result["orch_id"] = orch_id
            return result

        except Exception as exc:
            logger.error(
                "Dispatch failed for spec[%d] %s: %s",
                idx,
                exp_id,
                exc,
            )
            print(f"[DISPATCH spec[{idx}]] FAILED for {exp_id}: {exc}")
            return {
                "experiment_id": exp_id,
                "iteration": idx,
                "orch_id": orch_id,
                "status": "failed",
                "error": str(exc),
            }
        finally:
            if worker is not None:
                try:
                    print(
                        f"[DISPATCH spec[{idx}]] Destroying worker {worker.worker_id} …"
                    )
                    self.manager.destroy_worker(worker.worker_id)
                    logger.info("Destroyed worker %s", worker.worker_id)
                    print(
                        f"[DISPATCH spec[{idx}]] Worker {worker.worker_id} destroyed OK"
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to destroy worker %s: %s", worker.worker_id, exc
                    )
                    print(
                        f"[DISPATCH spec[{idx}]] WARNING: destroy worker failed: {exc}"
                    )
