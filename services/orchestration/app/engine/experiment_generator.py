"""Structured intent → list of GeneratedExperiment (Step 7).

Pure logic: Cartesian product over capacities, latencies,
and CC algorithms; no API calls or side effects.
"""

from itertools import product
from typing import Any, Dict, List

from app.models.schemas import GeneratedExperiment

_DEFAULT_DURATION_SECONDS = 60


class ExperimentGenerator:
    def generate(
        self,
        parsed_intent: dict,
    ) -> List[GeneratedExperiment]:
        """Generate experiment specs from parsed intent parameters.

        Args:
            parsed_intent: Structured output from the intent parser.
        """
        capacities = parsed_intent.get("capacities") or [25]
        latencies = parsed_intent.get("latencies") or [50]
        cc_algorithms = parsed_intent.get("cc_algorithms") or ["cubic"]
        aqm_policy = parsed_intent.get("aqm_policy") or "pfifo"
        application_type = parsed_intent.get("application_type") or "shell"
        duration = parsed_intent.get("duration_seconds") or _DEFAULT_DURATION_SECONDS
        num_trials = parsed_intent.get("num_trials", 1) or 1
        reasoning = parsed_intent.get("reasoning") or ""
        ctp_cluster = parsed_intent.get("ctp_cluster") or "cluster0"
        ctp_capacity_range = parsed_intent.get("ctp_capacity_range") or {
            "lower_value": 1,
            "higher_value": 10,
        }

        experiments: List[GeneratedExperiment] = []
        counter = 1
        for cap, lat, cc in product(capacities, latencies, cc_algorithms):
            exp = GeneratedExperiment(
                experiment_id=f"{application_type}-{cap}mbps-{lat}ms-{cc}-{counter:03d}",
                application_type=application_type,
                capacity_mbps=float(cap),
                latency_ms=float(lat),
                cc_algorithm=cc,
                aqm_policy=aqm_policy,
                duration_seconds=int(duration),
                num_trials=int(num_trials),
                reasoning=reasoning,
                ctp_cluster=ctp_cluster,
                ctp_capacity_range=ctp_capacity_range,
            )
            experiments.append(exp)
            counter += 1
        return experiments
