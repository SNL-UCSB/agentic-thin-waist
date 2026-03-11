class TestHealth:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_success_message(self, client):
        resp = client.get("/health")
        assert resp.get_json()["message"] == "Success"
