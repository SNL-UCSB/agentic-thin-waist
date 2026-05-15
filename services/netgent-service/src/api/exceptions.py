"""Custom exceptions for the NetGent API layer."""

from __future__ import annotations


class NetGentAPIError(Exception):
    """Base application error for API-facing service failures."""

    def __init__(self, message: str, error_code: str = "NETGENT_API_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code

    def __str__(self) -> str:
        return f"{self.message} (Error Code: {self.error_code})"


class UnsupportedApplicationError(NetGentAPIError):
    """Raised when a workflow targets an unknown application."""

    def __init__(self, application: str) -> None:
        super().__init__(
            message=f"Unsupported application '{application}'.",
            error_code="UNSUPPORTED_APPLICATION",
        )
        self.application = application


class WorkflowNotFoundError(NetGentAPIError):
    """Raised when a workflow result cannot be found."""

    def __init__(self, workflow_id: str) -> None:
        super().__init__(
            message=f"Workflow '{workflow_id}' was not found.",
            error_code="WORKFLOW_NOT_FOUND",
        )
        self.workflow_id = workflow_id
