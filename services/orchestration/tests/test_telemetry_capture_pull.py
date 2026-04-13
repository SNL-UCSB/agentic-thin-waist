from unittest.mock import MagicMock, patch

from app.engine.telemetry_capture_pull import stream_capture_pcap_to_telemetry


@patch("app.engine.telemetry_capture_pull.requests.post")
@patch("app.engine.telemetry_capture_pull.httpx.stream")
def test_stream_capture_pcap_to_telemetry_success(mock_stream, mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_bytes.return_value = iter([b"pcap-bytes-1", b"pcap-bytes-2"])
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    mock_stream.return_value = mock_resp

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 201
    mock_post_resp.json.return_value = {
        "artifact_id": "art-1",
        "artifact_path": "/tmp/a.pcap",
    }
    mock_post.return_value = mock_post_resp

    out = stream_capture_pcap_to_telemetry(
        worker_base_url="http://worker:8002",
        capture_id="cap-1",
        telemetry_base_url="http://telemetry:8004",
        result_id="res-1",
        pcap_filename="x.pcap",
    )

    assert out["status"] == "stored"
    assert out["artifact_id"] == "art-1"


@patch("app.engine.telemetry_capture_pull.httpx.stream")
def test_stream_capture_pcap_to_telemetry_download_error(mock_stream):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "not found"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    mock_stream.return_value = mock_resp

    out = stream_capture_pcap_to_telemetry(
        worker_base_url="http://worker:8002",
        capture_id="missing",
        telemetry_base_url="http://telemetry:8004",
        result_id="res-1",
        pcap_filename="x.pcap",
    )

    assert out["status"] == "error"
    assert out["phase"] == "download"
