from __future__ import annotations

import pytest
from pydantic import ValidationError

from netgent.src.engine.controller import ProgramController
from netgent.src.engine.executor import StateExecutor
from netgent.src.engine.runner import WorkflowRunner
from netgent.src.engine.schema import WorkflowSchema
from netgent.src.registry.triggers.base import TriggerRegistry


def test_workflow_schema_accepts_parameter_name_list():
    workflow = WorkflowSchema.model_validate(
        {
            "specification": "Ping a host",
            "states": [
                {
                    "checks": [],
                    "actions": [
                        {"type": "ping", "params": {"host": "{{host}}"}},
                    ],
                }
            ],
            "parameters": ["host"],
        }
    )

    assert workflow.parameters == ["host"]


def test_workflow_schema_rejects_parameter_dict():
    with pytest.raises(ValidationError, match="Workflow 'parameters' must be a list"):
        WorkflowSchema.model_validate(
            {
                "specification": "Ping a host",
                "states": [
                    {
                        "checks": [],
                        "actions": [
                            {"type": "ping", "params": {"host": "{{host}}"}},
                        ],
                    }
                ],
                "parameters": {
                    "host": "Target hostname or IP",
                },
            }
        )


def test_workflow_schema_rejects_parameter_dict_in_legacy_single_state_shape():
    with pytest.raises(ValidationError, match="Workflow 'parameters' must be a list"):
        WorkflowSchema.model_validate(
            {
                "specification": "Ping a host",
                "checks": [],
                "actions": [
                    {"type": "ping", "params": {"host": "{{host}}"}},
                ],
                "parameters": {
                    "host": "Target hostname or IP",
                },
            }
        )


def test_workflow_runner_requires_declared_parameters():
    runner = WorkflowRunner(
        controller=ProgramController(
            triggers=TriggerRegistry(),
        ),
        executor=StateExecutor(actions=[], parameters={}),
    )

    with pytest.raises(ValueError, match="Missing required workflow parameters: host"):
        runner.run(
            {
                "specification": "Ping a host",
                "states": [
                    {
                        "checks": [],
                        "actions": [],
                    }
                ],
                "parameters": ["host"],
            }
        )
