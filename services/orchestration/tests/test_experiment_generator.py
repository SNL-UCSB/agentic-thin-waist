"""Tests for ExperimentGenerator (Step 7): parsed intent → GeneratedExperiment list."""

import pytest

from app.engine.experiment_generator import ExperimentGenerator
from app.models.schemas import GeneratedExperiment


def test_youtube_at_three_capacities_returns_three_experiments():
    """YouTube at 10, 25, 50 Mbps → 3 experiments."""
    generator = ExperimentGenerator()
    # parsed = {
    #     "applications": ["youtube"],
    #     "capacities": [10, 25, 50],
    #     "latencies": None,
    #     "cc_algorithms": None,
    #     "reasoning": "",
    # }

    parsed ={
   
  "applications": [
    "youtube"
  ],
  "capacities": [
    10,
    25,
    50
  ],
  "latencies": None,
  "cc_algorithms": None,
  "aqm_policy": None,
  "ctp_cluster": None,
  "duration_seconds": None,
  "num_trials": 1,
  "clarification_needed": [],
  "design_type": [
    "isolated",
    "isolated",
    "isolated"
  ],
  "reasoning": "The intent clearly specifies a capacity sweep for YouTube at three distinct capacity values: 10, 25, and 50 Mbps. All three are within the valid range [0.1, 10000] Mbps and comfortably above the 3 Mbps minimum recommended for YouTube, so no constraint warnings apply. No latency, CC algorithm, AQM policy, cross-traffic, or duration were specified, so defaults will be applied: latency_ms=50, cc_algorithm=cubic, aqm_policy=fq_codel, duration_seconds=60 (YouTube default). Each capacity value results in one isolated experiment (single application, no concurrent traffic). num_trials defaults to 1. No clarification is needed as the intent is unambiguous."

    }
    experiments = generator.generate(parsed)
    assert len(experiments) == 3
    caps = [e.capacity_mbps for e in experiments]
    assert caps == [10, 25, 50]
    assert all(e.application == "youtube" for e in experiments)


# def test_youtube_zoom_two_capacities_returns_four_experiments():
#     """YouTube + Zoom at 10, 25 Mbps → 4 experiments (Cartesian)."""
#     generator = ExperimentGenerator()
#     parsed = {
#         "applications": ["youtube", "zoom"],
#         "capacities": [10, 25],
#         "latencies": None,
#         "cc_algorithms": None,
#         "reasoning": "",
#     }
#     experiments = generator.generate(parsed)
#     assert len(experiments) == 4
#     # Cartesian: (youtube,10), (youtube,25), (zoom,10), (zoom,25)
#     app_cap = [(e.application, e.capacity_mbps) for e in experiments]
#     assert set(app_cap) == {
#         ("youtube", 10),
#         ("youtube", 25),
#         ("zoom", 10),
#         ("zoom", 25),
#     }


def test_youtube_zoom_at_10_25_50_mbps_from_examples():
    """Example from examples.md (131-170): YouTube and Zoom at 10, 25, 50 Mbps.

    Generator produces Cartesian product: 2 apps × 3 capacities = 6 experiments
    (isolated per-app runs). Defaults apply for latency (50 ms), cc (cubic), aqm (fq_codel).
    """
    generator = ExperimentGenerator()
    parsed = {
        "applications": ["youtube", "zoom"],
        "capacities": [10, 25, 50],
        "latencies": None,
        "cc_algorithms": None,
        "aqm_policy": None,
        "ctp_cluster": None,
        "duration_seconds": None,
        "num_trials": 1,
        "clarification_needed": [
            "Latency is not specified — will default to 50 ms.",
            "It is ambiguous whether YouTube and Zoom should run in isolation or concurrently.",
        ],
        "design_type": [
            "isolated", "isolated", "isolated",
            "isolated", "isolated", "isolated",
            "concurrent", "concurrent", "concurrent",
        ],
        "reasoning": "Two applications, three capacity values; Cartesian comparison.",
    }
    experiments = generator.generate(parsed)
    for i, e in enumerate(experiments, 1):
        print(
            f"  {i}. {e.experiment_id}"
            f"  app={e.application}  cap={e.capacity_mbps} Mbps  lat={e.latency_ms} ms  loss={e.loss_rate}%"
            f"  cc={e.cc_algorithm}  aqm={e.aqm_policy}"
            f"  duration={e.duration_seconds}s  num_trials={e.num_trials}  ctp={e.ctp_cluster!r}"
        )
    assert len(experiments) == 6
    app_cap = [(e.application, e.capacity_mbps) for e in experiments]
    assert set(app_cap) == {
        ("youtube", 10), ("youtube", 25), ("youtube", 50),
        ("zoom", 10), ("zoom", 25), ("zoom", 50),
    }
    for e in experiments:
        assert e.latency_ms == 50
        assert e.cc_algorithm == "cubic"
        assert e.aqm_policy == "fq_codel"
        assert e.ctp_cluster is None
    ids = [e.experiment_id for e in experiments]
    assert ids[0].endswith("-001")
    assert ids[-1].endswith("-006")


def test_youtube_cubic_bbr_one_capacity_returns_two_experiments():
    """YouTube, CUBIC + BBR, 10 Mbps → 2 experiments."""
    generator = ExperimentGenerator()
    # parsed = {
    #     "applications": ["youtube"],
    #     "capacities": [10],
    #     "latencies": None,
    #     "cc_algorithms": ["cubic", "bbr"],
    #     "reasoning": "",
    # }


    parsed={
  "applications": [
    "youtube"
  ],
  "capacities": [
    10
  ],
  "latencies": None,
  "cc_algorithms": [
    "cubic",
    "bbr"
  ],
  "aqm_policy": None,
  "ctp_cluster": None,
  "duration_seconds": None,
  "num_trials": 1,
  "clarification_needed": [],
  "design_type": [
    "isolated",
    "isolated"
  ],
  "reasoning": "The intent is a classic CC algorithm comparison: CUBIC vs BBR for YouTube at a fixed 10 Mbps capacity. This maps directly to the 'CC Algorithm Comparisons' design pattern in the knowledge files. Applications: [youtube] (explicitly stated). Capacities: [10] Mbps (explicitly stated). CC algorithms: [cubic, bbr] (explicitly stated). Latency is not specified, so the default of 50 ms will be used at experiment generation time. AQM policy is not specified, so the default fq_codel will be applied. No cross-traffic is mentioned, so ctp_cluster is null. Duration is not specified, so the YouTube application default of 60s will be used. num_trials defaults to 1 since not specified. The two experiments are 'isolated' because each CC algorithm run is a separate, independent configuration (not concurrent). No clarification is needed \u2014 the intent is unambiguous and well-constrained."
    }
    experiments = generator.generate(parsed)
    assert len(experiments) == 2
    algs = [e.cc_algorithm for e in experiments]
    assert set(algs) == {"cubic", "bbr"}
    assert all(e.application == "youtube" and e.capacity_mbps == 10 for e in experiments)


def test_experiment_id_naming_convention():
    """Verify experiment_id format: {app}-{cap}mbps-{lat}ms-{cc}-{counter:03d}."""
    generator = ExperimentGenerator()
    parsed = {
        "applications": ["netflix"],
        "capacities": [25],
        "latencies": [50],
        "cc_algorithms": ["cubic"],
        "reasoning": "",
    }
    experiments = generator.generate(parsed)
    assert len(experiments) == 1
    e = experiments[0]
    assert e.experiment_id == "netflix-25mbps-50ms-cubic-001"

    # Two experiments to check counter
    parsed["cc_algorithms"] = ["cubic", "bbr"]
    experiments = generator.generate(parsed)
    ids = [e.experiment_id for e in experiments]
    assert ids == ["netflix-25mbps-50ms-cubic-001", "netflix-25mbps-50ms-bbr-002"]


def test_defaults_applied_for_unspecified_parameters():
    """Verify defaults: capacities=[25], latencies=[50], cc=cubic, aqm=fq_codel, duration=60, num_trials=1."""
    generator = ExperimentGenerator()
    parsed = {
        "applications": ["youtube"],
        # omit capacities, latencies, cc_algorithms, aqm_policy, duration_seconds, num_trials
        "reasoning": "",
    }
    experiments = generator.generate(parsed)
    assert len(experiments) == 1
    e = experiments[0]
    assert e.capacity_mbps == 25
    assert e.latency_ms == 50
    assert e.cc_algorithm == "cubic"
    assert e.aqm_policy == "fq_codel"
    assert e.duration_seconds == 60
    assert e.num_trials == 1
    assert e.loss_rate == 0.0
