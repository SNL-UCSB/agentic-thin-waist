import io
import pytest
from app.telemetry.models import Artifact


class TestPostArtifacts:
    def test_upload_artifact_returns_201(self, client, db, persisted_result, mock_s3):
        mock_s3.put_object.return_value = "artifacts/path/file.pcap"
        data = {
            "result_id": persisted_result["result_id"],
            "artifact_type": "pcap",
            "file": (io.BytesIO(b"fake pcap content"), "test.pcap"),
        }
        resp = client.post("/artifacts", data=data, content_type="multipart/form-data")
        assert resp.status_code == 201

    def test_upload_artifact_missing_file_returns_400(self, client, db, persisted_result):
        resp = client.post(
            "/artifacts",
            data={"result_id": persisted_result["result_id"]},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_upload_artifact_missing_result_id_returns_400(self, client, db):
        resp = client.post(
            "/artifacts",
            data={"file": (io.BytesIO(b"fake content"), "test.pcap")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_upload_artifact_invalid_result_id_returns_404(self, client, db, mock_s3):
        data = {
            "result_id": "nonexistent-id",
            "artifact_type": "pcap",
            "file": (io.BytesIO(b"fake content"), "test.pcap"),
        }
        resp = client.post("/artifacts", data=data, content_type="multipart/form-data")
        assert resp.status_code == 404

    def test_upload_artifact_persists_to_db(self, client, db, persisted_result, mock_s3):
        mock_s3.put_object.return_value = "artifacts/path/file.pcap"
        data = {
            "result_id": persisted_result["result_id"],
            "artifact_type": "pcap",
            "file": (io.BytesIO(b"fake pcap content"), "test.pcap"),
        }
        resp = client.post("/artifacts", data=data, content_type="multipart/form-data")
        artifact = Artifact.query.get(resp.get_json()["artifact_id"])
        assert artifact is not None
        assert artifact.result_id == persisted_result["result_id"]
        assert artifact.artifact_type == "pcap"


class TestGetArtifactById:
    def test_download_artifact_returns_200(self, client, db, persisted_result, mock_s3):
        mock_s3.put_object.return_value = "artifacts/path/file.pcap"
        mock_s3.get_object.return_value = b"fake pcap content"

        upload_resp = client.post(
            "/artifacts",
            data={
                "result_id": persisted_result["result_id"],
                "artifact_type": "pcap",
                "file": (io.BytesIO(b"fake pcap content"), "test.pcap"),
            },
            content_type="multipart/form-data",
        )
        artifact_id = upload_resp.get_json()["artifact_id"]
        resp = client.get(f"/artifacts/{artifact_id}")
        assert resp.status_code == 200
        assert resp.data == b"fake pcap content"

    def test_download_artifact_not_found(self, client, db):
        resp = client.get("/artifacts/nonexistent-id")
        assert resp.status_code == 404

    def test_get_result_artifacts_returns_200(self, client, db, persisted_result):
        resp = client.get(f"/results/{persisted_result['result_id']}/artifacts")
        assert resp.status_code == 200

    def test_get_result_artifacts_returns_list(self, client, db, persisted_result):
        resp = client.get(f"/results/{persisted_result['result_id']}/artifacts")
        assert "artifacts" in resp.get_json()

    def test_get_result_artifacts_not_found(self, client, db):
        resp = client.get("/results/nonexistent-id/artifacts")
        assert resp.status_code == 404
