class TestAddTags:
    def test_add_tags_returns_200(self, client, db, persisted_result):
        result_id = persisted_result["result_id"]
        resp = client.post(f"/results/{result_id}/tags", json={"tags": ["baseline"]})
        assert resp.status_code == 200

    def test_add_tags_persists(self, client, db, persisted_result):
        result_id = persisted_result["result_id"]
        client.post(
            f"/results/{result_id}/tags", json={"tags": ["baseline", "production-run"]}
        )
        data = client.get(f"/results/{result_id}").get_json()
        assert "baseline" in data["tags"]
        assert "production-run" in data["tags"]

    def test_add_tags_deduplicates(self, client, db, persisted_result):
        result_id = persisted_result["result_id"]
        client.post(f"/results/{result_id}/tags", json={"tags": ["baseline"]})
        client.post(f"/results/{result_id}/tags", json={"tags": ["baseline"]})
        tags = client.get(f"/results/{result_id}").get_json()["tags"]
        assert tags.count("baseline") == 1

    def test_add_tags_not_found(self, client, db):
        resp = client.post("/results/nonexistent-id/tags", json={"tags": ["baseline"]})
        assert resp.status_code == 404
