# NetGent Service

**Port**: 8003
**Deliverable**: D2 (Application Workflow Engine)
**Leads**: Eugene + Jaber

## Purpose

NetGent is the application-side execution service in the thin-waist stack. It accepts a natural-language workflow specification, turns that specification into a persisted workflow definition, and then executes that saved workflow asynchronously.

The service currently supports two workflow types:

- `browser`: browser automation compiled and executed through the embedded NetGent browser agent and Playwright-based actions.
- `shell`: host-level network workflows compiled into a single-state workflow that runs built-in tools such as `ping`, `iperf3`, and `ndt`.

NetGent is also the source of truth for which saved workflows exist in the service. Other services should treat it as a narrow execution service: it stores workflow specifications, queues jobs, runs them, and returns artifacts and metadata. It does not coordinate experiment sequencing.

## Current Workflow Model

The implemented API is a two-step asynchronous workflow:

1. `POST /workflows/generate`
   Submits a natural-language specification and creates a `workflow_specifications` record plus a background generation job.
2. `GET /workflows/result/{job_id}`
   Polls the generation job until it reaches `completed` or `failed`.
3. `POST /workflows/execute`
   Starts a second background job that runs the previously generated workflow by `workflow_id`.
4. `GET /workflows/result/{job_id}`
   Polls the execution job until it reaches `completed` or `failed`.

Important details from the current implementation:

- `generate` returns both `workflow_id` and `job_id`.
- `execute` requires a previously generated `workflow_id`.
- `result` is keyed by `job_id`, not `workflow_id`.
- There is no separate `/workflows/status/{id}` endpoint. Job status is returned by `GET /workflows/result/{job_id}`.
- Generated and executed jobs share the same status values: `pending`, `running`, `completed`, `failed`, `timeout`.

## API Surface

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/workflows/generate` | POST | Persist a specification and queue workflow generation |
| `/workflows/execute` | POST | Queue execution of a previously generated workflow |
| `/workflows/result/{job_id}` | GET | Return the current job status and job metadata |
| `/workflows/available` | GET | List persisted workflows and their latest execution timestamp |
| `/health` | GET | Liveness probe for the API process |

## Request and Response Contracts

### POST `/workflows/generate`

Creates a workflow record and enqueues a generation job.

Request:

```json
{
  "specification": "Run ping against 8.8.8.8, then run ndt7 with default settings",
  "type": "shell",
  "timeout": 30
}
```

Response:

```json
{
  "workflow_id": "6c0c5b31-4d31-44e0-8e4e-060fd35d1155",
  "job_id": "34739789-0c7e-485f-a3fc-9faab7910d22",
  "status": "pending",
  "error": null
}
```

Generation behavior:

- For `shell`, the agent decides which built-in tools to call, converts them into a `WorkflowSchema`, and stores that generated workflow.
- For `browser`, the agent uses the browser generation subagent to produce a workflow definition. If generation succeeds, the browser workflow is then executed immediately inside the same generation job and the final workflow is stored back on the specification.

### POST `/workflows/execute`

Queues execution for an already generated workflow.

Request:

```json
{
  "workflow_id": "6c0c5b31-4d31-44e0-8e4e-060fd35d1155",
  "timeout": 30
}
```

Response:

```json
{
  "job_id": "b939847a-78fc-4f2d-891f-d6de6ec078fe",
  "workflow_id": "6c0c5b31-4d31-44e0-8e4e-060fd35d1155",
  "status": "pending",
  "error": null
}
```

Execution behavior:

- The service rejects execution if the workflow record does not exist.
- The service rejects execution if `workflow.workflow` is still empty, which means generation has not completed successfully yet.
- The execution worker loads the saved workflow definition and passes it back to the NetGent agent for execution.

### GET `/workflows/result/{job_id}`

Returns job status and job metadata for either a generation job or an execution job.

Response:

```json
{
  "workflow_id": "6c0c5b31-4d31-44e0-8e4e-060fd35d1155",
  "job_id": "b939847a-78fc-4f2d-891f-d6de6ec078fe",
  "status": "completed",
  "metadata": {
    "timeout": 30,
    "operation": "execute",
    "artifacts": [
      {
        "bucket": "netgent",
        "key": "b939847a-78fc-4f2d-891f-d6de6ec078fe/shell/output.json",
        "s3_uri": "s3://netgent/b939847a-78fc-4f2d-891f-d6de6ec078fe/shell/output.json",
        "url": "http://localhost:9000/netgent/b939847a-78fc-4f2d-891f-d6de6ec078fe/shell/output.json",
        "type": "shell"
      }
    ],
    "artifact_prefix": {
      "bucket": "netgent",
      "prefix": "b939847a-78fc-4f2d-891f-d6de6ec078fe/"
    }
  }
}
```

Metadata rules:

- On queue failure or runtime failure, `metadata.error` is populated.
- Successful jobs attach an `artifacts` array.
- `artifact_prefix` is always derived from the job id and points to the storage prefix used for uploaded artifacts.

### GET `/workflows/available`

Lists persisted workflow specifications, not hard-coded application templates.

Response:

```json
{
  "workflows": [
    {
      "workflow_id": "6c0c5b31-4d31-44e0-8e4e-060fd35d1155",
      "specification": "Run ping against 8.8.8.8, then run ndt7 with default settings",
      "last_executed_at": "2026-03-30T07:43:11.211291+00:00"
    }
  ]
}
```

This endpoint is useful for discovery and reuse of already generated workflows. It is not currently a registry of built-in application families.

## Background Jobs and Storage

NetGent persists state in PostgreSQL and runs work asynchronously through Procrastinate.

Tables:

- `workflow_specifications`: saved natural-language specification, workflow type, generated workflow JSON.
- `workflow_runs`: one row per generation or execution job, keyed by `job_id`.
- `workflow_artifacts`: reserved ORM model for per-job artifact metadata.

Queues:

- `workflow_generation`
- `workflow_execution`

Artifacts are uploaded to S3 or MinIO under a prefix based on the `job_id`.

Artifact behavior by workflow type:

- `browser`: uploads screenshots discovered in the nested result payload plus a HAR file when present.
- `shell`: uploads the tool execution output as `shell/output.json`.

## Worker Semantics

Both queued operations use the same worker harness:

1. Load the `workflow_runs` row and related `workflow_specifications` row.
2. Mark the job `running`.
3. Invoke the NetGent agent with the original natural-language specification.
4. If the agent returns a workflow definition, save it back to `workflow_specifications.workflow`.
5. Upload artifacts to object storage.
6. Mark the job `completed` or `failed`.

One nuance matters for callers:

- A `browser` generation job may already perform a full browser run because the browser agent generates a workflow and then immediately executes it before returning.

## Local Development

The API process and worker process are separate.

Run the API:

```bash
cd services/netgent-service
uv run python -m api.main
```

Run the worker:

```bash
cd services/netgent-service
uv run python -m api.worker.main
```

The service expects:

- PostgreSQL for workflow and Procrastinate tables
- S3-compatible object storage for artifacts
- valid `S3_ACCESS_KEY` and `S3_SECRET_KEY`
- optional browserless / CDP configuration for browser workflows
- a Gemini API key for the embedded `ChatGoogleGenerativeAI` agents

Important environment variables:

- `NETGENT_HOST`
- `NETGENT_PORT`
- `NETGENT_TIMEOUT_DEFAULT`
- `NETGENT_QUEUE_CONCURRENCY`
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `S3_ENDPOINT_URL`
- `S3_ACCESS_KEY`
- `S3_SECRET_KEY`
- `S3_BUCKET_NAME` or `NETGENT_S3_BUCKET_NAME`
- `NETGENT_S3_PUBLIC_URL`
- `BROWSERLESS_CDP_ENDPOINT` or `BROWSERLESS_WS_ENDPOINT`
- `GOOGLE_API_KEY`

### Gemini API Key

NetGent uses `ChatGoogleGenerativeAI` in the embedded agent stack, so local development must provide a Gemini API key.

For this repository, the canonical environment variable is `GOOGLE_API_KEY`, which is how the shared repo `.env` is currently configured.

Get a Gemini API key from Google AI Studio:

1. Go to `https://aistudio.google.com/`.
2. Sign in and press the `Get API Keys` page.
3. Create a new key, or select an existing project and copy its key.

Set it locally:

```bash
export GOOGLE_API_KEY="your_api_key_here"
```

If you want the setting to persist in `zsh`, add that line to `~/.zshrc` and reload it with:

```bash
source ~/.zshrc
```

Official reference:

- `https://ai.google.dev/gemini-api/docs/api-key`

## Recommended Client Flow

Clients should follow this sequence:

1. Submit `POST /workflows/generate`.
2. Poll `GET /workflows/result/{job_id}` until the generation job is terminal.
3. If generation succeeded, submit `POST /workflows/execute` with the returned `workflow_id`.
4. Poll `GET /workflows/result/{job_id}` for the execution job.
5. Read artifact URLs from `metadata.artifacts`.

This is the workflow other services should document and integrate against until the API surface changes in code.
