from __future__ import annotations

from typing import Any

from engine.controller import ProgramController
from engine.executor import StateExecutor
from engine.schema import WorkflowSchema


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

    def run(self, workflow: dict[str, Any]) -> list[Any]:
        validated_workflow = WorkflowSchema.model_validate(workflow).model_dump(
            mode="json"
        )
        states = validated_workflow["states"]

        passed_states = self.controller.check(states)
        if not passed_states:
            return []

        return [self.executor.run(state) for state in passed_states]
