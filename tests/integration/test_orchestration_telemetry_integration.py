from __future__ import annotations

import os
import time
import uuid
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor
import pytest
import requests

from app.engine.executor import DownstreamClients
from app.engine.orchestration_workflow import _build_telemetry_result_payload

TELEMETRY_SERVICE_URL = os.getenv(
    "TELEMETRY_SERVICE_URL", "http://telemetry-service:8004"
).rstrip("/")


def _wait_for_health(url: str, timeout_seconds: float = 60.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "healthcheck did not run"

    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return
            last_error = f"unexpected status={response.status_code} body={response.text[:200]}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(1)

    raise AssertionError(f"service at {url} did not become healthy: {last_error}")


def _db_connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "telemetry"),
        user=os.getenv("DB_USER", "admin"),
        password=os.getenv("DB_PASSWORD", "admin123"),
        cursor_factory=RealDictCursor,
    )


def _fetch_result_row(experiment_id: str) -> dict[str, Any] | None:
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    result_id,
                    experiment_id,
                    application,
                    status,
                    configured_capacity,
                    configured_latency,
                    measured_throughput,
                    measured_rtt,
                    pcap_path,
                    qoe_metrics,
                    contextual_tree
                FROM results
                WHERE experiment_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (experiment_id,),
            )
            row = cur.fetchone()
    return dict(row) if row else None


@pytest.fixture(scope="session")
def telemetry_service_ready() -> str:
    _wait_for_health(f"{TELEMETRY_SERVICE_URL}/health")
    return TELEMETRY_SERVICE_URL


@pytest.fixture()
def clients(telemetry_service_ready: str) -> DownstreamClients:
    return DownstreamClients(telemetry_service_url=telemetry_service_ready)


def test_orchestration_result_roundtrip_persists_in_telemetry_db(
    clients: DownstreamClients,
) -> None:
    experiment_id = f"orch-tel-{uuid.uuid4().hex[:12]}"
    orchestration_id = f"orch-{uuid.uuid4().hex[:8]}"

    spec = {
        "experiment_id": experiment_id,
        "application": "youtube",
        "capacity_mbps": 25.0,
        "latency_ms": 40.0,
        "num_trials": 1,
        "aqm_policy": "fq_codel",
        "ctp_cluster": "cluster0",
    }
    shape_result = {
        "bottleneck_state": {
            "configured_capacity": spec["capacity_mbps"],
            "configured_latency": spec["latency_ms"],
            "aqm_policy": spec["aqm_policy"],
        }
    }
    capture_status = {"pcap_path": f"s3://telemetry-artifacts/{experiment_id}.pcap"}
    netgent_result = {
        "status": "completed",
        "video_startup_time_ms": 1250,
        "mean_bitrate_mbps": 7.5,
        "rebuffer_events": 1,
    }
    dynamic_state = {
        "bottleneck_state": {
            "download_mbps": 24.25,
            "latency_ms": 41.5,
        }
    }

    payload = _build_telemetry_result_payload(
        spec=spec,
        orch_id=orchestration_id,
        shape_result=shape_result,
        capture_status=capture_status,
        netgent_result=netgent_result,
        dynamic_state=dynamic_state,
    )

    post_response = clients.post_result(payload)
    assert post_response["status"] == "stored"
    result_id = post_response["result_id"]

    query_response = clients.query_results({"experiment_id": experiment_id, "limit": 10})
    assert "warning" not in query_response
    assert query_response["returned"] >= 1

    stored_result = next(
        item for item in query_response["results"] if item["result_id"] == result_id
    )
    assert stored_result["experiment_id"] == experiment_id
    assert stored_result["application"] == spec["application"]
    assert stored_result["status"] == payload["status"]
    assert stored_result["configured_capacity"] == pytest.approx(spec["capacity_mbps"])
    assert stored_result["configured_latency"] == pytest.approx(spec["latency_ms"])
    assert stored_result["pcap_path"] == capture_status["pcap_path"]
    assert stored_result["qoe_metrics"]["mean_bitrate_mbps"] == pytest.approx(
        netgent_result["mean_bitrate_mbps"]
    )
    assert stored_result["contextual_tree"]["orchestration_id"] == orchestration_id

    row = _fetch_result_row(experiment_id)
    assert row is not None
    assert row["result_id"] == result_id
    assert row["experiment_id"] == experiment_id
    assert row["application"] == spec["application"]
    assert row["status"] == payload["status"]
    assert row["configured_capacity"] == pytest.approx(spec["capacity_mbps"])
    assert row["configured_latency"] == pytest.approx(spec["latency_ms"])
    assert row["measured_throughput"] == pytest.approx(
        dynamic_state["bottleneck_state"]["download_mbps"]
    )
    assert row["measured_rtt"] == pytest.approx(
        dynamic_state["bottleneck_state"]["latency_ms"]
    )
    assert row["pcap_path"] == capture_status["pcap_path"]
    assert row["qoe_metrics"]["status"] == netgent_result["status"]
    assert row["qoe_metrics"]["video_startup_time_ms"] == netgent_result[
        "video_startup_time_ms"
    ]
    assert row["contextual_tree"]["orchestration_id"] == orchestration_id
    assert row["contextual_tree"]["c_app"]["application"] == spec["application"]
