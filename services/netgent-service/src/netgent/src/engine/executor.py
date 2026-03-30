from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable, Mapping
from typing import Any

from netgent.src.registry.actions.base import ActionRegistry
from netgent.src.registry.actions.network import NETWORK_ACTIONS

logger = logging.getLogger(__name__)


class StateExecutor:
    def __init__(
        self,
        *,
        registry: ActionRegistry | None = None,
        context: Any = None,
        actions: Iterable[Any] | None = None,
        config: Mapping[str, Any] | None = None,
    ) -> None:
        if registry is not None and (context is not None or actions is not None):
            raise ValueError(
                "Pass either `registry` or `context` / `actions`, not both"
            )

        self.registry = registry or ActionRegistry(
            context=context,
            actions=actions if actions is not None else NETWORK_ACTIONS,
        )

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
