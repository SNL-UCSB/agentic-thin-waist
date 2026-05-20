"""Tests for the CCAnalyzer congestion-control whitelist + observation parser.

Issue #142: substrate-worker must (1) accept exactly the 15 wide-area CCAs
enumerated in the CCAnalyzer paper, (2) attempt modprobe on demand for any
that aren't yet loaded, and (3) verify the configured CCA actually shows up
on live TCP sockets during workflow execution.
"""

from unittest.mock import MagicMock, patch

import pytest
import subprocess
from fastapi.testclient import TestClient

# Importing substrate.main triggers tc/iperf3 subprocess calls in the startup
# hook; pin them to no-op while the module loads.
with patch(
    "subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")
):
    from substrate.main import (
        CCANALYZER_CCAS,
        _ensure_cca_loaded,
        _parse_ss_congestion,
        app,
    )

client = TestClient(app)


# ── Whitelist contents ────────────────────────────────────────────────────────


class TestCCAnalyzerWhitelist:
    """The whitelist must be exactly the 15 wide-area algorithms from the
    CCAnalyzer paper. lp and dctcp are intentionally excluded (they require
    in-network LEDBAT / ECN support not available in the wide area)."""

    EXPECTED_15 = {
        "bbr",
        "bic",
        "cdg",
        "cubic",
        "highspeed",
        "htcp",
        "hybla",
        "illinois",
        "nv",
        "reno",
        "scalable",
        "vegas",
        "veno",
        "westwood",
        "yeah",
    }

    def test_whitelist_size(self):
        assert len(CCANALYZER_CCAS) == 15

    def test_whitelist_names(self):
        assert set(CCANALYZER_CCAS) == self.EXPECTED_15

    def test_lp_excluded(self):
        assert "lp" not in CCANALYZER_CCAS

    def test_dctcp_excluded(self):
        assert "dctcp" not in CCANALYZER_CCAS

    def test_reno_has_no_module(self):
        # reno is always built into the kernel; flagged with empty-string module.
        assert CCANALYZER_CCAS["reno"] == ""

    def test_module_names_are_tcp_prefixed(self):
        for algo, module in CCANALYZER_CCAS.items():
            if not module:
                continue
            assert module.startswith("tcp_"), f"{algo} → {module!r} missing tcp_ prefix"


# ── /congestion endpoint validation ───────────────────────────────────────────


class TestCongestionEndpoint:
    @patch("substrate.main._ensure_cca_loaded", return_value=(True, "already loaded"))
    @patch(
        "substrate.main._sysctl_get_available",
        return_value=["cubic", "reno", "bbr"],
    )
    @patch(
        "substrate.main._apply_cca_in_ns",
        return_value="sysctl -w net.ipv4.tcp_congestion_control=bbr",
    )
    def test_accepted_cca_returns_200(self, _apply, _avail, _ensure):
        resp = client.post("/congestion", json={"algorithm": "bbr", "namespace": "ns1"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["current_algorithm"] == "bbr"
        assert "bbr" in body["available_algorithms"]

    def test_unknown_cca_rejected_before_kernel_check(self):
        # 'fakecc' isn't in the whitelist — must 400 without ever calling sysctl.
        with patch("substrate.main._sysctl_get_available") as avail:
            resp = client.post(
                "/congestion", json={"algorithm": "fakecc", "namespace": "ns1"}
            )
            assert resp.status_code == 400
            assert "CCAnalyzer whitelist" in resp.json()["detail"]
            # whitelist check is purely string-based; no sysctl needed.
            avail.assert_not_called()

    def test_dctcp_rejected(self):
        resp = client.post(
            "/congestion", json={"algorithm": "dctcp", "namespace": "ns1"}
        )
        assert resp.status_code == 400
        assert "CCAnalyzer whitelist" in resp.json()["detail"]

    def test_lp_rejected(self):
        resp = client.post("/congestion", json={"algorithm": "lp", "namespace": "ns1"})
        assert resp.status_code == 400

    @patch(
        "substrate.main._ensure_cca_loaded",
        return_value=(False, "modprobe tcp_yeah failed: module not found"),
    )
    @patch(
        "substrate.main._sysctl_get_available",
        return_value=["cubic", "reno"],
    )
    def test_whitelisted_but_unloadable_returns_400_with_detail(self, _avail, _ensure):
        # Algorithm is in CCAnalyzer's 15 but this kernel can't load it.
        # Must surface the modprobe failure detail so callers can diagnose.
        resp = client.post(
            "/congestion", json={"algorithm": "yeah", "namespace": "ns1"}
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "yeah" in detail
        assert "modprobe tcp_yeah failed" in detail
        assert "Currently loadable" in detail


# ── _ensure_cca_loaded behavior ───────────────────────────────────────────────


class TestEnsureCcaLoaded:
    @patch(
        "substrate.main._sysctl_get_available",
        return_value=["cubic", "reno", "bbr"],
    )
    def test_returns_true_when_already_available(self, _avail):
        loaded, detail = _ensure_cca_loaded("bbr")
        assert loaded is True
        assert detail == "already loaded"

    def test_returns_false_for_unknown_name(self):
        with patch(
            "substrate.main._sysctl_get_available", return_value=["cubic", "reno"]
        ):
            loaded, detail = _ensure_cca_loaded("fakecc")
            assert loaded is False
            assert "CCAnalyzer whitelist" in detail

    @patch("subprocess.run")
    @patch("substrate.main._sysctl_get_available")
    def test_attempts_modprobe_and_succeeds(self, avail, run):
        # First call: not loaded. Second call (post-modprobe): loaded.
        avail.side_effect = [["cubic", "reno"], ["cubic", "reno", "bbr"]]
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        loaded, detail = _ensure_cca_loaded("bbr")
        assert loaded is True
        assert "modprobe tcp_bbr" in detail
        # Verify we actually called modprobe.
        modprobe_calls = [c for c in run.call_args_list if "modprobe" in str(c)]
        assert modprobe_calls

    @patch("subprocess.run")
    @patch(
        "substrate.main._sysctl_get_available",
        return_value=["cubic", "reno"],
    )
    def test_returns_false_when_modprobe_fails(self, _avail, run):
        run.return_value = MagicMock(returncode=1, stdout="", stderr="module not found")
        loaded, detail = _ensure_cca_loaded("bbr")
        assert loaded is False
        assert "modprobe tcp_bbr failed" in detail
        assert "module not found" in detail


# ── ss -tin output parsing ────────────────────────────────────────────────────


class TestParseSsCongestion:
    SS_SAMPLE_CUBIC = """
State    Recv-Q Send-Q   Local Address:Port    Peer Address:Port
ESTAB    0      0        172.16.1.1:40132     91.189.91.108:443
\t cubic wscale:7,7 rto:340 rtt:139.5/0.5 ato:40 mss:1448 pmtu:1500 rcvmss:1448 advmss:1448 cwnd:10 bytes_sent:5840 bytes_acked:5841 segs_out:122 segs_in:120 data_segs_out:1 send 829.7Kbps lastsnd:8 lastrcv:8 lastack:8 pacing_rate 1.7Mbps delivery_rate 829.7Kbps delivered:2 app_limited busy:8ms rcv_rtt:139 rcv_space:14600 rcv_ssthresh:64076 minrtt:139.5 snd_wnd:64256 cong:cubic
"""

    SS_SAMPLE_TWO_SOCKETS_BBR = """
ESTAB    0    0    172.16.1.1:40000   1.2.3.4:443
\t bbr wscale:7,7 cong:bbr
ESTAB    0    0    172.16.1.1:40002   5.6.7.8:443
\t bbr wscale:7,7 cong:bbr
"""

    SS_SAMPLE_MIXED = """
ESTAB    0    0    a:1 b:2
\t cong:cubic
ESTAB    0    0    c:3 d:4
\t cong:reno
ESTAB    0    0    e:5 f:6
\t cong:cubic
"""

    def test_parses_single_cubic_socket(self):
        assert _parse_ss_congestion(self.SS_SAMPLE_CUBIC) == {"cubic": 1}

    def test_counts_multiple_sockets_same_algo(self):
        assert _parse_ss_congestion(self.SS_SAMPLE_TWO_SOCKETS_BBR) == {"bbr": 2}

    def test_aggregates_mixed_algos(self):
        assert _parse_ss_congestion(self.SS_SAMPLE_MIXED) == {"cubic": 2, "reno": 1}

    def test_empty_output_returns_empty_dict(self):
        assert _parse_ss_congestion("") == {}

    def test_no_cong_field_returns_empty_dict(self):
        # Some kernels strip the `cong:` field when ss is run without --info.
        # Our parser must not invent matches from random text.
        assert _parse_ss_congestion("ESTAB 0 0 a:1 b:2") == {}

    def test_underscore_algo_names_supported(self):
        # bbr_v2 / dctcp-style underscored names appear on newer kernels.
        text = "ESTAB 0 0 a:1 b:2\n\t cong:bbr_v2"
        assert _parse_ss_congestion(text) == {"bbr_v2": 1}
