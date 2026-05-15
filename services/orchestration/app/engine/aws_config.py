"""AWS EC2 backend configuration for substrate worker provisioning.

All settings are read from environment variables with sensible defaults
where possible.  When ``AWS_SUBSTRATE_AUTO_PROVISION`` is enabled (the
default), ECR repository and security group are created automatically
on first use if not provided.

Environment variables
---------------------
AWS_REGION                      AWS region (default: ``AWS_DEFAULT_REGION`` or ``aws configure get region``, else ``us-east-1``)
AWS_SUBSTRATE_ECR_URI           ECR image URI for substrate-worker (auto-provisioned if blank)
AWS_SUBSTRATE_INSTANCE_TYPE     EC2 instance type (default: ``c5.xlarge``)
AWS_SUBSTRATE_SECURITY_GROUP    Security group ID allowing inbound 8002 (auto-provisioned if blank)
AWS_SUBSTRATE_SUBNET_ID         VPC subnet ID (optional, uses default VPC if omitted)
AWS_SUBSTRATE_KEY_PAIR          SSH key pair name for debugging (auto-created if blank and auto-provision is on)
AWS_SUBSTRATE_BOOT_TIMEOUT      Seconds to wait for instance + health check (default: ``300``)
AWS_SUBSTRATE_IAM_PROFILE       IAM instance profile name (optional, for ECR pull access)
AWS_SUBSTRATE_AUTO_PROVISION    Enable auto-provisioning of ECR/SG (default: ``true``)
TELEMETRY_SERVICE_URL           Passed to the substrate worker container (default: ``""``)
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field


def resolve_aws_region() -> str:
    """Resolve AWS region from env, CLI config, then safe fallback."""
    for key in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        value = os.getenv(key, "").strip()
        if value:
            return value

    try:
        result = subprocess.run(
            ["aws", "configure", "get", "region"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        result = None

    if result and result.returncode == 0:
        configured_region = result.stdout.strip()
        if configured_region:
            return configured_region

    return "us-east-1"


@dataclass(frozen=True)
class AWSConfig:
    """Immutable snapshot of AWS backend configuration."""

    region: str = field(default_factory=resolve_aws_region)
    ecr_uri: str = field(default_factory=lambda: os.getenv("AWS_SUBSTRATE_ECR_URI", ""))
    instance_type: str = field(
        default_factory=lambda: os.getenv("AWS_SUBSTRATE_INSTANCE_TYPE", "c5.xlarge")
    )
    security_group_id: str = field(
        default_factory=lambda: os.getenv("AWS_SUBSTRATE_SECURITY_GROUP", "")
    )
    subnet_id: str = field(
        default_factory=lambda: os.getenv("AWS_SUBSTRATE_SUBNET_ID", "")
    )
    key_pair: str = field(
        default_factory=lambda: os.getenv("AWS_SUBSTRATE_KEY_PAIR", "")
    )
    boot_timeout: int = field(
        default_factory=lambda: int(os.getenv("AWS_SUBSTRATE_BOOT_TIMEOUT", "300"))
    )
    iam_instance_profile: str = field(
        default_factory=lambda: os.getenv("AWS_SUBSTRATE_IAM_PROFILE", "")
    )
    telemetry_url: str = field(
        default_factory=lambda: os.getenv("TELEMETRY_SERVICE_URL", "")
    )
    auto_provision: bool = field(
        default_factory=lambda: (
            os.getenv("AWS_SUBSTRATE_AUTO_PROVISION", "true").lower()
            in ("true", "1", "yes")
        )
    )

    @property
    def needs_provisioning(self) -> bool:
        """Return True if ECR URI or security group need to be provisioned."""
        return not self.ecr_uri or not self.security_group_id

    def validate(self) -> None:
        """Raise :class:`ValueError` if config is invalid.

        When ``auto_provision`` is enabled, missing ECR URI/SG are allowed
        (they will be created on first use).  When disabled, both are
        required.
        """
        if self.auto_provision:
            return

        missing = []
        if not self.ecr_uri:
            missing.append("AWS_SUBSTRATE_ECR_URI")
        if not self.security_group_id:
            missing.append("AWS_SUBSTRATE_SECURITY_GROUP")
        if missing:
            raise ValueError(
                f"AWS backend requires the following environment variables "
                f"(or set AWS_SUBSTRATE_AUTO_PROVISION=true): "
                f"{', '.join(missing)}"
            )
