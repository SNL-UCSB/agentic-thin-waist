"""Structured intent → list of GeneratedExperiment (Step 7).

Pure logic: Cartesian product over applications, capacities, latencies,
and CC algorithms; no API calls or side effects.
"""

from itertools import product
from typing import List

from app.models.schemas import GeneratedExperiment

# Per-application default durations (s); see app/knowledge/application_defaults.md
_APP_DEFAULT_DURATION_SECONDS = {
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
_DEFAULT_DURATION_FALLBACK = 60


def _default_duration_for_apps(apps: List[str]) -> int:
    """Default duration when unspecified: max of per-application defaults, or fallback."""
    if not apps:
        return _DEFAULT_DURATION_FALLBACK
    return max(
        _APP_DEFAULT_DURATION_SECONDS.get(a, _DEFAULT_DURATION_FALLBACK) for a in apps
    )


class ExperimentGenerator:
    def generate(self, parsed_intent: dict) -> List[GeneratedExperiment]:
        """Generate experiment specs from parsed intent parameters."""
        apps = parsed_intent.get("applications") or []
        capacities = parsed_intent.get("capacities") or [25]
        latencies = parsed_intent.get("latencies") or [50]
        cc_algorithms = parsed_intent.get("cc_algorithms") or ["cubic"]
        aqm_policy = parsed_intent.get("aqm_policy") or "fq_codel"
        duration = parsed_intent.get("duration_seconds") or _default_duration_for_apps(
            apps
        )
        num_trials = parsed_intent.get("num_trials", 1) or 1
        reasoning = parsed_intent.get("reasoning") or ""
        ctp_cluster = parsed_intent.get("ctp_cluster") or "cluster0"

        experiments: List[GeneratedExperiment] = []
        counter = 1
        for app, cap, lat, cc in product(apps, capacities, latencies, cc_algorithms):
            exp = GeneratedExperiment(
                experiment_id=f"{app}-{cap}mbps-{lat}ms-{cc}-{counter:03d}",
                capacity_mbps=float(cap),
                latency_ms=float(lat),
                application=app,
                cc_algorithm=cc,
                aqm_policy=aqm_policy,
                duration_seconds=int(duration),
                num_trials=int(num_trials),
                reasoning=reasoning,
                ctp_cluster=ctp_cluster,
            )
            experiments.append(exp)
            counter += 1
        return experiments
