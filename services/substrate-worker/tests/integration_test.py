import pytest
import requests
import time

BASE = "http://localhost:8002"

SHAPE_PAYLOAD = {
    "upstream_iface": "veth4",
    "downstream_iface": "veth2",
    "download_mbps": 10.0,
    "upload_mbps": 5.0,
    "latency_ms": 50,
    "qdisc": "fq_codel",
    "buffer_packets": 1000,
}

TOLERANCE = 0.20


# ── Helpers ───────────────────────────────────────────────────────────────────


def within_tolerance(measured: float, expected: float, tol: float = TOLERANCE) -> bool:
    return abs(measured - expected) / expected <= tol


# ── /health ───────────────────────────────────────────────────────────────────

@pytest.mark.skip(reason="Not ready yet.")
class TestHealthIntegration:
    @pytest.fixture(autouse=True, scope="class")
    def health_response(self, request):
        """GET /health once for the whole class, share the response."""
        r = requests.get(f"{BASE}/health", timeout=5)
        request.cls.response = r
        request.cls.body = r.json()

    def test_health_reachable(self):
        assert self.response.status_code == 200

    def test_health_status_ok_or_degraded(self):
        assert self.body["status"] in ("ok", "degraded")

    def test_health_has_required_fields(self):
        for field in [
            "status",
            "root_privileges",
            "tc_available",
            "tshark_available",
            "tcpreplay_available",
            "qdisc_support",
            "interfaces",
            "timestamp",
        ]:
            assert field in self.body, f"Missing field: {field}"

    def test_health_interfaces_is_list(self):
        assert isinstance(self.body["interfaces"], list)

    def test_health_root_privileges_true(self):
        """Container must be running with --privileged."""
        assert self.body["root_privileges"] is True

    def test_health_tc_available(self):
        assert self.body["tc_available"] is True

    def test_health_tshark_available(self):
        assert self.body["tshark_available"] is True

    def test_health_tcpreplay_available(self):
        assert self.body["tcpreplay_available"] is True


# ── /state (before any shape) ─────────────────────────────────────────────────


@pytest.mark.skip(reason="Not ready yet.")
class TestStateBeforeShape:
    def test_state_returns_200(self):
        r = requests.get(f"{BASE}/state", timeout=10)
        assert r.status_code == 200

    def test_state_no_state_on_fresh_container(self):
        """Only meaningful if container was freshly started."""
        r = requests.get(f"{BASE}/state", timeout=10)
        body = r.json()
        # Either no_state (fresh) or ok (already shaped in a prior test)
        assert body["status"] in ("no_state", "ok")


# ── /shape ────────────────────────────────────────────────────────────────────


@pytest.mark.skip(reason="Not ready yet.")
class TestShapeIntegration:
    @pytest.fixture(autouse=True, scope="class")
    def shape_response(self, request):
        """POST /shape once for the whole class, share the response."""
        r = requests.post(f"{BASE}/shape", json=SHAPE_PAYLOAD, timeout=30)
        request.cls.response = r
        request.cls.body = r.json()
        request.cls.state = r.json()["bottleneck_state"]

    # ── single POST, all checks on the same response ──────────────────────────

    def test_shape_returns_200(self):
        assert self.response.status_code == 200

    def test_shape_status_is_shaped(self):
        assert self.body["status"] == "shaped"

    def test_shape_applied_commands_non_empty(self):
        assert len(self.body["applied_commands"]) > 0

    def test_shape_applied_commands_contain_tc(self):
        assert any("tc" in cmd for cmd in self.body["applied_commands"])

    def test_shape_bottleneck_state_fields_present(self):
        for field in [
            "download_mbps",
            "upload_mbps",
            "latency_ms",
            "qdisc",
            "verified",
            "buffer_packets",
        ]:
            assert field in self.state, f"Missing field: {field}"

    def test_shape_bottleneck_state_values_match_request(self):
        assert self.state["download_mbps"] == SHAPE_PAYLOAD["download_mbps"]
        assert self.state["upload_mbps"] == SHAPE_PAYLOAD["upload_mbps"]
        assert self.state["latency_ms"] == SHAPE_PAYLOAD["latency_ms"]
        assert self.state["qdisc"] == SHAPE_PAYLOAD["qdisc"]
        assert self.state["buffer_packets"] == SHAPE_PAYLOAD["buffer_packets"]

    # ── validation tests — each needs its own bad POST, unavoidable ───────────

    def test_shape_zero_bandwidth_rejected(self):
        r = requests.post(
            f"{BASE}/shape", json={**SHAPE_PAYLOAD, "download_mbps": 0}, timeout=10
        )
        assert r.status_code == 422

    def test_shape_negative_bandwidth_rejected(self):
        r = requests.post(
            f"{BASE}/shape", json={**SHAPE_PAYLOAD, "upload_mbps": -1}, timeout=10
        )
        assert r.status_code == 422

    def test_shape_negative_latency_rejected(self):
        r = requests.post(
            f"{BASE}/shape", json={**SHAPE_PAYLOAD, "latency_ms": -10}, timeout=10
        )
        assert r.status_code == 422

    def test_shape_missing_required_field_rejected(self):
        bad = {k: v for k, v in SHAPE_PAYLOAD.items() if k != "download_mbps"}
        r = requests.post(f"{BASE}/shape", json=bad, timeout=10)
        assert r.status_code == 422

    def test_shape_zero_latency_accepted(self):
        r = requests.post(
            f"{BASE}/shape", json={**SHAPE_PAYLOAD, "latency_ms": 0}, timeout=30
        )
        assert r.status_code == 200

    def test_shape_different_capacities(self):
        payload = {**SHAPE_PAYLOAD, "download_mbps": 25.0, "upload_mbps": 10.0}
        r = requests.post(f"{BASE}/shape", json=payload, timeout=30)
        assert r.status_code == 200
        state = r.json()["bottleneck_state"]
        assert state["download_mbps"] == 25.0
        assert state["upload_mbps"] == 10.0

        # Restore for subsequent test classes
        requests.post(f"{BASE}/shape", json=SHAPE_PAYLOAD, timeout=30)


# ── /state (after shape) ──────────────────────────────────────────────────────


@pytest.mark.skip(reason="Not ready yet.")
class TestStateAfterShape:
    @pytest.fixture(autouse=True, scope="class")
    def shape_then_state(self, request):
        """POST /shape once, then GET /state once, share both responses."""
        requests.post(f"{BASE}/shape", json=SHAPE_PAYLOAD, timeout=30)
        r = requests.get(f"{BASE}/state", timeout=10)
        request.cls.response = r
        request.cls.body = r.json()
        request.cls.state = r.json()["bottleneck_state"]

    def test_state_returns_200(self):
        assert self.response.status_code == 200

    def test_state_status_ok(self):
        assert self.body["status"] == "ok"

    def test_state_bottleneck_state_not_none(self):
        assert self.state is not None

    def test_state_download_mbps_matches(self):
        assert self.state["download_mbps"] == SHAPE_PAYLOAD["download_mbps"]

    def test_state_upload_mbps_matches(self):
        assert self.state["upload_mbps"] == SHAPE_PAYLOAD["upload_mbps"]

    def test_state_verified_field_present(self):
        assert "verified" in self.state

    def test_state_verified_true_after_successful_shape(self):
        """Passes only if iperf3 namespaces (ns1/ns2) are configured in container."""
        assert self.state["verified"] is True

    def test_state_measured_download_within_tolerance(self):
        log = self.state.get("verification_log") or []
        prefix = "download: measured="
        measured = None
        for entry in log:
            if entry.startswith(prefix):
                try:
                    # entry looks like:
                    # "download: measured=9.87Mbps expected=10.0Mbps diff=1.3%"
                    part = entry.split("measured=")[1].split("Mbps")[0]
                    measured = float(part)
                except Exception:
                    continue
        if measured is None:
            pytest.skip("No download measurement found in verification_log")
        assert within_tolerance(measured, SHAPE_PAYLOAD["download_mbps"])

    def test_state_measured_upload_within_tolerance(self):
        log = self.state.get("verification_log") or []
        prefix = "upload: measured="
        measured = None
        for entry in log:
            if entry.startswith(prefix):
                try:
                    # entry looks like:
                    # "upload: measured=9.87Mbps expected=10.0Mbps diff=1.3%"
                    part = entry.split("measured=")[1].split("Mbps")[0]
                    measured = float(part)
                except Exception:
                    continue
        if measured is None:
            pytest.skip("No upload measurement found in verification_log")
        assert within_tolerance(measured, SHAPE_PAYLOAD["upload_mbps"])


# ── /capture ──────────────────────────────────────────────────────────────────


@pytest.mark.skip(reason="Not ready yet.")
class TestCaptureIntegration:
    @pytest.fixture(autouse=True, scope="class")
    def capture_session(self, request):
        """POST /capture once for read-only checks, cleanup after all tests."""
        r = requests.post(
            f"{BASE}/capture",
            json={
                "interface": "veth2",
                "capture_filter": "",
                "filename": "integ_test_capture",
            },
            timeout=10,
        )
        request.cls.response = r
        request.cls.body = r.json()
        request.cls.capture_id = r.json().get("capture_id")
        yield
        # Cleanup shared session after all tests in class are done
        if request.cls.capture_id:
            requests.delete(f"{BASE}/capture/{request.cls.capture_id}", timeout=5)

    # ── shared session checks (no extra POST needed) ──────────────────────────

    def test_capture_start_returns_200(self):
        assert self.response.status_code == 200

    def test_capture_start_has_capture_id(self):
        assert "capture_id" in self.body

    def test_capture_start_has_correct_interface(self):
        assert self.body["interface"] == "veth2"

    def test_capture_status_running(self):
        status = requests.get(f"{BASE}/capture/{self.capture_id}", timeout=5)
        assert status.status_code == 200
        assert status.json()["status"] in ("running", "finished")

    # ── error path tests (no session needed) ─────────────────────────────────

    def test_capture_status_not_found(self):
        r = requests.get(f"{BASE}/capture/nonexistent-id", timeout=5)
        assert r.status_code == 404

    def test_capture_delete_not_found(self):
        r = requests.delete(f"{BASE}/capture/nonexistent-id", timeout=5)
        assert r.status_code == 404

    def test_capture_unknown_interface_rejected(self):
        r = requests.post(
            f"{BASE}/capture",
            json={
                "interface": "nonexistent99",
                "capture_filter": "",
                "filename": "bad_iface_test",
            },
            timeout=10,
        )
        assert r.status_code == 400

    # ── tests that need their own session (different behavior per test) ────────

    def test_capture_stop(self):
        r = requests.post(
            f"{BASE}/capture",
            json={
                "interface": "veth2",
                "capture_filter": "",
                "filename": "integ_stop_test",
            },
            timeout=10,
        )
        capture_id = r.json()["capture_id"]

        stop = requests.delete(f"{BASE}/capture/{capture_id}", timeout=5)
        assert stop.status_code == 200
        assert stop.json()["status"] == "stopped"

    def test_capture_stop_removes_session(self):
        """After DELETE, GET should return 404."""
        r = requests.post(
            f"{BASE}/capture",
            json={
                "interface": "veth2",
                "capture_filter": "",
                "filename": "integ_stop_removes_test",
            },
            timeout=10,
        )
        capture_id = r.json()["capture_id"]
        requests.delete(f"{BASE}/capture/{capture_id}", timeout=5)

        status = requests.get(f"{BASE}/capture/{capture_id}", timeout=5)
        assert status.status_code == 404

    def test_capture_with_duration(self):
        r = requests.post(
            f"{BASE}/capture",
            json={
                "interface": "veth2",
                "capture_filter": "",
                "filename": "integ_duration_test",
                "duration_seconds": 2,
            },
            timeout=10,
        )
        assert r.status_code == 200
        capture_id = r.json()["capture_id"]

        time.sleep(3)
        status = requests.get(f"{BASE}/capture/{capture_id}", timeout=5)
        assert status.json()["status"] == "finished"


# ── /replay ───────────────────────────────────────────────────────────────────


@pytest.mark.skip(reason="Not ready yet.")
class TestReplayIntegration:
    """
    Requires a valid .pcap file inside CTP_DIR inside the container.
    Mount with: -v /home/netreplica/config/ctp:/home/netreplica/config/ctp
    Test uses 'out_70_profile8.pcap' (note: no underscore before 8).
    Error-path tests always run. Success-path tests skip if CTP file is missing.
    """

    CTP_FILE = (
        "out_70_profile8"  # matches actual filename in /home/netreplica/config/ctp
    )
    REPLAY_PAYLOAD = {
        "ctp_file": CTP_FILE,
        "interface": "veth1",
        "rate": "10",
        "loop": False,
        "duration_seconds": 40,
        "pnat": "169.231.0.0/16:172.16.1.1,128.111.0.0/16:172.16.1.1",
    }

    @pytest.fixture(autouse=True, scope="class")
    def replay_session(self, request):
        """POST /replay once for read-only checks, cleanup after all tests."""
        r = requests.post(f"{BASE}/replay", json=self.REPLAY_PAYLOAD, timeout=10)

        if r.status_code == 400 and "CTP file not found" in r.json().get("detail", ""):
            request.cls.skipped = True
            request.cls.response = r
            request.cls.body = {}
            request.cls.replay_id = None
        else:
            request.cls.skipped = False
            request.cls.response = r
            request.cls.body = r.json()
            request.cls.replay_id = r.json().get("replay_id")

            # Also fetch status for status-check tests
            status = requests.get(f"{BASE}/replay/{request.cls.replay_id}", timeout=5)
            request.cls.status_response = status
            request.cls.status_body = status.json()

        yield

        # Cleanup shared session
        if request.cls.replay_id:
            requests.delete(f"{BASE}/replay/{request.cls.replay_id}", timeout=5)

    # ── error path tests — always run, no CTP file needed ────────────────────

    def test_replay_missing_ctp_file_returns_400(self):
        r = requests.post(
            f"{BASE}/replay",
            json={
                **self.REPLAY_PAYLOAD,
                "ctp_file": "nonexistent_file_xyz",
            },
            timeout=10,
        )
        assert r.status_code == 400
        assert "CTP file not found" in r.json()["detail"]

    def test_replay_missing_required_fields_rejected(self):
        bad = {k: v for k, v in self.REPLAY_PAYLOAD.items() if k != "interface"}
        r = requests.post(f"{BASE}/replay", json=bad, timeout=10)
        assert r.status_code == 422

    def test_replay_status_not_found(self):
        r = requests.get(f"{BASE}/replay/nonexistent-id", timeout=5)
        assert r.status_code == 404

    def test_replay_delete_not_found(self):
        r = requests.delete(f"{BASE}/replay/nonexistent-id", timeout=5)
        assert r.status_code == 404

    # ── shared session checks (no extra POST needed) ──────────────────────────

    def test_replay_start_returns_200(self):
        if self.skipped:
            pytest.skip(f"CTP file '{self.CTP_FILE}.pcap' not found in container")
        assert self.response.status_code == 200

    def test_replay_start_has_replay_id(self):
        if self.skipped:
            pytest.skip("CTP file not found")
        assert "replay_id" in self.body

    def test_replay_response_fields(self):
        if self.skipped:
            pytest.skip("CTP file not found")
        for field in ["replay_id", "status", "ctp_file", "interface", "rate"]:
            assert field in self.body, f"Missing field: {field}"

    def test_replay_response_status_is_started(self):
        if self.skipped:
            pytest.skip("CTP file not found")
        assert self.body["status"] == "started"

    def test_replay_response_ctp_file_matches(self):
        if self.skipped:
            pytest.skip("CTP file not found")
        assert self.body["ctp_file"] == self.CTP_FILE

    def test_replay_response_interface_matches(self):
        if self.skipped:
            pytest.skip("CTP file not found")
        assert self.body["interface"] == self.REPLAY_PAYLOAD["interface"]

    def test_replay_response_rate_matches(self):
        if self.skipped:
            pytest.skip("CTP file not found")
        assert self.body["rate"] == self.REPLAY_PAYLOAD["rate"]

    def test_replay_status_returns_200(self):
        if self.skipped:
            pytest.skip("CTP file not found")
        assert self.status_response.status_code == 200

    def test_replay_status_running_or_finished(self):
        if self.skipped:
            pytest.skip("CTP file not found")
        assert self.status_body["status"] in ("running", "finished")

    def test_replay_status_fields(self):
        if self.skipped:
            pytest.skip("CTP file not found")
        for field in [
            "replay_id",
            "status",
            "ctp_file",
            "interface",
            "rate",
            "start_time",
        ]:
            assert field in self.status_body, f"Missing field: {field}"

    def test_replay_status_replay_id_matches(self):
        if self.skipped:
            pytest.skip("CTP file not found")
        assert self.status_body["replay_id"] == self.replay_id

    # ── tests that need their own session (different behavior per test) ────────

    def test_replay_stop(self):
        if self.skipped:
            pytest.skip("CTP file not found")
        r = requests.post(
            f"{BASE}/replay", json={**self.REPLAY_PAYLOAD, "loop": True}, timeout=10
        )
        replay_id = r.json()["replay_id"]

        stop = requests.delete(f"{BASE}/replay/{replay_id}", timeout=5)
        assert stop.status_code == 200
        assert stop.json()["status"] == "stopped"
        assert stop.json()["replay_id"] == replay_id

    def test_replay_stop_removes_session(self):
        """After DELETE, GET should return 404."""
        if self.skipped:
            pytest.skip("CTP file not found")
        r = requests.post(
            f"{BASE}/replay", json={**self.REPLAY_PAYLOAD, "loop": True}, timeout=10
        )
        replay_id = r.json()["replay_id"]

        requests.delete(f"{BASE}/replay/{replay_id}", timeout=5)
        assert requests.get(f"{BASE}/replay/{replay_id}", timeout=5).status_code == 404

    def test_replay_with_duration(self):
        if self.skipped:
            pytest.skip("CTP file not found")
        r = requests.post(
            f"{BASE}/replay",
            json={**self.REPLAY_PAYLOAD, "loop": False, "duration_seconds": 2},
            timeout=10,
        )
        replay_id = r.json()["replay_id"]

        time.sleep(4)
        assert (
            requests.get(f"{BASE}/replay/{replay_id}", timeout=5).json()["status"]
            == "finished"
        )

    def test_multiple_concurrent_replays(self):
        """Two replay sessions must get distinct replay_ids."""
        if self.skipped:
            pytest.skip("CTP file not found")
        r1 = requests.post(
            f"{BASE}/replay", json={**self.REPLAY_PAYLOAD, "loop": True}, timeout=10
        )
        r2 = requests.post(
            f"{BASE}/replay", json={**self.REPLAY_PAYLOAD, "loop": True}, timeout=10
        )

        id1, id2 = r1.json()["replay_id"], r2.json()["replay_id"]
        assert id1 != id2

        requests.delete(f"{BASE}/replay/{id1}", timeout=5)
        requests.delete(f"{BASE}/replay/{id2}", timeout=5)
