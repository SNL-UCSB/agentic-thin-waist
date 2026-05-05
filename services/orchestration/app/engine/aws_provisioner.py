"""AWS infrastructure auto-provisioner for substrate workers.

Creates the ECR repository, pushes the substrate-worker Docker image,
and creates the security group and key pair required by
:class:`~app.engine.connectivity.AWSBackend` on first use.  Results
are cached to ``~/.agentic-thin-waist/aws-resources.json`` so that
subsequent runs reuse existing infrastructure.

Usage::

    from app.engine.aws_provisioner import AWSProvisioner

    p = AWSProvisioner(region="us-west-1")
    result = p.ensure_infrastructure()
    # result.ecr_uri, result.security_group_id, result.key_pair_name, result.docker_ami_id

    # Cleanup when done
    p.teardown()

CLI::

    python -m app.engine.aws_provisioner setup    # provision
    python -m app.engine.aws_provisioner teardown  # destroy
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .aws_config import resolve_aws_region

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

_BAR_WIDTH = 40


class ProvisioningProgress:
    """Simple CLI progress display for long-running provisioning steps.

    Prints a progress bar with step descriptions to stderr so it is
    visible in the terminal even when stdout is redirected.

    Example output::

        [========>                               ]  20%  0m15s  Creating security group...
        [=================>                      ]  45%  1m02s  Pushing image to ECR...
    """

    def __init__(self, total_steps: int) -> None:
        self._total = total_steps
        self._current = 0
        self._start_time = time.monotonic()

    def update(self, description: str) -> None:
        """Advance to the next step and display progress."""
        self._current += 1
        self._render(description)

    def complete(self) -> None:
        """Mark provisioning as complete."""
        elapsed = time.monotonic() - self._start_time
        self._current = self._total
        self._render(f"Done! ({elapsed:.0f}s total)")
        sys.stderr.write("\n")
        sys.stderr.flush()

    def _render(self, description: str) -> None:
        pct = self._current / self._total if self._total > 0 else 1.0
        filled = int(_BAR_WIDTH * pct)
        bar = "=" * filled
        if filled < _BAR_WIDTH:
            bar += ">"
            bar += " " * (_BAR_WIDTH - filled - 1)
        else:
            bar = "=" * _BAR_WIDTH

        elapsed = time.monotonic() - self._start_time
        elapsed_str = _format_duration(elapsed)

        line = f"\r  [{bar}] {pct:4.0%}  {elapsed_str}  {description}"
        sys.stderr.write(f"{line:<100}")
        sys.stderr.flush()


def _format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


# ---------------------------------------------------------------------------
# Resource cache
# ---------------------------------------------------------------------------

_CACHE_DIR = pathlib.Path.home() / ".agentic-thin-waist"
_CACHE_FILE = _CACHE_DIR / "aws-resources.json"
_KEY_DIR = _CACHE_DIR / "keys"

_ECR_REPO_NAME = "agentic-thin-waist/substrate-worker"
_IMAGE_TAG = "latest"
_LOCAL_IMAGE_NAME = "substrate-worker"


def _load_cache() -> dict[str, Any]:
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(data: dict[str, Any]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(data, indent=2))


def _clear_cache() -> None:
    if _CACHE_FILE.exists():
        _CACHE_FILE.unlink()


# ---------------------------------------------------------------------------
# AWSProvisioner
# ---------------------------------------------------------------------------


@dataclass
class ProvisionedResources:
    """IDs of provisioned AWS resources."""

    ecr_uri: str
    security_group_id: str
    key_pair_name: str
    docker_ami_id: str
    instance_profile_name: str = ""


class AWSProvisioner:
    """Provisions AWS infrastructure for substrate workers.

    Handles the full lifecycle:
    1. ECR repository creation and image push
    2. Security group creation (inbound 8002 + 22)
    3. EC2 key pair creation (for optional SSH debugging)
    4. ECS-optimized AMI lookup (has Docker pre-installed)
    5. Caching of resource IDs for reuse

    All resources are tagged with ``Project=agentic-thin-waist`` and
    ``ManagedBy=aws-provisioner`` for easy identification and cleanup.
    """

    _TAGS = [
        {"Key": "Project", "Value": "agentic-thin-waist"},
        {"Key": "ManagedBy", "Value": "aws-provisioner"},
    ]
    _KEY_PAIR_NAME = "agentic-substrate-worker"
    _SG_NAME = "agentic-substrate-worker-sg"
    _IAM_ROLE_NAME = "agentic-substrate-worker-role"
    _INSTANCE_PROFILE_NAME = "agentic-substrate-worker-profile"

    def __init__(self, region: str | None = None) -> None:
        self._region = region or resolve_aws_region()

        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for the AWS provisioner. "
                "Install it with: pip install boto3"
            )
        self._ec2 = boto3.client("ec2", region_name=self._region)
        self._ecr = boto3.client("ecr", region_name=self._region)
        self._iam = boto3.client("iam", region_name=self._region)
        self._sts = boto3.client("sts", region_name=self._region)
        self._cache = _load_cache()

    # --- Public API -------------------------------------------------------

    def ensure_infrastructure(self) -> ProvisionedResources:
        """Provision all required AWS resources, reusing cached ones.

        Returns :class:`ProvisionedResources` with the ECR URI, security
        group ID, key pair name, and Docker AMI ID.

        On first call this takes ~2-3 minutes (ECR push); subsequent
        calls return in <1 second from cache.
        """
        cached = self._cache.get(self._region)
        if cached and self._validate_cached(cached):
            logger.info(
                "Using cached AWS resources: ECR=%s, SG=%s",
                cached["ecr_uri"],
                cached["security_group_id"],
            )
            return ProvisionedResources(
                ecr_uri=cached["ecr_uri"],
                security_group_id=cached["security_group_id"],
                key_pair_name=cached["key_pair_name"],
                docker_ami_id=cached["docker_ami_id"],
                instance_profile_name=cached.get("instance_profile_name", ""),
            )

        sys.stderr.write(
            "\n  AWS auto-provisioning: setting up infrastructure "
            f"in {self._region}...\n"
        )
        progress = ProvisioningProgress(total_steps=7)

        # Step 1: Key pair
        progress.update("Creating EC2 key pair...")
        key_name, _key_path = self._ensure_key_pair()

        # Step 2: Security group
        progress.update("Creating security group...")
        sg_id = self._ensure_security_group()

        # Step 3: IAM role + instance profile (for ECR pull access)
        progress.update("Creating IAM instance profile for ECR access...")
        profile_name = self._ensure_instance_profile()

        # Step 4: ECR repository
        progress.update("Creating ECR repository...")
        ecr_uri = self._ensure_ecr_repository()

        # Step 5: Build and push image
        progress.update(
            "Pushing substrate-worker image to ECR (this may take a few minutes)..."
        )
        self._push_image_to_ecr(ecr_uri)

        # Step 6: Find Docker-ready AMI
        progress.update("Finding Docker-ready AMI...")
        docker_ami_id = self._find_docker_ami()

        # Step 7: Save
        progress.update("Saving configuration...")
        result = ProvisionedResources(
            ecr_uri=ecr_uri,
            security_group_id=sg_id,
            key_pair_name=key_name,
            docker_ami_id=docker_ami_id,
            instance_profile_name=profile_name,
        )

        self._cache[self._region] = {
            "ecr_uri": ecr_uri,
            "security_group_id": sg_id,
            "key_pair_name": key_name,
            "docker_ami_id": docker_ami_id,
            "instance_profile_name": profile_name,
        }
        _save_cache(self._cache)

        progress.complete()
        sys.stderr.write(
            f"\n  ECR Image:         {ecr_uri}:{_IMAGE_TAG}\n"
            f"  Security Group:    {sg_id}\n"
            f"  Key Pair:          {key_name}\n"
            f"  Instance Profile:  {profile_name}\n"
            f"  Docker AMI:        {docker_ami_id}\n\n"
        )

        return result

    def teardown(self) -> None:
        """Remove all provisioned AWS resources and clear cache."""
        cached = self._cache.get(self._region)
        if not cached:
            logger.info("No cached resources to teardown in %s", self._region)
            return

        sys.stderr.write(f"\n  Tearing down AWS resources in {self._region}...\n")

        ecr_uri = cached.get("ecr_uri", "")
        sg_id = cached.get("security_group_id")
        key_name = cached.get("key_pair_name")

        # Delete ECR repository
        if ecr_uri:
            try:
                self._ecr.delete_repository(repositoryName=_ECR_REPO_NAME, force=True)
                sys.stderr.write(f"  Deleted ECR repository {_ECR_REPO_NAME}\n")
            except Exception as exc:
                sys.stderr.write(f"  Warning: ECR cleanup failed: {exc}\n")

        # Delete security group
        if sg_id:
            try:
                self._ec2.delete_security_group(GroupId=sg_id)
                sys.stderr.write(f"  Deleted security group {sg_id}\n")
            except Exception as exc:
                sys.stderr.write(f"  Warning: SG cleanup failed: {exc}\n")

        # Delete key pair
        if key_name:
            try:
                self._ec2.delete_key_pair(KeyName=key_name)
                key_file = _KEY_DIR / f"{key_name}.pem"
                if key_file.exists():
                    key_file.unlink()
                sys.stderr.write(f"  Deleted key pair {key_name}\n")
            except Exception as exc:
                sys.stderr.write(f"  Warning: key pair cleanup failed: {exc}\n")

        # Delete IAM instance profile and role
        profile_name = cached.get("instance_profile_name")
        if profile_name:
            try:
                # Remove role from profile first
                try:
                    self._iam.remove_role_from_instance_profile(
                        InstanceProfileName=profile_name,
                        RoleName=self._IAM_ROLE_NAME,
                    )
                except Exception:
                    pass
                # Delete instance profile
                self._iam.delete_instance_profile(InstanceProfileName=profile_name)
                sys.stderr.write(f"  Deleted instance profile {profile_name}\n")
                # Detach policy and delete role
                try:
                    self._iam.detach_role_policy(
                        RoleName=self._IAM_ROLE_NAME,
                        PolicyArn="arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
                    )
                except Exception:
                    pass
                self._iam.delete_role(RoleName=self._IAM_ROLE_NAME)
                sys.stderr.write(f"  Deleted IAM role {self._IAM_ROLE_NAME}\n")
            except Exception as exc:
                sys.stderr.write(f"  Warning: IAM cleanup failed: {exc}\n")

        self._cache.pop(self._region, None)
        _save_cache(self._cache)
        sys.stderr.write("  Teardown complete.\n\n")

    # --- Validation -------------------------------------------------------

    def _validate_cached(self, cached: dict[str, Any]) -> bool:
        """Check that cached resource IDs still exist in AWS."""
        ecr_uri = cached.get("ecr_uri")
        sg_id = cached.get("security_group_id")
        docker_ami_id = cached.get("docker_ami_id")

        if not ecr_uri or not sg_id or not docker_ami_id:
            return False

        try:
            # Check ECR repo exists
            self._ecr.describe_repositories(repositoryNames=[_ECR_REPO_NAME])

            # Check SG exists
            self._ec2.describe_security_groups(GroupIds=[sg_id])

            # Check AMI exists
            resp = self._ec2.describe_images(ImageIds=[docker_ami_id])
            if not resp.get("Images"):
                logger.info("Cached Docker AMI %s no longer exists", docker_ami_id)
                return False
        except Exception:
            logger.info("Cached resources are stale, will re-provision")
            return False

        return True

    # --- Key pair ---------------------------------------------------------

    def _ensure_key_pair(self) -> tuple[str, pathlib.Path]:
        """Create the EC2 key pair if it doesn't exist. Returns (name, pem_path)."""
        key_name = self._KEY_PAIR_NAME
        key_path = _KEY_DIR / f"{key_name}.pem"

        try:
            self._ec2.describe_key_pairs(KeyNames=[key_name])
            if key_path.exists():
                logger.info("Key pair %s already exists", key_name)
                return key_name, key_path
            self._ec2.delete_key_pair(KeyName=key_name)
        except Exception:
            pass

        _KEY_DIR.mkdir(parents=True, exist_ok=True)
        resp = self._ec2.create_key_pair(
            KeyName=key_name,
            TagSpecifications=[{"ResourceType": "key-pair", "Tags": self._TAGS}],
        )
        key_path.write_text(resp["KeyMaterial"])
        key_path.chmod(0o400)
        logger.info("Created key pair %s -> %s", key_name, key_path)
        return key_name, key_path

    # --- Security group ---------------------------------------------------

    def _ensure_security_group(self) -> str:
        """Create the security group if it doesn't exist. Returns SG ID."""
        try:
            resp = self._ec2.describe_security_groups(
                Filters=[
                    {"Name": "group-name", "Values": [self._SG_NAME]},
                    {"Name": "tag:ManagedBy", "Values": ["aws-provisioner"]},
                ]
            )
            if resp["SecurityGroups"]:
                sg_id = resp["SecurityGroups"][0]["GroupId"]
                logger.info(
                    "Security group %s already exists: %s", self._SG_NAME, sg_id
                )
                return sg_id
        except Exception:
            pass

        vpc_resp = self._ec2.describe_vpcs(
            Filters=[{"Name": "is-default", "Values": ["true"]}]
        )
        vpcs = vpc_resp.get("Vpcs", [])
        if not vpcs:
            raise RuntimeError(
                f"No default VPC found in {self._region}. "
                "Set AWS_SUBSTRATE_SUBNET_ID to specify a VPC subnet, "
                "or create a default VPC with: aws ec2 create-default-vpc"
            )
        vpc_id = vpcs[0]["VpcId"]

        sg_resp = self._ec2.create_security_group(
            GroupName=self._SG_NAME,
            Description="Substrate worker access (port 8002 + SSH). Managed by agentic-thin-waist.",
            VpcId=vpc_id,
            TagSpecifications=[{"ResourceType": "security-group", "Tags": self._TAGS}],
        )
        sg_id = sg_resp["GroupId"]

        my_ip = self._get_public_ip()
        cidr = f"{my_ip}/32" if my_ip else "0.0.0.0/0"
        if not my_ip:
            logger.warning(
                "Could not determine public IP — security group will allow "
                "inbound from 0.0.0.0/0. Restrict this after provisioning."
            )

        self._ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 8002,
                    "ToPort": 8002,
                    "IpRanges": [
                        {"CidrIp": cidr, "Description": "Substrate worker API"}
                    ],
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": cidr, "Description": "SSH for debugging"}],
                },
            ],
        )

        logger.info(
            "Created security group %s (%s) in VPC %s", sg_id, self._SG_NAME, vpc_id
        )
        return sg_id

    # --- IAM instance profile (for ECR pull access) ------------------------

    def _ensure_instance_profile(self) -> str:
        """Create IAM role + instance profile for ECR read access.

        Returns the instance profile name.  The role gets the
        ``AmazonEC2ContainerRegistryReadOnly`` managed policy attached,
        which allows EC2 instances to pull images from ECR.
        """
        profile_name = self._INSTANCE_PROFILE_NAME
        role_name = self._IAM_ROLE_NAME

        # Check if instance profile already exists
        try:
            self._iam.get_instance_profile(InstanceProfileName=profile_name)
            logger.info("Instance profile %s already exists", profile_name)
            return profile_name
        except Exception:
            pass

        # Create IAM role with EC2 trust policy
        trust_policy = json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "ec2.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                    }
                ],
            }
        )

        try:
            self._iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=trust_policy,
                Description="ECR read access for agentic-thin-waist substrate workers",
                Tags=self._TAGS,
            )
            logger.info("Created IAM role %s", role_name)
        except self._iam.exceptions.EntityAlreadyExistsException:
            logger.info("IAM role %s already exists", role_name)

        # Attach ECR read-only policy
        ecr_policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
        try:
            self._iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn=ecr_policy_arn,
            )
        except Exception:
            pass  # Already attached

        # Create instance profile
        try:
            self._iam.create_instance_profile(
                InstanceProfileName=profile_name,
                Tags=self._TAGS,
            )
            logger.info("Created instance profile %s", profile_name)
        except self._iam.exceptions.EntityAlreadyExistsException:
            logger.info("Instance profile %s already exists", profile_name)

        # Add role to instance profile
        try:
            self._iam.add_role_to_instance_profile(
                InstanceProfileName=profile_name,
                RoleName=role_name,
            )
        except self._iam.exceptions.LimitExceededException:
            pass  # Role already in profile

        # IAM instance profiles can take a few seconds to propagate
        import time

        time.sleep(10)

        return profile_name

    # --- ECR repository + image push --------------------------------------

    def _ensure_ecr_repository(self) -> str:
        """Create ECR repository if it doesn't exist. Returns the repository URI."""
        try:
            resp = self._ecr.describe_repositories(repositoryNames=[_ECR_REPO_NAME])
            uri = resp["repositories"][0]["repositoryUri"]
            logger.info("ECR repository already exists: %s", uri)
            return uri
        except self._ecr.exceptions.RepositoryNotFoundException:
            pass
        except Exception as exc:
            # For other errors (permissions etc), try to create anyway
            logger.debug("ECR describe failed: %s", exc)

        resp = self._ecr.create_repository(
            repositoryName=_ECR_REPO_NAME,
            imageScanningConfiguration={"scanOnPush": False},
            tags=[{"Key": k["Key"], "Value": k["Value"]} for k in self._TAGS],
        )
        uri = resp["repository"]["repositoryUri"]
        logger.info("Created ECR repository: %s", uri)
        return uri

    def _push_image_to_ecr(self, ecr_uri: str) -> None:
        """Build for linux/amd64, authenticate to ECR, and push the image.

        Always builds with ``--platform linux/amd64`` to ensure the image
        runs on x86_64 EC2 instances, regardless of the local machine's
        architecture (e.g. Apple Silicon ARM).

        Uses the Docker CLI via subprocess since it's available in the
        orchestration container (docker socket is mounted).
        """
        import base64

        # Get ECR auth token
        token_resp = self._ecr.get_authorization_token()
        auth_data = token_resp["authorizationData"][0]
        registry = auth_data["proxyEndpoint"]

        token = base64.b64decode(auth_data["authorizationToken"]).decode()
        _username, password = token.split(":", 1)

        # Docker login to ECR
        self._run_docker(
            ["docker", "login", "--username", "AWS", "--password-stdin", registry],
            input_data=password,
            description="ECR login",
        )

        remote_tag = f"{ecr_uri}:{_IMAGE_TAG}"

        # Always build for linux/amd64 (EC2 target architecture)
        repo_root = os.getenv("REPO_ROOT", "")
        if not repo_root or not os.path.isdir(repo_root):
            raise RuntimeError(
                "REPO_ROOT not set or not a directory. "
                "Cannot build substrate-worker image for ECR push."
            )

        dockerfile = f"{repo_root}/services/substrate-worker/Dockerfile"
        if not os.path.isfile(dockerfile):
            raise RuntimeError(
                f"Dockerfile not found at {dockerfile}. "
                "Ensure REPO_ROOT points to the repository root."
            )

        logger.info(
            "Building substrate-worker image for linux/amd64 from %s",
            repo_root,
        )
        self._run_docker(
            [
                "docker",
                "buildx",
                "build",
                "--platform",
                "linux/amd64",
                "--load",
                "-f",
                dockerfile,
                "-t",
                remote_tag,
                repo_root,
            ],
            description="Docker buildx build (linux/amd64)",
        )
        self._run_docker(
            [
                "docker",
                "build",
                "--platform",
                "linux/amd64",
                "-f",
                dockerfile,
                "-t",
                remote_tag,
                repo_root,
            ],
            description="Docker build (linux/amd64)",
        )

        # Push to ECR
        self._run_docker(
            ["docker", "push", remote_tag],
            description="Docker push",
        )
        logger.info("Pushed image to %s", remote_tag)

    # --- Docker-ready AMI lookup ------------------------------------------

    def _find_docker_ami(self) -> str:
        """Find the latest Amazon Linux 2023 AMI (Docker installed via user-data).

        We use the standard Amazon Linux 2023 AMI and install Docker via
        cloud-init user-data, which is simpler than finding ECS-optimized
        AMIs that vary by region.
        """
        resp = self._ec2.describe_images(
            Owners=["amazon"],
            Filters=[
                {"Name": "name", "Values": ["al2023-ami-2023.*-x86_64"]},
                {"Name": "state", "Values": ["available"]},
            ],
        )
        images = sorted(resp["Images"], key=lambda i: i["CreationDate"])
        if not images:
            raise RuntimeError(
                f"No Amazon Linux 2023 AMI found in {self._region}. "
                "Check your region setting."
            )
        ami_id = images[-1]["ImageId"]
        logger.info("Using Docker AMI: %s", ami_id)
        return ami_id

    # --- Helpers ----------------------------------------------------------

    @staticmethod
    def _get_public_ip() -> str | None:
        """Get the caller's public IP address."""
        try:
            resp = httpx.get("https://checkip.amazonaws.com", timeout=5)
            return resp.text.strip()
        except Exception:
            return None

    @staticmethod
    def _run_docker(
        cmd: list[str],
        *,
        description: str = "docker command",
        input_data: str | None = None,
        timeout: int = 600,
    ) -> str:
        """Run a docker CLI command via subprocess. Raises on failure."""
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            input=input_data,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"{description} failed (exit {result.returncode}):\n"
                f"  cmd: {' '.join(cmd[:5])}...\n"
                f"  stderr: {result.stderr[:2000]}"
            )
        return result.stdout


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for provisioning and teardown."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if len(sys.argv) < 2 or sys.argv[1] not in ("setup", "teardown"):
        print("Usage: python -m app.engine.aws_provisioner [setup|teardown]")
        print()
        print("  setup     Provision AWS infrastructure (ECR, SG, key pair)")
        print("  teardown  Destroy all provisioned resources")
        sys.exit(1)

    region = resolve_aws_region()
    provisioner = AWSProvisioner(region=region)

    if sys.argv[1] == "setup":
        result = provisioner.ensure_infrastructure()
        print(f"\nExport these to use the AWS backend:\n")
        print(f"  export CONNECTIVITY_BACKEND=aws")
        print(f"  export AWS_REGION={region}")
        print(f"  export AWS_SUBSTRATE_ECR_URI={result.ecr_uri}")
        print(f"  export AWS_SUBSTRATE_SECURITY_GROUP={result.security_group_id}")
        print(f"  export AWS_SUBSTRATE_KEY_PAIR={result.key_pair_name}")
    else:
        provisioner.teardown()


if __name__ == "__main__":
    main()
