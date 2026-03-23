"""Service helpers for querying NetGent persistence models."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import sqlalchemy as sa
from botocore.client import BaseClient
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from sqlalchemy.orm import sessionmaker

from netgent.executor.main import NetGentExecutor

from .exceptions import UnsupportedApplicationError
from .models import AvailableWorkflows, WorkflowRun
from .schemas import (
    AvailableWorkflowItem,
    AvailableWorkflowsResponse,
    GenerateWorkflowRequest,
    WorkflowResultResponse,
)


class NetGentService:
    def __init__(
        self,
        session_factory: sessionmaker,
        s3_client: BaseClient,
        s3_bucket_name: str,
    ):
        self._session_factory = session_factory
        self._s3_client = s3_client
        self._s3_bucket_name = s3_bucket_name

    @staticmethod
    def _run_youtube_workflow(
        search_query: str,
        workflow_id: str,
    ) -> dict[str, object]:
        executor: NetGentExecutor | None = None
        execution_result: dict[str, object] | None = None
        try:
            executor = NetGentExecutor(workflow_id=workflow_id)
            execution_result = executor.execute_youtube_workflow(search_query=search_query)
        finally:
            if executor is not None:
                har_file_path = executor.close()
                if execution_result is not None and har_file_path is not None:
                    execution_result["har_file_path"] = har_file_path

        if execution_result is None:
            raise RuntimeError("YouTube workflow execution did not return a result.")

        return execution_result

    def _upload_screenshots(
        self, workflow_id: UUID, screenshots: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        uploaded_screenshots: list[dict[str, str]] = []

        for screenshot in screenshots:
            action = screenshot["action"]
            object_key = f"{workflow_id}/screenshots/{action}.png"
            screenshot_bytes = base64.b64decode(screenshot["image_base64"])
            self._s3_client.put_object(
                Bucket=self._s3_bucket_name,
                Key=object_key,
                Body=screenshot_bytes,
                ContentType="image/png",
            )
            uploaded_screenshots.append(
                {
                    "action": action,
                    "bucket": self._s3_bucket_name,
                    "key": object_key,
                    "uri": f"s3://{self._s3_bucket_name}/{object_key}",
                }
            )

        return uploaded_screenshots

    def _upload_har_file(self, workflow_id: UUID, har_file_path: str) -> dict[str, str]:
        object_key = f"{workflow_id}/har/{workflow_id}.har"
        try:
            self._s3_client.upload_file(
                har_file_path,
                self._s3_bucket_name,
                object_key,
                ExtraArgs={"ContentType": "application/json"},
            )
            return {
                "bucket": self._s3_bucket_name,
                "key": object_key,
                "uri": f"s3://{self._s3_bucket_name}/{object_key}",
            }
        finally:
            if har_file_path:
                try:
                    import os

                    if os.path.exists(har_file_path):
                        os.remove(har_file_path)
                except OSError:
                    pass

    def generate_workflow(self, request: GenerateWorkflowRequest) -> WorkflowRun:
        with self._session_factory() as session:
            available_workflow = (
                session.execute(
                    sa.select(AvailableWorkflows).where(
                        AvailableWorkflows.application == request.application
                    )
                )
                .scalar_one_or_none()
            )
            if available_workflow is None:
                raise UnsupportedApplicationError(request.application)

            workflow_run = WorkflowRun(
                application_id=available_workflow.application_id,
                query=request.query,
                status="pending",
                metadata_={},
                parameters=request.parameters,
                workflow={
                    "application": request.application,
                    "query": request.query,
                    "parameters": request.parameters,
                    "timeout": request.timeout,
                },
            )
            session.add(workflow_run)
            session.commit()
            session.refresh(workflow_run)

            if request.application != "youtube":
                return workflow_run

            workflow_run.status = "running"
            session.commit()

            try:
                search_query = request.parameters.get("search_query") or request.query
                with ThreadPoolExecutor(max_workers=1) as executor_pool:
                    execution_result = executor_pool.submit(
                        self._run_youtube_workflow,
                        search_query,
                        str(workflow_run.id),
                    ).result()
                screenshots = execution_result.pop("screenshots", [])
                har_file_path = execution_result.pop("har_file_path", None)
                execution_result["screenshots"] = self._upload_screenshots(
                    workflow_run.id,
                    screenshots,
                )
                if har_file_path is not None:
                    execution_result["har"] = self._upload_har_file(
                        workflow_run.id,
                        har_file_path,
                    )
                workflow_run.status = "completed"
                workflow_run.metadata_ = execution_result
            except PlaywrightTimeoutError as exc:
                workflow_run.status = "timeout"
                workflow_run.metadata_ = {"error": str(exc)}
            except Exception as exc:
                workflow_run.status = "failed"
                workflow_run.metadata_ = {"error": str(exc)}

            session.commit()
            session.refresh(workflow_run)
            return workflow_run

    def get_available_workflows(self) -> AvailableWorkflowsResponse:
        with self._session_factory() as session:
            stmt = sa.select(AvailableWorkflows).order_by(
                AvailableWorkflows.application
            )
            rows = session.execute(stmt).scalars().all()
            return AvailableWorkflowsResponse(
                applications=[
                    AvailableWorkflowItem(
                        application=row.application,
                        notes=row.notes,
                    )
                    for row in rows
                ]
            )

    def get_workflow_status(self, workflow_id: UUID | str) -> WorkflowRun | None:
        workflow_uuid = UUID(str(workflow_id))
        with self._session_factory() as session:
            stmt = sa.select(WorkflowRun).where(WorkflowRun.id == workflow_uuid)
            return session.execute(stmt).scalar_one_or_none()

    def get_workflow_result(
        self, workflow_id: UUID | str
    ) -> WorkflowResultResponse | None:
        workflow = self.get_workflow_status(workflow_id)
        if workflow is None:
            return None
        return WorkflowResultResponse(
            workflow_id=str(workflow.id),
            status=workflow.status,
            metadata=workflow.metadata_,
        )

    def get_available_workflow(
        self, workflow_id: UUID | str
    ) -> AvailableWorkflowItem | None:
        workflow_uuid = UUID(str(workflow_id))
        with self._session_factory() as session:
            stmt = (
                sa.select(AvailableWorkflows)
                .join(
                    WorkflowRun,
                    WorkflowRun.application_id == AvailableWorkflows.application_id,
                )
                .where(WorkflowRun.id == workflow_uuid)
            )
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return None
            return AvailableWorkflowItem(
                application=row.application,
                notes=row.notes,
            )
