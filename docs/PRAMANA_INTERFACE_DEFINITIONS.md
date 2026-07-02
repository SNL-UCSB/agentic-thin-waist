# Pramana — Interface Definitions (the low-level companion)

**2026-07-02 · Companion to `PRAMANA_DESIGN_SPEC.md` v1.2.** The design spec
records *decisions*; this file records the *definitions*: copy-pasteable model
stubs, the full state-transition table, wire contracts with example payloads,
SQL, and the file manifest per migration step. Where the two disagree, this
file wins for implementation detail and the spec wins for intent. Everything
here is v1-scope only.

---

## 1. Repository layout delta (what gets created/edited, exactly)

```
shared/models/                        # M-1 — NEW package (owner: Jaber)
  __init__.py
  units.py            # Rate, Duration, Percent parse/format (canonical decimal)
  spec.py             # ExperimentSet, Experiment, NodeDecl, Regime blocks (A5)
  artifacts.py        # Deployment, WorkItem, StatusEvent, ResultEnvelope (A6–A9)
  capability.py       # CapabilityFile, WorkflowEntry, KnobEntry (A3)
  hashing.py          # identity() — the ONLY RFC 8785 call site
  defaults.py         # operational constants (spec §10)
  lexicon.yaml
  fixtures/           # golden A5 docs + hash vectors + capability files
shared/tests/         # property + golden-vector tests (M-1 gate)
capabilities/                         # M-2 — NEW, hand-authored, PR-reviewed
  netgent.yaml  netreplica.yaml  ctp.yaml
services/orchestration/app/
  scheduler/                          # M-3 — NEW (owner: Manni)
    store.py          # Postgres A6 store (CAS transitions, SKIP LOCKED claim)
    dispatch.py       # HTTP client: idempotent-accept, breaker, jitter
    lifecycle.py      # transition table + reap/requeue/cancel logic
    recovery.py       # crash-only startup reconciliation
  engine/executor.py                  # RETIRED by M-3 (delete after parity)
services/substrate-worker/src/substrate/
  work.py                             # M-4 — NEW: /v1/work + /v1/status handlers
  prepare.py                          # CTP batch fetch + workflow pin check
  probe.py                            # envelope verification (wraps /shape checks)
cli/pramana/                          # M-7 — NEW (typer app)
```

## 2. Model stubs (Pydantic v2 — normative field lists, A5–A9)

```python
# shared/models/spec.py
class Quantity(BaseModel):
    value: float
    unit: Literal["mbps","ms","s","pct"]          # canonical units only

class Static(BaseModel):
    capacity_down: Quantity; capacity_up: Quantity
    latency: Quantity
    jitter: Quantity | None = None                 # netem jitter
    queue: Queue                                   # {qdisc: str, args: str}
    impair: Impair | None = None                   # {loss_pct, reorder_pct, dup_pct}
    cca: str                                       # validated against capability

class Application(BaseModel):
    workflow: str      # "zoom_client@sha256:..."  pinned form REQUIRED post-compile
    params: dict[str, str | Quantity]              # values or "$secrets.<key>"

class Dynamic(BaseModel):
    mode: Literal["replay","load","both","none"]
    ctp: list[str] = []                            # len 1 or == iterations
    source: Literal["ctp_service","local_dir"] = "ctp_service"
    min_available: int = 1
    load: list[LoadEntry] = []                     # {workflow, node, params}

class Verify(BaseModel):
    probe: bool = True
    tolerance: Tolerance                            # {capacity_pct: 5, latency_ms: 2}
    policy: Literal["annotate"] = "annotate"        # v1: annotate only

class Experiment(BaseModel):
    id: str                                        # "e_" + identity_hash[:8]
    static: Static; application: Application; dynamic: Dynamic
    iterations: int = 1
    telemetry: Telemetry                            # {pcap, qtrace, app_metrics}
    verify: Verify

class NodeDecl(BaseModel):
    name: str
    kind: Literal["pool","service"]
    count: int = 1
    pool: Literal["fixed","elastic"] = "fixed"
    persistence: Literal["set","experiment","fresh-per-experiment"] = "experiment"
    pipeline: list[str]                             # workflow ids (unpinned ok here)
    requirements: list[str] = []
    params: dict[str, str] = {}                     # service nodes only

class ExperimentSet(BaseModel):
    model_config = ConfigDict(extra="forbid")       # STRICT at the gate
    schema_version: int = 1
    id: str
    intent_ref: str | None = None
    capability_pins: dict[str, Pin]                 # Pin={version,url,sha256,pinned_at}
    secrets: list[str] = []
    nodes: list[NodeDecl]
    mapping: dict[str, str]                         # node name -> connector id
    experiments: list[Experiment]                   # FLAT, fully expanded
# Consumers below the waist use the same models with extra="ignore".
```

```python
# shared/models/artifacts.py
class Deployment(BaseModel):                        # A6 — scheduler-owned row
    deployment_id: str                              # "d_" + uuid4 hex[:8] (row id,
                                                    # NOT experiment identity)
    experiment_id: str
    node: str                                       # "pool/worker-07"
    state: Literal["assigned","preparing","ready","running",
                   "reporting","done","failed","cancelled"]
    attempt: int = 1                                # <= 2
    fence: int = 1                                  # bumped on every requeue
    start_iteration: int = 1                        # resume point
    cancel_requested: bool = False
    prepare: PrepareInfo | None = None              # {ctp_batch, workflow_sha, skipped}
    error: str | None = None
    ts: dict[str, datetime] = {}                    # stage -> timestamp

class WorkItem(BaseModel):                          # A7 — POST /v1/work body
    deployment_id: str; fence: int; attempt: int
    start_iteration: int
    leaf: Experiment                                # full leaf, secrets RESOLVED
    secrets: dict[str, str] = {}                    # in-memory only; never logged

class StatusReply(BaseModel):                       # A8 — GET /v1/status response
    worker_id: str
    deployments: list[DeploymentStatus]             # all non-terminal on this worker
class DeploymentStatus(BaseModel):
    deployment_id: str; fence: int
    state: str; stage: str                          # stage: docker_up|prepare|
                                                    # service_ready|verify|run|
                                                    # publish|reset
    iteration: int
    ts: datetime
    log_tail: str = ""

class ResultEnvelope(BaseModel):                    # A9 — publish() body
    deployment_id: str; experiment_id: str
    iteration: int; attempt: int; fence: int
    spec_hash: str                                  # = experiment identity hash
    artifacts: list[Artifact]                       # {kind: pcap|qtrace|log,
                                                    #  key: str, bytes: int}
    metrics: dict                                   # {app: {...}, transport: {...}}
    verification: Verification
    ctp_realized_count: int | None = None
    context: dict                                   # static+dynamic+workflow_sha echo
class Verification(BaseModel):
    probed: bool
    per_factor: dict[str, str]   # {"envelope":"verified|failed|n/a",
                                 #  "ctp_realized":"characterized|n/a",
                                 #  "cca_negotiated":"characterized|n/a",
                                 #  "app_content":"unverified"}
    measured: dict               # {"capacity_down_mbps": 9.7, "latency_ms": 10.4, ...}
    tolerance_requested: Tolerance; tolerance_applied: Tolerance
    within_tolerance: bool | None
```

## 3. The deployment state machine — the actual table

Single writer: the scheduler. Events arrive from status polls, dispatch
results, and operator actions. **Any event whose `fence` < row fence is
DROPPED (stale).** Unlisted (state, event) pairs are errors → `failed`.

| Current | Event | Next | Side effects |
|---|---|---|---|
| assigned | dispatch_accepted | preparing | ts.dispatched |
| assigned | dispatch_conn_error ×N>breaker | assigned | mark worker suspect; try next worker (affinity fallback) |
| preparing | stage=prepare heartbeat | preparing | ts.prepare refreshed (prepare has its own 10-min budget) |
| preparing | stage=service_ready (service nodes) | ready | unblock dependent deployments |
| preparing | prepare_done | ready | prepare.skipped recorded |
| ready | stage=run | running | ts.run |
| running | iteration_completed(i) | running | start_iteration=i+1 persisted |
| running | stage=publish | reporting | — |
| reporting | envelopes_confirmed | done | release worker lock; FIFO advance |
| any active | 3 failed polls + no corroborating activity | (reap) | see below |
| (reap) | attempt < 2 | assigned | attempt+1, fence+1, start_iteration=last durable+1, requeue |
| (reap) | attempt == 2 | failed | error="reaped_max_attempts" |
| any active | cancel_requested set + next poll | cancelled | worker told to stop; fence retired |
| any active | worker reports fenced (its fence < ours) | (no-op) | worker self-terminates that run |
| any | operator force_fail | failed | error recorded |

Mass-reap brake: if >50% of active workers hit the reap condition within one
poll window, reaping pauses and the Core alarms (suspect observer).

## 4. Wire contracts (exact)

**Worker HTTP (served by substrate-worker, existing FastAPI app):**

```
POST /v1/work            body: WorkItem
  202 {"deployment_id","fence","state":"preparing"}     accepted (idempotent:
  200 {current DeploymentStatus}                        same (deployment_id,fence)
                                                        redelivered => current state,
                                                        NEVER a second run
  409 {"reason":"fence_stale","current_fence":N}        stale fence
  409 {"reason":"busy","running":"d_xxx"}               worker occupied (pool bug)
  422 problem+json                                      schema/sha refusal
GET  /v1/status          -> StatusReply (200 always if alive)
POST /v1/cancel          body: {"deployment_id","fence"} -> 202
(existing endpoints unchanged: /shape /capture /replay /qtrace /ctp/fetch /health)
```

**Core REST (FastAPI, /v1 prefix, RFC 9457 problem+json errors):**

```
POST /v1/experiment-sets      body: ExperimentSet (flat; sweeps pre-expanded by CLI)
  201 {"id": "es_..."}                        created
  200 {"id": "es_..."}                        identical content re-POSTed (idempotent)
  422 problem+json type=".../validation"      schema violation (field pointer inside)
  409 problem+json type=".../needs-input"     unresolved prerequisites; body carries
                                              questions: [{pointer, prompt, kind}]
GET  /v1/experiment-sets/{id}                 -> {execution: {...}, ingested: "n/m",
                                                  deployments: [DeploymentStatus...]}
POST /v1/experiment-sets/{id}/cancel          -> 202
POST /v1/intent               body: {"text": "..."}   (LLM path)
  200 {"session_id", "questions":[...]}        batched round (may be empty)
POST /v1/sessions/{id}/answers  body: {answers:{name:value}}
  200 {"echo": "<plain language>", "defaults":[...], "sweep_axes":[...],
       "spec": ExperimentSet}                  confirm via POST /v1/experiment-sets
```

**Error catalog (problem+json `type` suffixes):** `validation` ·
`needs-input` · `capability-mismatch` (value outside pinned ranges; body names
file+field) · `pin-stale` (capability hash no longer resolvable) ·
`secrets-missing` (key not in local file) · `pool-exhausted` · `not-found`.

## 5. SQL (scheduler store, M-3)

```sql
CREATE TABLE deployments (
  deployment_id  text PRIMARY KEY,
  experiment_id  text NOT NULL,
  set_id         text NOT NULL,
  node           text,
  state          text NOT NULL DEFAULT 'assigned',
  attempt        int  NOT NULL DEFAULT 1,
  fence          int  NOT NULL DEFAULT 1,
  start_iteration int NOT NULL DEFAULT 1,
  cancel_requested boolean NOT NULL DEFAULT false,
  prepare        jsonb,
  error          text,
  ts             jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at     timestamptz NOT NULL DEFAULT now()
) WITH (fillfactor = 70);                      -- heartbeat-update HOT headroom
CREATE INDEX ON deployments (set_id, state);

-- claim (assign next work to a free worker; affinity first, then any):
UPDATE deployments SET node = $worker, state = 'assigned', updated_at = now()
WHERE deployment_id = (
  SELECT deployment_id FROM deployments
  WHERE set_id = $active_set AND state = 'assigned' AND node IS NULL
  ORDER BY (preferred_node = $worker) DESC, deployment_id
  FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING *;

-- CAS transition (single-writer discipline enforced in SQL):
UPDATE deployments SET state = $next, ts = ts || $stamp, updated_at = now()
WHERE deployment_id = $id AND state = $expected AND fence = $fence;
-- rowcount 0 => stale observation, dropped.
```

Telemetry upsert key: `UNIQUE (spec_hash, deployment_id, iteration, attempt)`;
envelope insert is `ON CONFLICT DO NOTHING` + fence check in the WHERE.

## 6. One leaf, end to end (payload walk)

1. CLI expands sweeps → `POST /v1/experiment-sets` (A5, 100 leaves) → `201 es_zoom_9f3a1c22`.
2. Scheduler (set-FIFO) claims leaf `e_5b1d09aa` for `pool/worker-03` (SQL §5) →
   `POST http://worker-03:8002/v1/work` with WorkItem `{deployment_id:"d_ab12cd34",
   fence:1, attempt:1, start_iteration:1, leaf:{...}, secrets:{zoom_meeting_code:"…"}}` → `202`.
3. Worker: prepare (fetch `ctp c303` via `/ctp/fetch`, cached; fetch
   `zoom_client@sha256:9e…` — sha verified), probe (5 s iperf3×2 + 10 pings →
   `measured:{capacity_down_mbps:9.7,…}`), run 30 s, publish
   `ResultEnvelope{fence:1, spec_hash:"5b1d09aa…", verification:{per_factor:
   {envelope:"verified", ctp_realized:"characterized", app_content:"unverified"},
   within_tolerance:true}}` → telemetry `201` (upsert).
4. Core poll `GET /v1/status` sees `state:reporting→done` → CAS transition →
   next claim. Crash the Core anywhere in 2–4: restart reloads non-terminal
   rows, re-polls worker-03, reconciles by (fence, state), resumes.

## 7. Per-migration-step file manifest

| Step | Creates | Modifies | Deletes |
|---|---|---|---|
| M-1 | `shared/models/*`, `shared/tests/*` | root `pyproject.toml` (uv workspace), CI | per-service `requirements.txt` (phased) |
| M-2 | `capabilities/*.yaml`, loader in `shared/models/capability.py` | `orchestration/app/engine/tools.py` (snapshot reads) | runtime index.json fetch |
| M-3 | `orchestration/app/scheduler/*` | compose (worker count) | `engine/executor.py` (after parity test) |
| M-4 | `substrate/work.py`, `prepare.py`, `probe.py` | `substrate/main.py` (mount routers) | — |
| M-5 | telemetry migration (upsert key) | telemetry routes (+filters) | — |
| M-6 | match/backflow/echo in `orchestration/app/engine/` | `experiment_generator.py` (pins) | — |
| M-7 | `cli/pramana/*`, `examples/*` | — | `services/experiment-api/` |
