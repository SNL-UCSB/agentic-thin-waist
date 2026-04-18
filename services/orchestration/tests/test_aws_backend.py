"""Unit tests for the AWS EC2 connectivity backend."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _env_with_aws(extra: dict | None = None) -> dict:
    """Minimal env vars for a valid AWSConfig."""
    env = {
        "AWS_SUBSTRATE_ECR_URI": "507836838729.dkr.ecr.us-west-1.amazonaws.com/agentic-thin-waist/substrate-worker",
        "AWS_SUBSTRATE_SECURITY_GROUP": "sg-test456",
        "AWS_REGION": "us-west-1",
        "AWS_SUBSTRATE_BOOT_TIMEOUT": "10",
        "AWS_SUBSTRATE_AUTO_PROVISION": "false",
    }
    if extra:
        env.update(extra)
    return env


def _mock_ec2_client(
    *,
    public_ip: str = "1.2.3.4",
    instance_id: str = "i-abc123",
    start_state: str = "running",
):
    """Return a mocked boto3 EC2 client."""
    ec2 = MagicMock()
    ec2.run_instances.return_value = {"Instances": [{"InstanceId": instance_id}]}
    ec2.describe_instances.return_value = {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": instance_id,
                        "State": {"Name": start_state},
                        "PublicIpAddress": public_ip
                        if start_state == "running"
                        else None,
                    }
                ]
            }
        ]
    }
    ec2.terminate_instances.return_value = {}
    return ec2


def _health_response_ok(*args, **kwargs):
    mock_client = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    mock_client.get.return_value = resp
    mock_client.__enter__ = lambda s: mock_client
    mock_client.__exit__ = MagicMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# AWSConfig tests
# ---------------------------------------------------------------------------


class TestAWSConfig:
    def test_valid_config(self, monkeypatch):
        for k, v in _env_with_aws().items():
            monkeypatch.setenv(k, v)

        from app.engine.aws_config import AWSConfig

        cfg = AWSConfig()
        cfg.validate()
        assert (
            cfg.ecr_uri
            == "507836838729.dkr.ecr.us-west-1.amazonaws.com/agentic-thin-waist/substrate-worker"
        )
        assert cfg.security_group_id == "sg-test456"
        assert cfg.region == "us-west-1"

    def test_missing_ecr_with_auto_provision_ok(self, monkeypatch):
        monkeypatch.setenv("AWS_SUBSTRATE_SECURITY_GROUP", "sg-test")
        monkeypatch.delenv("AWS_SUBSTRATE_ECR_URI", raising=False)
        monkeypatch.setenv("AWS_SUBSTRATE_AUTO_PROVISION", "true")

        from app.engine.aws_config import AWSConfig

        cfg = AWSConfig()
        cfg.validate()
        assert cfg.needs_provisioning

    def test_missing_ecr_without_auto_provision_raises(self, monkeypatch):
        monkeypatch.setenv("AWS_SUBSTRATE_SECURITY_GROUP", "sg-test")
        monkeypatch.delenv("AWS_SUBSTRATE_ECR_URI", raising=False)
        monkeypatch.setenv("AWS_SUBSTRATE_AUTO_PROVISION", "false")

        from app.engine.aws_config import AWSConfig

        cfg = AWSConfig()
        with pytest.raises(ValueError, match="AWS_SUBSTRATE_ECR_URI"):
            cfg.validate()

    def test_missing_security_group_without_auto_provision_raises(self, monkeypatch):
        monkeypatch.setenv("AWS_SUBSTRATE_ECR_URI", "test-uri")
        monkeypatch.delenv("AWS_SUBSTRATE_SECURITY_GROUP", raising=False)
        monkeypatch.setenv("AWS_SUBSTRATE_AUTO_PROVISION", "false")

        from app.engine.aws_config import AWSConfig

        cfg = AWSConfig()
        with pytest.raises(ValueError, match="AWS_SUBSTRATE_SECURITY_GROUP"):
            cfg.validate()


# ---------------------------------------------------------------------------
# AWSBackend tests
# ---------------------------------------------------------------------------


class TestAWSBackend:
    @pytest.fixture()
    def aws_env(self, monkeypatch):
        for k, v in _env_with_aws().items():
            monkeypatch.setenv(k, v)

    @pytest.fixture()
    def mock_ec2(self):
        ec2 = _mock_ec2_client()
        with patch("boto3.client", return_value=ec2):
            yield ec2

    @pytest.fixture()
    def mock_health(self):
        with patch(
            "app.engine.connectivity.httpx.Client", side_effect=_health_response_ok
        ):
            yield

    def _make_backend(self):
        from app.engine.connectivity import AWSBackend

        backend = AWSBackend()
        # Set a docker AMI ID since we're not auto-provisioning
        backend._docker_ami_id = "ami-test123"
        return backend

    def test_create_and_destroy_worker(self, aws_env, mock_ec2, mock_health):
        backend = self._make_backend()
        info = backend.create_worker({})

        assert info.backend == "aws"
        assert info.endpoint == "http://1.2.3.4:8002"
        assert info.metadata["instance_id"] == "i-abc123"
        assert info.worker_id.startswith("worker-")

        backend.destroy_worker(info.worker_id)
        mock_ec2.terminate_instances.assert_called_once_with(InstanceIds=["i-abc123"])

    def test_get_worker_info(self, aws_env, mock_ec2, mock_health):
        backend = self._make_backend()
        info = backend.create_worker({})
        assert backend.get_worker_info(info.worker_id) == info

    def test_unknown_worker_raises(self, aws_env, mock_ec2):
        backend = self._make_backend()
        with pytest.raises(KeyError, match="Unknown worker_id"):
            backend.get_worker_info("worker-nonexistent")

    def test_config_overrides(self, aws_env, mock_ec2, mock_health):
        backend = self._make_backend()

        backend.create_worker(
            {
                "ami": "ami-override",
                "instance_type": "m5.2xlarge",
                "subnet_id": "subnet-123",
                "key_pair": "my-key",
            }
        )

        call_kwargs = mock_ec2.run_instances.call_args[1]
        assert call_kwargs["ImageId"] == "ami-override"
        assert call_kwargs["InstanceType"] == "m5.2xlarge"
        assert call_kwargs["SubnetId"] == "subnet-123"
        assert call_kwargs["KeyName"] == "my-key"

    def test_instance_terminated_during_boot_raises(self, aws_env, mock_ec2):
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-abc123",
                            "State": {"Name": "terminated"},
                        }
                    ]
                }
            ]
        }

        backend = self._make_backend()
        with pytest.raises(RuntimeError, match="terminated"):
            backend.create_worker({})

        mock_ec2.terminate_instances.assert_called()

    def test_health_check_timeout_terminates(self, aws_env, mock_ec2, monkeypatch):
        def _health_fail(*args, **kwargs):
            mock_client = MagicMock()
            mock_client.get.side_effect = httpx.ConnectError("refused")
            mock_client.__enter__ = lambda s: mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            return mock_client

        monkeypatch.setenv("AWS_SUBSTRATE_BOOT_TIMEOUT", "1")
        with patch("app.engine.connectivity.httpx.Client", side_effect=_health_fail):
            with patch("app.engine.connectivity.time.sleep"):
                backend = self._make_backend()
                with pytest.raises(TimeoutError, match="did not become healthy"):
                    backend.create_worker({})

        mock_ec2.terminate_instances.assert_called()

    def test_missing_env_vars_without_auto_provision_raises(self, monkeypatch):
        monkeypatch.delenv("AWS_SUBSTRATE_ECR_URI", raising=False)
        monkeypatch.delenv("AWS_SUBSTRATE_SECURITY_GROUP", raising=False)
        monkeypatch.setenv("AWS_SUBSTRATE_AUTO_PROVISION", "false")

        with pytest.raises(ValueError, match="AWS_SUBSTRATE_ECR_URI"):
            self._make_backend()


# ---------------------------------------------------------------------------
# ConnectivityManager integration
# ---------------------------------------------------------------------------


class TestConnectivityManagerAWS:
    def test_selects_aws_backend(self, monkeypatch):
        for k, v in _env_with_aws().items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("CONNECTIVITY_BACKEND", "aws")

        with patch("boto3.client", return_value=_mock_ec2_client()):
            from app.engine.connectivity import ConnectivityManager

            mgr = ConnectivityManager()
            assert mgr.backend_name == "aws"


# ---------------------------------------------------------------------------
# User-data generation
# ---------------------------------------------------------------------------


class TestUserData:
    def test_user_data_contains_docker_run(self):
        from app.engine.connectivity import _build_user_data

        script = _build_user_data(
            worker_image="507836838729.dkr.ecr.us-west-1.amazonaws.com/repo:latest",
            telemetry_url="http://telemetry:8004",
            ecr_region="us-west-1",
        )
        assert "docker run" in script
        assert "--privileged" in script
        assert "--net=host" in script
        assert "TELEMETRY_SERVICE_URL=http://telemetry:8004" in script

    def test_user_data_ecr_login(self):
        from app.engine.connectivity import _build_user_data

        script = _build_user_data(
            worker_image="507836838729.dkr.ecr.us-west-1.amazonaws.com/repo:latest",
            telemetry_url="",
            ecr_region="us-west-1",
        )
        assert "aws ecr get-login-password" in script
        assert "docker login" in script
        assert "docker pull" in script

    def test_user_data_no_ecr_login_for_local_image(self):
        from app.engine.connectivity import _build_user_data

        script = _build_user_data(
            worker_image="substrate-worker",
            telemetry_url="",
            ecr_region="",
        )
        assert "ecr get-login-password" not in script

    def test_user_data_installs_docker(self):
        from app.engine.connectivity import _build_user_data

        script = _build_user_data(
            worker_image="substrate-worker",
            telemetry_url="",
        )
        assert "yum install" in script
        assert "docker" in script
