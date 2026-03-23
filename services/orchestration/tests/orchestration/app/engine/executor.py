"""Runtime execution and tool routing for orchestration (Steps 9-12)."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from app.engine.experiment_lifecycle import (
    ExperimentLifecycleSession,
    is_terminal_experiment_poll_status,
)


def _raise_for_status(resp: httpx.Response) -> None:
    """Raise with response body on failure (easier debugging than bare HTTPStatusError)."""
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        body = ""
        try:
            body = (e.response.text or "")[:4000]
        except Exception:
            pass
        raise RuntimeError(
            f"HTTP {e.response.status_code} {e.request.url!s}\n{body}"
        ) from e


class _ServiceHttp:
    """HTTP helpers scoped to one service base URL."""

    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = httpx.get(self.base_url + path, params=params, timeout=self.timeout)
        _raise_for_status(resp)
        return resp.json()

    def post(self, path: str, json_data: dict[str, Any]) -> dict[str, Any]:
        resp = httpx.post(self.base_url + path, json=json_data, timeout=self.timeout)
        _raise_for_status(resp)
        return resp.json()

    def delete(self, path: str) -> dict[str, Any]:
        resp = httpx.delete(self.base_url + path, timeout=self.timeout)
        _raise_for_status(resp)
        return resp.json()

    def patch(self, path: str, json_data: dict[str, Any]) -> dict[str, Any]:
        resp = httpx.patch(self.base_url + path, json=json_data, timeout=self.timeout)
        _raise_for_status(resp)
        return resp.json()

    def stream_to_file(
        self, path: str, dest: str, params: dict[str, Any] | None = None
    ) -> str:
        """Stream a GET response body to a local file. Returns *dest*."""
        with httpx.stream(
            "GET", self.base_url + path, params=params, timeout=self.timeout
        ) as resp:
            resp.raise_for_status()
            parent = os.path.dirname(dest)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)
        return dest


class ExperimentApis:
    """Experiment API (register, query, update experiments)."""

    def __init__(self, base_url: str, timeout: float) -> None:
        self._http = _ServiceHttp(base_url, timeout)

    def run_experiment(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.post("/experiments", payload)

    def patch_experiment(
        self, experiment_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self._http.patch(f"/experiments/{experiment_id}", payload)

    def get_experiment(self, experiment_id: str) -> dict[str, Any]:
        return self._http.get(f"/experiments/{experiment_id}")

    def list_experiments(self) -> list[dict[str, Any]]:
        return self._http.get("/experiments")


class CtpApis:
    """CTP service (list, select, validate, replay data)."""

    def __init__(self, base_url: str, timeout: float) -> None:
        self._http = _ServiceHttp(base_url, timeout)

    def list_ctps(self, limit: int = 50) -> dict[str, Any]:
        return self._http.get("/ctps", params={"limit": limit, "offset": 0})

    def select_ctps(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.post("/ctps/select", payload)

    def validate_ctp_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        return self._http.post("/ctps/validate", spec)

    def replay_data(
        self, ctp_id: str, replay_dir: str, users_root: str
    ) -> dict[str, Any]:
        return self._http.get(
            f"/ctps/{ctp_id}/replay-data",
            params={
                "replay_dir": replay_dir,
                "users_root": users_root,
                "direction": "download",
            },
        )

    def export_replay_pcap(
        self,
        ctp_id: str,
        dest_path: str,
        replay_dir: str,
        users_root: str,
        direction: str = "download",
    ) -> str:
        """Stream replay-ready PCAP from CTP service to *dest_path*. Returns the path."""
        return self._http.stream_to_file(
            f"/ctps/{ctp_id}/replay-data",
            dest_path,
            params={
                "replay_dir": replay_dir,
                "users_root": users_root,
                "direction": direction,
            },
        )


class SubstrateApis:
    """Substrate worker (shape, capture, replay)."""

    def __init__(self, base_url: str, timeout: float) -> None:
        self._http = _ServiceHttp(base_url, timeout)

    def shape_substrate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.post("/shape", payload)

    def capture_substrate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.post("/capture", payload)

    def get_capture(self, capture_id: str) -> dict[str, Any]:
        return self._http.get(f"/capture/{capture_id}")

    def stop_capture(self, capture_id: str) -> dict[str, Any]:
        return self._http.delete(f"/capture/{capture_id}")

    def replay_substrate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.post("/replay", payload)

    def get_health(self) -> dict[str, Any]:
        return self._http.get("/health")

    def get_state(self) -> dict[str, Any]:
        return self._http.get("/state")

    def get_replay(self, replay_id: str) -> dict[str, Any]:
        return self._http.get(f"/replay/{replay_id}")

    def stop_replay(self, replay_id: str) -> dict[str, Any]:
        return self._http.delete(f"/replay/{replay_id}")


class NetGentApis:
    """NetGent service (workflow generation, status, available applications)."""

    def __init__(self, base_url: str, timeout: float) -> None:
        self._http = _ServiceHttp(base_url, timeout)

    def get_available_workflows(self) -> dict[str, Any]:
        return self._http.get("/workflows/available")

    def generate_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.post("/workflows/generate", payload)

    def get_workflow_status(self, workflow_id: str) -> dict[str, Any]:
        return self._http.get(f"/workflows/status/{workflow_id}")

    def get_workflow_result(self, workflow_id: str) -> dict[str, Any]:
        return self._http.get(f"/workflows/result/{workflow_id}")


class TelemetryApis:
    """Telemetry service (results query)."""

    def __init__(self, base_url: str, timeout: float) -> None:
        self._http = _ServiceHttp(base_url, timeout)

    def query_results(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._http.get("/results", params=params)
        except Exception:
            # Degrade gracefully when telemetry service endpoint is absent.
            return {
                "results": [],
                "warning": "telemetry_service_unavailable_or_unsupported",
            }

    def post_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist an experiment result via ``POST /results``."""
        try:
            return self._http.post("/results", payload)
        except Exception:
            return {"error": "telemetry_service_unavailable", "stored": False}


class DownstreamClients:
    """HTTP clients for downstream services used by OpenClaw tools."""

    def __init__(
        self,
        experiment_api_url: str | None = None,
        ctp_service_url: str | None = None,
        substrate_worker_url: str | None = None,
        telemetry_service_url: str | None = None,
        netgent_service_url: str | None = None,
    ) -> None:
        self.experiment_api_url = (
            experiment_api_url
            or os.getenv("EXPERIMENT_API_URL", "http://localhost:8000")
        ).rstrip("/")
        self.ctp_service_url = (
            ctp_service_url or os.getenv("CTP_SERVICE_URL", "http://localhost:8001")
        ).rstrip("/")
        self.substrate_worker_url = (
            substrate_worker_url
            or os.getenv("SUBSTRATE_WORKER_URL", "http://localhost:8002")
        ).rstrip("/")
        self.telemetry_service_url = (
            telemetry_service_url
            or os.getenv("TELEMETRY_SERVICE_URL", "http://localhost:8004")
        ).rstrip("/")
        self.netgent_service_url = (
            netgent_service_url
            or os.getenv("NETGENT_SERVICE_URL", "http://localhost:8003")
        ).rstrip("/")
        self.timeout = float(os.getenv("ORCH_HTTP_TIMEOUT_SECONDS", "20"))

        self.experiment_apis = ExperimentApis(self.experiment_api_url, self.timeout)
        self.ctp_apis = CtpApis(self.ctp_service_url, self.timeout)
        self.substrate_apis = SubstrateApis(self.substrate_worker_url, self.timeout)
        self.telemetry_apis = TelemetryApis(self.telemetry_service_url, self.timeout)
        self.netgent_apis = NetGentApis(self.netgent_service_url, self.timeout)

    def health(self) -> dict[str, str]:
        checks = {
            "experiment_api": self.experiment_api_url + "/health",
            "ctp_service": self.ctp_service_url + "/health",
            "substrate_worker": self.substrate_worker_url + "/health",
            "telemetry_service": self.telemetry_service_url + "/health",
            "netgent_service": self.netgent_service_url + "/health",
        }
        out: dict[str, str] = {}
        for name, url in checks.items():
            try:
                httpx.get(url, timeout=self.timeout).raise_for_status()
                out[name] = "reachable"
            except Exception:
                out[name] = "unreachable"
        return out

    # --- Delegates (same surface as before; call through per-service API objects) ---

    def run_experiment(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.experiment_apis.run_experiment(payload)

    def patch_experiment(
        self, experiment_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self.experiment_apis.patch_experiment(experiment_id, payload)

    def get_experiment(self, experiment_id: str) -> dict[str, Any]:
        return self.experiment_apis.get_experiment(experiment_id)

    def list_experiments(self) -> list[dict[str, Any]]:
        return self.experiment_apis.list_experiments()

    def shape_substrate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.substrate_apis.shape_substrate(payload)

    def capture_substrate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.substrate_apis.capture_substrate(payload)

    def get_capture(self, capture_id: str) -> dict[str, Any]:
        return self.substrate_apis.get_capture(capture_id)

    def stop_capture(self, capture_id: str) -> dict[str, Any]:
        return self.substrate_apis.stop_capture(capture_id)

    def replay_substrate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.substrate_apis.replay_substrate(payload)

    def list_ctps(self, limit: int = 50) -> dict[str, Any]:
        return self.ctp_apis.list_ctps(limit=limit)

    def select_ctps(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.ctp_apis.select_ctps(payload)

    def validate_ctp_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        return self.ctp_apis.validate_ctp_spec(spec)

    def replay_data(
        self, ctp_id: str, replay_dir: str, users_root: str
    ) -> dict[str, Any]:
        return self.ctp_apis.replay_data(ctp_id, replay_dir, users_root)

    def query_results(self, params: dict[str, Any]) -> dict[str, Any]:
        return self.telemetry_apis.query_results(params)

    def post_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.telemetry_apis.post_result(payload)

    # --- NetGent delegates ---

    def get_available_workflows(self) -> dict[str, Any]:
        return self.netgent_apis.get_available_workflows()

    def generate_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.netgent_apis.generate_workflow(payload)

    def get_workflow_status(self, workflow_id: str) -> dict[str, Any]:
        return self.netgent_apis.get_workflow_status(workflow_id)

    def get_workflow_result(self, workflow_id: str) -> dict[str, Any]:
        return self.netgent_apis.get_workflow_result(workflow_id)

    # --- Substrate extended delegates ---

    def get_substrate_health(self) -> dict[str, Any]:
        return self.substrate_apis.get_health()

    def get_substrate_state(self) -> dict[str, Any]:
        return self.substrate_apis.get_state()

    def get_replay(self, replay_id: str) -> dict[str, Any]:
        return self.substrate_apis.get_replay(replay_id)

    def stop_replay(self, replay_id: str) -> dict[str, Any]:
        return self.substrate_apis.stop_replay(replay_id)

    # --- CTP extended delegates ---

    def export_replay_pcap(
        self,
        ctp_id: str,
        dest_path: str,
        replay_dir: str,
        users_root: str,
        direction: str = "download",
    ) -> str:
        return self.ctp_apis.export_replay_pcap(
            ctp_id, dest_path, replay_dir, users_root, direction
        )


class ToolRouter:
    """OpenClaw tool execution loop target."""

    def __init__(self, clients: DownstreamClients | None = None) -> None:
        self.clients = clients or DownstreamClients()

    def handle_tool_call(
        self, tool_name: str, tool_input: dict[str, Any]
    ) -> dict[str, Any]:
        if tool_name == "run_experiment":
            return self._run_experiment(tool_input)
        if tool_name == "query_results":
            return self.clients.query_results(tool_input)
        if tool_name == "validate_ctp":
            return self._validate_ctp(tool_input)
        if tool_name == "get_available_applications":
            return {
                "applications": [
                    "youtube",
                    "netflix",
                    "zoom",
                    "twitch",
                    "discord",
                    "google-meet",
                    "ndt",
                    "ping",
                    "iperf3",
                ]
            }
        if tool_name == "get_available_cc_algorithms":
            return {"cc_algorithms": ["cubic", "bbr", "reno", "htcp", "vegas", "bic"]}
        if tool_name == "list_experiments":
            return {"experiments": self.clients.list_experiments()}
        raise ValueError(f"Unknown tool: {tool_name}")

    def _validate_ctp(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.clients.validate_ctp_spec(tool_input)
        except Exception as exc:
            return {
                "valid": False,
                "ctp_cluster_id": tool_input.get("ctp_cluster"),
                "warnings": [f"ctp_validate_failed: {exc}"],
                "matches": [],
            }

    def _run_experiment(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Cross-service pipeline for one experiment iteration.

        Order (INTEGRATION_PLAN Step 12 + substrate integration):

        1. **Experiment API** — ``POST /experiments`` registers the spec as *pending*
           (persisted via Experiment API → Telemetry PostgreSQL when configured).
        2. **Substrate** — ``POST /shape`` applies bottleneck (capacity, latency, AQM).
        3. **Substrate** — ``POST /capture`` starts PCAP capture for this iteration.

        CTP validation is *not* done here; run it first via ``validate_ctp`` /
        ``ExecutionManager(..., enable_ctp_validation=True)`` so the chain is
        conceptually: CTP check → register experiment → shape → capture.
        """
        experiment_spec = dict(tool_input)
        exp_id = experiment_spec.get("experiment_id")
        if not exp_id:
            raise ValueError("experiment_id is required in experiment spec")

        capture_iface = os.getenv("SUBSTRATE_CAPTURE_IFACE", "veth2")
        capture_seconds = int(
            os.getenv(
                "ORCH_CAPTURE_DURATION_SECONDS",
                str(min(int(experiment_spec.get("duration_seconds", 60)), 30)),
            )
        )
        capture_payload = {
            "interface": capture_iface,
            "capture_filter": "",
            "filename": exp_id,
            "duration_seconds": capture_seconds,
        }

        shape_payload = {
            "upstream_iface": os.getenv("SUBSTRATE_UPSTREAM_IFACE", "veth4"),
            "downstream_iface": os.getenv("SUBSTRATE_DOWNSTREAM_IFACE", "veth2"),
            "download_mbps": float(experiment_spec["capacity_mbps"]),
            "upload_mbps": float(
                experiment_spec.get("upload_mbps", experiment_spec["capacity_mbps"])
            ),
            "latency_ms": float(experiment_spec["latency_ms"]),
            "latency_location": experiment_spec.get("latency_location", "both"),
            "qdisc": experiment_spec.get("aqm_policy", "fq_codel"),
            "buffer_packets": int(experiment_spec.get("buffer_packets", 1000)),
            "qdisc_params": experiment_spec.get(
                "qdisc_params", {"target": "5ms", "interval": "100ms"}
            ),
        }

        experiment_result = self.clients.run_experiment(experiment_spec)
        shape_result = self.clients.shape_substrate(shape_payload)
        capture_result = self.clients.capture_substrate(capture_payload)

        return {
            "status": "dispatched",
            "pipeline": ["experiment_api", "shape", "capture"],
            "experiment": experiment_result,
            "shape": shape_result,
            "capture": capture_result,
        }


class ExecutionManager:
    """Step 12 style execution manager with polling and aggregation.

    CTP validation is controlled by ``enable_ctp_validation`` and
    ``ORCH_ENABLE_CTP_VALIDATION``; the CTP Service ``POST /ctps/validate`` endpoint
    is used when validation runs.
    """

    def __init__(self, clients: DownstreamClients | None = None) -> None:
        self.clients = clients or DownstreamClients()
        self.capture_timeout_seconds = int(
            os.getenv("ORCH_CAPTURE_TIMEOUT_SECONDS", "120")
        )
        self.experiment_timeout_seconds = int(
            os.getenv("ORCH_EXPERIMENT_TIMEOUT_SECONDS", "60")
        )
        self.poll_interval_seconds = float(os.getenv("ORCH_POLL_INTERVAL_SECONDS", "2"))
        self.poll_experiment_status = (
            os.getenv("ORCH_POLL_EXPERIMENT_STATUS", "1").lower() != "0"
        )

    def run_experiments(
        self,
        experiment_specs: list[dict[str, Any]],
        *,
        enable_ctp_validation: bool = False,
    ) -> dict[str, Any]:
        """Dispatch experiments and aggregate outcomes.

        For each spec: optional CTP ``/ctps/validate``, then
        ``run_experiment`` tool (Experiment API → shape → capture), poll capture
        and experiment status, query Telemetry results, and PATCH experiment
        status to *complete* or *failed* (Experiment API → Telemetry DB).

        Returns:
            {
                "experiment_results": [...],
                "summary": {...}
            }
        """
        if not experiment_specs:
            return {
                "experiment_results": [],
                "summary": {
                    "total_experiments": 0,
                    "successful": 0,
                    "failed": 0,
                },
            }

        router = ToolRouter(clients=self.clients)
        results: list[dict[str, Any]] = []

        for spec in experiment_specs:
            exp_id = spec.get("experiment_id", "unknown")
            item: dict[str, Any] = {"experiment_id": exp_id}
            lifecycle = ExperimentLifecycleSession(self.clients, exp_id)
            try:
                if enable_ctp_validation:
                    lifecycle.on_ctp_validation_start()
                    ctp_validation = router.handle_tool_call(
                        "validate_ctp",
                        {
                            "capacity_mbps": spec.get("capacity_mbps"),
                            "latency_ms": spec.get("latency_ms"),
                            "ctp_cluster": spec.get("ctp_cluster"),
                        },
                    )
                    lifecycle.on_ctp_validation_done(bool(ctp_validation.get("valid")))
                    item["ctp_validation"] = ctp_validation

                dispatch = router.handle_tool_call("run_experiment", spec)
                item["dispatch"] = dispatch

                lifecycle.on_registered_pending()
                lifecycle.mark_running()

                capture_info = dispatch.get("capture", {})
                capture_id = capture_info.get("capture_id")
                lifecycle.mark_collecting()
                if capture_id:
                    item["capture_status"] = self._wait_for_capture(capture_id)
                else:
                    item["capture_status"] = {"status": "missing_capture_id"}

                experiment_record = dispatch.get("experiment", {})
                if self.poll_experiment_status and experiment_record.get(
                    "experiment_id"
                ):
                    item["experiment_status"] = self._wait_for_experiment(
                        experiment_record["experiment_id"]
                    )
                else:
                    item["experiment_status"] = {
                        "status": experiment_record.get("status", "unknown")
                    }

                telemetry = self.clients.query_results({"experiment_id": exp_id})
                item["telemetry"] = telemetry
                item["status"] = "success"
                lifecycle.mark_complete()
            except Exception as exc:
                # Partial-failure handling: keep going for remaining experiments.
                item["status"] = "failed"
                item["error"] = str(exc)
                if exp_id != "unknown":
                    lifecycle.mark_failed(str(exc))
            finally:
                item["lifecycle"] = {
                    "phases": lifecycle.phases,
                    "last_status": (
                        lifecycle.last_status.value if lifecycle.last_status else None
                    ),
                }
            results.append(item)

        successful = sum(1 for r in results if r.get("status") == "success")
        failed = len(results) - successful
        summary = {
            "total_experiments": len(results),
            "successful": successful,
            "failed": failed,
        }
        return {"experiment_results": results, "summary": summary}

    def _wait_for_capture(self, capture_id: str) -> dict[str, Any]:
        deadline = time.time() + self.capture_timeout_seconds
        last: dict[str, Any] = {}
        while time.time() < deadline:
            last = self.clients.get_capture(capture_id)
            if last.get("status") == "finished":
                return last
            time.sleep(self.poll_interval_seconds)
        return {
            "status": "timeout",
            "capture_id": capture_id,
            "last_observed": last,
        }

    def _wait_for_experiment(self, experiment_id: str) -> dict[str, Any]:
        deadline = time.time() + self.experiment_timeout_seconds
        last: dict[str, Any] = {}
        while time.time() < deadline:
            last = self.clients.get_experiment(experiment_id)
            if is_terminal_experiment_poll_status(last.get("status")):
                return last
            time.sleep(self.poll_interval_seconds)
        return {
            "status": "timeout",
            "experiment_id": experiment_id,
            "last_observed": last,
        }
