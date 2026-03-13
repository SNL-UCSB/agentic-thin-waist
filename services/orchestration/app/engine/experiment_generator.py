"""Structured intent → list of GeneratedExperiment (Step 7).

Pure logic: Cartesian product over applications, capacities, latencies,
and CC algorithms; no API calls or side effects.
"""

from itertools import product
from typing import List

from app.models.schemas import GeneratedExperiment

# Per-application default durations (from app/knowledge/application_defaults.md)
APP_DEFAULT_DURATIONS = {
    "youtube": 60,
    "netflix": 60,
    "zoom": 120,
    "twitch": 60,
    "discord": 120,
    "google-meet": 120,
    "ndt": 30,
    "ping": 30,
    "iperf3": 30,
}


class ExperimentGenerator:
    def generate(self, parsed_intent: dict) -> List[GeneratedExperiment]:
        """Generate experiment specs from parsed intent parameters."""
        apps = parsed_intent.get("applications") or []
        capacities = parsed_intent.get("capacities") or [25]
        latencies = parsed_intent.get("latencies") or [50]
        cc_algorithms = parsed_intent.get("cc_algorithms") or ["cubic"]
        aqm_policy = parsed_intent.get("aqm_policy") or "fq_codel"
        explicit_duration = parsed_intent.get("duration_seconds")
        num_trials = parsed_intent.get("num_trials", 1) or 1
        reasoning = parsed_intent.get("reasoning") or ""
        ctp_cluster = parsed_intent.get("ctp_cluster") or "ctp_low_background"

        experiments: List[GeneratedExperiment] = []
        counter = 1
        for app, cap, lat, cc in product(apps, capacities, latencies, cc_algorithms):
            duration = (
                int(explicit_duration)
                if explicit_duration is not None
                else APP_DEFAULT_DURATIONS.get(app, 60)
            )
            exp = GeneratedExperiment(
                experiment_id=f"{app}-{cap}mbps-{lat}ms-{cc}-{counter:03d}",
                capacity_mbps=float(cap),
                latency_ms=float(lat),
                application=app,
                cc_algorithm=cc,
                aqm_policy=aqm_policy,
                duration_seconds=duration,
                num_trials=int(num_trials),
                reasoning=reasoning,
                ctp_cluster=ctp_cluster,
            )
            experiments.append(exp)
            counter += 1
        return experiments
