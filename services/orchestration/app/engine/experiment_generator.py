"""Structured intent → list of GeneratedExperiment (Step 7).

Pure logic: Cartesian product over capacities, latencies,
and CC algorithms; no API calls or side effects.
"""

import re
import uuid
from itertools import product
from typing import Callable, List, Optional

from app.models.schemas import GeneratedExperiment

_DEFAULT_DURATION_SECONDS = 60
_UUID_LEN = 8
_MAX_UNIQUENESS_ATTEMPTS = 8


def _slugify_app(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "", (name or "").lower())
    return s or "app"


def _fmt_num(x: float) -> str:
    f = float(x)
    return str(int(f)) if f.is_integer() else str(f)


class ExperimentGenerator:
    def generate(
        self,
        parsed_intent: dict,
        id_taken: Optional[Callable[[str], bool]] = None,
    ) -> List[GeneratedExperiment]:
        """Generate experiment specs from parsed intent parameters.

        Args:
            parsed_intent: Structured output from the intent parser.
            id_taken: Optional callable that returns True if an experiment_id
                already exists (e.g. in the telemetry service). Used to ensure
                global uniqueness; if None, only intra-batch uniqueness is
                guaranteed via the random UUID suffix.
        """
        capacities = parsed_intent.get("capacities") or [25]
        latencies = parsed_intent.get("latencies") or [50]
        cc_algorithms = parsed_intent.get("cc_algorithms") or ["cubic"]
        aqm_policy = parsed_intent.get("aqm_policy") or "pfifo"
        application_type = parsed_intent.get("application_type") or "shell"
        duration = parsed_intent.get("duration_seconds") or _DEFAULT_DURATION_SECONDS
        num_trials = parsed_intent.get("num_trials", 1) or 1
        reasoning = parsed_intent.get("reasoning") or ""
        # When the intent does not mention CTP, leave both fields as None so
        # the orchestrator skips CTP selection + replay entirely (no
        # background cross-traffic, no 172.16.1.20 packets in the pcap).
        ctp_cluster = parsed_intent.get("ctp_cluster")
        ctp_capacity_range = parsed_intent.get("ctp_capacity_range")
        ctp_name = parsed_intent.get("ctp_name")
        # CTP fan-out: when a caller supplies an explicit list of CTP names, the
        # cap x lat x cc product is multiplied by the CTP list so a single intent
        # expands into one experiment per CTP (each pinned to a distinct profile
        # via ``ctp_name``). This is how the receiver rooms sweep N CTPs in
        # parallel from one /intent submission without per-CTP list files.
        ctp_list = parsed_intent.get("ctp_list")
        if isinstance(ctp_list, list):
            ctp_values: list = [c for c in ctp_list if c] or [ctp_name]
        else:
            ctp_values = [ctp_name]

        buffer_packets = parsed_intent.get("buffer_packets")
        qdisc_params = parsed_intent.get("qdisc_params")
        # Receive-only experiments set fake_media=False so their worker browser
        # has no camera/mic device and cannot broadcast. Defaults to True.
        fake_media = parsed_intent.get("fake_media")
        fake_media = True if fake_media is None else bool(fake_media)

        applications = parsed_intent.get("applications") or []
        app_slug = _slugify_app(applications[0]) if applications else application_type

        used: set[str] = set()
        experiments: List[GeneratedExperiment] = []
        for cap, lat, cc in product(capacities, latencies, cc_algorithms):
            download = _fmt_num(cap)
            upload = _fmt_num(parsed_intent.get("upload_mbps") or cap)
            base_lat = _fmt_num(lat)
            for ctp_choice in ctp_values:
                ctp_slug = _slugify_app(str(ctp_choice)) if ctp_choice else ""
                prefix = f"{app_slug}_{download}_{upload}_{base_lat}_{aqm_policy}_{cc}"
                if ctp_slug:
                    prefix = f"{prefix}_{ctp_slug}"
                exp_id = self._mint_unique_id(prefix, used, id_taken)
                used.add(exp_id)

                exp = GeneratedExperiment(
                    experiment_id=exp_id,
                    application_type=application_type,
                    capacity_mbps=float(cap),
                    latency_ms=float(lat),
                    cc_algorithm=cc,
                    aqm_policy=aqm_policy,
                    buffer_packets=(
                        int(buffer_packets) if buffer_packets is not None else None
                    ),
                    qdisc_params=qdisc_params if qdisc_params else None,
                    duration_seconds=int(duration),
                    num_trials=int(num_trials),
                    reasoning=reasoning,
                    ctp_cluster=ctp_cluster,
                    ctp_capacity_range=ctp_capacity_range,
                    ctp_name=ctp_choice,
                    fake_media=fake_media,
                )
                experiments.append(exp)
        return experiments

    @staticmethod
    def _mint_unique_id(
        prefix: str,
        used: set[str],
        id_taken: Optional[Callable[[str], bool]],
    ) -> str:
        for _ in range(_MAX_UNIQUENESS_ATTEMPTS):
            candidate = f"{prefix}_{uuid.uuid4().hex[:_UUID_LEN]}"
            if candidate in used:
                continue
            if id_taken is not None:
                try:
                    if id_taken(candidate):
                        continue
                except Exception:
                    # Telemetry unreachable: trust the random suffix.
                    return candidate
            return candidate
        # Extremely unlikely — fall back to a longer suffix.
        return f"{prefix}_{uuid.uuid4().hex}"
