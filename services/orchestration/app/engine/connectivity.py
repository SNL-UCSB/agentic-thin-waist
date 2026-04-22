"""Connectivity Abstraction Layer — provisions substrate worker containers across backends.

Supported backends:
  - local_docker  (default) — launches containers via Docker HTTP API on the host socket
  - aws           — stub (not yet implemented)
  - gcp           — stub (not yet implemented)
  - remote        — stub (pre-existing endpoint, not yet implemented)

Quick start (local Docker, no config needed)::

    mgr = ConnectivityManager()
    info = mgr.create_worker({})
    # info.worker_id  → "worker-a1b2c3d4"
    # info.endpoint   → "http://localhost:49213"
    mgr.destroy_worker(info.worker_id)

Environment variables
---------------------
CONNECTIVITY_BACKEND       Backend name (default: ``local_docker``)
SUBSTRATE_WORKER_IMAGE     Docker image for substrate workers (default: ``substrate-worker``)
SUBSTRATE_DOCKER_NETWORK   Docker network to attach workers to (default: ``agentic-network``)
SUBSTRATE_WORKER_HOST      Host advertised in worker endpoint URLs (default: ``localhost``)
DOCKER_SOCKET              Path to Docker Unix socket (default: ``/var/run/docker.sock``)
"""

from __future__ import annotations

import logging
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_DOCKER_API_VERSION = "v1.41"
_SUBSTRATE_CONTAINER_PORT = 8002


@dataclass
class WorkerInfo:
    """Metadata for a provisioned substrate worker."""

    worker_id: str
    endpoint: str  # http://host:port
    backend: str  # "local_docker" | "aws" | "gcp" | "remote"
    container_id: str | None = None  # Docker container ID (local_docker only)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Backend interface
# ---------------------------------------------------------------------------


class ConnectivityBackend(ABC):
    """Abstract interface all backends must implement."""

    @abstractmethod
    def create_worker(self, config: dict[str, Any]) -> WorkerInfo:
        """Launch a substrate worker and return its :class:`WorkerInfo`."""

    @abstractmethod
    def destroy_worker(self, worker_id: str) -> None:
        """Stop and remove the worker identified by *worker_id*."""

    @abstractmethod
    def get_worker_info(self, worker_id: str) -> WorkerInfo:
        """Return current :class:`WorkerInfo` for *worker_id*."""


# ---------------------------------------------------------------------------
# LocalDocker backend  (fully implemented)
# ---------------------------------------------------------------------------


def _docker_http_client() -> httpx.Client:
    """httpx client routed through the Docker Unix socket."""
    sock = os.getenv("DOCKER_SOCKET", "/var/run/docker.sock")
    transport = httpx.HTTPTransport(uds=sock)
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=30)


class LocalDockerBackend(ConnectivityBackend):
    """Provisions substrate workers as Docker containers on the local daemon.

    Requires ``/var/run/docker.sock`` to be mounted in the orchestration
    container (add ``- /var/run/docker.sock:/var/run/docker.sock`` to its
    compose volumes).  No additional Python packages needed — uses the Docker
    HTTP API directly over the socket via httpx.
    """

    def __init__(self) -> None:
        self._workers: dict[str, WorkerInfo] = {}

    # --- Public API -------------------------------------------------------

    def create_worker(self, config: dict[str, Any]) -> WorkerInfo:
        """Launch a new substrate worker container and return its info.

        Supported *config* keys (all optional):
            image (str)          — Docker image name
            network (str)        — Docker network to attach to
            telemetry_url (str)  — TELEMETRY_SERVICE_URL passed to the container
            ctp_dir (str)        — host path for CTP PCAPs (mounted read-only)
            capture_dir (str)    — host path for capture output
        """
        image = config.get(
            "image", os.getenv("SUBSTRATE_WORKER_IMAGE", "substrate-worker")
        )
        network = config.get(
            "network", os.getenv("SUBSTRATE_DOCKER_NETWORK", "agentic-network")
        )
        telemetry_url = config.get(
            "telemetry_url",
            os.getenv("TELEMETRY_SERVICE_URL", "http://telemetry-service:8004"),
        )
        netgent_use_local = str(
            config.get("netgent_use_local") or os.getenv("NETGENT_USE_LOCAL")
        ).strip()
        netgent_namespace = str(
            config.get("netgent_namespace") or os.getenv("NETGENT_NAMESPACE")
        ).strip()
        ctp_dir = config.get("ctp_dir") or os.getenv("SUBSTRATE_CTP_DIR")
        capture_dir = config.get("capture_dir") or os.getenv("SUBSTRATE_CAPTURE_DIR")

        required_values = {
            "NETGENT_USE_LOCAL": netgent_use_local,
            "NETGENT_NAMESPACE": netgent_namespace,
            "SUBSTRATE_CTP_DIR": ctp_dir,
            "SUBSTRATE_CAPTURE_DIR": capture_dir,
        }
        missing = [name for name, value in required_values.items() if not value]
        if missing:
            raise ValueError(
                "Missing required worker provisioning configuration: "
                + ", ".join(missing)
            )

        worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        container_name = f"substrate-worker-{worker_id}"

        container_config = {
            "Image": image,
            "Env": [
                f"TELEMETRY_SERVICE_URL={telemetry_url}",
                f"CTP_DIR={ctp_dir}",
                f"CAPTURE_DIR={capture_dir}",
                f"NETGENT_USE_LOCAL={netgent_use_local}",
                f"NETGENT_NAMESPACE={netgent_namespace}",
            ],
            "ExposedPorts": {f"{_SUBSTRATE_CONTAINER_PORT}/tcp": {}},
            "Labels": {"substrate_worker_id": worker_id},
            "HostConfig": {
                "Privileged": True,
                "CapAdd": ["NET_ADMIN", "SYS_ADMIN"],
                # Port 0 → let Docker assign a free host port
                "PortBindings": {
                    f"{_SUBSTRATE_CONTAINER_PORT}/tcp": [{"HostIp": "", "HostPort": ""}]
                },
                "Binds": [
                    f"{ctp_dir}:{ctp_dir}",
                    f"{capture_dir}:{capture_dir}",
                    "/var/run/docker.sock:/var/run/docker.sock",
                ],
                "NetworkMode": network,
            },
        }

        with _docker_http_client() as docker:
            # Create container
            resp = docker.post(
                f"/{_DOCKER_API_VERSION}/containers/create",
                params={"name": container_name},
                json=container_config,
            )
            if resp.status_code not in (200, 201):
                raise RuntimeError(
                    f"docker create failed for {worker_id} "
                    f"(HTTP {resp.status_code}): {resp.text[:1000]}"
                )
            container_id: str = resp.json()["Id"]

            # Start container
            start_resp = docker.post(
                f"/{_DOCKER_API_VERSION}/containers/{container_id}/start"
            )
            if start_resp.status_code not in (204, 200):
                docker.delete(
                    f"/{_DOCKER_API_VERSION}/containers/{container_id}",
                    params={"force": "true"},
                )
                raise RuntimeError(
                    f"docker start failed for {worker_id} "
                    f"(HTTP {start_resp.status_code}): {start_resp.text[:1000]}"
                )

            # Inspect to get assigned host port
            inspect_resp = docker.get(
                f"/{_DOCKER_API_VERSION}/containers/{container_id}/json"
            )
            inspect_resp.raise_for_status()
            inspect = inspect_resp.json()

        # Prefer the container's IP on the Docker network for container-to-
        # container communication.  Fall back to host-mapped port.
        container_ip: str | None = None
        networks_info = inspect.get("NetworkSettings", {}).get("Networks", {})
        if network and network in networks_info:
            container_ip = networks_info[network].get("IPAddress")
        if not container_ip:
            for net_info in networks_info.values():
                ip = net_info.get("IPAddress")
                if ip:
                    container_ip = ip
                    break

        if container_ip:
            endpoint = f"http://{container_ip}:{_SUBSTRATE_CONTAINER_PORT}"
        else:
            port_bindings = (
                inspect.get("NetworkSettings", {})
                .get("Ports", {})
                .get(f"{_SUBSTRATE_CONTAINER_PORT}/tcp")
            )
            if not port_bindings:
                raise RuntimeError(
                    f"Could not read host port for container {container_id[:12]}. "
                    "Ensure the container started correctly."
                )
            host_port = port_bindings[0]["HostPort"]
            host = os.getenv("SUBSTRATE_WORKER_HOST", "localhost")
            endpoint = f"http://{host}:{host_port}"

        info = WorkerInfo(
            worker_id=worker_id,
            endpoint=endpoint,
            backend="local_docker",
            container_id=container_id,
            metadata={"container_name": container_name, "image": image},
        )
        self._workers[worker_id] = info
        logger.info(
            "Created worker %s → %s (container %s)",
            worker_id,
            endpoint,
            container_id[:12],
        )
        return info

    def destroy_worker(self, worker_id: str) -> None:
        """Stop and remove the container for *worker_id*."""
        info = self._get(worker_id)
        if info.container_id:
            with _docker_http_client() as docker:
                docker.delete(
                    f"/{_DOCKER_API_VERSION}/containers/{info.container_id}",
                    params={"force": "true"},
                )
            logger.info(
                "Destroyed worker %s (container %s)", worker_id, info.container_id[:12]
            )
        del self._workers[worker_id]

    def get_worker_info(self, worker_id: str) -> WorkerInfo:
        return self._get(worker_id)

    # --- Internals --------------------------------------------------------

    def _get(self, worker_id: str) -> WorkerInfo:
        info = self._workers.get(worker_id)
        if info is None:
            raise KeyError(f"Unknown worker_id: {worker_id!r}")
        return info


# ---------------------------------------------------------------------------
# Stub backends
# ---------------------------------------------------------------------------


class AWSBackend(ConnectivityBackend):
    """AWS ECS/Fargate substrate worker provisioning — not yet implemented."""

    def create_worker(self, config: dict[str, Any]) -> WorkerInfo:
        raise NotImplementedError(
            "AWS backend is not implemented. "
            "Set CONNECTIVITY_BACKEND=local_docker or provide an AWS ECS task definition."
        )

    def destroy_worker(self, worker_id: str) -> None:
        raise NotImplementedError("AWS backend is not implemented.")

    def get_worker_info(self, worker_id: str) -> WorkerInfo:
        raise NotImplementedError("AWS backend is not implemented.")


class GCPBackend(ConnectivityBackend):
    """GCP Cloud Run substrate worker provisioning — not yet implemented."""

    def create_worker(self, config: dict[str, Any]) -> WorkerInfo:
        raise NotImplementedError(
            "GCP backend is not implemented. "
            "Configure a Cloud Run service and set CONNECTIVITY_BACKEND=gcp."
        )

    def destroy_worker(self, worker_id: str) -> None:
        raise NotImplementedError("GCP backend is not implemented.")

    def get_worker_info(self, worker_id: str) -> WorkerInfo:
        raise NotImplementedError("GCP backend is not implemented.")


class StaticWorkerBackend(ConnectivityBackend):
    """Reuses the existing substrate-worker container from Docker Compose.

    Instead of spinning up ephemeral containers, all experiments run against
    the already-running ``substrate-worker`` service.  ``destroy_worker`` is a
    no-op so the Compose service stays alive between experiments.

    Environment variables:
        SUBSTRATE_WORKER_URL  — endpoint of the static worker
                                (default: ``http://substrate-worker:8002``)
    """

    def __init__(self) -> None:
        self._workers: dict[str, WorkerInfo] = {}
        self._endpoint = os.getenv(
            "SUBSTRATE_WORKER_URL", "http://substrate-worker:8002"
        )

    def create_worker(self, config: dict[str, Any]) -> WorkerInfo:
        endpoint = config.get("endpoint", self._endpoint)
        worker_id = f"worker-static-{uuid.uuid4().hex[:8]}"
        info = WorkerInfo(
            worker_id=worker_id,
            endpoint=endpoint,
            backend="static",
            container_id=None,
            metadata={"reuse": True},
        )
        self._workers[worker_id] = info
        logger.info(
            "Static worker %s → %s (reusing existing container)", worker_id, endpoint
        )
        return info

    def destroy_worker(self, worker_id: str) -> None:
        info = self._workers.pop(worker_id, None)
        if info:
            logger.info("Static worker %s released (container kept alive)", worker_id)

    def get_worker_info(self, worker_id: str) -> WorkerInfo:
        info = self._workers.get(worker_id)
        if info is None:
            raise KeyError(f"Unknown worker_id: {worker_id!r}")
        return info


class RemoteServerBackend(ConnectivityBackend):
    """Remote server substrate worker (pre-existing endpoint) — not yet implemented.

    Expected *config* key:
        endpoint (str): full base URL, e.g. ``http://192.168.1.50:8002``
    """

    def create_worker(self, config: dict[str, Any]) -> WorkerInfo:
        raise NotImplementedError(
            "RemoteServer backend is not implemented. "
            "Set CONNECTIVITY_BACKEND=remote and supply an endpoint URL in config."
        )

    def destroy_worker(self, worker_id: str) -> None:
        raise NotImplementedError("RemoteServer backend is not implemented.")

    def get_worker_info(self, worker_id: str) -> WorkerInfo:
        raise NotImplementedError("RemoteServer backend is not implemented.")


# ---------------------------------------------------------------------------
# ConnectivityManager — unified entry point
# ---------------------------------------------------------------------------

_BACKENDS: dict[str, type[ConnectivityBackend]] = {
    "local_docker": LocalDockerBackend,
    "static": StaticWorkerBackend,
    "aws": AWSBackend,
    "gcp": GCPBackend,
    "remote": RemoteServerBackend,
}


class ConnectivityManager:
    """Manages the lifecycle of substrate workers across pluggable backends.

    The backend is selected via the ``CONNECTIVITY_BACKEND`` environment variable
    (default: ``local_docker``).  All workers created through this manager are
    tracked internally.

    Methods
    -------
    create_worker(config) → WorkerInfo
    destroy_worker(worker_id)
    get_worker_info(worker_id) → WorkerInfo
    """

    def __init__(self, backend: str | None = None) -> None:
        backend_name = backend or os.getenv("CONNECTIVITY_BACKEND", "local_docker")
        backend_cls = _BACKENDS.get(backend_name)
        if backend_cls is None:
            raise ValueError(
                f"Unknown connectivity backend: {backend_name!r}. "
                f"Choose from: {sorted(_BACKENDS)}"
            )
        self._backend: ConnectivityBackend = backend_cls()
        self._backend_name = backend_name

    # --- Public API -------------------------------------------------------

    def create_worker(self, config: dict[str, Any] | None = None) -> WorkerInfo:
        """Provision a new substrate worker.

        Args:
            config: Backend-specific overrides.  For ``local_docker`` the
                    supported keys are ``image``, ``network``, ``telemetry_url``,
                    ``ctp_dir``, and ``capture_dir``.

        Returns:
            :class:`WorkerInfo` containing ``worker_id`` and ``endpoint``.
        """
        return self._backend.create_worker(config or {})

    def destroy_worker(self, worker_id: str) -> None:
        """Stop and remove the worker identified by *worker_id*."""
        self._backend.destroy_worker(worker_id)

    def get_worker_info(self, worker_id: str) -> WorkerInfo:
        """Return current :class:`WorkerInfo` for *worker_id*."""
        return self._backend.get_worker_info(worker_id)

    def apply_shaping(
        self,
        worker_id: str,
        *,
        download_mbps: float,
        upload_mbps: float,
        latency_ms: float = 0.0,
        qdisc: str = "pfifo",
        buffer_packets: int = 1000,
        qdisc_params: dict[str, str] | None = None,
        latency_location: str = "both",
        upstream_iface: str = "veth4",
        downstream_iface: str = "veth2",
    ) -> dict[str, Any]:
        """Apply traffic shaping on the worker via ``POST /shape``.

        Only includes ``latency_location`` when *latency_ms* > 0, matching
        the behaviour of ``run_experiment.py``.
        """
        info = self._backend.get_worker_info(worker_id)
        payload: dict[str, Any] = {
            "upstream_iface": upstream_iface,
            "downstream_iface": downstream_iface,
            "download_mbps": download_mbps,
            "upload_mbps": upload_mbps,
            "latency_ms": latency_ms,
            "qdisc": qdisc,
            "buffer_packets": buffer_packets,
        }
        if qdisc_params:
            payload["qdisc_params"] = qdisc_params
        if latency_ms > 0:
            payload["latency_location"] = latency_location or "both"

        with httpx.Client(timeout=120) as client:
            resp = client.post(f"{info.endpoint}/shape", json=payload)
        if resp.status_code != 200:
            raise RuntimeError(
                f"POST /shape failed for worker {worker_id} "
                f"(HTTP {resp.status_code}): {resp.text[:1000]}"
            )
        result = resp.json()
        logger.info(
            "Shaping applied on worker %s: %sMbps down, %sMbps up, %sms latency",
            worker_id,
            download_mbps,
            upload_mbps,
            latency_ms,
        )
        return result

    def apply_congestion(
        self,
        worker_id: str,
        *,
        algorithm: str = "cubic",
        namespace: str = "ns1",
    ) -> dict[str, Any]:
        """Set the TCP congestion control algorithm via ``POST /congestion``."""
        info = self._backend.get_worker_info(worker_id)
        payload = {"algorithm": algorithm, "namespace": namespace}

        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{info.endpoint}/congestion", json=payload)
        if resp.status_code != 200:
            raise RuntimeError(
                f"POST /congestion failed for worker {worker_id} "
                f"(HTTP {resp.status_code}): {resp.text[:1000]}"
            )
        result = resp.json()
        logger.info(
            "Congestion control set on worker %s: %s",
            worker_id,
            result.get("current_algorithm", algorithm),
        )
        return result

    def run_workflow(
        self,
        worker_id: str,
        workflow: dict[str, Any],
        *,
        runtime: str = "shell",
        parameters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a workflow on the worker via ``POST /run``.

        Assumes shaping and congestion have already been applied via
        :meth:`apply_shaping` and :meth:`apply_congestion`.
        """
        info = self._backend.get_worker_info(worker_id)
        payload: dict[str, Any] = {
            "workflow": workflow,
            "runtime": runtime,
        }
        if parameters:
            payload["parameters"] = parameters

        with httpx.Client(timeout=300) as client:
            resp = client.post(f"{info.endpoint}/run", json=payload)
        if resp.status_code != 200:
            raise RuntimeError(
                f"POST /run failed for worker {worker_id} "
                f"(HTTP {resp.status_code}): {resp.text[:1000]}"
            )
        return resp.json()

    def run_experiment(
        self,
        worker_id: str,
        workflow: dict[str, Any],
        *,
        download_mbps: float,
        upload_mbps: float,
        latency_ms: float = 0.0,
        qdisc: str = "pfifo",
        buffer_packets: int = 1000,
        qdisc_params: dict[str, str] | None = None,
        latency_location: str = "both",
        cca: str = "cubic",
        cca_namespace: str = "ns1",
        upstream_iface: str = "veth4",
        downstream_iface: str = "veth2",
        runtime: str = "shell",
        parameters: dict[str, str] | None = None,
        experiment_id: str | None = None,
        application: str | None = None,
        telemetry_url: str | None = None,
    ) -> dict[str, Any]:
        """Shape the network, set congestion control, and run a workflow.

        Mirrors the three-step flow of ``run_experiment.py``:
        ``POST /shape`` → ``POST /congestion`` → ``POST /run``.

        Args:
            worker_id:        ID returned by :meth:`create_worker`.
            workflow:         Workflow definition dict (state machine JSON).
            download_mbps:    Download capacity in Mbps.
            upload_mbps:      Upload capacity in Mbps.
            latency_ms:       One-way latency in ms (default: 0).
            qdisc:            Queue discipline (default: ``pfifo``).
            buffer_packets:   Queue depth in packets (default: 1000).
            latency_location: Where to inject latency — ``upstream``,
                              ``downstream``, or ``both`` (default).
                              Ignored when *latency_ms* is 0.
            cca:              TCP congestion control algorithm (default: ``cubic``).
            cca_namespace:    Namespace for CCA (default: ``ns1``).
            upstream_iface:   Upload interface inside the worker (default: ``veth4``).
            downstream_iface: Download interface inside the worker (default: ``veth2``).
            runtime:          Workflow runtime — ``shell`` or ``browser`` (default: ``shell``).
            parameters:       Workflow parameter substitutions (``key=value``).
            experiment_id:    Identifier stored in telemetry (auto-generated if omitted).
            application:      Application name stored in telemetry contextual tree.
            telemetry_url:    Base URL of the Telemetry Service.  Reads
                              ``TELEMETRY_SERVICE_URL`` env var when omitted; set to
                              an empty string to skip telemetry entirely.

        Returns:
            Dict with ``shaping``, ``congestion``, ``workflow_result``, and
            ``telemetry`` keys.
        """
        shaping_result = self.apply_shaping(
            worker_id,
            download_mbps=download_mbps,
            upload_mbps=upload_mbps,
            latency_ms=latency_ms,
            qdisc=qdisc,
            buffer_packets=buffer_packets,
            qdisc_params=qdisc_params,
            latency_location=latency_location,
            upstream_iface=upstream_iface,
            downstream_iface=downstream_iface,
        )

        congestion_result = self.apply_congestion(
            worker_id,
            algorithm=cca,
            namespace=cca_namespace,
        )

        workflow_result = self.run_workflow(
            worker_id,
            workflow,
            runtime=runtime,
            parameters=parameters,
        )

        # --- Telemetry persistence ---
        resolved_telemetry_url = (
            telemetry_url
            if telemetry_url is not None
            else os.getenv("TELEMETRY_SERVICE_URL", "http://telemetry-service:8004")
        ).rstrip("/")

        telemetry_save: dict[str, Any] | None = None
        if resolved_telemetry_url:
            exp_id = experiment_id or f"connectivity-{uuid.uuid4().hex[:12]}"
            # Keep `application` compact for telemetry indexing; verbose workflow
            # text is preserved in contextual_tree.
            app_label = (application or runtime or "unknown").strip()
            if len(app_label) > 256:
                app_label = app_label[:256]
            telemetry_payload = {
                "experiment_id": exp_id,
                "status": (
                    "success" if workflow_result.get("status") == "ok" else "failure"
                ),
                "trial_number": 1,
                "bottleneck_state": {
                    "configured_capacity": download_mbps,
                    "configured_latency": latency_ms,
                    "measured_throughput": None,
                    "measured_rtt": None,
                },
                "contextual_tree": {
                    "c_static": {
                        "capacity_mbps": download_mbps,
                        "upload_mbps": upload_mbps,
                        "latency_ms": latency_ms,
                        "qdisc": qdisc,
                        "buffer_packets": buffer_packets,
                    },
                    "c_app": {"application": application},
                    "c_trans": {
                        "congestion_control": cca,
                        "runtime": runtime,
                    },
                },
                "application": app_label,
                "qoe_metrics": workflow_result,
                "transport_state": {},
                "pcap_path": "",
            }
            try:
                with httpx.Client(timeout=10) as client:
                    tel_resp = client.post(
                        f"{resolved_telemetry_url}/results", json=telemetry_payload
                    )
                if tel_resp.status_code >= 400:
                    telemetry_save = {
                        "error": f"HTTP {tel_resp.status_code}",
                        "body": (tel_resp.text or "")[:2000],
                        "stored": False,
                    }
                else:
                    telemetry_save = tel_resp.json()
                logger.info(
                    "Telemetry saved for experiment %s (HTTP %s)",
                    exp_id,
                    tel_resp.status_code,
                )
            except Exception as exc:
                telemetry_save = {"error": str(exc), "stored": False}
                logger.warning(
                    "Telemetry POST failed for experiment %s: %s", exp_id, exc
                )

        return {
            "shaping": shaping_result,
            "congestion": congestion_result,
            "workflow_result": workflow_result,
            "telemetry": telemetry_save,
        }

    @property
    def backend_name(self) -> str:
        return self._backend_name
