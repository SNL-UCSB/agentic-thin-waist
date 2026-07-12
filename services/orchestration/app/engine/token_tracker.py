"""Per-intent Anthropic (orchestrator LLM) token accounting.

Every intent submitted to ``POST /intent`` triggers one or more calls to the
orchestrator's own LLM (Anthropic Claude, via ``langchain_anthropic``) — intent
parsing plus, where applicable, the shell/browser workflow sub-agents.  This
module aggregates the token usage of **those** calls (not the Claude Code CLI or
anything else) and appends a human-readable record to ``intent_tokens.md``.

The mechanism is a LangChain ``BaseCallbackHandler``: attach one instance to the
top-level ``graph.invoke(config={"callbacks": [cb]})`` call and LangChain
propagates it to every nested LLM invocation, so the counts cover the whole
orchestration run.  Token counts are read from each response's
``usage_metadata`` (populated by ``ChatAnthropic``).
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

# Serialize appends across concurrent background tasks in the same process.
_FILE_LOCK = threading.Lock()

# Default output path. ``/app`` is bind-mounted from ``services/orchestration``
# in docker-compose, so this file is visible on the host at
# ``services/orchestration/intent_tokens.md``.  Override with INTENT_TOKENS_FILE.
_DEFAULT_TOKENS_FILE = Path(__file__).resolve().parents[2] / "intent_tokens.md"


def _tokens_file() -> Path:
    override = os.environ.get("INTENT_TOKENS_FILE", "").strip()
    return Path(override) if override else _DEFAULT_TOKENS_FILE


class TokenUsageCallback(BaseCallbackHandler):
    """Accumulate LLM token usage across every model call in one intent run."""

    def __init__(self) -> None:
        super().__init__()
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.llm_calls = 0
        # Per-model breakdown: {model_name: {"input", "output", "total", "calls"}}
        self.by_model: dict[str, dict[str, int]] = {}
        # Per-call log, in completion order: [{label, model, input, output, total}]
        self.calls: list[dict[str, Any]] = []
        # run_id -> label captured at start, consumed at end.
        self._labels: dict[Any, str] = {}
        self._lock = threading.Lock()

    # -- label capture --------------------------------------------------
    @staticmethod
    def _label_from(metadata: Any, tags: Any, name: Any) -> str:
        meta = metadata or {}
        node = meta.get("langgraph_node") if isinstance(meta, dict) else None
        if node:
            return str(node)
        if name:
            return str(name)
        if tags:
            return str(tags[0]) if isinstance(tags, list) and tags else str(tags)
        return "llm"

    def on_chat_model_start(self, serialized, messages, **kwargs):  # noqa: D401
        run_id = kwargs.get("run_id")
        self._labels[run_id] = self._label_from(
            kwargs.get("metadata"), kwargs.get("tags"), kwargs.get("name")
        )

    def on_llm_start(self, serialized, prompts, **kwargs):  # noqa: D401
        run_id = kwargs.get("run_id")
        self._labels[run_id] = self._label_from(
            kwargs.get("metadata"), kwargs.get("tags"), kwargs.get("name")
        )

    def _add(
        self, model: str, inp: int, out: int, total: int, label: str = "llm"
    ) -> None:
        with self._lock:
            self.input_tokens += inp
            self.output_tokens += out
            self.total_tokens += total
            self.llm_calls += 1
            bucket = self.by_model.setdefault(
                model, {"input": 0, "output": 0, "total": 0, "calls": 0}
            )
            bucket["input"] += inp
            bucket["output"] += out
            bucket["total"] += total
            bucket["calls"] += 1
            self.calls.append(
                {
                    "label": label,
                    "model": model,
                    "input": inp,
                    "output": out,
                    "total": total,
                }
            )

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:  # noqa: D401
        """Read usage from an ``LLMResult`` regardless of provider surface."""
        model = "unknown"
        inp = out = total = 0

        # Preferred source: usage_metadata on the generated AIMessage.
        try:
            for gen_list in getattr(response, "generations", []) or []:
                for gen in gen_list:
                    message = getattr(gen, "message", None)
                    usage = getattr(message, "usage_metadata", None) if message else None
                    if usage:
                        inp += int(usage.get("input_tokens", 0) or 0)
                        out += int(usage.get("output_tokens", 0) or 0)
                        total += int(usage.get("total_tokens", 0) or 0)
                    meta = getattr(message, "response_metadata", {}) or {}
                    model = meta.get("model_name") or meta.get("model") or model
        except Exception:  # pragma: no cover - defensive
            pass

        # Fallback: llm_output token block (older/plain integrations).
        if inp == 0 and out == 0 and total == 0:
            llm_output = getattr(response, "llm_output", None) or {}
            usage = llm_output.get("usage") or llm_output.get("token_usage") or {}
            inp = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
            out = int(
                usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
            )
            total = int(usage.get("total_tokens", 0) or 0)
            model = llm_output.get("model_name") or llm_output.get("model") or model

        if total == 0:
            total = inp + out

        label = self._labels.pop(kwargs.get("run_id"), "llm")
        # Record even zero-token calls so llm_calls reflects reality.
        self._add(model, inp, out, total, label=label)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens,
                "llm_calls": self.llm_calls,
                "by_model": {k: dict(v) for k, v in self.by_model.items()},
                "calls": [dict(c) for c in self.calls],
            }


def _fmt_params(parsed: dict[str, Any] | None) -> str:
    if not parsed:
        return "n/a"
    keys = [
        ("cc_algorithms", "cc"),
        ("capacities", "capacities_mbps"),
        ("latencies", "latencies_ms"),
        ("aqm_policy", "aqm"),
        ("buffer_packets", "buffer_packets"),
        ("qdisc_params", "qdisc_params"),
        ("num_trials", "num_trials"),
        ("duration_seconds", "duration_s"),
        ("applications", "applications"),
        ("application_type", "application_type"),
    ]
    parts = []
    for src, label in keys:
        if src in parsed and parsed[src] not in (None, [], {}):
            parts.append(f"{label}={parsed[src]}")
    return "  ".join(parts) if parts else "n/a"


def record_intent_tokens(
    *,
    orchestration_id: str,
    intent: str,
    provider: str,
    model: str,
    usage: dict[str, Any],
    status: str,
    parsed_intent: dict[str, Any] | None,
    experiments_count: int,
    error: str | None = None,
) -> Path:
    """Append one markdown record for this intent to ``intent_tokens.md``.

    Returns the path written to.  Never raises — token accounting must not break
    the orchestration pipeline.
    """
    path = _tokens_file()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    by_model = usage.get("by_model", {}) or {}
    model_lines = "; ".join(
        f"{name}: in={b['input']} out={b['output']} total={b['total']} calls={b['calls']}"
        for name, b in by_model.items()
    ) or "n/a"

    calls = usage.get("calls", []) or []
    call_lines = [
        f"  {i + 1}. `{c['label']}` ({c['model']}): "
        f"in={c['input']} out={c['output']} total={c['total']}"
        for i, c in enumerate(calls)
    ]

    record = {
        "orchestration_id": orchestration_id,
        "timestamp": ts,
        "provider": provider,
        "model": model,
        "status": status,
        "llm_calls": usage.get("llm_calls", 0),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "experiments_generated": experiments_count,
        "by_model": by_model,
        "calls": calls,
    }

    section = [
        f"## {orchestration_id} — {ts}",
        "",
        f"- **Intent:** {intent}",
        f"- **Provider / Model:** {provider} / {model}",
        f"- **Status:** {status}",
        f"- **Orchestrator LLM calls:** {usage.get('llm_calls', 0)}",
        f"- **Input tokens:** {usage.get('input_tokens', 0)}",
        f"- **Output tokens:** {usage.get('output_tokens', 0)}",
        f"- **Total tokens:** {usage.get('total_tokens', 0)}",
        f"- **Experiments generated:** {experiments_count}",
        f"- **Parsed params:** {_fmt_params(parsed_intent)}",
        f"- **Per-model breakdown:** {model_lines}",
        "- **Per-call breakdown:**",
        *(call_lines or ["  (none)"]),
    ]
    if error:
        section.append(f"- **Error:** {error}")
    section.append("")
    section.append("```json")
    section.append(json.dumps(record, indent=2))
    section.append("```")
    section.append("")

    try:
        with _FILE_LOCK:
            new_file = not path.exists()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                if new_file:
                    fh.write(
                        "# Intent Token Usage\n\n"
                        "Per-intent Anthropic (orchestrator LLM) token accounting. "
                        "One section per submitted intent.\n"
                    )
                fh.write("\n" + "\n".join(section))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[TOKENS {orchestration_id}] WARNING: failed to write {path}: {exc}")

    return path
