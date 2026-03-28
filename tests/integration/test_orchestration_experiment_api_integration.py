from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

from app.engine.executor import DownstreamClients

EXPERIMENT_API_URL = os.getenv(
    "EXPERIMENT_API_URL", "http://experiment-api:8000"
).rstrip("/")


def _wait_for_health(url: str, timeout_seconds: float = 60.0) -> str:
    deadline = time.time() + timeout_seconds
    last_error = "healthcheck did not run"

    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return url
            last_error = (
                f"unexpected status={response.status_code} body={response.text[:200]}"
            )
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(1)

    raise AssertionError(f"service at {url} did not become healthy: {last_error}")


@pytest.fixture(scope="session")
def experiment_api_ready() -> str:
    _wait_for_health(f"{EXPERIMENT_API_URL}/health")
    return EXPERIMENT_API_URL


@pytest.fixture()
def clients(experiment_api_ready: str) -> DownstreamClients:
    return DownstreamClients(experiment_api_url=EXPERIMENT_API_URL)


def test_orchestration_can_reach_live_experiment_api_health(
    clients: DownstreamClients,
    experiment_api_ready: str,
) -> None:
    orchestration_health = clients.health()
    assert orchestration_health["experiment_api"] == "reachable"

    response = requests.get(f"{experiment_api_ready}/status", timeout=5)
    response.raise_for_status()
    payload = response.json()

    assert payload["status"] == "healthy"
    assert payload["services"]["ctp_service"] == "http://ctp-service:8001"
    assert payload["services"]["telemetry_service"] == "http://telemetry-service:8004"


def test_orchestration_can_register_and_read_back_experiment_via_experiment_api(
    clients: DownstreamClients,
) -> None:
    experiment_id = f"orch-exp-{uuid.uuid4().hex[:12]}"
    payload = {
        "experiment_id": experiment_id,
        "application": "youtube",
        "capacity_mbps": 25.0,
        "latency_ms": 40.0,
        "aqm_policy": "fq_codel",
        "num_trials": 1,
        "ctp_cluster": "cluster0",
        "orchestration_id": f"orch-{uuid.uuid4().hex[:8]}",
    }

    created = clients.run_experiment(payload)
    assert created["experiment_id"] == experiment_id
    assert created["status"] == "pending"
    assert created["spec"]["application"] == payload["application"]
    assert created["spec"]["orchestration_id"] == payload["orchestration_id"]

    fetched = clients.get_experiment(experiment_id)
    assert fetched == created

    all_experiments = clients.list_experiments()
    matching = [
        item for item in all_experiments if item["experiment_id"] == experiment_id
    ]
    assert len(matching) == 1
    assert matching[0]["status"] == "pending"
    assert matching[0]["spec"]["capacity_mbps"] == pytest.approx(
        payload["capacity_mbps"]
    )
    assert matching[0]["spec"]["latency_ms"] == pytest.approx(payload["latency_ms"])
