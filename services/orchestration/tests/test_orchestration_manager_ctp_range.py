from app.engine import orchestration_manager as om


def test_select_ctp_uses_explicit_intensity_range(monkeypatch):
    seen = {}

    class FakeClients:
        def __init__(self, ctp_service_url=None):
            self.ctp_service_url = ctp_service_url

        def select_ctps(self, payload):
            seen["payload"] = payload
            return {
                "ctps": [
                    {"ctp_id": "ctp-1", "intensity": {"mean_mbps": 3.0}},
                ]
            }

    monkeypatch.setattr(om, "DownstreamClients", FakeClients)
    out = om._select_ctp({"lower_value": 2.0, "higher_value": 5.0}, "exp-1")

    assert out is not None
    assert seen["payload"]["query"]["intensity_range_mbps"] == [2.0, 5.0]


def test_select_ctp_uses_default_range_when_missing(monkeypatch):
    seen = {}

    class FakeClients:
        def __init__(self, ctp_service_url=None):
            self.ctp_service_url = ctp_service_url

        def select_ctps(self, payload):
            seen["payload"] = payload
            return {"ctps": []}

    monkeypatch.setattr(om, "DownstreamClients", FakeClients)
    om._select_ctp(None, "exp-2")
    assert seen["payload"]["query"]["intensity_range_mbps"] == [1.0, 10.0]
