"""
test_routes.py — Unit tests for CTP Service API endpoints.

All pipeline functions (Extractor, CTPSelector, CTPTransformer, CTPMerger,
CTPExporter) and the database dependency are mocked so tests run without
PostgreSQL or real PCAP files.
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes import _get_db
from app.main import app
from app.models.ctp import (
    CrossTrafficProfile,
    CTPBurstiness,
    CTPIntensity,
    CTPStructure,
    CTPTemporalCorrelation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctp(
    ctp_id: str = "ctp-test-169.231.0.0/16-0",
    subnet: str = "169.231.0.0/16",
    window_index: int = 0,
    mean_bps: float = 8_000_000.0,
    contributor_count: int = 50,
) -> CrossTrafficProfile:
    """Return a fully-populated CrossTrafficProfile for use in mocks."""
    return CrossTrafficProfile(
        ctp_id=ctp_id,
        dataset_name="test-dataset",
        subnet=subnet,
        window_index=window_index,
        extracted_from="test.pcap",
        duration_seconds=30,
        upload_timeseries=[1.0, 2.0, 3.0],
        download_timeseries=[4.0, 5.0, 6.0],
        intensity=CTPIntensity(
            mean_pps=1000.0,
            mean_bps=mean_bps,
            peak_pps=2000.0,
            peak_bps=mean_bps * 2,
        ),
        burstiness=CTPBurstiness(
            peak_to_mean_ratio=2.0,
            coefficient_of_variation=0.5,
            percentile_95_to_mean=1.8,
            on_periods=10,
            off_periods=5,
        ),
        temporal_correlation=CTPTemporalCorrelation(
            lag_1=0.9,
            lag_5=0.7,
            lag_10=0.5,
            lag_60=0.2,
        ),
        structure=CTPStructure(
            contributor_count=contributor_count,
            unique_source_ips=100,
            unique_dest_ips=200,
            upload_download_ratio=0.3,
            prefix_diversity=0.8,
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db():
    """Mock Database object with health_check returning True."""
    db = MagicMock()
    db.health_check.return_value = True
    return db


@pytest.fixture()
def client(mock_db):
    """TestClient with the db dependency overridden; skips lifespan."""
    app.dependency_overrides[_get_db] = lambda: mock_db
    yield TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_ok(self, client, mock_db):
        mock_db.health_check.return_value = True
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["postgresql_connected"] is True
        assert "service_version" in body
        assert "python_version" in body
        assert "platform" in body

    def test_health_degraded(self, client, mock_db):
        mock_db.health_check.return_value = False
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["postgresql_connected"] is False


# ---------------------------------------------------------------------------
# GET /ctps
# ---------------------------------------------------------------------------


class TestListCTPs:
    def test_list_default_params(self, client):
        ctp = _make_ctp()
        with patch("app.api.routes.CTPSelector") as MockSelector:
            instance = MockSelector.return_value
            instance.list_all.return_value = (1, [ctp])
            resp = client.get("/ctps")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["returned"] == 1
        assert len(body["ctps"]) == 1
        assert body["ctps"][0]["ctp_id"] == ctp.ctp_id

    def test_list_passes_pagination_params(self, client):
        with patch("app.api.routes.CTPSelector") as MockSelector:
            instance = MockSelector.return_value
            instance.list_all.return_value = (0, [])
            resp = client.get("/ctps?limit=10&offset=100&order_by=burstiness")

        assert resp.status_code == 200
        instance.list_all.assert_called_once_with(
            limit=10, offset=100, order_by="burstiness"
        )

    def test_list_empty_corpus(self, client):
        with patch("app.api.routes.CTPSelector") as MockSelector:
            instance = MockSelector.return_value
            instance.list_all.return_value = (0, [])
            resp = client.get("/ctps")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["returned"] == 0
        assert body["ctps"] == []

    def test_list_multiple_results(self, client):
        ctps = [_make_ctp(f"ctp-test-{i}") for i in range(3)]
        with patch("app.api.routes.CTPSelector") as MockSelector:
            instance = MockSelector.return_value
            instance.list_all.return_value = (3, ctps)
            resp = client.get("/ctps")

        assert resp.status_code == 200
        assert resp.json()["returned"] == 3

    def test_list_limit_below_minimum(self, client):
        resp = client.get("/ctps?limit=0")
        assert resp.status_code == 422

    def test_list_limit_above_maximum(self, client):
        resp = client.get("/ctps?limit=10001")
        assert resp.status_code == 422

    def test_list_negative_offset(self, client):
        resp = client.get("/ctps?offset=-1")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /ctps/{ctp_id}
# ---------------------------------------------------------------------------


class TestGetCTP:
    def test_get_existing_ctp(self, client):
        # Use a slash-free ctp_id so it parses correctly as a URL path segment
        ctp = _make_ctp(ctp_id="ctp-test-dataset-0")
        with patch("app.api.routes.CTPSelector") as MockSelector:
            instance = MockSelector.return_value
            instance.get_by_id.return_value = ctp
            resp = client.get(f"/ctps/{ctp.ctp_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ctp_id"] == ctp.ctp_id
        assert body["dataset_name"] == ctp.dataset_name
        assert body["subnet"] == ctp.subnet

    def test_get_not_found(self, client):
        with patch("app.api.routes.CTPSelector") as MockSelector:
            instance = MockSelector.return_value
            instance.get_by_id.return_value = None
            resp = client.get("/ctps/nonexistent-id")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_calls_selector_with_correct_id(self, client):
        ctp = _make_ctp(ctp_id="ctp-dataset-abc-0")
        with patch("app.api.routes.CTPSelector") as MockSelector:
            instance = MockSelector.return_value
            instance.get_by_id.return_value = ctp
            client.get("/ctps/ctp-dataset-abc-0")

        instance.get_by_id.assert_called_once_with("ctp-dataset-abc-0")


# ---------------------------------------------------------------------------
# POST /ctps/extract
# ---------------------------------------------------------------------------


_EXTRACT_PAYLOAD = {
    "pcap_input": "/data/trace.pcap",
    "output_dir": "/data/out",
    "dataset_name": "test-dataset",
    "window_duration_sec": 30,
    "burst_interval_ms": 100,
    "workers": 4,
}


class TestExtract:
    def test_extract_success(self, client):
        ctps = [
            _make_ctp(f"ctp-test-{i}", subnet=f"169.231.0.{i}/32") for i in range(5)
        ]
        with patch("app.api.routes.Extractor") as MockExtractor:
            instance = MockExtractor.return_value
            instance.run.return_value = ctps
            resp = client.post("/ctps/extract", json=_EXTRACT_PAYLOAD)

        assert resp.status_code == 200
        body = resp.json()
        assert body["dataset_name"] == "test-dataset"
        assert body["ctp_count"] == 5
        assert body["extraction_status"] == "success"

    def test_extract_counts_windows_and_users(self, client):
        # 2 windows × 3 /32 subnets = 6 CTPs
        ctps = [
            _make_ctp(
                ctp_id=f"ctp-test-169.231.0.{i}/32-{w}",
                subnet=f"169.231.0.{i}/32",
                window_index=w,
            )
            for w in range(2)
            for i in range(3)
        ]
        with patch("app.api.routes.Extractor") as MockExtractor:
            instance = MockExtractor.return_value
            instance.run.return_value = ctps
            resp = client.post("/ctps/extract", json=_EXTRACT_PAYLOAD)

        assert resp.status_code == 200
        body = resp.json()
        assert body["ctp_count"] == 6
        assert body["window_count"] == 2
        assert body["user_count"] == 3

    def test_extract_non_user_subnets_not_counted(self, client):
        # /16 and /24 nodes should not be counted as users
        ctps = [
            _make_ctp("ctp-root", subnet="169.231.0.0/16", window_index=0),
            _make_ctp("ctp-leaf", subnet="169.231.0.1/32", window_index=0),
        ]
        with patch("app.api.routes.Extractor") as MockExtractor:
            instance = MockExtractor.return_value
            instance.run.return_value = ctps
            resp = client.post("/ctps/extract", json=_EXTRACT_PAYLOAD)

        assert resp.status_code == 200
        assert resp.json()["user_count"] == 1

    def test_extract_pipeline_error_returns_500(self, client):
        with patch("app.api.routes.Extractor") as MockExtractor:
            instance = MockExtractor.return_value
            instance.run.side_effect = RuntimeError("disk full")
            resp = client.post("/ctps/extract", json=_EXTRACT_PAYLOAD)

        assert resp.status_code == 500
        assert "Extraction failed" in resp.json()["detail"]

    def test_extract_missing_pcap_input(self, client):
        payload = {"output_dir": "/data/out", "dataset_name": "test"}
        resp = client.post("/ctps/extract", json=payload)
        assert resp.status_code == 422

    def test_extract_missing_output_dir(self, client):
        payload = {"pcap_input": "/data/trace.pcap", "dataset_name": "test"}
        resp = client.post("/ctps/extract", json=payload)
        assert resp.status_code == 422

    def test_extract_missing_dataset_name(self, client):
        payload = {"pcap_input": "/data/trace.pcap", "output_dir": "/data/out"}
        resp = client.post("/ctps/extract", json=payload)
        assert resp.status_code == 422

    def test_extract_passes_optional_overrides(self, client):
        ctps = [_make_ctp()]
        with patch("app.api.routes.Extractor") as MockExtractor:
            instance = MockExtractor.return_value
            instance.run.return_value = ctps
            resp = client.post("/ctps/extract", json=_EXTRACT_PAYLOAD)

        assert resp.status_code == 200
        call_kwargs = instance.run.call_args.kwargs
        assert call_kwargs["window_duration_sec"] == 30
        assert call_kwargs["burst_interval_ms"] == 100
        assert call_kwargs["workers"] == 4


# ---------------------------------------------------------------------------
# POST /ctps/select
# ---------------------------------------------------------------------------


_SELECT_PAYLOAD = {
    "query": {
        "intensity_range_mbps": [100.0, 3000.0],
        "burstiness_pmr_range": [2.0, 5.0],
        "temporal_correlation_min": 0.3,
        "contributor_count_min": 10,
    },
    "limit": 20,
    "order_by": "intensity",
}


class TestSelect:
    def test_select_returns_matched_ctps(self, client):
        ctps = [_make_ctp()]
        with patch("app.api.routes.CTPSelector") as MockSelector:
            instance = MockSelector.return_value
            instance.select.return_value = (1, ctps)
            resp = client.post("/ctps/select", json=_SELECT_PAYLOAD)

        assert resp.status_code == 200
        body = resp.json()
        assert body["query_matched"] == 1
        assert body["results_returned"] == 1
        assert body["ctps"][0]["ctp_id"] == ctps[0].ctp_id

    def test_select_empty_result(self, client):
        with patch("app.api.routes.CTPSelector") as MockSelector:
            instance = MockSelector.return_value
            instance.select.return_value = (0, [])
            resp = client.post("/ctps/select", json={"query": {}})

        assert resp.status_code == 200
        body = resp.json()
        assert body["query_matched"] == 0
        assert body["results_returned"] == 0
        assert body["ctps"] == []

    def test_select_passes_query_params(self, client):
        with patch("app.api.routes.CTPSelector") as MockSelector:
            instance = MockSelector.return_value
            instance.select.return_value = (0, [])
            resp = client.post("/ctps/select", json=_SELECT_PAYLOAD)

        assert resp.status_code == 200
        call_kwargs = instance.select.call_args.kwargs
        assert call_kwargs["limit"] == 20
        assert call_kwargs["order_by"] == "intensity"

    def test_select_invalid_order_by(self, client):
        payload = {"query": {}, "order_by": "invalid_field"}
        resp = client.post("/ctps/select", json=payload)
        assert resp.status_code == 422

    def test_select_invalid_intensity_range(self, client):
        # min > max should fail validation
        payload = {"query": {"intensity_range_mbps": [500.0, 100.0]}}
        resp = client.post("/ctps/select", json=payload)
        assert resp.status_code == 422

    def test_select_invalid_pmr_range(self, client):
        payload = {"query": {"burstiness_pmr_range": [5.0, 2.0]}}
        resp = client.post("/ctps/select", json=payload)
        assert resp.status_code == 422

    def test_select_valid_order_by_options(self, client):
        valid_orders = ["intensity", "burstiness", "contributor_count", "window_index"]
        for order in valid_orders:
            with patch("app.api.routes.CTPSelector") as MockSelector:
                instance = MockSelector.return_value
                instance.select.return_value = (0, [])
                resp = client.post(
                    "/ctps/select", json={"query": {}, "order_by": order}
                )
            assert resp.status_code == 200, f"Failed for order_by={order}"


# ---------------------------------------------------------------------------
# POST /ctps/transform
# ---------------------------------------------------------------------------


_TRANSFORM_PAYLOAD = {
    "ctp_id": "ctp-test-169.231.0.0/16-0",
    "throughput_threshold_mbps": 500.0,
    "output_dir": "/data/transform-out",
    "users_root": "/data/users",
}


class TestTransform:
    def test_transform_success(self, client, mock_db, tmp_path):
        transformed = _make_ctp("ctp-transformed")
        dl_path = tmp_path / "dl.pcap"
        ul_path = tmp_path / "ul.pcap"

        with patch("app.api.routes.CTPTransformer") as MockTransformer:
            instance = MockTransformer.return_value
            instance.transform.return_value = (transformed, dl_path, ul_path)
            resp = client.post("/ctps/transform", json=_TRANSFORM_PAYLOAD)

        assert resp.status_code == 200
        body = resp.json()
        assert body["original_ctp_id"] == "ctp-test-169.231.0.0/16-0"
        assert body["transformed_ctp_id"] == "ctp-transformed"
        assert body["throughput_threshold_mbps"] == 500.0
        assert body["download_pcap"] == str(dl_path)
        assert body["upload_pcap"] == str(ul_path)

    def test_transform_ctp_not_found_returns_404(self, client):
        with patch("app.api.routes.CTPTransformer") as MockTransformer:
            instance = MockTransformer.return_value
            instance.transform.side_effect = ValueError("CTP not found")
            resp = client.post("/ctps/transform", json=_TRANSFORM_PAYLOAD)

        assert resp.status_code == 404
        assert "CTP not found" in resp.json()["detail"]

    def test_transform_pipeline_error_returns_500(self, client):
        with patch("app.api.routes.CTPTransformer") as MockTransformer:
            instance = MockTransformer.return_value
            instance.transform.side_effect = RuntimeError("transform crashed")
            resp = client.post("/ctps/transform", json=_TRANSFORM_PAYLOAD)

        assert resp.status_code == 500
        assert "Transform failed" in resp.json()["detail"]

    def test_transform_missing_ctp_id(self, client):
        payload = {
            "throughput_threshold_mbps": 100.0,
            "output_dir": "/data/out",
            "users_root": "/data/users",
        }
        resp = client.post("/ctps/transform", json=payload)
        assert resp.status_code == 422

    def test_transform_missing_throughput_threshold(self, client):
        payload = {
            "ctp_id": "ctp-abc",
            "output_dir": "/data/out",
            "users_root": "/data/users",
        }
        resp = client.post("/ctps/transform", json=payload)
        assert resp.status_code == 422

    def test_transform_missing_users_root(self, client):
        payload = {
            "ctp_id": "ctp-abc",
            "throughput_threshold_mbps": 100.0,
            "output_dir": "/data/out",
        }
        resp = client.post("/ctps/transform", json=payload)
        assert resp.status_code == 422

    def test_transform_zero_throughput_threshold_rejected(self, client):
        payload = {**_TRANSFORM_PAYLOAD, "throughput_threshold_mbps": 0.0}
        resp = client.post("/ctps/transform", json=payload)
        assert resp.status_code == 422

    def test_transform_response_includes_notes(self, client, mock_db, tmp_path):
        transformed = _make_ctp("ctp-transformed")
        dl_path = tmp_path / "dl.pcap"
        ul_path = tmp_path / "ul.pcap"

        with patch("app.api.routes.CTPTransformer") as MockTransformer:
            instance = MockTransformer.return_value
            instance.transform.return_value = (transformed, dl_path, ul_path)
            resp = client.post("/ctps/transform", json=_TRANSFORM_PAYLOAD)

        assert "notes" in resp.json()


# ---------------------------------------------------------------------------
# POST /ctps/merge
# ---------------------------------------------------------------------------


_MERGE_PAYLOAD = {
    "dataset_name": "test-dataset",
    "subnet": "169.231.0.0/24",
    "start_index": 0,
    "end_index": 2,
    "output_dir": "/data/merge-out",
    "users_root": "/data/users",
}


class TestMerge:
    def test_merge_success(self, client, tmp_path):
        merged = _make_ctp("ctp-merged", mean_bps=50_000_000.0, contributor_count=3)
        dl_path = tmp_path / "dl.pcap"
        ul_path = tmp_path / "ul.pcap"

        with patch("app.api.routes.CTPMerger") as MockMerger:
            instance = MockMerger.return_value
            instance.merge_subnet_range.return_value = (merged, dl_path, ul_path)
            resp = client.post("/ctps/merge", json=_MERGE_PAYLOAD)

        assert resp.status_code == 200
        body = resp.json()
        assert body["merged_ctp_id"] == "ctp-merged"
        assert body["dataset_name"] == "test-dataset"
        assert body["subnet"] == "169.231.0.0/24"
        assert body["start_index"] == 0
        assert body["end_index"] == 2

    def test_merge_response_includes_intensity_and_contributors(self, client, tmp_path):
        merged = _make_ctp("ctp-merged", mean_bps=50_000_000.0, contributor_count=75)
        dl_path = tmp_path / "dl.pcap"
        ul_path = tmp_path / "ul.pcap"

        with patch("app.api.routes.CTPMerger") as MockMerger:
            instance = MockMerger.return_value
            instance.merge_subnet_range.return_value = (merged, dl_path, ul_path)
            resp = client.post("/ctps/merge", json=_MERGE_PAYLOAD)

        body = resp.json()
        assert abs(body["merged_intensity_mbps"] - 50.0) < 1e-6
        assert body["merged_contributor_count"] == 75
        assert body["leaf_count"] == 75

    def test_merge_response_includes_pcap_paths(self, client, tmp_path):
        merged = _make_ctp("ctp-merged")
        dl_path = tmp_path / "dl.pcap"
        ul_path = tmp_path / "ul.pcap"

        with patch("app.api.routes.CTPMerger") as MockMerger:
            instance = MockMerger.return_value
            instance.merge_subnet_range.return_value = (merged, dl_path, ul_path)
            resp = client.post("/ctps/merge", json=_MERGE_PAYLOAD)

        body = resp.json()
        assert body["download_pcap"] == str(dl_path)
        assert body["upload_pcap"] == str(ul_path)

    def test_merge_not_found_returns_400(self, client):
        with patch("app.api.routes.CTPMerger") as MockMerger:
            instance = MockMerger.return_value
            instance.merge_subnet_range.side_effect = ValueError(
                "No /32 leaf CTPs found"
            )
            resp = client.post("/ctps/merge", json=_MERGE_PAYLOAD)

        assert resp.status_code == 400
        assert "No /32 leaf CTPs found" in resp.json()["detail"]

    def test_merge_pipeline_error_returns_500(self, client):
        with patch("app.api.routes.CTPMerger") as MockMerger:
            instance = MockMerger.return_value
            instance.merge_subnet_range.side_effect = RuntimeError("merge crashed")
            resp = client.post("/ctps/merge", json=_MERGE_PAYLOAD)

        assert resp.status_code == 500
        assert "Merge failed" in resp.json()["detail"]

    def test_merge_notes_field_present(self, client, tmp_path):
        merged = _make_ctp("ctp-merged")
        dl_path = tmp_path / "dl.pcap"
        ul_path = tmp_path / "ul.pcap"

        with patch("app.api.routes.CTPMerger") as MockMerger:
            instance = MockMerger.return_value
            instance.merge_subnet_range.return_value = (merged, dl_path, ul_path)
            resp = client.post("/ctps/merge", json=_MERGE_PAYLOAD)

        assert "notes" in resp.json()

    def test_merge_missing_dataset_name(self, client):
        payload = {k: v for k, v in _MERGE_PAYLOAD.items() if k != "dataset_name"}
        resp = client.post("/ctps/merge", json=payload)
        assert resp.status_code == 422

    def test_merge_missing_subnet(self, client):
        payload = {k: v for k, v in _MERGE_PAYLOAD.items() if k != "subnet"}
        resp = client.post("/ctps/merge", json=payload)
        assert resp.status_code == 422

    def test_merge_end_index_before_start_index(self, client):
        payload = {**_MERGE_PAYLOAD, "start_index": 5, "end_index": 2}
        resp = client.post("/ctps/merge", json=payload)
        assert resp.status_code == 422

    def test_merge_passes_correct_params_to_merger(self, client, tmp_path):
        merged = _make_ctp("ctp-merged")
        dl_path = tmp_path / "dl.pcap"
        ul_path = tmp_path / "ul.pcap"

        with patch("app.api.routes.CTPMerger") as MockMerger:
            instance = MockMerger.return_value
            instance.merge_subnet_range.return_value = (merged, dl_path, ul_path)
            client.post("/ctps/merge", json=_MERGE_PAYLOAD)

        instance.merge_subnet_range.assert_called_once_with(
            dataset_name="test-dataset",
            subnet="169.231.0.0/24",
            start_index=0,
            end_index=2,
            output_dir="/data/merge-out",
            users_root="/data/users",
        )


# ---------------------------------------------------------------------------
# GET /ctps/{ctp_id}/replay-data
# ---------------------------------------------------------------------------


_REPLAY_PARAMS = {
    "replay_dir": "/data/replay",
    "users_root": "/data/users",
    "direction": "download",
}


class TestReplayData:
    def test_replay_download_direction(self, client, tmp_path):
        dl_path = tmp_path / "merged_dl.pcap"
        ul_path = tmp_path / "merged_ul.pcap"
        dl_path.write_bytes(b"PCAP_MAGIC")

        with patch("app.api.routes.CTPExporter") as MockExporter:
            instance = MockExporter.return_value
            instance.export_replay_pcap.return_value = (dl_path, ul_path)
            resp = client.get("/ctps/ctp-test/replay-data", params=_REPLAY_PARAMS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["download_pcap"] == str(dl_path)
        assert body["upload_pcap"] == str(ul_path)

    def test_replay_upload_direction(self, client, tmp_path):
        dl_path = tmp_path / "merged_dl.pcap"
        ul_path = tmp_path / "merged_ul.pcap"
        ul_path.write_bytes(b"PCAP_MAGIC")

        params = {**_REPLAY_PARAMS, "direction": "upload"}
        with patch("app.api.routes.CTPExporter") as MockExporter:
            instance = MockExporter.return_value
            instance.export_replay_pcap.return_value = (dl_path, ul_path)
            resp = client.get("/ctps/ctp-test/replay-data", params=params)

        assert resp.status_code == 200
        body = resp.json()
        assert body["download_pcap"] == str(dl_path)
        assert body["upload_pcap"] == str(ul_path)

    def test_replay_pcap_file_missing_returns_404(self, client, tmp_path):
        # exporter returns paths, but neither file exists on disk
        dl_path = tmp_path / "nonexistent.pcap"
        ul_path = tmp_path / "nonexistent_ul.pcap"

        with patch("app.api.routes.CTPExporter") as MockExporter:
            instance = MockExporter.return_value
            instance.export_replay_pcap.return_value = (dl_path, ul_path)
            resp = client.get("/ctps/ctp-test/replay-data", params=_REPLAY_PARAMS)

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_replay_ctp_not_found_returns_404(self, client):
        with patch("app.api.routes.CTPExporter") as MockExporter:
            instance = MockExporter.return_value
            instance.export_replay_pcap.side_effect = ValueError("CTP not found")
            resp = client.get("/ctps/ctp-test/replay-data", params=_REPLAY_PARAMS)

        assert resp.status_code == 404
        assert "CTP not found" in resp.json()["detail"]

    def test_replay_pipeline_error_returns_500(self, client):
        with patch("app.api.routes.CTPExporter") as MockExporter:
            instance = MockExporter.return_value
            instance.export_replay_pcap.side_effect = RuntimeError("export crashed")
            resp = client.get("/ctps/ctp-test/replay-data", params=_REPLAY_PARAMS)

        assert resp.status_code == 500
        assert "Export failed" in resp.json()["detail"]

    def test_replay_missing_replay_dir_returns_422(self, client):
        params = {"users_root": "/data/users", "direction": "download"}
        resp = client.get("/ctps/ctp-test/replay-data", params=params)
        assert resp.status_code == 422

    def test_replay_missing_users_root_returns_422(self, client):
        params = {"replay_dir": "/data/replay", "direction": "download"}
        resp = client.get("/ctps/ctp-test/replay-data", params=params)
        assert resp.status_code == 422

    def test_replay_passes_correct_ctp_id_to_exporter(self, client, tmp_path):
        dl_path = tmp_path / "dl.pcap"
        ul_path = tmp_path / "ul.pcap"
        dl_path.write_bytes(b"PCAP")

        with patch("app.api.routes.CTPExporter") as MockExporter:
            instance = MockExporter.return_value
            instance.export_replay_pcap.return_value = (dl_path, ul_path)
            client.get("/ctps/my-specific-ctp-id/replay-data", params=_REPLAY_PARAMS)

        instance.export_replay_pcap.assert_called_once()
        call_kwargs = instance.export_replay_pcap.call_args.kwargs
        assert call_kwargs["ctp_id"] == "my-specific-ctp-id"
        assert call_kwargs["replay_dir"] == "/data/replay"
        assert call_kwargs["users_root"] == "/data/users"
