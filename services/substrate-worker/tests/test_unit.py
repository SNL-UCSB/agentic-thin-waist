import pytest
import subprocess
from unittest.mock import patch, MagicMock, call
from fastapi.testclient import TestClient

with patch(
    "subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")
):
    from app.main import app, _build_qdisc_args, BottleneckState
    import app.main as main_module

client = TestClient(app)

VALID_SHAPE_PAYLOAD = {
    "upstream_iface": "veth4",
    "downstream_iface": "veth2",
    "download_mbps": 10.0,
    "upload_mbps": 5.0,
    "latency_ms": 50,
    "qdisc": "fq_codel",
    "buffer_packets": 1000,
}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global state before each test."""
    main_module.CURRENT_BOTTLENECK_STATE = None
    main_module.CURRENT_INTERFACES = None
    main_module.ACTIVE_CAPTURES = {}
    main_module.ACTIVE_REPLAYS = {}
    yield
    main_module.CURRENT_BOTTLENECK_STATE = None
    main_module.CURRENT_INTERFACES = None
    main_module.ACTIVE_CAPTURES = {}
    main_module.ACTIVE_REPLAYS = {}


# ── Pure logic tests ──────────────────────────────────────────────────────────


class TestBuildQdiscArgs:
    # AQM qdiscs: limit is NOT injected automatically
    def test_fq_codel_no_limit_by_default(self):
        assert _build_qdisc_args("fq_codel", 500) == "fq_codel"

    def test_codel_no_limit_by_default(self):
        assert _build_qdisc_args("codel", 200) == "codel"

    # Limit-based qdiscs: limit IS injected from buffer_packets
    def test_pfifo_includes_limit(self):
        assert _build_qdisc_args("pfifo", 1000) == "pfifo limit 1000"

    def test_bfifo_includes_limit(self):
        assert _build_qdisc_args("bfifo", 500) == "bfifo limit 500"

    def test_sfq_includes_limit(self):
        assert _build_qdisc_args("sfq", 200) == "sfq limit 200"

    # Unknown qdiscs: no limit injected
    def test_tbf_passthrough(self):
        assert _build_qdisc_args("tbf", 500) == "tbf"

    # qdisc_params are appended verbatim for any qdisc
    def test_codel_with_qdisc_params(self):
        result = _build_qdisc_args(
            "codel", 1000, {"target": "5ms", "interval": "100ms"}
        )
        assert result == "codel target 5ms interval 100ms"

    def test_fq_codel_with_qdisc_params(self):
        result = _build_qdisc_args("fq_codel", 1000, {"target": "5ms"})
        assert result == "fq_codel target 5ms"

    def test_pfifo_with_extra_qdisc_params(self):
        # limit from buffer_packets + any extra params
        result = _build_qdisc_args("pfifo", 500, {"quantum": "1514"})
        assert result == "pfifo limit 500 quantum 1514"

    def test_no_qdisc_params_leaves_output_unchanged(self):
        assert _build_qdisc_args("pfifo", 100, None) == "pfifo limit 100"
        assert _build_qdisc_args("fq_codel", 100, None) == "fq_codel"


class TestBottleneckStateModel:
    def test_defaults(self):
        state = BottleneckState(
            download_mbps=10, upload_mbps=5, latency_ms=50, qdisc="fq_codel"
        )
        assert state.verified is False
        assert state.buffer_packets == 1000
        assert state.loss_rate_percent == 0.0
        assert state.verification_log == []

    def test_all_fields_set(self):
        state = BottleneckState(
            download_mbps=100,
            upload_mbps=50,
            latency_ms=20,
            qdisc="pfifo",
            buffer_packets=500,
            verified=True,
            loss_rate_percent=1.5,
        )
        assert state.download_mbps == 100
        assert state.upload_mbps == 50
        assert state.latency_ms == 20
        assert state.qdisc == "pfifo"
        assert state.buffer_packets == 500
        assert state.verified is True
        assert state.loss_rate_percent == 1.5

    def test_zero_latency_allowed(self):
        state = BottleneckState(
            download_mbps=10, upload_mbps=5, latency_ms=0, qdisc="fq_codel"
        )
        assert state.latency_ms == 0


# ── /health endpoint ──────────────────────────────────────────────────────────


class TestHealthEndpoint:
    @patch(
        "app.main.HEALTH_CACHE",
        {
            "status": "ok",
            "root_privileges": True,
            "tc_available": True,
            "tshark_available": True,
            "tcpreplay_available": True,
            "qdisc_support": True,
            "interfaces": ["veth0", "veth2"],
        },
    )
    def test_health_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["root_privileges"] is True
        assert data["tc_available"] is True
        assert data["tshark_available"] is True
        assert data["tcpreplay_available"] is True
        assert data["qdisc_support"] is True
        assert "timestamp" in data

    @patch(
        "app.main.HEALTH_CACHE",
        {
            "status": "degraded",
            "root_privileges": False,
            "tc_available": True,
            "tshark_available": True,
            "tcpreplay_available": True,
            "qdisc_support": True,
            "interfaces": [],
        },
    )
    def test_health_degraded_no_root(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["root_privileges"] is False

    @patch(
        "app.main.HEALTH_CACHE",
        {
            "status": "degraded",
            "root_privileges": True,
            "tc_available": False,
            "tshark_available": False,
            "tcpreplay_available": False,
            "qdisc_support": False,
            "interfaces": [],
        },
    )
    def test_health_degraded_no_tools(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["tc_available"] is False
        assert data["tshark_available"] is False
        assert data["tcpreplay_available"] is False
        assert data["qdisc_support"] is False

    @patch(
        "app.main.HEALTH_CACHE",
        {
            "status": "ok",
            "root_privileges": True,
            "tc_available": True,
            "tshark_available": True,
            "tcpreplay_available": True,
            "qdisc_support": True,
            "interfaces": ["veth0", "veth2", "veth4"],
        },
    )
    def test_health_returns_all_interfaces(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["interfaces"] == ["veth0", "veth2", "veth4"]


# ── /state endpoint ───────────────────────────────────────────────────────────


class TestStateEndpoint:
    def test_state_no_config(self):
        resp = client.get("/state")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "no_state"
        assert body["bottleneck_state"] is None

    def test_state_returns_cached_state(self):
        main_module.CURRENT_BOTTLENECK_STATE = BottleneckState(
            download_mbps=10,
            upload_mbps=5,
            latency_ms=50,
            qdisc="fq_codel",
            verified=True,
        )
        resp = client.get("/state")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["bottleneck_state"]["download_mbps"] == 10
        assert body["bottleneck_state"]["upload_mbps"] == 5
        assert body["bottleneck_state"]["verified"] is True

    def test_state_does_not_call_verify(self):
        """GET /state must return cached result without re-running iperf3."""
        main_module.CURRENT_BOTTLENECK_STATE = BottleneckState(
            download_mbps=10, upload_mbps=5, latency_ms=50, qdisc="fq_codel"
        )
        with patch("app.main._verify_bottleneck_state") as mock_verify:
            client.get("/state")
            mock_verify.assert_not_called()

    def test_state_verified_false_by_default(self):
        main_module.CURRENT_BOTTLENECK_STATE = BottleneckState(
            download_mbps=25, upload_mbps=10, latency_ms=30, qdisc="pfifo"
        )
        resp = client.get("/state")
        assert resp.json()["bottleneck_state"]["verified"] is False


# ── /shape endpoint ───────────────────────────────────────────────────────────


class TestShapeEndpoint:
    @patch("app.main._verify_bottleneck_state")
    @patch("subprocess.run", return_value=MagicMock(returncode=0))
    def test_shape_returns_shaped_status(self, _run, _verify):
        resp = client.post("/shape", json=VALID_SHAPE_PAYLOAD)
        assert resp.status_code == 200
        assert resp.json()["status"] == "shaped"

    @patch("app.main._verify_bottleneck_state")
    @patch("subprocess.run", return_value=MagicMock(returncode=0))
    def test_shape_returns_correct_bottleneck_state(self, _run, _verify):
        resp = client.post("/shape", json=VALID_SHAPE_PAYLOAD)
        state = resp.json()["bottleneck_state"]
        assert state["download_mbps"] == 10.0
        assert state["upload_mbps"] == 5.0
        assert state["latency_ms"] == 50
        assert state["qdisc"] == "fq_codel"
        assert state["buffer_packets"] == 1000

    @patch("app.main._verify_bottleneck_state")
    @patch("subprocess.run", return_value=MagicMock(returncode=0))
    def test_shape_returns_applied_commands(self, _run, _verify):
        resp = client.post("/shape", json=VALID_SHAPE_PAYLOAD)
        assert len(resp.json()["applied_commands"]) > 0

    @patch("app.main._verify_bottleneck_state")
    @patch("subprocess.run", return_value=MagicMock(returncode=0))
    def test_shape_calls_verify_once(self, _run, mock_verify):
        """verify must be called exactly once per /shape call."""
        client.post("/shape", json=VALID_SHAPE_PAYLOAD)
        mock_verify.assert_called_once()

    @patch("app.main._verify_bottleneck_state")
    @patch("subprocess.run", return_value=MagicMock(returncode=0))
    def test_shape_updates_global_state(self, _run, _verify):
        client.post("/shape", json=VALID_SHAPE_PAYLOAD)
        assert main_module.CURRENT_BOTTLENECK_STATE is not None
        assert main_module.CURRENT_BOTTLENECK_STATE.download_mbps == 10.0
        assert main_module.CURRENT_INTERFACES["downstream_iface"] == "veth2"
        assert main_module.CURRENT_INTERFACES["upstream_iface"] == "veth4"

    def test_shape_missing_download_mbps(self):
        bad = {k: v for k, v in VALID_SHAPE_PAYLOAD.items() if k != "download_mbps"}
        assert client.post("/shape", json=bad).status_code == 422

    def test_shape_missing_upload_mbps(self):
        bad = {k: v for k, v in VALID_SHAPE_PAYLOAD.items() if k != "upload_mbps"}
        assert client.post("/shape", json=bad).status_code == 422

    def test_shape_missing_interfaces(self):
        bad = {k: v for k, v in VALID_SHAPE_PAYLOAD.items() if k != "upstream_iface"}
        assert client.post("/shape", json=bad).status_code == 422

    def test_shape_zero_download_rejected(self):
        assert (
            client.post(
                "/shape", json={**VALID_SHAPE_PAYLOAD, "download_mbps": 0}
            ).status_code
            == 422
        )

    def test_shape_zero_upload_rejected(self):
        assert (
            client.post(
                "/shape", json={**VALID_SHAPE_PAYLOAD, "upload_mbps": 0}
            ).status_code
            == 422
        )

    def test_shape_negative_bandwidth_rejected(self):
        assert (
            client.post(
                "/shape", json={**VALID_SHAPE_PAYLOAD, "download_mbps": -5}
            ).status_code
            == 422
        )

    def test_shape_negative_latency_rejected(self):
        assert (
            client.post(
                "/shape", json={**VALID_SHAPE_PAYLOAD, "latency_ms": -1}
            ).status_code
            == 422
        )

    def test_shape_zero_latency_allowed(self):
        with patch("app.main._verify_bottleneck_state"), patch(
            "subprocess.run", return_value=MagicMock(returncode=0)
        ):
            resp = client.post("/shape", json={**VALID_SHAPE_PAYLOAD, "latency_ms": 0})
            assert resp.status_code == 200

    @patch("app.main._verify_bottleneck_state")
    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "tc"))
    def test_shape_tc_failure_returns_500(self, _run, _verify):
        resp = client.post("/shape", json=VALID_SHAPE_PAYLOAD)
        assert resp.status_code == 500
        assert "tc command failed" in resp.json()["detail"]

    # ── qdisc_params validation ────────────────────────────────────────────────

    def test_shape_acm_qdisc_nondefault_buffer_packets_rejected(self):
        """buffer_packets != default is meaningless for AQM qdiscs — reject it."""
        resp = client.post(
            "/shape",
            json={**VALID_SHAPE_PAYLOAD, "qdisc": "fq_codel", "buffer_packets": 500},
        )
        assert resp.status_code == 422
        assert "buffer_packets" in resp.json()["detail"]

    def test_shape_limit_in_qdisc_params_for_limit_qdisc_rejected(self):
        """Passing 'limit' in qdisc_params for a limit-based qdisc conflicts with buffer_packets."""
        resp = client.post(
            "/shape",
            json={
                **VALID_SHAPE_PAYLOAD,
                "qdisc": "pfifo",
                "qdisc_params": {"limit": "200"},
            },
        )
        assert resp.status_code == 422
        assert "limit" in resp.json()["detail"]

    @patch("app.main._verify_bottleneck_state")
    @patch("subprocess.run", return_value=MagicMock(returncode=0))
    def test_shape_qdisc_params_stored_in_state(self, _run, _verify):
        params = {"target": "5ms", "interval": "100ms"}
        resp = client.post(
            "/shape",
            json={**VALID_SHAPE_PAYLOAD, "qdisc": "fq_codel", "qdisc_params": params},
        )
        assert resp.status_code == 200
        state = resp.json()["bottleneck_state"]
        assert state["qdisc_params"] == params

    @patch("app.main._verify_bottleneck_state")
    @patch("subprocess.run", return_value=MagicMock(returncode=0))
    def test_shape_qdisc_params_none_by_default(self, _run, _verify):
        resp = client.post("/shape", json=VALID_SHAPE_PAYLOAD)
        assert resp.status_code == 200
        assert resp.json()["bottleneck_state"]["qdisc_params"] is None

    @patch("app.main._verify_bottleneck_state")
    @patch("subprocess.run", return_value=MagicMock(returncode=0))
    def test_shape_acm_qdisc_default_buffer_packets_allowed(self, _run, _verify):
        """Default buffer_packets (1000) with AQM qdisc is fine — no error."""
        resp = client.post(
            "/shape",
            json={**VALID_SHAPE_PAYLOAD, "qdisc": "fq_codel", "buffer_packets": 1000},
        )
        assert resp.status_code == 200

    @patch("app.main._verify_bottleneck_state")
    @patch("subprocess.run", return_value=MagicMock(returncode=0))
    def test_shape_limit_in_qdisc_params_for_acm_qdisc_allowed(self, _run, _verify):
        """Explicit 'limit' in qdisc_params for AQM is allowed (advanced use)."""
        resp = client.post(
            "/shape",
            json={
                **VALID_SHAPE_PAYLOAD,
                "qdisc": "fq_codel",
                "qdisc_params": {"limit": "2000"},
            },
        )
        assert resp.status_code == 200


# ── /capture endpoint ─────────────────────────────────────────────────────────


class TestCaptureEndpoint:
    @patch("app.main._get_interfaces", return_value=["veth2", "veth4"])
    @patch("subprocess.Popen")
    def test_capture_started(self, mock_popen, _ifaces):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        resp = client.post(
            "/capture",
            json={
                "interface": "veth2",
                "capture_filter": "tcp port 443",
                "filename": "test_capture",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "started"
        assert "capture_id" in body
        assert body["interface"] == "veth2"
        assert body["capture_filter"] == "tcp port 443"

    @patch("app.main._get_interfaces", return_value=["veth2"])
    @patch("subprocess.Popen")
    def test_capture_stored_in_active_captures(self, mock_popen, _ifaces):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        resp = client.post(
            "/capture",
            json={
                "interface": "veth2",
                "capture_filter": "",
                "filename": "my_capture",
            },
        )
        capture_id = resp.json()["capture_id"]
        assert capture_id in main_module.ACTIVE_CAPTURES

    @patch("app.main._get_interfaces", return_value=["veth2"])
    def test_capture_unknown_interface(self, _):
        resp = client.post(
            "/capture",
            json={
                "interface": "nonexistent99",
                "capture_filter": "",
                "filename": "test",
            },
        )
        assert resp.status_code == 400
        assert "Unknown interface" in resp.json()["detail"]

    def test_capture_empty_filename_rejected(self):
        with patch("app.main._get_interfaces", return_value=["veth2"]):
            resp = client.post(
                "/capture",
                json={
                    "interface": "veth2",
                    "capture_filter": "",
                    "filename": "",
                },
            )
            assert resp.status_code == 400

    @patch("app.main._get_interfaces", return_value=["veth2"])
    @patch("subprocess.Popen")
    def test_capture_status_running(self, mock_popen, _ifaces):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_popen.return_value = mock_proc

        start_resp = client.post(
            "/capture",
            json={
                "interface": "veth2",
                "capture_filter": "",
                "filename": "running_test",
            },
        )
        capture_id = start_resp.json()["capture_id"]

        status_resp = client.get(f"/capture/{capture_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "running"

    @patch("app.main._get_interfaces", return_value=["veth2"])
    @patch("subprocess.Popen")
    def test_capture_status_finished(self, mock_popen, _ifaces):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # finished
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        start_resp = client.post(
            "/capture",
            json={
                "interface": "veth2",
                "capture_filter": "",
                "filename": "finished_test",
            },
        )
        capture_id = start_resp.json()["capture_id"]

        status_resp = client.get(f"/capture/{capture_id}")
        assert status_resp.json()["status"] == "finished"

    def test_capture_status_not_found(self):
        resp = client.get("/capture/nonexistent-id")
        assert resp.status_code == 404

    @patch("app.main._get_interfaces", return_value=["veth2"])
    @patch("subprocess.Popen")
    def test_capture_delete_stops_process(self, mock_popen, _ifaces):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        start_resp = client.post(
            "/capture",
            json={
                "interface": "veth2",
                "capture_filter": "",
                "filename": "to_delete",
            },
        )
        capture_id = start_resp.json()["capture_id"]

        del_resp = client.delete(f"/capture/{capture_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "stopped"
        mock_proc.terminate.assert_called_once()
        assert capture_id not in main_module.ACTIVE_CAPTURES

    def test_capture_delete_not_found(self):
        resp = client.delete("/capture/nonexistent-id")
        assert resp.status_code == 404


# ── /replay endpoint ──────────────────────────────────────────────────────────


class TestReplayEndpoint:
    VALID_REPLAY_PAYLOAD = {
        "ctp_file": "youtube_10mbps",
        "interface": "veth4",
        "rate": "10",
        "loop": False,
    }

    @patch("os.path.exists", return_value=True)
    @patch("subprocess.Popen")
    def test_replay_started(self, mock_popen, _exists):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        resp = client.post("/replay", json=self.VALID_REPLAY_PAYLOAD)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "started"
        assert "replay_id" in body
        assert body["ctp_file"] == "youtube_10mbps"
        assert body["interface"] == "veth4"
        assert body["rate"] == "10"

    @patch("os.path.exists", return_value=False)
    def test_replay_missing_ctp_file(self, _):
        resp = client.post("/replay", json=self.VALID_REPLAY_PAYLOAD)
        assert resp.status_code == 400
        assert "CTP file not found" in resp.json()["detail"]

    @patch("os.path.exists", return_value=True)
    @patch("subprocess.Popen")
    def test_replay_stored_in_active_replays(self, mock_popen, _exists):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        resp = client.post("/replay", json=self.VALID_REPLAY_PAYLOAD)
        replay_id = resp.json()["replay_id"]
        assert replay_id in main_module.ACTIVE_REPLAYS

    @patch("os.path.exists", return_value=True)
    @patch("subprocess.Popen")
    def test_replay_uses_tcpreplay_edit_with_pnat(self, mock_popen, _exists):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        payload = {**self.VALID_REPLAY_PAYLOAD, "pnat": "169.231.0.0/16:172.16.1.1"}
        client.post("/replay", json=payload)

        cmd_used = mock_popen.call_args[0][0]
        assert "tcpreplay-edit" in cmd_used
        assert "--pnat=" in cmd_used

    @patch("os.path.exists", return_value=True)
    @patch("subprocess.Popen")
    def test_replay_uses_plain_tcpreplay_without_pnat(self, mock_popen, _exists):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        client.post("/replay", json=self.VALID_REPLAY_PAYLOAD)

        cmd_used = mock_popen.call_args[0][0]
        assert "tcpreplay-edit" not in cmd_used
        assert "tcpreplay" in cmd_used

    @patch("os.path.exists", return_value=True)
    @patch("subprocess.Popen")
    def test_replay_status_running(self, mock_popen, _exists):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        start_resp = client.post("/replay", json=self.VALID_REPLAY_PAYLOAD)
        replay_id = start_resp.json()["replay_id"]

        status_resp = client.get(f"/replay/{replay_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "running"

    @patch("os.path.exists", return_value=True)
    @patch("subprocess.Popen")
    def test_replay_status_finished(self, mock_popen, _exists):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_popen.return_value = mock_proc

        start_resp = client.post("/replay", json=self.VALID_REPLAY_PAYLOAD)
        replay_id = start_resp.json()["replay_id"]

        status_resp = client.get(f"/replay/{replay_id}")
        assert status_resp.json()["status"] == "finished"

    def test_replay_status_not_found(self):
        resp = client.get("/replay/nonexistent-id")
        assert resp.status_code == 404

    @patch("os.path.exists", return_value=True)
    @patch("subprocess.Popen")
    def test_replay_delete_stops_process(self, mock_popen, _exists):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        start_resp = client.post("/replay", json=self.VALID_REPLAY_PAYLOAD)
        replay_id = start_resp.json()["replay_id"]

        del_resp = client.delete(f"/replay/{replay_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "stopped"
        mock_proc.terminate.assert_called_once()
        assert replay_id not in main_module.ACTIVE_REPLAYS

    def test_replay_delete_not_found(self):
        resp = client.delete("/replay/nonexistent-id")
        assert resp.status_code == 404
