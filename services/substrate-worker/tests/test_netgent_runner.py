from clients.netgent.src.engine.controller import ProgramController
from clients.netgent.src.engine.executor import StateExecutor
from clients.netgent.src.engine.runner import WorkflowRunner
from clients.netgent.src.registry.actions.network import NETWORK_ACTIONS
from clients.netgent.src.registry.triggers.base_action import always_true


def build_shell_runner() -> WorkflowRunner:
    return WorkflowRunner(
        controller=ProgramController(triggers=(always_true,)),
        executor=StateExecutor(actions=NETWORK_ACTIONS),
    )


def test_validate_rejects_unknown_action() -> None:
    runner = build_shell_runner()

    workflow = {
        "specification": "invalid action workflow",
        "states": [
            {
                "checks": [],
                "actions": [{"type": "does_not_exist", "params": {}}],
                "end_state": "done",
            }
        ],
    }

    try:
        runner.validate(workflow)
    except ValueError as exc:
        assert "Invalid action 'does_not_exist'" in str(exc)
    else:
        raise AssertionError("Expected runner.validate(...) to reject unknown action")


def test_validate_rejects_invalid_action_params() -> None:
    runner = build_shell_runner()

    workflow = {
        "specification": "invalid params workflow",
        "states": [
            {
                "checks": [],
                "actions": [{"type": "ping", "params": {"count": 1}}],
                "end_state": "done",
            }
        ],
    }

    try:
        runner.validate(workflow)
    except ValueError as exc:
        assert "Invalid action 'ping'" in str(exc)
        assert "missing a required argument: 'host'" in str(exc)
    else:
        raise AssertionError("Expected runner.validate(...) to reject invalid params")
