from pydantic import BaseModel


class ExecuteWorkflowRequest(BaseModel):
    workflow_id: str
    job_id: str
    parameters: dict


class ExecuteWorkflowResponse(BaseModel):
    workflow_id: str
    job_id: str
    status: str
    error: str | None = None
