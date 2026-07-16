from app.engine.experiment_generator import ExperimentGenerator


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


def test_generator_retains_per_application_latency_without_creating_a_sweep():
    parsed = {
        "applications": ["youtube", "twitch", "tubi"],
        "application_type": "browser",
        "capacities": [6],
        "latencies": [50, 100],
        "application_configs": [
            {"application": "youtube", "latency_ms": 50},
            {"application": "twitch", "latency_ms": 100},
            {"application": "tubi", "latency_ms": 0},
        ],
        "cc_algorithms": ["cubic"],
        "aqm_policy": "pfifo",
        "duration_seconds": 60,
    }

    out = ExperimentGenerator().generate(parsed)

    assert len(out) == 1
    assert out[0].capacity_mbps == 6
    assert out[0].latency_ms == 0
    assert [config.model_dump() for config in out[0].application_configs] == [
        {"application": "youtube", "latency_ms": 50.0},
        {"application": "twitch", "latency_ms": 100.0},
        {"application": "tubi", "latency_ms": 0.0},
    ]
