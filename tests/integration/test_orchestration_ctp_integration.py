from __future__ import annotations

import os
import time
import uuid

import psycopg2
from psycopg2.extras import Json, RealDictCursor
import pytest
import requests

from app.engine.executor import DownstreamClients

CTP_SERVICE_URL = os.getenv("CTP_SERVICE_URL", "http://ctp-service:8001").rstrip("/")
CTP_DB_NAME = os.getenv("CTP_DB_NAME", os.getenv("DB_NAME", "telemetry"))


def _wait_for_ctp_health(timeout_seconds: float = 90.0) -> str:
    deadline = time.time() + timeout_seconds
    last_error = "healthcheck did not run"
    health_url = f"{CTP_SERVICE_URL}/health"

    while time.time() < deadline:
        try:
            response = requests.get(health_url, timeout=5)
            payload = response.json()
            if (
                response.status_code == 200
                and payload.get("status") == "healthy"
                and payload.get("postgresql_connected") is True
            ):
                return health_url
            last_error = f"unexpected status={response.status_code} payload={payload!r}"
        except (ValueError, requests.RequestException) as exc:
            last_error = str(exc)
        time.sleep(1)

    raise AssertionError(
        f"service at {health_url} did not become healthy: {last_error}"
    )


def _db_connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=CTP_DB_NAME,
        user=os.getenv("DB_USER", "admin"),
        password=os.getenv("DB_PASSWORD", "admin123"),
        cursor_factory=RealDictCursor,
    )


def _seed_ctp_dataset(dataset_name: str) -> list[dict]:
    seeded_rows = [
        {
            "ctp_id": f"{dataset_name}-high",
            "dataset_name": dataset_name,
            "subnet": "169.231.10.0/24",
            "window_index": 0,
            "extracted_from": f"/captures/{dataset_name}.pcap",
            "duration_seconds": 30,
            "upload_timeseries": [1.0, 3.0, 5.0, 7.0],
            "download_timeseries": [12.0, 15.0, 18.0, 21.0],
            "contributor_count": 12,
            "intensity": {
                "mean_pps": 320.0,
                "mean_bps": 18_200_000.0,
                "mean_mbps": 18.2,
                "peak_pps": 440.0,
                "peak_bps": 24_500_000.0,
            },
            "burstiness": {
                "peak_to_mean_ratio": 2.4,
                "coefficient_of_variation": 0.82,
                "percentile_95_to_mean": 1.6,
                "on_periods": 5,
                "off_periods": 2,
            },
            "temporal_correlation": {
                "lag_1": 0.91,
                "lag_5": 0.77,
                "lag_10": 0.66,
                "lag_60": None,
            },
            "structure": {
                "contributor_count": 12,
                "unique_source_ips": 12,
                "unique_dest_ips": 4,
                "upload_download_ratio": 0.65,
                "prefix_diversity": 0.72,
            },
        },
        {
            "ctp_id": f"{dataset_name}-medium",
            "dataset_name": dataset_name,
            "subnet": "169.231.11.0/24",
            "window_index": 1,
            "extracted_from": f"/captures/{dataset_name}.pcap",
            "duration_seconds": 30,
            "upload_timeseries": [2.0, 4.0, 4.0, 6.0],
            "download_timeseries": [8.0, 11.0, 12.0, 15.0],
            "contributor_count": 7,
            "intensity": {
                "mean_pps": 215.0,
                "mean_bps": 11_400_000.0,
                "mean_mbps": 11.4,
                "peak_pps": 280.0,
                "peak_bps": 15_800_000.0,
            },
            "burstiness": {
                "peak_to_mean_ratio": 1.8,
                "coefficient_of_variation": 0.46,
                "percentile_95_to_mean": 1.3,
                "on_periods": 4,
                "off_periods": 1,
            },
            "temporal_correlation": {
                "lag_1": 0.73,
                "lag_5": 0.58,
                "lag_10": 0.42,
                "lag_60": None,
            },
            "structure": {
                "contributor_count": 7,
                "unique_source_ips": 7,
                "unique_dest_ips": 3,
                "upload_download_ratio": 0.85,
                "prefix_diversity": 0.55,
            },
        },
        {
            "ctp_id": f"{dataset_name}-excluded",
            "dataset_name": dataset_name,
            "subnet": "169.231.12.9/32",
            "window_index": 2,
            "extracted_from": f"/captures/{dataset_name}.pcap",
            "duration_seconds": 30,
            "upload_timeseries": [3.0, 3.0, 4.0, 3.0],
            "download_timeseries": [2.0, 3.0, 3.0, 2.0],
            "contributor_count": 2,
            "intensity": {
                "mean_pps": 94.0,
                "mean_bps": 6_200_000.0,
                "mean_mbps": 6.2,
                "peak_pps": 130.0,
                "peak_bps": 8_000_000.0,
            },
            "burstiness": {
                "peak_to_mean_ratio": 1.4,
                "coefficient_of_variation": 0.22,
                "percentile_95_to_mean": 1.1,
                "on_periods": 2,
                "off_periods": 0,
            },
            "temporal_correlation": {
                "lag_1": 0.38,
                "lag_5": 0.12,
                "lag_10": 0.0,
                "lag_60": None,
            },
            "structure": {
                "contributor_count": 2,
                "unique_source_ips": 2,
                "unique_dest_ips": 1,
                "upload_download_ratio": 1.4,
                "prefix_diversity": 0.18,
            },
        },
    ]

    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO datasets (
                    dataset_name,
                    pcap_source,
                    window_duration_sec,
                    burst_interval_ms,
                    gateway_subnet,
                    total_windows,
                    total_users
                ) VALUES (%s, %s, %s, %s, %s::cidr, %s, %s)
                ON CONFLICT (dataset_name) DO UPDATE SET
                    pcap_source = EXCLUDED.pcap_source,
                    window_duration_sec = EXCLUDED.window_duration_sec,
                    burst_interval_ms = EXCLUDED.burst_interval_ms,
                    gateway_subnet = EXCLUDED.gateway_subnet,
                    total_windows = EXCLUDED.total_windows,
                    total_users = EXCLUDED.total_users
                """,
                (
                    dataset_name,
                    f"/captures/{dataset_name}.pcap",
                    30,
                    100,
                    "169.231.0.0/16",
                    3,
                    21,
                ),
            )

            for row in seeded_rows:
                cur.execute(
                    """
                    INSERT INTO ctp_nodes (
                        ctp_id,
                        dataset_name,
                        subnet,
                        window_index,
                        extracted_from,
                        duration_seconds,
                        upload_timeseries,
                        download_timeseries,
                        contributor_count,
                        intensity,
                        burstiness,
                        temporal_correlation,
                        structure
                    ) VALUES (
                        %(ctp_id)s,
                        %(dataset_name)s,
                        %(subnet)s::cidr,
                        %(window_index)s,
                        %(extracted_from)s,
                        %(duration_seconds)s,
                        %(upload_timeseries)s,
                        %(download_timeseries)s,
                        %(contributor_count)s,
                        %(intensity)s,
                        %(burstiness)s,
                        %(temporal_correlation)s,
                        %(structure)s
                    )
                    ON CONFLICT (ctp_id) DO UPDATE SET
                        dataset_name = EXCLUDED.dataset_name,
                        subnet = EXCLUDED.subnet,
                        window_index = EXCLUDED.window_index,
                        extracted_from = EXCLUDED.extracted_from,
                        duration_seconds = EXCLUDED.duration_seconds,
                        upload_timeseries = EXCLUDED.upload_timeseries,
                        download_timeseries = EXCLUDED.download_timeseries,
                        contributor_count = EXCLUDED.contributor_count,
                        intensity = EXCLUDED.intensity,
                        burstiness = EXCLUDED.burstiness,
                        temporal_correlation = EXCLUDED.temporal_correlation,
                        structure = EXCLUDED.structure
                    """,
                    {
                        **row,
                        "intensity": Json(row["intensity"]),
                        "burstiness": Json(row["burstiness"]),
                        "temporal_correlation": Json(row["temporal_correlation"]),
                        "structure": Json(row["structure"]),
                    },
                )

    return seeded_rows


@pytest.fixture(scope="session")
def ctp_service_ready() -> str:
    return _wait_for_ctp_health()


@pytest.fixture()
def clients(ctp_service_ready: str) -> DownstreamClients:
    return DownstreamClients(ctp_service_url=CTP_SERVICE_URL)


@pytest.fixture()
def seeded_ctp_dataset(ctp_service_ready: str) -> dict:
    dataset_name = f"orch-ctp-{uuid.uuid4().hex[:12]}"
    seeded_rows = _seed_ctp_dataset(dataset_name)

    try:
        yield {"dataset_name": dataset_name, "rows": seeded_rows}
    finally:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM ctp_nodes WHERE dataset_name = %s", (dataset_name,)
                )
                cur.execute(
                    "DELETE FROM datasets WHERE dataset_name = %s", (dataset_name,)
                )


def test_orchestration_ctp_health_reports_real_db_connectivity(
    clients: DownstreamClients,
    ctp_service_ready: str,
) -> None:
    orchestration_health = clients.health()
    assert orchestration_health["ctp_service"] == "reachable"

    response = requests.get(ctp_service_ready, timeout=5)
    response.raise_for_status()
    payload = response.json()

    assert payload["status"] == "healthy"
    assert payload["postgresql_connected"] is True


def test_orchestration_can_list_live_ctps(
    clients: DownstreamClients,
    seeded_ctp_dataset: dict,
) -> None:
    seeded_rows = seeded_ctp_dataset["rows"]
    seeded_ids = {row["ctp_id"] for row in seeded_rows}

    response = clients.list_ctps(limit=200)
    assert response["total"] >= len(seeded_rows)
    assert response["returned"] >= len(seeded_rows)

    listed_by_id = {ctp["ctp_id"]: ctp for ctp in response["ctps"]}
    assert seeded_ids.issubset(listed_by_id)

    highest = listed_by_id[seeded_rows[0]["ctp_id"]]
    assert highest["dataset_name"] == seeded_ctp_dataset["dataset_name"]
    assert highest["subnet"] == seeded_rows[0]["subnet"]
    assert highest["intensity"]["mean_mbps"] == pytest.approx(
        seeded_rows[0]["intensity"]["mean_mbps"]
    )
    assert (
        highest["structure"]["contributor_count"]
        == seeded_rows[0]["structure"]["contributor_count"]
    )


def test_orchestration_can_select_live_ctps(
    clients: DownstreamClients,
    seeded_ctp_dataset: dict,
) -> None:
    seeded_rows = seeded_ctp_dataset["rows"]

    response = clients.select_ctps(
        {
            "query": {
                "dataset_name": seeded_ctp_dataset["dataset_name"],
                "subnet_prefix_len": 24,
                "intensity_range_mbps": [10.0, 20.0],
                "contributor_count_min": 5,
                "upload_download_ratio_max": 1.0,
            },
            "limit": 10,
            "offset": 0,
            "order_by": "intensity",
        }
    )

    assert response["query_matched"] == 2
    assert response["results_returned"] == 2
    assert [ctp["ctp_id"] for ctp in response["ctps"]] == [
        seeded_rows[0]["ctp_id"],
        seeded_rows[1]["ctp_id"],
    ]
    assert response["ctps"][0]["intensity"]["mean_mbps"] == pytest.approx(18.2)
    assert response["ctps"][1]["intensity"]["mean_mbps"] == pytest.approx(11.4)
