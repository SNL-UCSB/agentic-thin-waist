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


def test_generator_defaults_ctp_capacity_range_when_missing():
    parsed = {
        "application_type": "shell",
        "capacities": [10],
        "latencies": [50],
        "cc_algorithms": ["cubic"],
    }
    out = ExperimentGenerator().generate(parsed)
    assert len(out) == 1
    assert out[0].ctp_capacity_range == {"lower_value": 1, "higher_value": 10}
