from __future__ import annotations

import asyncio
import inspect
import logging
import time
import types
import typing
from collections.abc import Iterable, Mapping
from typing import Any


def _coerce_to_annotation(value: str, annotation: Any) -> Any:
    """Best-effort coercion of a resolved string to match a type annotation."""
    if annotation is inspect.Parameter.empty:
        return value

    # "none" / "null" → None for Optional fields
    if value.lower() in ("none", "null"):
        return None

    # Unwrap Union / Optional — coerce to the first non-None member
    origin = getattr(annotation, "__origin__", None)
    is_union = isinstance(annotation, types.UnionType) or origin is typing.Union
    if is_union:
        non_none = [a for a in annotation.__args__ if a is not type(None)]
        if non_none:
            return _coerce_to_annotation(value, non_none[0])
        return value

    if annotation is int:
        try:
            return int(value)
        except (ValueError, TypeError):
            return value

    if annotation is float:
        try:
            return float(value)
        except (ValueError, TypeError):
            return value

    if annotation is bool:
        return value.lower() in ("true", "1", "yes")

    return value


def _get_type_hints(func: Any) -> dict[str, Any]:
    """Return resolved type hints for *func*, falling back to {} on failure."""
    try:
        return typing.get_type_hints(func)
    except Exception:
        return {}


def _resolve_params(
    params: Mapping[str, Any],
    parameters: dict[str, str],
    type_hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replace {{key}} placeholders in action params with values from parameters.

    If *type_hints* is provided (from typing.get_type_hints), resolved string
    values are coerced to match the annotated type (e.g. "5" → 5 for int).
    """
    resolved: dict[str, Any] = {}
    for k, v in params.items():
        if isinstance(v, str) and v.startswith("{{") and v.endswith("}}"):
            placeholder_key = v[2:-2].strip()
            value = parameters.get(placeholder_key, v)
            if type_hints is not None and k in type_hints and isinstance(value, str):
                value = _coerce_to_annotation(value, type_hints[k])
            resolved[k] = value
        else:
            resolved[k] = v
    return resolved


from clients.netgent.src.registry.actions.base import ActionRegistry
from clients.netgent.src.registry.actions.network import NETWORK_ACTIONS

logger = logging.getLogger(__name__)


class StateExecutor:
    def __init__(
        self,
        *,
        registry: ActionRegistry | None = None,
        context: Any = None,
        actions: Iterable[Any] | None = None,
        config: Mapping[str, Any] | None = None,
        parameters: dict[str, str] | None = None,
    ) -> None:
        if registry is not None and (context is not None or actions is not None):
            raise ValueError(
                "Pass either `registry` or `context` / `actions`, not both"
            )

        self.registry = registry or ActionRegistry(
            context=context,
            actions=actions if actions is not None else NETWORK_ACTIONS,
        )

        self._parameters: dict[str, str] = dict(parameters or {})

        default_config = {
            "action_period": 1,
        }
        self.config = {**default_config, **dict(config or {})}

        logger.info(
            "StateExecutor initialized with actions: %s",
            list(self.registry.names()),
        )

    def execute(
        self,
        action: Mapping[str, Any],
    ) -> Any:
        if "type" not in action:
            raise ValueError("Action dictionary must contain 'type' key")

        action_type = action["type"]
        params = action.get("params", {})
        if not isinstance(params, Mapping):
            raise ValueError("Action 'params' must be a dictionary")

        if self._parameters:
            action_func = self.registry.get(action_type)
            params = _resolve_params(
                params, self._parameters, _get_type_hints(action_func)
            )

        logger.info("Executing action '%s' with params=%s", action_type, params)

        result = self.registry.run(action_type, param=dict(params))

        logger.info("Action '%s' executed successfully", action_type)
        return result

    async def aexecute(
        self,
        action: Mapping[str, Any],
    ) -> Any:
        if "type" not in action:
            raise ValueError("Action dictionary must contain 'type' key")

        action_type = action["type"]
        params = action.get("params", {})
        if not isinstance(params, Mapping):
            raise ValueError("Action 'params' must be a dictionary")

        if self._parameters:
            action_func = self.registry.get(action_type)
            params = _resolve_params(
                params, self._parameters, _get_type_hints(action_func)
            )

        logger.info("Executing action '%s' with params=%s", action_type, params)

        result = await self.registry.arun(action_type, param=dict(params))

        logger.info("Action '%s' executed successfully", action_type)
        return result

    def run(
        self,
        state: Mapping[str, Any],
    ) -> list[Any]:
        if "actions" not in state:
            raise ValueError("State dictionary must contain 'actions' key")

        actions = state["actions"]
        if not isinstance(actions, list):
            raise ValueError("State 'actions' must be a list")

        logger.info("Running state with %s actions", len(actions))

        results: list[Any] = []
        for index, action in enumerate(actions):
            if not isinstance(action, Mapping):
                raise ValueError("Each action must be a dictionary")

            logger.debug(
                "Action %s/%s: %s",
                index + 1,
                len(actions),
                action.get("type", "unknown"),
            )
            results.append(self.execute(action))

            if index < len(actions) - 1:
                time.sleep(self.config["action_period"])

        logger.info("State execution completed successfully")
        return results

    async def arun(
        self,
        state: Mapping[str, Any],
    ) -> list[Any]:
        if "actions" not in state:
            raise ValueError("State dictionary must contain 'actions' key")

        actions = state["actions"]
        if not isinstance(actions, list):
            raise ValueError("State 'actions' must be a list")

        logger.info("Running state with %s actions", len(actions))

        results: list[Any] = []
        for index, action in enumerate(actions):
            if not isinstance(action, Mapping):
                raise ValueError("Each action must be a dictionary")

            logger.debug(
                "Action %s/%s: %s",
                index + 1,
                len(actions),
                action.get("type", "unknown"),
            )
            results.append(await self.aexecute(action))

            if index < len(actions) - 1:
                await asyncio.sleep(self.config["action_period"])

        logger.info("State execution completed successfully")
        return results


__all__ = ["StateExecutor"]
