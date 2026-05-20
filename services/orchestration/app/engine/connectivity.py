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
import time
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
                    # Read-only host module dir so the ephemeral worker can
                    # `modprobe tcp_<algo>` the 14 loadable CCAnalyzer CCAs.
                    # No-op on Docker Desktop's LinuxKit kernel (no modules
                    # to load), required on real Linux hosts.
                    "/lib/modules:/lib/modules:ro",
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


def _build_user_data(
    *,
    worker_image: str,
    telemetry_url: str,
    ecr_region: str = "",
    netgent_use_local: str = "false",
    netgent_namespace: str = "ns1",
) -> str:
    """Build the EC2 user-data script that starts the substrate worker.

    The script runs on first boot (cloud-init) and:
    1. Installs Docker if not present
    2. Authenticates to ECR if the image is an ECR reference
    3. Pulls the substrate-worker image
    4. Launches it in privileged host-network mode
    """
    env_parts: list[str] = []
    if telemetry_url:
        env_parts.append(f"-e TELEMETRY_SERVICE_URL={telemetry_url}")
    # Used by substrate-worker container startup dispatch to choose AWS-specific
    # setup/runtime files.
    env_parts.append("-e CONNECTIVITY_BACKEND=aws")
    # Shell workflows (ping, etc.) must run inside the same netns as the shaped
    # veth path (ns1). NetGent defaults NETGENT_USE_LOCAL=true if unset, which
    # bypasses `ip netns exec` — traffic exits the host directly and does not
    # appear on SUBSTRATE_CAPTURE_IFACE (veth2). Match docker-compose substrate-worker.
    env_parts.append(f"-e NETGENT_USE_LOCAL={netgent_use_local}")
    env_parts.append(f"-e NETGENT_NAMESPACE={netgent_namespace}")
    env_flags = " \\\n    ".join(env_parts)

    # Build ECR login block if image is from ECR
    ecr_login = ""
    if ".dkr.ecr." in worker_image and ecr_region:
        registry = worker_image.split("/")[0]
        ecr_login = f"""
# Authenticate Docker to ECR
echo "Authenticating to ECR..."
aws ecr get-login-password --region {ecr_region} | \\
    docker login --username AWS --password-stdin {registry}
"""

    return f"""#!/bin/bash
set -euo pipefail
exec > /var/log/substrate-worker-init.log 2>&1

echo "Starting substrate worker at $(date)"

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    yum update -y -q
    yum install -y -q docker aws-cli-2 2>/dev/null || yum install -y -q docker awscli
    systemctl enable docker
fi

# Ensure Docker is running
systemctl start docker || true
sleep 2
{ecr_login}
# Pull image
echo "Pulling image {worker_image}..."
docker pull {worker_image}

# WAN interface for setup.sh SNAT (iptables MASQUERADE). Wrong iface => no return path
# from ns1/ns2 => ping gets 0 replies and exits non-zero. Detect at boot from host routing.
WAN_IF="$(ip -4 route show default 2>/dev/null | awk '{{print $5; exit}}')"
if [ -z "$WAN_IF" ] || [ ! -d "/sys/class/net/$WAN_IF" ]; then
  WAN_IF="eth0"
fi
echo "SUBSTRATE_WAN_IF=$WAN_IF (for SNAT to Internet from client netns)"

# Run substrate worker
docker run -d \\
    --name substrate-worker \\
    --restart unless-stopped \\
    --privileged \\
    --cap-add NET_ADMIN \\
    --cap-add SYS_ADMIN \\
    --net=host \\
    {env_flags} \\
    -e SUBSTRATE_WAN_IF="$WAN_IF" \\
    {worker_image}

echo "Substrate worker started at $(date)"
"""


class AWSBackend(ConnectivityBackend):
    """Provisions substrate workers as EC2 instances on AWS.

    Each worker is a dedicated EC2 instance running the substrate-worker
    Docker container in ``--privileged --net=host`` mode, giving full
    access to ``tc``/``netem`` for traffic shaping.

    When ``AWS_SUBSTRATE_AUTO_PROVISION=true`` (the default), the backend
    automatically creates the ECR repository, pushes the Docker image,
    and creates a security group on first use.  This takes ~2-3 minutes
    on the first call; results are cached to
    ``~/.agentic-thin-waist/aws-resources.json`` for subsequent runs.

    Prerequisites:
        1. AWS credentials configured (``aws configure`` or env vars).
        2. Either:
           a. Set ``AWS_SUBSTRATE_ECR_URI`` and ``AWS_SUBSTRATE_SECURITY_GROUP``
              to use pre-existing resources, OR
           b. Leave them blank and let auto-provisioning handle it.

    See :mod:`app.engine.aws_config` for the full list of environment
    variables.
    """

    def __init__(self) -> None:
        from app.engine.aws_config import AWSConfig

        self._config = AWSConfig()
        self._config.validate()
        self._workers: dict[str, WorkerInfo] = {}
        self._provisioned = False
        self._docker_ami_id: str = ""  # Populated by auto-provisioning

        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for the AWS backend. "
                "Install it with: pip install boto3"
            )
        self._ec2 = boto3.client("ec2", region_name=self._config.region)

    # --- Public API -------------------------------------------------------

    def create_worker(self, config: dict[str, Any]) -> WorkerInfo:
        """Launch an EC2 instance running the substrate-worker container.

        Supported *config* keys (all optional, override env-var defaults):
            ami (str)            — AMI ID (uses Docker-ready AMI if blank)
            instance_type (str)  — EC2 instance type
            security_group (str) — Security group ID
            subnet_id (str)      — VPC subnet ID
            key_pair (str)       — SSH key pair name
            telemetry_url (str)  — TELEMETRY_SERVICE_URL for the container
            ecr_uri (str)        — ECR image URI (e.g. ACCOUNT.dkr.ecr.REGION.amazonaws.com/repo)
            boot_timeout (int)   — Max seconds to wait for healthy worker
        """
        # Auto-provision infrastructure on first call if needed
        if self._config.needs_provisioning and not self._provisioned:
            self._auto_provision()

        ami = config.get("ami", self._docker_ami_id)
        instance_type = config.get("instance_type", self._config.instance_type)
        sg = config.get("security_group", self._config.security_group_id)
        subnet = config.get("subnet_id", self._config.subnet_id)
        key_pair = config.get("key_pair", self._config.key_pair)
        telemetry_url = config.get("telemetry_url", self._config.telemetry_url)
        ecr_uri = config.get("ecr_uri", self._config.ecr_uri)
        worker_image = f"{ecr_uri}:latest" if ecr_uri else "substrate-worker"
        boot_timeout = int(config.get("boot_timeout", self._config.boot_timeout))

        worker_id = f"worker-{uuid.uuid4().hex[:8]}"

        netgent_use_local = str(
            config.get("netgent_use_local") or os.getenv("NETGENT_USE_LOCAL", "false")
        ).strip()
        netgent_namespace = str(
            config.get("netgent_namespace") or os.getenv("NETGENT_NAMESPACE", "ns1")
        ).strip()
        user_data = _build_user_data(
            worker_image=worker_image,
            telemetry_url=telemetry_url,
            ecr_region=self._config.region,
            netgent_use_local=netgent_use_local or "false",
            netgent_namespace=netgent_namespace or "ns1",
        )

        run_kwargs: dict[str, Any] = {
            "ImageId": ami,
            "InstanceType": instance_type,
            "MinCount": 1,
            "MaxCount": 1,
            "SecurityGroupIds": [sg],
            "UserData": user_data,
            "TagSpecifications": [
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": f"substrate-worker-{worker_id}"},
                        {"Key": "substrate_worker_id", "Value": worker_id},
                        {"Key": "Project", "Value": "agentic-thin-waist"},
                        {"Key": "ManagedBy", "Value": "orchestration"},
                    ],
                }
            ],
        }
        if subnet:
            run_kwargs["SubnetId"] = subnet
        if key_pair:
            run_kwargs["KeyName"] = key_pair
        if self._config.iam_instance_profile:
            run_kwargs["IamInstanceProfile"] = {
                "Name": self._config.iam_instance_profile,
            }

        # Launch instance
        resp = self._ec2.run_instances(**run_kwargs)
        instance_id = resp["Instances"][0]["InstanceId"]
        logger.info(
            "Launched EC2 instance %s for worker %s (ami=%s, type=%s)",
            instance_id,
            worker_id,
            ami,
            instance_type,
        )

        # Wait for running state + public IP
        try:
            public_ip = self._wait_for_instance(instance_id, boot_timeout)
        except Exception:
            logger.error("Instance %s failed to start, terminating", instance_id)
            self._terminate_instance(instance_id)
            raise

        endpoint = f"http://{public_ip}:{_SUBSTRATE_CONTAINER_PORT}"

        # Wait for substrate-worker /health to respond
        try:
            self._wait_for_health(endpoint, boot_timeout)
        except Exception:
            logger.error(
                "Worker health check failed on %s, terminating %s",
                endpoint,
                instance_id,
            )
            self._terminate_instance(instance_id)
            raise

        info = WorkerInfo(
            worker_id=worker_id,
            endpoint=endpoint,
            backend="aws",
            container_id=instance_id,
            metadata={
                "instance_id": instance_id,
                "instance_type": instance_type,
                "ami": ami,
                "public_ip": public_ip,
                "region": self._config.region,
            },
        )
        self._workers[worker_id] = info
        logger.info(
            "AWS worker %s ready → %s (instance %s)",
            worker_id,
            endpoint,
            instance_id,
        )
        return info

    def destroy_worker(self, worker_id: str) -> None:
        """Terminate the EC2 instance for *worker_id*."""
        info = self._get(worker_id)
        instance_id = info.metadata.get("instance_id") or info.container_id
        if instance_id:
            self._terminate_instance(instance_id)
            logger.info(
                "Terminated EC2 instance %s for worker %s",
                instance_id,
                worker_id,
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

    def _terminate_instance(self, instance_id: str) -> None:
        try:
            self._ec2.terminate_instances(InstanceIds=[instance_id])
        except Exception as exc:
            logger.warning("Failed to terminate instance %s: %s", instance_id, exc)

    def _wait_for_instance(self, instance_id: str, timeout: int) -> str:
        """Poll until instance is running and has a public IP. Returns the IP."""
        deadline = time.monotonic() + timeout
        poll_interval = 5
        last_error = ""

        while time.monotonic() < deadline:
            try:
                resp = self._ec2.describe_instances(InstanceIds=[instance_id])
                reservations = resp.get("Reservations", [])
                if not reservations or not reservations[0].get("Instances"):
                    last_error = "instance not yet visible in describe_instances"
                    time.sleep(poll_interval)
                    continue
                instance = reservations[0]["Instances"][0]
            except Exception as exc:
                # EC2 can be eventually consistent right after run_instances and
                # transiently return InvalidInstanceID.NotFound for a valid ID.
                msg = str(exc)
                if "InvalidInstanceID.NotFound" in msg:
                    last_error = msg
                    logger.debug(
                        "Instance %s not yet visible to EC2 DescribeInstances; retrying",
                        instance_id,
                    )
                    time.sleep(poll_interval)
                    continue
                raise
            state = instance["State"]["Name"]

            if state == "terminated" or state == "shutting-down":
                raise RuntimeError(
                    f"Instance {instance_id} entered state '{state}' "
                    f"before becoming ready"
                )

            if state == "running":
                public_ip = instance.get("PublicIpAddress")
                if public_ip:
                    logger.info("Instance %s running at %s", instance_id, public_ip)
                    return public_ip

            logger.debug("Waiting for instance %s (state=%s)...", instance_id, state)
            time.sleep(poll_interval)

        raise TimeoutError(
            f"Instance {instance_id} did not reach running state with a "
            f"public IP within {timeout}s (last error: {last_error})"
        )

    def _wait_for_health(self, endpoint: str, timeout: int) -> None:
        """Poll ``GET /health`` until the substrate worker responds 200."""
        deadline = time.monotonic() + timeout
        poll_interval = 5
        health_url = f"{endpoint}/health"
        last_error: str = ""

        while time.monotonic() < deadline:
            try:
                with httpx.Client(timeout=5) as client:
                    resp = client.get(health_url)
                if resp.status_code == 200:
                    logger.info("Health check passed at %s", health_url)
                    return
                last_error = f"HTTP {resp.status_code}"
            except Exception as exc:
                last_error = str(exc)

            logger.debug("Waiting for health at %s (%s)...", health_url, last_error)
            time.sleep(poll_interval)

        raise TimeoutError(
            f"Substrate worker at {endpoint} did not become healthy "
            f"within {timeout}s (last error: {last_error})"
        )

    def _auto_provision(self) -> None:
        """Run the AWS provisioner to create ECR repo, push image, and create SG.

        Updates ``self._config`` fields in-place (via object.__setattr__
        since the dataclass is frozen) so that subsequent calls use the
        provisioned resources.
        """
        from app.engine.aws_provisioner import AWSProvisioner

        provisioner = AWSProvisioner(region=self._config.region)
        result = provisioner.ensure_infrastructure()

        # Update the frozen config with provisioned values
        object.__setattr__(self._config, "ecr_uri", result.ecr_uri)
        object.__setattr__(self._config, "security_group_id", result.security_group_id)
        if not self._config.key_pair:
            object.__setattr__(self._config, "key_pair", result.key_pair_name)
        if result.instance_profile_name and not self._config.iam_instance_profile:
            object.__setattr__(
                self._config, "iam_instance_profile", result.instance_profile_name
            )
        self._docker_ami_id = result.docker_ami_id

        self._provisioned = True
        logger.info(
            "Auto-provisioned AWS resources: ECR=%s, SG=%s, Key=%s, AMI=%s, Profile=%s",
            result.ecr_uri,
            result.security_group_id,
            result.key_pair_name,
            result.docker_ami_id,
            result.instance_profile_name,
        )


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
        latency_location: str = "upstream",
        upstream_iface: str = "veth4",
        downstream_iface: str = "veth2",
        verify: bool = True,
    ) -> dict[str, Any]:
        """Apply traffic shaping on the worker via ``POST /shape``.

        Only includes ``latency_location`` when *latency_ms* > 0, matching
        the behaviour of ``run_experiment.py``.

        ``latency_location`` defaults to ``"upstream"`` (netem on ns2/veth3
        only) so a requested ``latency_ms=100`` contributes ~100 ms to RTT.
        Using ``"both"`` would put netem on both legs and double the RTT
        contribution (100 ms each direction = 200 ms RTT).

        Pass ``verify=False`` when calling during a concurrent pcap capture
        (e.g. from the /intent pipeline) so the worker skips iperf3 + ping
        probes and the trace doesn't get polluted with verification traffic.
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
            "verify": verify,
        }
        if qdisc_params:
            payload["qdisc_params"] = qdisc_params
        if latency_ms > 0:
            payload["latency_location"] = latency_location or "upstream"

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
        experiment_max_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Execute a workflow on the worker via ``POST /run``.

        Assumes shaping and congestion have already been applied via
        :meth:`apply_shaping` and :meth:`apply_congestion`.

        ``experiment_max_seconds`` is a wallclock deadline (seconds) that the
        substrate worker applies to any shell command in the workflow. On
        timeout the process is SIGTERMed/SIGKILLed and the response carries
        ``terminated_at_deadline=True`` — the run still produces partial
        stdout/stderr and a usable pcap/qtrace pair.
        """
        info = self._backend.get_worker_info(worker_id)
        payload: dict[str, Any] = {
            "workflow": workflow,
            "runtime": runtime,
        }
        if parameters:
            payload["parameters"] = parameters
        if experiment_max_seconds is not None and experiment_max_seconds > 0:
            payload["experiment_max_seconds"] = float(experiment_max_seconds)

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
        latency_location: str = "upstream",
        cca: str = "cubic",
        cca_namespace: str = "ns1",
        upstream_iface: str = "veth4",
        downstream_iface: str = "veth2",
        runtime: str = "shell",
        parameters: dict[str, str] | None = None,
        experiment_id: str | None = None,
        application: str | None = None,
        telemetry_url: str | None = None,
        experiment_max_seconds: float | None = None,
        verify_shaping: bool = True,
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
            latency_location: Where to inject latency — ``upstream``
                              (default; netem only on ns2/veth3, so
                              ``latency_ms`` contributes ~1× to RTT),
                              ``downstream``, or ``both`` (netem on both
                              legs → 2× contribution to RTT). Ignored
                              when *latency_ms* is 0.
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
            verify=verify_shaping,
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
            experiment_max_seconds=experiment_max_seconds,
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
                    # Keep application bounded for telemetry DB constraints.
                    "c_app": {"application": app_label},
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
