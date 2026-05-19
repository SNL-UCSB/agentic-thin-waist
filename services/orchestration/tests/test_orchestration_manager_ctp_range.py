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


def test_select_ctp_skips_when_range_missing(monkeypatch):
    """A missing ctp_capacity_range means the intent did not ask for CTP.

    _select_ctp must short-circuit to None without contacting the CTP service
    so the orchestrator skips /replay and the captured pcap stays free of
    background traffic (no 172.16.1.20 packets).
    """
    called = {"select": False}

    class FakeClients:
        def __init__(self, ctp_service_url=None):
            self.ctp_service_url = ctp_service_url

        def select_ctps(self, payload):
            called["select"] = True
            return {"ctps": []}

    monkeypatch.setattr(om, "DownstreamClients", FakeClients)
    result = om._select_ctp(None, "exp-2")

    assert result is None
    assert called["select"] is False
