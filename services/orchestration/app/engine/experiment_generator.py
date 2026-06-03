"""Structured intent → list of GeneratedExperiment (Step 7).

Pure logic: Cartesian product over capacities, latencies,
and CC algorithms; no API calls or side effects.

When the parsed intent contains multiple applications and the LLM sets
``design_type`` accordingly, the generator produces:

- ``"isolated"`` experiments: one per (app × capacity × latency × cc)
- ``"concurrent"`` experiments: one per (capacity × latency × cc) with all
  applications bundled together for simultaneous execution on one worker
- ``"full"``: both isolated AND concurrent experiments
"""

import re
import uuid
from itertools import product
from typing import Callable, List, Optional

from app.models.schemas import GeneratedExperiment

_DEFAULT_DURATION_SECONDS = 60
_UUID_LEN = 8
_MAX_UNIQUENESS_ATTEMPTS = 8

_SHELL_APPS = {"ping", "iperf", "iperf3", "ndt", "ndt7", "wget", "speedtest", "curl"}
_BROWSER_APPS = {"youtube", "zoom", "teams", "netflix", "browsing", "twitch", "web"}


def _slugify_app(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "", (name or "").lower())
    return s or "app"


def _classify_app(name: str) -> str:
    """Return 'shell' or 'browser' for a given application name."""
    slug = _slugify_app(name)
    if slug in _BROWSER_APPS:
        return "browser"
    return "shell"


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
        ctp_cluster = parsed_intent.get("ctp_cluster")
        ctp_capacity_range = parsed_intent.get("ctp_capacity_range")

        buffer_packets = parsed_intent.get("buffer_packets")
        qdisc_params = parsed_intent.get("qdisc_params")

        applications = parsed_intent.get("applications") or []
        design_types = parsed_intent.get("design_type") or []

        # Single-app or no apps: preserve original behavior exactly.
        if len(applications) <= 1:
            return self._generate_single_app(
                parsed_intent,
                capacities=capacities,
                latencies=latencies,
                cc_algorithms=cc_algorithms,
                aqm_policy=aqm_policy,
                application_type=application_type,
                duration=duration,
                num_trials=num_trials,
                reasoning=reasoning,
                ctp_cluster=ctp_cluster,
                ctp_capacity_range=ctp_capacity_range,
                buffer_packets=buffer_packets,
                qdisc_params=qdisc_params,
                applications=applications,
                id_taken=id_taken,
            )

        # Multi-app: use design_type to decide which experiments to generate.
        want_isolated = "isolated" in design_types or "full" in design_types
        want_concurrent = "concurrent" in design_types or "full" in design_types

        # If design_type is empty or unrecognized with multiple apps, let the
        # LLM's omission default to concurrent (the primary multi-app use case).
        if not want_isolated and not want_concurrent:
            want_concurrent = True

        used: set[str] = set()
        experiments: List[GeneratedExperiment] = []
        common = dict(
            aqm_policy=aqm_policy,
            duration=duration,
            num_trials=num_trials,
            reasoning=reasoning,
            ctp_cluster=ctp_cluster,
            ctp_capacity_range=ctp_capacity_range,
            buffer_packets=buffer_packets,
            qdisc_params=qdisc_params,
        )

        if want_isolated:
            experiments.extend(
                self._generate_isolated(
                    parsed_intent,
                    applications=applications,
                    capacities=capacities,
                    latencies=latencies,
                    cc_algorithms=cc_algorithms,
                    used=used,
                    id_taken=id_taken,
                    **common,
                )
            )

        if want_concurrent:
            experiments.extend(
                self._generate_concurrent(
                    parsed_intent,
                    applications=applications,
                    application_type=application_type,
                    capacities=capacities,
                    latencies=latencies,
                    cc_algorithms=cc_algorithms,
                    used=used,
                    id_taken=id_taken,
                    **common,
                )
            )

        return experiments

    # ------------------------------------------------------------------
    # Single-app generation (backward-compatible path)
    # ------------------------------------------------------------------

    def _generate_single_app(
        self,
        parsed_intent: dict,
        *,
        capacities: list,
        latencies: list,
        cc_algorithms: list,
        aqm_policy: str,
        application_type: str,
        duration: int,
        num_trials: int,
        reasoning: str,
        ctp_cluster,
        ctp_capacity_range,
        buffer_packets,
        qdisc_params,
        applications: list,
        id_taken,
    ) -> List[GeneratedExperiment]:
        app_slug = _slugify_app(applications[0]) if applications else application_type

        used: set[str] = set()
        experiments: List[GeneratedExperiment] = []
        for cap, lat, cc in product(capacities, latencies, cc_algorithms):
            download = _fmt_num(cap)
            upload = _fmt_num(parsed_intent.get("upload_mbps") or cap)
            base_lat = _fmt_num(lat)
            prefix = f"{app_slug}_{download}_{upload}_{base_lat}_{aqm_policy}_{cc}"
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
            )
            experiments.append(exp)
        return experiments

    # ------------------------------------------------------------------
    # Isolated: one experiment per (app × capacity × latency × cc)
    # ------------------------------------------------------------------

    def _generate_isolated(
        self,
        parsed_intent: dict,
        *,
        applications: list,
        capacities: list,
        latencies: list,
        cc_algorithms: list,
        aqm_policy: str,
        duration: int,
        num_trials: int,
        reasoning: str,
        ctp_cluster,
        ctp_capacity_range,
        buffer_packets,
        qdisc_params,
        used: set,
        id_taken,
    ) -> List[GeneratedExperiment]:
        experiments: List[GeneratedExperiment] = []
        for app in applications:
            app_slug = _slugify_app(app)
            app_type = _classify_app(app)
            for cap, lat, cc in product(capacities, latencies, cc_algorithms):
                download = _fmt_num(cap)
                upload = _fmt_num(parsed_intent.get("upload_mbps") or cap)
                base_lat = _fmt_num(lat)
                prefix = f"{app_slug}_{download}_{upload}_{base_lat}_{aqm_policy}_{cc}"
                exp_id = self._mint_unique_id(prefix, used, id_taken)
                used.add(exp_id)

                exp = GeneratedExperiment(
                    experiment_id=exp_id,
                    application_type=app_type,
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
                    applications=[app],
                    application_types=[app_type],
                    execution_mode="isolated",
                )
                experiments.append(exp)
        return experiments

    # ------------------------------------------------------------------
    # Concurrent: one experiment per (capacity × latency × cc) with
    # all applications bundled for simultaneous execution.
    # ------------------------------------------------------------------

    def _generate_concurrent(
        self,
        parsed_intent: dict,
        *,
        applications: list,
        application_type: str,
        capacities: list,
        latencies: list,
        cc_algorithms: list,
        aqm_policy: str,
        duration: int,
        num_trials: int,
        reasoning: str,
        ctp_cluster,
        ctp_capacity_range,
        buffer_packets,
        qdisc_params,
        used: set,
        id_taken,
    ) -> List[GeneratedExperiment]:
        composite_slug = "+".join(_slugify_app(a) for a in applications)
        app_types = [_classify_app(a) for a in applications]
        unique_types = set(app_types)
        if len(unique_types) == 1:
            resolved_type = unique_types.pop()
        else:
            resolved_type = "mixed"

        experiments: List[GeneratedExperiment] = []
        for cap, lat, cc in product(capacities, latencies, cc_algorithms):
            download = _fmt_num(cap)
            upload = _fmt_num(parsed_intent.get("upload_mbps") or cap)
            base_lat = _fmt_num(lat)
            prefix = (
                f"{composite_slug}_{download}_{upload}_{base_lat}_{aqm_policy}_{cc}"
            )
            exp_id = self._mint_unique_id(prefix, used, id_taken)
            used.add(exp_id)

            exp = GeneratedExperiment(
                experiment_id=exp_id,
                application_type=resolved_type,
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
                applications=list(applications),
                application_types=app_types,
                execution_mode="concurrent",
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
                    return candidate
            return candidate
        return f"{prefix}_{uuid.uuid4().hex}"
