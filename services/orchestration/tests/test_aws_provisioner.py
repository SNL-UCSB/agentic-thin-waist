"""Unit tests for the AWS auto-provisioner (ECR-based)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_ec2():
    """Return a mocked boto3 EC2 client."""
    ec2 = MagicMock()

    ec2.exceptions = MagicMock()
    ec2.exceptions.ClientError = type("ClientError", (Exception,), {})
    ec2.describe_key_pairs.side_effect = ec2.exceptions.ClientError()

    ec2.create_key_pair.return_value = {
        "KeyMaterial": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
        "KeyName": "agentic-substrate-worker",
    }

    ec2.describe_security_groups.return_value = {"SecurityGroups": []}
    ec2.describe_vpcs.return_value = {"Vpcs": [{"VpcId": "vpc-test123"}]}
    ec2.create_security_group.return_value = {"GroupId": "sg-test456"}
    ec2.authorize_security_group_ingress.return_value = {}

    # AMI lookup
    ec2.describe_images.return_value = {
        "Images": [
            {
                "ImageId": "ami-docker123",
                "CreationDate": "2024-01-01T00:00:00Z",
                "State": "available",
            }
        ]
    }

    ec2.terminate_instances.return_value = {}
    return ec2


def _mock_ecr():
    """Return a mocked boto3 ECR client."""
    ecr = MagicMock()

    ecr.exceptions = MagicMock()
    ecr.exceptions.RepositoryNotFoundException = type(
        "RepositoryNotFoundException", (Exception,), {}
    )

    # Repo doesn't exist yet
    ecr.describe_repositories.side_effect = ecr.exceptions.RepositoryNotFoundException()
    ecr.create_repository.return_value = {
        "repository": {
            "repositoryUri": "507836838729.dkr.ecr.us-west-1.amazonaws.com/agentic-thin-waist/substrate-worker"
        }
    }
    import base64

    ecr.get_authorization_token.return_value = {
        "authorizationData": [
            {
                "authorizationToken": base64.b64encode(b"AWS:mock-password").decode(),
                "proxyEndpoint": "https://507836838729.dkr.ecr.us-west-1.amazonaws.com",
            }
        ]
    }
    ecr.delete_repository.return_value = {}
    return ecr


def _mock_sts():
    sts = MagicMock()
    sts.get_caller_identity.return_value = {"Account": "507836838729"}
    return sts


def _mock_iam():
    iam = MagicMock()
    iam.exceptions = MagicMock()
    iam.exceptions.EntityAlreadyExistsException = type(
        "EntityAlreadyExistsException", (Exception,), {}
    )
    iam.exceptions.LimitExceededException = type(
        "LimitExceededException", (Exception,), {}
    )
    # Instance profile doesn't exist yet
    iam.get_instance_profile.side_effect = Exception("not found")
    iam.create_role.return_value = {}
    iam.attach_role_policy.return_value = {}
    iam.create_instance_profile.return_value = {}
    iam.add_role_to_instance_profile.return_value = {}
    iam.remove_role_from_instance_profile.return_value = {}
    iam.delete_instance_profile.return_value = {}
    iam.detach_role_policy.return_value = {}
    iam.delete_role.return_value = {}
    return iam


def _mock_boto3_clients(ec2=None, ecr=None, sts=None, iam=None):
    """Patch boto3.client to return different mocks per service."""
    _ec2 = ec2 or _mock_ec2()
    _ecr = ecr or _mock_ecr()
    _sts = sts or _mock_sts()
    _iam = iam or _mock_iam()

    def client_factory(service, **kwargs):
        return {"ec2": _ec2, "ecr": _ecr, "sts": _sts, "iam": _iam}[service]

    return client_factory, _ec2, _ecr, _sts


# ---------------------------------------------------------------------------
# ProvisioningProgress tests
# ---------------------------------------------------------------------------


class TestProvisioningProgress:
    def test_progress_renders(self, capsys):
        from app.engine.aws_provisioner import ProvisioningProgress

        p = ProvisioningProgress(total_steps=3)
        p.update("Step 1")
        p.update("Step 2")
        p.update("Step 3")
        p.complete()

        captured = capsys.readouterr()
        assert "Step 1" in captured.err
        assert "Step 3" in captured.err
        assert "Done!" in captured.err


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------


class TestCache:
    def test_save_and_load(self, tmp_path, monkeypatch):
        from app.engine import aws_provisioner

        monkeypatch.setattr(aws_provisioner, "_CACHE_FILE", tmp_path / "cache.json")
        monkeypatch.setattr(aws_provisioner, "_CACHE_DIR", tmp_path)

        aws_provisioner._save_cache({"us-west-1": {"ecr_uri": "test"}})
        loaded = aws_provisioner._load_cache()
        assert loaded["us-west-1"]["ecr_uri"] == "test"

    def test_load_missing_file(self, tmp_path, monkeypatch):
        from app.engine import aws_provisioner

        monkeypatch.setattr(
            aws_provisioner, "_CACHE_FILE", tmp_path / "nonexistent.json"
        )
        assert aws_provisioner._load_cache() == {}

    def test_clear_cache(self, tmp_path, monkeypatch):
        from app.engine import aws_provisioner

        cache_file = tmp_path / "cache.json"
        monkeypatch.setattr(aws_provisioner, "_CACHE_FILE", cache_file)
        monkeypatch.setattr(aws_provisioner, "_CACHE_DIR", tmp_path)

        aws_provisioner._save_cache({"data": True})
        aws_provisioner._clear_cache()
        assert not cache_file.exists()


# ---------------------------------------------------------------------------
# AWSProvisioner tests
# ---------------------------------------------------------------------------


class TestAWSProvisioner:
    @pytest.fixture(autouse=True)
    def setup_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AWS_REGION", "us-west-1")

        # Set REPO_ROOT to the actual repo root (for Dockerfile path checks)
        import pathlib

        repo_root = pathlib.Path(__file__).resolve().parent.parent.parent.parent
        monkeypatch.setenv("REPO_ROOT", str(repo_root))

        from app.engine import aws_provisioner

        self.cache_dir = tmp_path / "cache"
        self.key_dir = tmp_path / "keys"
        monkeypatch.setattr(aws_provisioner, "_CACHE_DIR", self.cache_dir)
        monkeypatch.setattr(
            aws_provisioner, "_CACHE_FILE", self.cache_dir / "aws-resources.json"
        )
        monkeypatch.setattr(aws_provisioner, "_KEY_DIR", self.key_dir)

    @pytest.fixture()
    def mock_clients(self):
        factory, ec2, ecr, sts = _mock_boto3_clients()
        with patch("boto3.client", side_effect=factory):
            yield ec2, ecr, sts

    @pytest.fixture()
    def mock_docker(self):
        with patch("app.engine.aws_provisioner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            yield mock_run

    @pytest.fixture()
    def mock_docker(self):
        with patch("app.engine.aws_provisioner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            yield mock_run

    @pytest.fixture()
    def mock_public_ip(self):
        with patch("app.engine.aws_provisioner.httpx.get") as mock_get:
            resp = MagicMock()
            resp.text = "1.2.3.4"
            mock_get.return_value = resp
            yield

    @pytest.fixture()
    def mock_sleep(self):
        with patch("app.engine.aws_provisioner.time.sleep"):
            yield

    def _make_provisioner(self):
        from app.engine.aws_provisioner import AWSProvisioner

        return AWSProvisioner(region="us-west-1")

    def test_ensure_infrastructure_full_flow(
        self, mock_clients, mock_docker, mock_public_ip, mock_sleep
    ):
        ec2, ecr, _sts = mock_clients

        provisioner = self._make_provisioner()
        result = provisioner.ensure_infrastructure()

        assert (
            result.ecr_uri
            == "507836838729.dkr.ecr.us-west-1.amazonaws.com/agentic-thin-waist/substrate-worker"
        )
        assert result.security_group_id == "sg-test456"
        assert result.key_pair_name == "agentic-substrate-worker"
        assert result.docker_ami_id == "ami-docker123"

        # Verify ECR repo was created
        ecr.create_repository.assert_called_once()

        # Verify docker commands were run (login, tag, push)
        docker_calls = mock_docker.call_args_list
        cmds = [c[0][0] for c in docker_calls]
        # Should have: login, image inspect, tag, push
        assert any("login" in str(c) for c in cmds)
        assert any("push" in str(c) for c in cmds)

        # Verify cache was written
        cache_file = self.cache_dir / "aws-resources.json"
        assert cache_file.exists()
        cached = json.loads(cache_file.read_text())
        assert cached["us-west-1"]["ecr_uri"] == result.ecr_uri

    def test_cached_resources_reused(self, mock_clients):
        ec2, ecr, _sts = mock_clients

        # Pre-populate cache
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "aws-resources.json").write_text(
            json.dumps(
                {
                    "us-west-1": {
                        "ecr_uri": "507836838729.dkr.ecr.us-west-1.amazonaws.com/cached",
                        "security_group_id": "sg-cached",
                        "key_pair_name": "cached-key",
                        "docker_ami_id": "ami-cached",
                    }
                }
            )
        )

        # Make validation pass
        ecr.describe_repositories.side_effect = None
        ecr.describe_repositories.return_value = {
            "repositories": [{"repositoryUri": "cached"}]
        }
        ec2.describe_security_groups.return_value = {
            "SecurityGroups": [{"GroupId": "sg-cached"}]
        }
        ec2.describe_images.return_value = {
            "Images": [{"ImageId": "ami-cached", "State": "available"}]
        }

        provisioner = self._make_provisioner()
        result = provisioner.ensure_infrastructure()

        assert result.ecr_uri == "507836838729.dkr.ecr.us-west-1.amazonaws.com/cached"
        assert result.security_group_id == "sg-cached"
        # No ECR repo should have been created
        ecr.create_repository.assert_not_called()

    def test_stale_cache_reprovisions(
        self, mock_clients, mock_docker, mock_public_ip, mock_sleep
    ):
        ec2, ecr, _sts = mock_clients

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "aws-resources.json").write_text(
            json.dumps(
                {
                    "us-west-1": {
                        "ecr_uri": "old-uri",
                        "security_group_id": "sg-deleted",
                        "key_pair_name": "old-key",
                        "docker_ami_id": "ami-deleted",
                    }
                }
            )
        )

        # Validation fails — SG doesn't exist
        call_count = [0]

        def describe_sg_side_effect(**kwargs):
            call_count[0] += 1
            # First call is validation (GroupIds=) — fail
            if "GroupIds" in kwargs:
                raise Exception("not found")
            # Subsequent calls with Filters are for creation flow
            return {"SecurityGroups": []}

        ec2.describe_security_groups.side_effect = describe_sg_side_effect
        ec2.create_security_group.return_value = {"GroupId": "sg-new"}
        ec2.describe_vpcs.return_value = {"Vpcs": [{"VpcId": "vpc-123"}]}

        # ECR create works
        ecr.describe_repositories.side_effect = (
            ecr.exceptions.RepositoryNotFoundException()
        )
        ecr.create_repository.return_value = {
            "repository": {"repositoryUri": "new-ecr-uri"}
        }

        provisioner = self._make_provisioner()
        result = provisioner.ensure_infrastructure()

        assert result.ecr_uri == "new-ecr-uri"
        assert result.security_group_id == "sg-new"

    def test_teardown(self, mock_clients):
        _ec2, ecr, _sts = mock_clients
        ec2 = _ec2

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "aws-resources.json").write_text(
            json.dumps(
                {
                    "us-west-1": {
                        "ecr_uri": "ecr-uri",
                        "security_group_id": "sg-teardown",
                        "key_pair_name": "key-teardown",
                        "docker_ami_id": "ami-123",
                    }
                }
            )
        )

        provisioner = self._make_provisioner()
        provisioner.teardown()

        ecr.delete_repository.assert_called_once()
        ec2.delete_security_group.assert_called_with(GroupId="sg-teardown")
        ec2.delete_key_pair.assert_called_with(KeyName="key-teardown")

        cached = json.loads((self.cache_dir / "aws-resources.json").read_text())
        assert "us-west-1" not in cached

    def test_teardown_no_cache(self, mock_clients):
        _ec2, ecr, _sts = mock_clients
        provisioner = self._make_provisioner()
        provisioner.teardown()
        ecr.delete_repository.assert_not_called()

    def test_no_default_vpc_raises(self, mock_clients, mock_public_ip):
        ec2, _ecr, _sts = mock_clients
        ec2.describe_vpcs.return_value = {"Vpcs": []}

        provisioner = self._make_provisioner()
        with pytest.raises(RuntimeError, match="No default VPC"):
            provisioner._ensure_security_group()

    def test_ecr_repo_already_exists(self, mock_clients):
        _ec2, ecr, _sts = mock_clients

        ecr.describe_repositories.side_effect = None
        ecr.describe_repositories.return_value = {
            "repositories": [
                {
                    "repositoryUri": "507836838729.dkr.ecr.us-west-1.amazonaws.com/existing"
                }
            ]
        }

        provisioner = self._make_provisioner()
        uri = provisioner._ensure_ecr_repository()

        assert uri == "507836838729.dkr.ecr.us-west-1.amazonaws.com/existing"
        ecr.create_repository.assert_not_called()


# ---------------------------------------------------------------------------
# Integration with AWSBackend
# ---------------------------------------------------------------------------


class TestAWSBackendAutoProvision:
    def test_auto_provision_on_first_create(self, monkeypatch):
        monkeypatch.setenv("AWS_REGION", "us-west-1")
        monkeypatch.setenv("AWS_SUBSTRATE_ECR_URI", "")
        monkeypatch.setenv("AWS_SUBSTRATE_SECURITY_GROUP", "")
        monkeypatch.setenv("AWS_SUBSTRATE_AUTO_PROVISION", "true")

        from app.engine.aws_provisioner import ProvisionedResources

        mock_result = ProvisionedResources(
            ecr_uri="507836838729.dkr.ecr.us-west-1.amazonaws.com/repo",
            security_group_id="sg-auto",
            key_pair_name="auto-key",
            docker_ami_id="ami-auto",
        )

        ec2 = _mock_ec2()
        ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-worker",
                            "State": {"Name": "running"},
                            "PublicIpAddress": "5.6.7.8",
                        }
                    ]
                }
            ]
        }

        factory, _, _, _ = _mock_boto3_clients(ec2=ec2)
        with (
            patch("boto3.client", side_effect=factory),
            patch(
                "app.engine.aws_provisioner.AWSProvisioner.ensure_infrastructure",
                return_value=mock_result,
            ),
            patch("app.engine.connectivity.httpx.Client") as mock_httpx,
        ):
            mock_client = MagicMock()
            resp = MagicMock()
            resp.status_code = 200
            mock_client.get.return_value = resp
            mock_client.__enter__ = lambda s: mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_httpx.return_value = mock_client

            from app.engine.connectivity import AWSBackend

            backend = AWSBackend()
            info = backend.create_worker({})

            assert info.backend == "aws"
            assert info.endpoint == "http://5.6.7.8:8002"

    def test_no_auto_provision_when_configured(self, monkeypatch):
        monkeypatch.setenv("AWS_REGION", "us-west-1")
        monkeypatch.setenv("AWS_SUBSTRATE_ECR_URI", "manual-ecr")
        monkeypatch.setenv("AWS_SUBSTRATE_SECURITY_GROUP", "sg-manual")
        monkeypatch.setenv("AWS_SUBSTRATE_AUTO_PROVISION", "false")

        ec2 = _mock_ec2()
        factory, _, _, _ = _mock_boto3_clients(ec2=ec2)
        with (
            patch("boto3.client", side_effect=factory),
            patch(
                "app.engine.aws_provisioner.AWSProvisioner.ensure_infrastructure"
            ) as mock_provision,
        ):
            from app.engine.connectivity import AWSBackend

            backend = AWSBackend()
            assert not backend._config.needs_provisioning
            mock_provision.assert_not_called()
