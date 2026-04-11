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
        return WorkflowSchema.model_validate(workflow).model_dump(mode="json")

    def _check_parameters(self, validated_workflow: dict[str, Any]) -> None:
        declared: list[str] = validated_workflow.get("parameters") or []
        if not declared:
            return
        supplied = set(self.executor._parameters or {})
        missing = [name for name in declared if name not in supplied]
        if missing:
            raise ValueError(
                f"Missing required workflow parameters: {', '.join(missing)}"
            )

    def run(self, workflow: dict[str, Any]) -> list[Any]:
        validated_workflow = self.validate(workflow)
        self._check_parameters(validated_workflow)
        states = validated_workflow["states"]

        passed_states = self.controller.check(states)
        if not passed_states:
            return []

        return [self.executor.run(state) for state in passed_states]

    async def arun(self, workflow: dict[str, Any]) -> list[Any]:
        validated_workflow = self.validate(workflow)
        self._check_parameters(validated_workflow)
        states = validated_workflow["states"]

        passed_states = await self.controller.acheck(states)
        if not passed_states:
            return []

        return [await self.executor.arun(state) for state in passed_states]
