"""Utility helpers for the Orchestrator Agent."""

from __future__ import annotations

import os
from typing import Any

from langchain_anthropic import ChatAnthropic
from pydantic import SecretStr

from app.engine.orchestration_store import save_orchestration
from app.models.schemas import OrchestrationStatus


def get_model() -> ChatAnthropic:
    """Build a ChatAnthropic instance from environment variables."""
    api_key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("CLAUDE_API_KEY or ANTHROPIC_API_KEY must be set")
    model_name = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
    return ChatAnthropic(
        model_name=model_name,
        api_key=SecretStr(api_key),
        timeout=60.0,
        stop=None,
    )


def save_state(state: dict[str, Any], **overrides: Any) -> None:
    """Persist orchestration state to the Telemetry Service."""
    record: dict[str, Any] = {
        "orchestration_id": state["orchestration_id"],
        "intent": state["intent"],
        "status": overrides.get("status", OrchestrationStatus.pending),
        "experiments": state.get("experiments") or [],
        "reasoning_steps": state.get("reasoning_steps") or [],
        "results": [],
    }
    record.update(overrides)
    try:
        save_orchestration(record)
    except Exception as exc:
        print(
            f"[AGENT {state['orchestration_id']}] WARNING: save_orchestration failed: {exc}"
        )
