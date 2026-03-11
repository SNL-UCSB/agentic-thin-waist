class TestExportCsv:
    def test_export_csv_returns_200(self, client, db, persisted_result):
        resp = client.get("/results/export/csv")
        assert resp.status_code == 200

    def test_export_csv_content_type(self, client, db, persisted_result):
        resp = client.get("/results/export/csv")
        assert "text/csv" in resp.content_type

    def test_export_csv_has_header_row(self, client, db, persisted_result):
        resp = client.get("/results/export/csv")
        lines = resp.data.decode("utf-8").strip().splitlines()
        assert "result_id" in lines[0]
        assert "experiment_id" in lines[0]
        assert "application" in lines[0]

    def test_export_csv_filter_by_application(self, client, db, persisted_result):
        resp = client.get("/results/export/csv?application=youtube")
        lines = resp.data.decode("utf-8").strip().splitlines()
        assert len(lines) >= 2  # header + at least 1 row

    def test_export_csv_empty_filter_returns_header_only(self, client, db, persisted_result):
        resp = client.get("/results/export/csv?application=netflix")
        lines = resp.data.decode("utf-8").strip().splitlines()
        assert len(lines) == 1  # header only
