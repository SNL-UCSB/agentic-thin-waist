"""Procrastinate task definitions registered on the shared queue app."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from api.utils import (
    create_session_factory,
    get_job,
    get_workflow,
    update_job_status,
)
from api.worker import get_queue_app
from netgent.engine.main import NetGentEngine

logger = logging.getLogger(__name__)

queue_app = get_queue_app()


@queue_app.task(queue="workflows", name="run_netgent")
def run_netgent(job_id: str) -> None:
    session_factory = create_session_factory()
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

            workflow_definition = workflow.workflow
            update_job_status(session, job_id, "running")
            session.commit()

        engine = NetGentEngine()
        asyncio.run(engine.execute(workflow=workflow_definition))

    except Exception:
        logger.exception("NetGent worker execution failed for job %s", job_id)
        with session_factory() as session:
            job = get_job(session, job_id)
            if job is not None:
                update_job_status(session, job_id, "failed")
                session.commit()
            return

    with session_factory() as session:
        job = get_job(session, job_id)
        if job is None:
            return
        update_job_status(session, job_id, "completed")
        session.commit()
