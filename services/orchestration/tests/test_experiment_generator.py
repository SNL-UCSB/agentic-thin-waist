from app.engine.experiment_generator import ExperimentGenerator, _classify_app


def test_generator_propagates_explicit_ctp_capacity_range():
    parsed = {
        "application_type": "shell",
        "capacities": [10],
        "latencies": [50],
        "cc_algorithms": ["cubic"],
        "ctp_capacity_range": {"lower_value": 2, "higher_value": 5},
    }
    out = ExperimentGenerator().generate(parsed)
    assert len(out) == 1
    assert out[0].ctp_capacity_range == {"lower_value": 2, "higher_value": 5}


def test_generator_leaves_ctp_capacity_range_none_when_missing():
    """Absent CTP in intent → None in spec → orchestrator skips CTP replay."""
    parsed = {
        "application_type": "shell",
        "capacities": [10],
        "latencies": [50],
        "cc_algorithms": ["cubic"],
    }
    out = ExperimentGenerator().generate(parsed)
    assert len(out) == 1
    assert out[0].ctp_capacity_range is None
    assert out[0].ctp_cluster is None


# ---------------------------------------------------------------------------
# Single-app backward compatibility
# ---------------------------------------------------------------------------


def test_single_app_unchanged():
    """Single application produces the same output as before."""
    parsed = {
        "applications": ["wget"],
        "application_type": "shell",
        "capacities": [10, 25],
        "latencies": [50],
        "cc_algorithms": ["cubic"],
    }
    out = ExperimentGenerator().generate(parsed)
    assert len(out) == 2
    for e in out:
        assert e.execution_mode == "isolated"
        assert e.applications == []
        assert e.application_types == []
        assert "wget" in e.experiment_id


def test_no_apps_uses_application_type():
    """Empty applications list uses application_type as slug."""
    parsed = {
        "applications": [],
        "application_type": "shell",
        "capacities": [10],
        "latencies": [50],
        "cc_algorithms": ["cubic"],
    }
    out = ExperimentGenerator().generate(parsed)
    assert len(out) == 1
    assert "shell" in out[0].experiment_id


# ---------------------------------------------------------------------------
# Multi-app: concurrent design_type
# ---------------------------------------------------------------------------


def test_concurrent_multi_app():
    """Two apps + design_type=['concurrent'] → one concurrent experiment per combo."""
    parsed = {
        "applications": ["iperf3", "wget"],
        "application_type": "shell",
        "capacities": [10, 25],
        "latencies": [50],
        "cc_algorithms": ["cubic"],
        "design_type": ["concurrent"],
    }
    out = ExperimentGenerator().generate(parsed)
    assert len(out) == 2  # 2 capacities × 1 latency × 1 cc
    for e in out:
        assert e.execution_mode == "concurrent"
        assert e.applications == ["iperf3", "wget"]
        assert e.application_types == ["shell", "shell"]
        assert "iperf3+wget" in e.experiment_id
        assert e.application_type == "shell"


def test_concurrent_mixed_types():
    """Shell + browser apps → application_type='mixed'."""
    parsed = {
        "applications": ["youtube", "ndt"],
        "application_type": "mixed",
        "capacities": [25],
        "latencies": [50],
        "cc_algorithms": ["cubic"],
        "design_type": ["concurrent"],
    }
    out = ExperimentGenerator().generate(parsed)
    assert len(out) == 1
    e = out[0]
    assert e.execution_mode == "concurrent"
    assert e.applications == ["youtube", "ndt"]
    assert e.application_types == ["browser", "shell"]
    assert e.application_type == "mixed"
    assert "youtube+ndt" in e.experiment_id


# ---------------------------------------------------------------------------
# Multi-app: isolated design_type
# ---------------------------------------------------------------------------


def test_isolated_multi_app():
    """Two apps + design_type=['isolated'] → one experiment per (app × combo)."""
    parsed = {
        "applications": ["iperf3", "wget"],
        "application_type": "shell",
        "capacities": [10],
        "latencies": [50],
        "cc_algorithms": ["cubic", "bbr"],
        "design_type": ["isolated"],
    }
    out = ExperimentGenerator().generate(parsed)
    assert len(out) == 4  # 2 apps × 1 cap × 1 lat × 2 cc
    slugs = [e.experiment_id for e in out]
    assert sum("iperf3" in s for s in slugs) == 2
    assert sum("wget" in s for s in slugs) == 2
    for e in out:
        assert e.execution_mode == "isolated"
        assert len(e.applications) == 1


# ---------------------------------------------------------------------------
# Multi-app: full design_type
# ---------------------------------------------------------------------------


def test_full_multi_app():
    """Two apps + design_type=['full'] → isolated + concurrent experiments."""
    parsed = {
        "applications": ["iperf3", "wget"],
        "application_type": "shell",
        "capacities": [10],
        "latencies": [50],
        "cc_algorithms": ["cubic"],
        "design_type": ["full"],
    }
    out = ExperimentGenerator().generate(parsed)
    # 2 isolated (one per app) + 1 concurrent = 3
    assert len(out) == 3
    isolated = [e for e in out if e.execution_mode == "isolated"]
    concurrent = [e for e in out if e.execution_mode == "concurrent"]
    assert len(isolated) == 2
    assert len(concurrent) == 1
    assert concurrent[0].applications == ["iperf3", "wget"]


# ---------------------------------------------------------------------------
# Multi-app: default (no design_type) → concurrent
# ---------------------------------------------------------------------------


def test_multi_app_no_design_type_defaults_concurrent():
    """Multiple apps with empty design_type defaults to concurrent."""
    parsed = {
        "applications": ["ping", "wget"],
        "application_type": "shell",
        "capacities": [10],
        "latencies": [50],
        "cc_algorithms": ["cubic"],
        "design_type": [],
    }
    out = ExperimentGenerator().generate(parsed)
    assert len(out) == 1
    assert out[0].execution_mode == "concurrent"


# ---------------------------------------------------------------------------
# App classification helper
# ---------------------------------------------------------------------------


def test_classify_app():
    assert _classify_app("youtube") == "browser"
    assert _classify_app("zoom") == "browser"
    assert _classify_app("iperf3") == "shell"
    assert _classify_app("wget") == "shell"
    assert _classify_app("ndt") == "shell"
    assert _classify_app("ping") == "shell"
    assert _classify_app("unknown_app") == "shell"
