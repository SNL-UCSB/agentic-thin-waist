from __future__ import annotations

from typing import Any

from netgent.src.engine.controller import ProgramController
from netgent.src.engine.executor import StateExecutor
from netgent.src.engine.schema import WorkflowSchema


class WorkflowRunner:
    def __init__(
        self,
        controller: ProgramController,
        executor: StateExecutor,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.controller = controller
        self.executor = executor
        self.config = dict(config or {})

    def validate(self, workflow: dict[str, Any]) -> dict[str, Any]:
        validated_workflow = WorkflowSchema.model_validate(workflow).model_dump(
            mode="json"
        )

        for state_index, state in enumerate(validated_workflow["states"]):
            self._validate_state(state, state_index=state_index)

        return validated_workflow

    def _validate_state(self, state: dict[str, Any], *, state_index: int) -> None:
        for check_index, check in enumerate(state.get("checks", [])):
            self._validate_check(
                check,
                state_index=state_index,
                check_index=check_index,
            )

        for action_index, action in enumerate(state.get("actions", [])):
            self._validate_action(
                action,
                state_index=state_index,
                action_index=action_index,
            )

    def _validate_check(
        self,
        check: dict[str, Any],
        *,
        state_index: int,
        check_index: int,
    ) -> None:
        self._validate_registry_entry(
            registry=self.controller.registry,
            entry_kind="check",
            entry=check,
            state_index=state_index,
            entry_index=check_index,
        )

    def _validate_action(
        self,
        action: dict[str, Any],
        *,
        state_index: int,
        action_index: int,
    ) -> None:
        self._validate_registry_entry(
            registry=self.executor.registry,
            entry_kind="action",
            entry=action,
            state_index=state_index,
            entry_index=action_index,
        )

    def _validate_registry_entry(
        self,
        *,
        registry: Any,
        entry_kind: str,
        entry: dict[str, Any],
        state_index: int,
        entry_index: int,
    ) -> None:
        entry_type = entry["type"]
        params = entry.get("params", {})

        try:
            definition = registry.definition(entry_type)
            definition.public_signature.bind(**params)
        except Exception as exc:
            raise ValueError(
                f"Invalid {entry_kind} '{entry_type}' in state {state_index} "
                f"at index {entry_index}: {exc}"
            ) from exc

    def run(self, workflow: dict[str, Any]) -> list[Any]:
        validated_workflow = self.validate(workflow)
        states = validated_workflow["states"]

        passed_states = self.controller.check(states)
        if not passed_states:
            return []

        return [self.executor.run(state) for state in passed_states]

    async def arun(self, workflow: dict[str, Any]) -> list[Any]:
        validated_workflow = self.validate(workflow)
        states = validated_workflow["states"]

        passed_states = await self.controller.acheck(states)
        if not passed_states:
            return []

        return [await self.executor.arun(state) for state in passed_states]
