from __future__ import annotations

import os
from typing import Any, Literal

from langchain_anthropic import ChatAnthropic as LangChainChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

LLMProvider = Literal["anthropic", "gemini"]

_DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
_DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite-preview"


def _canonicalize_provider(raw_provider: str) -> LLMProvider:
    provider = raw_provider.strip().lower()
    if provider in {"anthropic", "claude"}:
        return "anthropic"
    if provider in {"gemini", "google"}:
        return "gemini"
    raise ValueError(
        "NETGENT_LLM_PROVIDER must be one of: anthropic, claude, gemini, google"
    )


def get_llm_provider() -> LLMProvider:
    raw_provider = (
        os.getenv("NETGENT_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "gemini"
    )
    return _canonicalize_provider(raw_provider)


def _get_anthropic_api_key() -> str | None:
    return os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")


def _get_gemini_api_key() -> str | None:
    return os.getenv("GOOGLE_API_KEY")


def has_llm_credentials(provider: str | None = None) -> bool:
    selected_provider = (
        _canonicalize_provider(provider) if provider is not None else get_llm_provider()
    )
    if selected_provider == "anthropic":
        return bool(_get_anthropic_api_key())
    return bool(_get_gemini_api_key())


def _get_anthropic_model_name() -> str:
    return (
        os.getenv("NETGENT_ANTHROPIC_MODEL")
        or os.getenv("CLAUDE_MODEL")
        or _DEFAULT_ANTHROPIC_MODEL
    )


def _get_gemini_model_name() -> str:
    return (
        os.getenv("NETGENT_GOOGLE_MODEL")
        or os.getenv("GOOGLE_MODEL")
        or _DEFAULT_GEMINI_MODEL
    )


def get_langchain_model() -> BaseChatModel:
    provider = get_llm_provider()
    if provider == "anthropic":
        api_key = _get_anthropic_api_key()
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY or CLAUDE_API_KEY must be set when "
                "NETGENT_LLM_PROVIDER=anthropic"
            )
        return LangChainChatAnthropic(
            model_name=_get_anthropic_model_name(),
            api_key=SecretStr(api_key),
            timeout=60.0,
            stop=None,
        )

    api_key = _get_gemini_api_key()
    if not api_key:
        raise ValueError("GOOGLE_API_KEY must be set when NETGENT_LLM_PROVIDER=gemini")
    return ChatGoogleGenerativeAI(
        model=_get_gemini_model_name(),
        google_api_key=SecretStr(api_key),
    )


def get_browser_use_model() -> Any:
    from browser_use import ChatAnthropic, ChatGoogle

    provider = get_llm_provider()
    if provider == "anthropic":
        if not _get_anthropic_api_key():
            raise ValueError(
                "ANTHROPIC_API_KEY or CLAUDE_API_KEY must be set when "
                "NETGENT_LLM_PROVIDER=anthropic"
            )
        return ChatAnthropic(model=_get_anthropic_model_name())

    if not _get_gemini_api_key():
        raise ValueError("GOOGLE_API_KEY must be set when NETGENT_LLM_PROVIDER=gemini")
    return ChatGoogle(model=_get_gemini_model_name())
