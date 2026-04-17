"""Procrastinate task definitions registered on the shared queue app."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Literal

from api.utils import (
    create_session_factory,
    get_job,
    get_workflow,
    update_job_status,
    update_workflow,
    upload_job_artifacts,
)
from api.worker import get_queue_app
from api.worker.constants import WORKFLOW_EXECUTE_QUEUE, WORKFLOW_GENERATE_QUEUE
from clients.netgent import NetGent

logger = logging.getLogger(__name__)

queue_app = get_queue_app()


def _fail_job(job_id: str, *, error: str | None = None) -> None:
    session_factory = create_session_factory()
    with session_factory() as session:
        job = get_job(session, job_id)
        if job is None:
            return
        update_job_status(session, job_id, "failed")
        if error is not None:
            metadata = dict(job.metadata_ or {})
            metadata["error"] = error
            job.metadata_ = metadata
        session.commit()


def _run_netgent_job(job_id: str, *, operation: Literal["generate", "execute"]) -> None:
    session_factory = create_session_factory()
    specification = ""
    workflow_id = None
    workflow_type: Literal["shell", "browser", "hybrid"] = "shell"
    workflow_definition: dict[str, Any] = {}

    try:
        with session_factory() as session:
            job = get_job(session, job_id)
            if job is None:
                return

            workflow = (
                get_workflow(session, job.workflow_id)
                if job.workflow_id is not None
                else None
            )
            if workflow is None:
                update_job_status(session, job_id, "failed")
                session.commit()
                return

            workflow_id = workflow.id
            specification = workflow.specification
            workflow_type = workflow.type
            workflow_definition = workflow.workflow
            parameters: dict[str, str] = {
                str(k): str(v)
                for k, v in (dict(job.metadata_ or {}).get("parameters") or {}).items()
            }

            if operation == "execute" and not workflow_definition:
                metadata = dict(job.metadata_ or {})
                metadata["error"] = "Workflow has not been generated yet"
                job.metadata_ = metadata
                update_job_status(session, job_id, "failed")
                session.commit()
                return

            update_job_status(session, job_id, "running")
            session.commit()

        client = NetGent(
            cdp_url=os.environ.get("BROWSERLESS_WS_ENDPOINT", "").strip() or None,
            headless=True,
        )
        if operation == "generate":
            agent_state = asyncio.run(
                client.generate(specification, type=workflow_type)
            )
            generated_workflow = (
                agent_state.get("workflow") if isinstance(agent_state, dict) else None
            )
            updated_workflow = generated_workflow or workflow_definition
            artifact_payload = updated_workflow
        else:
            execution_result = client.run_workflow(
                workflow_definition,
                type=workflow_type,
                parameters=parameters,
                record_har=workflow_type in ("browser", "hybrid"),
            )
            updated_workflow = workflow_definition
            artifact_payload = execution_result

        if workflow_id is not None and updated_workflow:
            with session_factory() as session:
                update_workflow(
                    session,
                    workflow_id,
                    workflow_definition=updated_workflow,
                )
                session.commit()

        artifacts = upload_job_artifacts(
            job_id=job_id,
            workflow_type=workflow_type,
            result=artifact_payload,
        )

    except Exception as exc:
        logger.exception(
            "NetGent %s worker execution failed for job %s", operation, job_id
        )
        _fail_job(job_id, error=str(exc))
        return

    with session_factory() as session:
        job = get_job(session, job_id)
        if job is None:
            return
        metadata = dict(job.metadata_ or {})
        metadata["artifacts"] = artifacts
        metadata["artifact_prefix"] = {
            "bucket": artifacts[0]["bucket"] if artifacts else None,
            "prefix": f"{job_id}/",
        }
        job.metadata_ = metadata
        update_job_status(session, job_id, "completed")
        session.commit()


@queue_app.task(
    queue=WORKFLOW_GENERATE_QUEUE,
    name="generate_netgent_workflow",
)
def generate_netgent_workflow(job_id: str) -> None:
    _run_netgent_job(job_id, operation="generate")


@queue_app.task(
    queue=WORKFLOW_EXECUTE_QUEUE,
    name="execute_netgent_workflow",
)
def execute_netgent_workflow(job_id: str) -> None:
    _run_netgent_job(job_id, operation="execute")
