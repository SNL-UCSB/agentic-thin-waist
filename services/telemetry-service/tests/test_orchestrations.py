"""Tests for PUT/GET/DELETE /orchestrations/<id> routes."""


class TestOrchestrationUpsert:
    def test_put_creates_new_orchestration(self, client, db):
        payload = {
            "orchestration_id": "orch-001",
            "status": "pending",
            "intent": "Run ping at 10 Mbps",
            "experiments": [],
            "reasoning_steps": [],
            "results": [],
        }
        resp = client.put("/orchestrations/orch-001", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["orchestration_id"] == "orch-001"
        assert data["status"] == "pending"
        assert data["intent"] == "Run ping at 10 Mbps"

    def test_put_updates_existing_orchestration(self, client, db):
        payload_v1 = {
            "orchestration_id": "orch-002",
            "status": "pending",
            "intent": "Run iperf3",
            "experiments": [],
            "results": [],
        }
        client.put("/orchestrations/orch-002", json=payload_v1)

        payload_v2 = {
            "orchestration_id": "orch-002",
            "status": "complete",
            "intent": "Run iperf3",
            "experiments": [{"id": "exp-1"}],
            "results": [{"status": "success"}],
        }
        resp = client.put("/orchestrations/orch-002", json=payload_v2)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "complete"
        assert len(data["results"]) == 1

    def test_put_requires_json_body(self, client, db):
        resp = client.put(
            "/orchestrations/orch-bad",
            data="not json",
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestOrchestrationGet:
    def test_get_existing_orchestration(self, client, db):
        payload = {
            "orchestration_id": "orch-get",
            "status": "parsing",
            "intent": "test",
        }
        client.put("/orchestrations/orch-get", json=payload)

        resp = client.get("/orchestrations/orch-get")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["orchestration_id"] == "orch-get"
        assert data["status"] == "parsing"

    def test_get_missing_orchestration_returns_404(self, client, db):
        resp = client.get("/orchestrations/orch-missing")
        assert resp.status_code == 404


class TestOrchestrationDelete:
    def test_delete_existing_orchestration(self, client, db):
        payload = {
            "orchestration_id": "orch-del",
            "status": "complete",
            "intent": "test",
        }
        client.put("/orchestrations/orch-del", json=payload)

        resp = client.delete("/orchestrations/orch-del")
        assert resp.status_code == 200
        assert resp.get_json()["deleted"] == "orch-del"

        resp = client.get("/orchestrations/orch-del")
        assert resp.status_code == 404

    def test_delete_missing_returns_404(self, client, db):
        resp = client.delete("/orchestrations/orch-ghost")
        assert resp.status_code == 404
