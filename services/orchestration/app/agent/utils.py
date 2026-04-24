"""Utility helpers for the Orchestrator Agent."""

from __future__ import annotations

import os
from typing import Any, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel
from pydantic import SecretStr

from app.engine.orchestration_store import save_orchestration
from app.models.schemas import OrchestrationStatus


def _truncate_for_log(value: Any, limit: int = 1500) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def log_claude_step(
    step: str,
    *,
    orchestration_id: str | None = None,
    prompt: Any | None = None,
    reasoning: Any | None = None,
    output: Any | None = None,
) -> None:
    """Print structured logs for a Claude interaction step."""
    prefix = f"[CLAUDE {orchestration_id}]" if orchestration_id else "[CLAUDE]"
    print(f"{prefix} --- {step} ---")
    if prompt is not None:
        print(f"{prefix} prompt/input:\n{_truncate_for_log(prompt)}")
    if reasoning is not None:
        print(f"{prefix} reasoning:\n{_truncate_for_log(reasoning)}")
    if output is not None:
        print(f"{prefix} output:\n{_truncate_for_log(output)}")
    print(f"{prefix} --- end {step} ---")


LLMProvider = Literal["anthropic", "gemini"]


def _canonicalize_provider(raw_provider: str) -> LLMProvider:
    provider = raw_provider.strip().lower()
    if provider in {"anthropic", "claude"}:
        return "anthropic"
    if provider in {"gemini", "google"}:
        return "gemini"
    raise ValueError(
        "ORCHESTRATOR_LLM_PROVIDER must be one of: anthropic, claude, gemini, google"
    )


def get_model_provider() -> LLMProvider:
    raw_provider = (
        os.environ.get("ORCHESTRATOR_LLM_PROVIDER")
        or os.environ.get("ORCHESTRATION_LLM_PROVIDER")
        or os.environ.get("LLM_PROVIDER")
        or "anthropic"
    )
    return _canonicalize_provider(raw_provider)


def get_model() -> BaseChatModel:
    """Build an LLM instance for the configured orchestration provider."""
    provider = get_model_provider()
    if provider == "anthropic":
        api_key = os.environ.get("CLAUDE_API_KEY") or os.environ.get(
            "ANTHROPIC_API_KEY"
        )
        if not api_key:
            raise ValueError("CLAUDE_API_KEY or ANTHROPIC_API_KEY must be set")
        model_name = (
            os.environ.get("ORCHESTRATOR_ANTHROPIC_MODEL")
            or os.environ.get("CLAUDE_MODEL")
            or "claude-sonnet-4-6"
        )
        return ChatAnthropic(
            model_name=model_name,
            api_key=SecretStr(api_key),
            timeout=60.0,
            stop=None,
        )

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "GOOGLE_API_KEY must be set when ORCHESTRATOR_LLM_PROVIDER=gemini"
        )
    model_name = (
        os.environ.get("ORCHESTRATOR_GOOGLE_MODEL")
        or os.environ.get("GOOGLE_MODEL")
        or "gemini-3.1-flash-lite-preview"
    )
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=SecretStr(api_key),
    )


def with_structured_output(
    model: BaseChatModel,
    schema: type[BaseModel],
    *,
    include_raw: bool = False,
) -> Any:
    """Wrap provider-specific structured output settings."""
    kwargs: dict[str, Any] = {"include_raw": include_raw}
    if get_model_provider() == "gemini":
        kwargs["method"] = "json_mode"
    return model.with_structured_output(schema, **kwargs)


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
