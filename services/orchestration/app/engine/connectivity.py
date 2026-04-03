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
    endpoint: str                     # http://host:port
    backend: str                      # "local_docker" | "aws" | "gcp" | "remote"
    container_id: str | None = None   # Docker container ID (local_docker only)
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
        image = config.get("image", os.getenv("SUBSTRATE_WORKER_IMAGE", "substrate-worker"))
        network = config.get("network", os.getenv("SUBSTRATE_DOCKER_NETWORK", "agentic-network"))
        telemetry_url = config.get(
            "telemetry_url",
            os.getenv("TELEMETRY_SERVICE_URL", "http://telemetry-service:8004"),
        )
        ctp_dir = config.get("ctp_dir", os.getenv("SUBSTRATE_CTP_DIR", "/mnt/md0/ctp_test"))
        capture_dir = config.get(
            "capture_dir", os.getenv("SUBSTRATE_CAPTURE_DIR", "/mnt/md0/cap_test")
        )

        worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        container_name = f"substrate-worker-{worker_id}"

        container_config = {
            "Image": image,
            "Env": [
                f"TELEMETRY_SERVICE_URL={telemetry_url}",
                f"CTP_DIR={ctp_dir}",
                f"CAPTURE_DIR={capture_dir}",
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
                    f"{ctp_dir}:{ctp_dir}:ro",
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
            "Created worker %s → %s (container %s)", worker_id, endpoint, container_id[:12]
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

    @property
    def backend_name(self) -> str:
        return self._backend_name
