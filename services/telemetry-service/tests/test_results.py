from app.telemetry.models import Result


class TestPostResults:
    def test_store_result_returns_201(self, client, db, sample_result_payload):
        resp = client.post("/results", json=sample_result_payload)
        assert resp.status_code == 201

    def test_store_result_returns_result_id(self, client, db, sample_result_payload):
        resp = client.post("/results", json=sample_result_payload)
        data = resp.get_json()
        assert "result_id" in data
        assert data["status"] == "stored"
        assert data["experiment_id"] == "youtube-10mbps-001"

    def test_store_result_persists_to_db(self, client, db, sample_result_payload):
        resp = client.post("/results", json=sample_result_payload)
        result = Result.query.get(resp.get_json()["result_id"])
        assert result is not None
        assert result.experiment_id == "youtube-10mbps-001"
        assert result.configured_capacity == 10.0
        assert result.application == "youtube"

    def test_store_result_no_body_returns_400(self, client, db):
        resp = client.post("/results", json={})
        assert resp.status_code == 400

    def test_store_result_sets_contextual_tree(self, client, db, sample_result_payload):
        resp = client.post("/results", json=sample_result_payload)
        result = Result.query.get(resp.get_json()["result_id"])
        assert result.contextual_tree["c_app"]["application"] == "youtube"
        assert result.contextual_tree["c_trans"]["congestion_control"] == "cubic"


class TestGetResults:
    def test_get_results_returns_200(self, client, db, persisted_result):
        resp = client.get("/results")
        assert resp.status_code == 200

    def test_get_results_returns_list(self, client, db, persisted_result):
        data = client.get("/results").get_json()
        assert "results" in data
        assert "total" in data
        assert "returned" in data

    def test_get_results_filter_by_application(self, client, db, persisted_result):
        data = client.get("/results?application=youtube").get_json()
        assert data["total"] >= 1
        assert all(r["application"] == "youtube" for r in data["results"])

    def test_get_results_filter_no_match(self, client, db, persisted_result):
        data = client.get("/results?application=netflix").get_json()
        assert data["total"] == 0

    def test_get_results_filter_by_capacity_range(self, client, db, persisted_result):
        data = client.get("/results?capacity_min=5&capacity_max=20").get_json()
        assert data["total"] >= 1

    def test_get_results_filter_capacity_excludes_out_of_range(
        self, client, db, persisted_result
    ):
        data = client.get("/results?capacity_min=50&capacity_max=100").get_json()
        assert data["total"] == 0

    def test_get_results_pagination(self, client, db, sample_result_payload):
        for _ in range(3):
            client.post("/results", json=sample_result_payload)
        data = client.get("/results?limit=2&offset=0").get_json()
        assert data["returned"] == 2
        assert data["limit"] == 2

    def test_get_results_sort_order(self, client, db, sample_result_payload):
        for _ in range(2):
            client.post("/results", json=sample_result_payload)
        resp = client.get("/results?sort_order=asc")
        assert resp.status_code == 200


class TestGetResultById:
    def test_get_result_by_id_returns_200(self, client, db, persisted_result):
        resp = client.get(f"/results/{persisted_result['result_id']}")
        assert resp.status_code == 200

    def test_get_result_by_id_returns_correct_data(self, client, db, persisted_result):
        data = client.get(f"/results/{persisted_result['result_id']}").get_json()
        assert data["result_id"] == persisted_result["result_id"]
        assert data["experiment_id"] == "youtube-10mbps-001"

    def test_get_result_by_id_not_found(self, client, db):
        resp = client.get("/results/nonexistent-id")
        assert resp.status_code == 404
