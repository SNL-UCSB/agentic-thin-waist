from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_WORKFLOW_SCHEMAS_PATH = (
    Path(__file__).parent.parent / "config" / "workflow_schemas.json"
)
_WORKFLOW_SCHEMAS: dict[str, dict[str, dict[str, Any]]] = (
    json.loads(_WORKFLOW_SCHEMAS_PATH.read_text())
    if _WORKFLOW_SCHEMAS_PATH.exists()
    else {}
)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def build_workflow_parameters(
    context: dict[str, Any] | None, workflow_id: str | None = None
) -> dict[str, Any] | None:
    ctx = context or {}
    explicit = ctx.get("workflow_parameters")
    params: dict[str, Any] = dict(explicit) if isinstance(explicit, dict) else {}

    if not workflow_id:
        return params or None

    schema = _WORKFLOW_SCHEMAS.get(workflow_id) or {}
    if schema:
        for key in schema.keys():
            if key in ctx and ctx[key] is not None and key not in params:
                params[key] = ctx[key]
        params = {k: v for k, v in params.items() if k in schema}

    return params or None


def build_parsed_intent(
    context: dict[str, Any] | None,
    intent: str | None = None,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    ctx = context or {}
    applications = _as_list(ctx.get("applications"))
    if not applications:
        app = ctx.get("application")
        applications = [app] if app else ["app"]
    app_lc = {str(a).strip().lower() for a in applications if a is not None}
    inferred_app_type = "browser" if "zoom" in app_lc else "shell"

    capacities = _as_list(ctx.get("capacities")) or [25]
    latencies = _as_list(ctx.get("latencies")) or [50]
    cc_algorithms = _as_list(ctx.get("cc_algorithms")) or ["cubic"]

    return {
        "applications": applications,
        "application_type": ctx.get("application_type") or inferred_app_type,
        "capacities": capacities,
        "latencies": latencies,
        "cc_algorithms": cc_algorithms,
        "aqm_policy": ctx.get("aqm_policy") or "pfifo",
        "buffer_packets": ctx.get("buffer_packets"),
        "qdisc_params": ctx.get("qdisc_params"),
        "ctp_cluster": ctx.get("ctp_cluster"),
        "ctp_capacity_range": ctx.get("ctp_capacity_range"),
        "ctp_name": ctx.get("ctp_name"),
        "ctp_list": ctx.get("ctp_list"),
        "duration_seconds": int(ctx.get("duration_seconds") or 60),
        "num_trials": int(ctx.get("num_trials") or 1),
        "workflow_parameters": build_workflow_parameters(ctx, workflow_id),
        "upload_mbps": (
            float(ctx["upload_mbps"])
            if ctx.get("upload_mbps") is not None
            else (
                float(capacities[0])
                if capacities and capacities[0] is not None
                else None
            )
        ),
        "fake_media": True if ctx.get("fake_media") is None else bool(ctx["fake_media"]),
        "clarification_needed": [],
        "design_type": [],
        "reasoning": "deterministic bypass - LLM skipped",
        "intent": intent or "",
    }
