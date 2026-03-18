"""
Global pytest fixtures for integration and E2E tests.

Service base URLs are read from environment variables so the same tests run:
  - inside the Docker Compose network (using internal hostnames), and
  - from the GitHub Actions runner (using localhost ports).
"""

import os
import pytest
import requests


def _url(env_var: str, default: str) -> str:
    return os.environ.get(env_var, default).rstrip("/")


@pytest.fixture(scope="session")
def experiment_api_url() -> str:
    return _url("EXPERIMENT_API_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def ctp_service_url() -> str:
    return _url("CTP_SERVICE_URL", "http://localhost:8001")


@pytest.fixture(scope="session")
def substrate_worker_url() -> str:
    return _url("SUBSTRATE_WORKER_URL", "http://localhost:8002")


@pytest.fixture(scope="session")
def netgent_service_url() -> str:
    return _url("NETGENT_SERVICE_URL", "http://localhost:8003")


@pytest.fixture(scope="session")
def telemetry_service_url() -> str:
    return _url("TELEMETRY_SERVICE_URL", "http://localhost:8004")


@pytest.fixture(scope="session")
def orchestration_url() -> str:
    return _url("ORCHESTRATION_URL", "http://localhost:8005")


@pytest.fixture(scope="session")
def http() -> requests.Session:
    """A pre-configured requests.Session for integration tests."""
    return requests.Session()
