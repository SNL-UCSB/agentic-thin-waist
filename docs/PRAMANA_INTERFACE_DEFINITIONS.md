# Pramana — Interface Definitions (the low-level companion)

**2026-07-02 · Companion to `PRAMANA_DESIGN_SPEC.md` v1.2.** The design spec
records *decisions*; this file records the *definitions*: copy-pasteable model
stubs, the full state-transition table, wire contracts with example payloads,
SQL, and the file manifest per migration step. **The v2 conditions model
(`PRAMANA_GRAMMAR_V2_RATIONALE.md`) revises the models tagged `[v2]` below —
`Static`, `Workflow`/`Path`, `Queue`, `iterations`; read it before refining
them.** Where the two disagree, this
file wins for implementation detail and the spec wins for intent. Everything
here is v1-scope only.

---

## 1. Repository layout delta (what gets created/edited, exactly)

```
shared/models/                        # M-1 — NEW package (owner: Jaber)
  __init__.py
  units.py            # Rate, Duration, Percent parse/format (canonical decimal)
  spec.py             # ExperimentSet, Experiment, NodeDecl, Regime blocks (A5)
  artifacts.py        # Deployment, WorkItem, StatusReply/DeploymentStatus, ResultEnvelope, NodeDescriptor (A6–A10)
  capability.py       # CapabilityFile, WorkflowEntry, KnobEntry (A3)
  hashing.py          # identity() — the ONLY RFC 8785 call site
  defaults.py         # operational constants (spec §10)
  lexicon.yaml
  fixtures/           # golden A5 docs + hash vectors + capability files
shared/tests/         # property + golden-vector tests (M-1 gate)
shared/db/            # EXISTING psycopg client (reused); pooled variant added in M-3
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

## 1.5 Module & function outline (every public function, one line each)

```python
# shared/models/units.py
parse(text: str) -> Quantity                 # "10mbps" -> Quantity(10.0,"mbps"); raises UnitError
render(q: Quantity) -> str                   # canonical decimal string + unit ("10mbps");
                                             #   parse(render(q)) == q (BP-2). Named render,
                                             #   not format, to avoid shadowing the builtin

# shared/models/hashing.py
canonical_json(obj) -> bytes                 # RFC 8785; the ONLY call site, no reimplementation
identity(exp: Experiment) -> str             # sha256 over {workflow_sha, params-sans-secrets,
                                             #   static, dynamic}; excludes placement/iterations
set_hash(spec: ExperimentSet) -> str         # RT3-1: FULL equality key =
                                             # sha256(rfc8785({schema_version, nodes,
                                             # mapping, secrets, leaves})) — stored as its
                                             # own column; ALL equality/idempotency checks
                                             # use set_hash, never the id string
set_id(spec, slug_source: str = "intent") -> str   # "es_<slug>_" + set_hash[:8] (BP-5:
                                             #   slug from the CLI-supplied filename stem,
                                             #   default "intent"); slug DISPLAY-ONLY:
                                             #   kebab of spec filename stem (or "intent"),
                                             #   [a-z0-9-], <=24 chars; EQUALITY uses the
                                             #   full canonical hash alone, never the slug

# shared/models/capability.py
load_dir(path) -> Snapshot                   # read capabilities/*.yaml, content-hash each
Snapshot.pin() -> dict[str, Pin]             # pins for SpecGen
Snapshot.workflow(id) -> WorkflowEntry       # raises UnknownWorkflow
Snapshot.knob_range(name) -> Range

# orchestration/app/engine/llm_binding.py        (M3a)
class Provider(Protocol):
    complete(prompt, output_schema) -> dict  # validate-retry-once inside
    ask(context) -> list[Question]
make_provider(cfg) -> Provider               # "anthropic" | "openai_compatible"

# orchestration/app/engine/match.py             (M5)
match(draft, snap, lexicon) -> MatchResult   # Ok(validated, provenance) | NeedsInput(questions)
resolve_lexicon(phrase) -> CriteriaTemplate  # only source of fuzzy-word -> numbers
check_secrets(leaf, snap) -> list[str]       # keys required but undeclared -> questions

# orchestration/app/engine/spec_gen.py          (M6)
compile(matched, snap) -> ExperimentSet      # expand, pin shas+capability hashes, assign ids
echo(spec, provenance) -> str                # plain-language rendering + itemized defaults

# orchestration/app/scheduler/store.py          (M8, owner Manni)
create_all(spec) -> list[Deployment]
claim_next(worker_id, attrs) -> Deployment | None      # SKIP LOCKED (SQL §5)
transition(id, expected, next, fence, stamp) -> bool   # CAS; False = stale, drop
requeue(id) -> Deployment                    # attempt+1, fence+1, start_iteration=durable+1
mark_cancel(set_id) -> int

# orchestration/app/scheduler/dispatch.py
send_work(worker, item) -> DispatchResult    # idempotent-accept; breaker per worker
poll(worker) -> StatusReply                  # deadline << poll interval; jittered

# orchestration/app/scheduler/lifecycle.py
fold(status: DeploymentStatus) -> None       # applies transition table (§3)
reap_scan() -> None                          # 3 misses + corroboration + mass-reap brake
# orchestration/app/scheduler/recovery.py
recover() -> None                            # startup = load non-terminal rows, re-poll all

# substrate/work.py                             (M10)
POST /v1/work  -> accept_work(item)          # 202/200/409 semantics (§4)
GET  /v1/status -> status()
run_sequence(item)                           # prepare -> probe -> run -> publish -> reset
# substrate/prepare.py
fetch_ctp_batch(ptrs, source) -> paths       # outside shaped ns; skip-if-cached
fetch_workflow(pinned) -> path               # sha verify, refuse mismatch
# substrate/probe.py
probe(static, tolerance) -> Verification     # 5s iperf3 x2 + 10 pings + 2s drain

# cli/pramana/                                  (M7 CLI)
init(), doctor(), run(path, yes: bool), status(id, json: bool), cancel(id)
expand_sweeps(doc) -> ExperimentSet          # client-side; CTP criteria resolved via the select query (§8.6)
```

Anything not listed here is module-private. A student implementing a card
touches exactly the functions its INTERFACE block names — nothing else.

## 2. Model stubs (Pydantic v2 — normative field lists, A5–A9)

**Strictness mechanism (BP-6, normative):** every model below inherits
`StrictModel(BaseModel)` with `model_config = ConfigDict(extra="forbid")` —
Pydantic config does NOT propagate to nested models, so the base class is the
only correct way to make the compile gate strict at every level. Below-waist
consumers use lenient clones produced by one helper,
`lenient(Model) -> type[Model]` (same fields, `extra="ignore"`), exported as
`spec_lenient.*` from `shared/models`.

**Wire-vs-file shape (RT2-1, normative):** the YAML `experiment_set:` wrapper
exists ONLY in on-disk spec files (it hosts the sibling client-side `sweeps:`
block). On the wire, `POST /v1/experiment-sets` carries the **flat
`ExperimentSet` object** — the CLI unwraps the file and strips `sweeps:` after
expansion. Every model and endpoint example below uses the flat shape.

```python
# shared/models/spec.py
class Quantity(BaseModel):
    value: float
    unit: Literal["mbps","ms","pct"]              # canonical STORED units (BP-1):
    # a model validator NORMALIZES on construction — kbps/gbps -> mbps,
    # s/min -> ms — and QUANTIZES value (round-half-even, <= 6 fractional
    # digits, BP-11) so identical physical quantities always hash identically.
    # Input flexibility is preserved: {value: 30, unit: s} is ACCEPTED and
    # stored as {value: 30000.0, unit: ms}.

# [v2] Conditions split into the bottleneck link (Static, below) and the
# per-workflow path (a Path model on the workflow). See PRAMANA_GRAMMAR_V2_RATIONALE.md.
# v2 target: Static keeps ONLY bottleneck knobs {capacity, queue}; latency, jitter,
# impair move to a per-workflow Path{latency,jitter,loss,reorder,dup}; cca -> per-workflow
# structured Cca{algo,stack,version,params,flags,build}. (v1 fields kept below until migrated.)
class Static(BaseModel):
    capacity_down: Quantity; capacity_up: Quantity
    latency: Quantity                              # [v2] -> Path (per-workflow)
    jitter: Quantity | None = None                 # netem jitter — [v2] -> Path (per-workflow)
    queue: Queue                                   # {qdisc: str, args: str} — [v2] structured, see Queue
    impair: Impair | None = None                   # {loss_pct, reorder_pct, dup_pct} — [v2] -> Path
    cca: str                                       # validated vs capability — [v2] -> per-workflow Cca

class Application(BaseModel):
    workflow: str      # "zoom_client@sha256:..."  pinned form REQUIRED post-compile
    params: dict[str, str | Quantity | int | float | bool]   # values or "$secrets.<key>" (BP-12)

class Dynamic(BaseModel):
    mode: Literal["replay","load","both","none"]
    # validation matrix (RT2-11): replay => ctp non-empty & load empty;
    # load => load non-empty & ctp empty; both => both non-empty;
    # none => both empty. Anything else = 422.
    ctp: list[str] = []                            # len 1 or == iterations — enforced as a
                                                   # model validator = schema-gate 422 (BP-10)
    source: Literal["ctp_service","local_dir"] = "ctp_service"
    local_dir: str | None = None                   # RT3-3/BP-9: strict biconditional — REQUIRED
                                                   # when source=="local_dir", FORBIDDEN (422)
                                                   # when source=="ctp_service";
                                                   # absolute path AS SEEN INSIDE the worker
                                                   # container (RT7-1): the local_docker
                                                   # connector bind-mounts the host directory at
                                                   # the IDENTICAL path (compose volume), so host
                                                   # and container paths coincide; the CLI
                                                   # validates the host-side path and the mount.
                                                   # Layout
                                                   # {local_dir}/{incoming|outgoing}/{ctp_id}.pcap;
                                                   # CLI validates existence at submit; no config
                                                   # fallback. T1-ONLY (RT4-2/BP-8, set-level rule:
                                                   # leaves have no node binding at the gate): if
                                                   # ANY leaf uses source=local_dir, ALL mapping
                                                   # values must be local_docker — mixed sets with
                                                   # local_dir are illegal in v1
    min_available: int = 1
    load: list[LoadEntry] = []                     # {workflow, node, params}

class Verify(BaseModel):
    probe: bool = True
    tolerance: Tolerance = Tolerance()              # defaults 5%/2ms (BP-14)
    policy: Literal["annotate"] = "annotate"        # v1: annotate only

class Experiment(BaseModel):
    id: str                                        # "e_" + identity_hash[:8]
    static: Static; application: Application; dynamic: Dynamic
    iterations: int = 1                             # [v2] int | StopCriterion (event-triggered;
                                                    # PRAMANA_GRAMMAR_V2_RATIONALE.md §3)
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
    kind: Literal["leaf","service"] = "leaf"       # RT3-6
    state: Literal["assigned","preparing","ready","running",
                   "reporting","done","failed","cancelled"]
    attempt: int = 1                                # <= 2
    fence: int = 1                                  # bumped on every requeue
    start_iteration: int = 1                        # resume point
    cancel_requested: bool = False
    prepare: PrepareInfo | None = None              # {ctp_batch, workflow_sha, skipped}
    error: str | None = None
    ts: dict[str, datetime] = {}                    # stage -> timestamp

class WorkItem(BaseModel):                          # A7 — POST /v1/work body (NORMATIVE shape;
    deployment_id: str; fence: int; attempt: int    #  the design spec's A7 sketch defers here)
    start_iteration: int
    leaf: Experiment                                # full leaf
    secrets: dict[str, str] = {}                    # resolved values; in-memory only; never logged

# A8 is transported as a BATCHED reply to a scheduler-initiated poll (there is
# no per-event push in the direct binding). 'StatusEvent' in older sketches ==
# one DeploymentStatus entry inside this reply.
class StatusReply(BaseModel):                       # A8 — GET /v1/status response
    worker_id: str
    deployments: list[DeploymentStatus]             # all deployments NOT YET ACKNOWLEDGED
                                                    # by the Core — terminal states included
                                                    # until acked (RT6-6): the poll request
                                                    # carries ?ack=<id,id,...> of entries the
                                                    # Core has durably folded; worker drops them
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
| running | iteration_completed(i) | running | advisory fast-path only (RT6-7): the AUTHORITATIVE resume point is telemetry-confirmed envelopes; on requeue, start_iteration = max confirmed iteration + 1 |
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
  422 problem+json type=…/validation                    schema errors
  409 problem+json type=…/pin-mismatch                  workflow/capability sha
                                                        mismatch (error field:
                                                        workflow_pin_mismatch)
GET  /v1/status?ack=<id,id,...>  -> StatusReply (200 always if alive; ack =
                          comma-separated deployment_ids durably folded by the
                          Core — worker drops those entries, §2)
POST /v1/cancel          body: {"deployment_id","fence"} -> 202
GET  /v1/envelopes?since=<cursor>   (T2-ONLY collection; §8.4b)
GET  /v1/artifacts/{deployment_id}/{iteration}/{attempt}/{kind}  (T2-ONLY; §8.5)
(existing endpoints unchanged: /shape /capture /replay /qtrace /ctp/fetch /health)
This block is the COMPLETE worker HTTP surface (RT4-10).
```

**Core REST (FastAPI, /v1 prefix, RFC 9457 problem+json errors):**

```
POST /v1/experiment-sets      body: DraftExperimentSet — same shape as
                              ExperimentSet EXCEPT: capability_pins ABSENT,
                              workflow refs MAY be unpinned ids, experiment ids
                              ABSENT; sweeps already expanded by the CLI.
                              COMPILATION IS CORE-SIDE for both doors (RT6-1):
                              the Core validates (Match), may 409 needs-input,
                              then pins + assigns ids and RETURNS the compiled
                              ExperimentSet (which is what it stores)
  201 <compiled ExperimentSet>                created (FULL body, RT7-2)
  200 <compiled ExperimentSet>                same set_hash re-POSTed (idempotent)
  422 problem+json type=".../validation"      schema violation (field pointer inside)
  409 problem+json type=".../needs-input"     unresolved prerequisites; ONE body shape
                                              (RT3-4): {type,title,status, session_id,
                                              questions: [Question]} — session_id ALWAYS
                                              present; resume via /v1/sessions/{id}/answers
GET  /v1/experiment-sets/{id}                 (full schema, RT3-11) ->
  {execution: {state: running|done|cancelled|failed,
               total: int, assigned: int, running: int,
               done: int, failed: int, cancelled: int},
   ingested: {ingested: int, expected: int},
   deployments: {items: [DeploymentStatus...], next_cursor: str|null}}
                                  # ?deployments_limit=<=200&deployments_cursor=...
POST /v1/experiment-sets/{id}/cancel          -> 202
POST /v1/intent               body: {"text": "..."}   (LLM path)
  200 {"session_id", "questions":[Question,...]}            when questions exist
  200 {"session_id", "questions":[], "echo": str,
       "spec": ExperimentSet}                               when nothing to ask
                                                (exactly these two bodies; §8.10)
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
  preferred_node text,            -- planner affinity hint; the claim ORDER BY uses it
  kind           text NOT NULL DEFAULT 'leaf',
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
## 8. Completions (red-team round 1 — normative)

### 8.1 Remaining models (referenced in §2, defined here)

```python
# [v2] The AQM is a structured, capability-matched object: params leave the opaque
# `args` string and gain typed fields + ECN. v2 target adds `size`, `params`, `ecn`,
# `mode`; `args` stays as an exotic-knob passthrough. See PRAMANA_GRAMMAR_V2_RATIONALE.md §2.
class Queue(BaseModel):                          # RT-2/3
    qdisc: Literal["pfifo","bfifo","fifo","red","pie","fq_pie","codel",
                   "fq_codel","fq","cake"]       # closed set v1; extending it
                                                 # is a capability-file change
    args: str = ""                               # verbatim tc suffix appended after
                                                 # `tc qdisc add ... <qdisc> <args>`;
                                                 # validated by regex ^[a-z0-9 ._%]*$
                                                 # (no shell metachars); semantics owned
                                                 # by tc. Participates in identity as-is.

class Impair(BaseModel):                         # RT-4 — maps 1:1 onto netem
    loss_pct: float = 0.0                        # 0..100; netem `loss X%`
    reorder_pct: float = 0.0                     # 0..100; netem `reorder X%` (requires
                                                 # a delay; validator: latency > 0)
    dup_pct: float = 0.0                         # 0..100; netem `duplicate X%`
    # fields are independent; all default 0 = impairment absent; in identity.

class LoadEntry(BaseModel):                      # RT-5 — closed-loop cross-traffic
    workflow: str                                # pinned `id@sha256:...` post-compile,
                                                 # same rule as application.workflow
    node: str                                    # must name a declared node whose
                                                 # `pipeline` contains this workflow id
    params: dict[str, str | Quantity] = {}       # same typing as Application.params;
                                                 # $secrets refs allowed, same rules

class Tolerance(BaseModel):                      # RT-6 — closed key set v1
    capacity_pct: float = 5.0                    # max |measured-requested|/requested
    latency_ms: float = 2.0                      # max |measured-requested|
    # No other keys in v1 (extra="forbid"); adding a factor = schema_version bump.

class Artifact(BaseModel):                       # RT-7
    kind: Literal["pcap","qtrace","app_log","shell_log"]
    key: str                                     # object key, layout:
                                                 # {spec_hash}/{deployment_id}/{iteration}/{attempt}/{kind}
    bytes: int
    sha256: str                                  # integrity; verified on ingest/pull

class Pin(BaseModel):                            # RT2-5
    version: str
    url: str | None = None                       # None for local files (e.g. the lexicon,
                                                 # pinned from shared/models/lexicon.yaml)
    sha256: str
    pinned_at: datetime
    signed_by: str | None = None                 # v2 signing; None in v1

class Telemetry(BaseModel):                      # RT2-5 — per-leaf collection switches
    pcap: bool = True
    qtrace: bool = False
    app_metrics: bool = True

class PrepareInfo(BaseModel):                    # RT2-5
    ctp_batch: list[str] = []
    workflow_sha: str
    skipped: bool = False                        # True when all inputs were cached

class NodeDescriptor(BaseModel):                 # RT-32/41 — A10, connector -> planner
    node_id: str                                 # "pool/worker-03"
    connector: str
    endpoint: str                                # http://host:port (worker API)
    attrs: list[str]                             # browser, audio, cca_host, public_reach
    max_concurrent_regimes: int = 8
    state: Literal["healthy","suspect","down"]

class PoolSpec(BaseModel):                       # RT2-3 — Planner -> Connector.deploy
    name_prefix: str
    connector: str                               # from mapping
    count: int
    pool: Literal["fixed","elastic"]
    attrs_required: list[str] = []
    worker_image: str                            # default from config
```

### 8.2 Capability file schemas + examples (RT-8)

```yaml
# capabilities/netgent.yaml       kind: static
kind: static
service: netgent
service_version: "2.4.0"
artifact_base: "https://raw.githubusercontent.com/SNL-UCSB/netgent-workflow/main/workflows"
endpoints: []                      # allow-list for URL/host params (suffix or exact)
workflows:
  - id: zoom_client
    application: zoom
    role: client                   # client | server
    peer: zoom_server              # optional; required peer workflow id
    engine: browser                # browser | shell
    workflow_sha: "sha256:9e…"     # sha256 of workflows/<id>/workflow.json bytes
    params:                        # FULL param schema (RT6-4): flag/positional/arity
      - {name: duration, type: seconds, required: true, flag: "-d"}
      - {name: server,   type: node_ref, required: true, flag: "-s"}
      - {name: meeting_code, type: string, required: true, flag: "-m",
         kind: secret_or_param}
      # every field: {name, type, required, default?, flag?, positional?: int,
      #               arity?: 1|"*", kind?: secret|secret_or_param}
    prerequisites:                 # RT6-4: objects, not bare names
      - {name: meeting_code, kind: secret_or_param}
      - {name: meeting_password, kind: secret}
    # RULE (RT2-7): every prerequisite MUST also be a declared param with
    # kind secret|secret_or_param; `prerequisites` is exactly the subset of
    # params that must resolve before compile completes — there is no second
    # injection channel. (meeting_password therefore also appears in params:)
    #   - {name: meeting_password, type: string, required: true, kind: secret}
    node_requirements: [browser, audio]

# capabilities/netreplica.yaml    kind: static
kind: static
service: netreplica
knobs:
  - {name: capacity_down, type: rate, range: ["0.1mbps","10gbps"]}
  - {name: capacity_up,   type: rate, range: ["0.1mbps","10gbps"]}
  - {name: latency,  type: time, range: ["0ms","2000ms"]}
  - {name: jitter,   type: time, range: ["0ms","500ms"]}
  - {name: qdisc,    type: enum, values: [pfifo,bfifo,fifo,red,pie,fq_pie,codel,fq_codel,fq,cake]}
  - {name: cca,      type: enum, values: [cubic,bbr,reno,vegas,...], host_kernel: true}
realization_modes: [in_container_pair, split_pair]    # RT6-4
ceilings: {concurrent_regimes_per_host: 8}

# capabilities/ctp.yaml           kind: live
kind: live
service: ctp
endpoint: "http://ctp-service:8001"     # or the configured global instance
query_schema:                            # dimensions accepted by select (§8.6)
  - {name: intensity_range_mbps, type: "[float,float]"}
  - {name: burstiness_pmr_range, type: "[float,float]"}
  - {name: intensity_direction,  type: enum, values: [download,upload,both]}
  - {name: contributor_count_min, type: int}
```

### 8.3 Secrets file (RT-13)

`~/.pramana/secrets.yaml`, permissions 0600 (enforced: `doctor` and dispatch
hard-fail otherwise). Format: one flat map — `secrets: {zoom_meeting_code:
"…", meeting_password: "…"}`. Key charset `[a-z0-9_]{1,64}`. Precedence:
`PRAMANA_SECRET_<UPPERCASED_KEY>` env var > file entry > error
`secrets-missing`. A `$secrets.<key>` reference resolves only if `<key>` is a
declared prerequisite of that leaf's workflow.

### 8.4 Telemetry ingest contract (RT-11)

```
POST /v1/results        body: ResultEnvelope
  201 created · 200 duplicate (same (spec_hash,deployment_id,iteration,attempt) —
  body unchanged, upsert no-op) · 409 problem+json type=…/fence-stale (envelope
  fence < scheduler-recorded fence) · 422 schema
Who performs ingest (RT2-8 — one path per tier, end to end):
**T1:** the worker uploads artifact bytes to MinIO (same host, §8.1 key
layout), then POSTs the envelope to telemetry directly. **T2:** the worker
stores artifacts locally and queues envelopes; the Core's poll loop collects
envelopes (`GET /v1/envelopes?since=<cursor>`, §8.4b), pulls artifact bytes
(§8.5), uploads them to MinIO itself, then POSTs the envelope. Workers never
need to reach the laptop in either tier.
```

### 8.4b Worker envelope queue (T2 collection)

```
GET /v1/envelopes?since=<cursor>   -> {envelopes: [ResultEnvelope...], cursor}
  cursor = monotonic per-worker enqueue sequence number (RT6-2). COMMIT POINT:
  the Core advances `since` ONLY after, for every envelope in the page, (a)
  artifact bytes are uploaded to the object store and (b) telemetry returned
  2xx. Partial failure => re-fetch the same page; safe because ingest is
  idempotent on (spec_hash, deployment_id, iteration, attempt). Worker retains
  envelopes until the cursor passes them + 24 h.
```

### 8.5 Worker artifact access (RT-12 — T2 pull path)

```
GET /v1/artifacts/{deployment_id}/{iteration}/{attempt}/{kind}
  200 bytes (headers: X-Sha256, Content-Length) · 404 unknown · 410 evicted
Retention on the worker: until set completion + 24 h, then evicted.
At T1 workers write MinIO directly; this endpoint is the T2 collection path.
```

### 8.6 CTP select query (RT-9/26 — mirrors the implemented ctp-service API)

```
POST {endpoint}/ctps/select
  body: {query: {<dimensions from capability query_schema>}, limit: int<=10000,
         offset: int, order_by: intensity|burstiness|contributor_count}
  200 {query_matched: int, results_returned: int, ctps: [{ctp_id, intensity,
       burstiness, …}]}    — partial results are VALID (query_matched may be
                              less than requested; compile applies the
                              min_available rule, spec §4)
Deterministic selection (RT3-8): the CLI orders matches by (intensity asc,
ctp_id lexicographic) and takes the first N required; the RESOLVED pointer
list — not the query — is what enters the spec and the identity hash.
Replay direction rule (RT6-3): every CTP id ALWAYS fetches and replays BOTH
directions — incoming at the server-side endpoint, outgoing at the client-side
endpoint — mirroring the two-thread tcpreplay model. Direction is not a spec
knob in v1.
Payload fetch: GET {endpoint}/ctps/{ctp_id}/pcap?direction=incoming|outgoing
  (local_dir source: files at {dir}/{incoming|outgoing}/{ctp_id}.pcap)
```

### 8.7 /shape mapping for the probe (RT-10)

The worker's existing `/shape` endpoint accepts
`{download_mbps, upload_mbps, latency_ms, jitter_ms, qdisc, qdisc_args,
loss_pct, reorder_pct, dup_pct, cca, verify: {tolerance_capacity_pct,
tolerance_latency_ms}}` and returns `{applied: {...}, verified: bool,
measured: {capacity_down_mbps, capacity_up_mbps, latency_ms},
verification_log: str}`. `probe()` = call `/shape` with `verify` set (5 s
iperf3 per direction + 10 pings, 2 s drain before capture) and translate the
response into the `Verification` model (§2), factor `envelope`.

### 8.8 Workflow artifact contract (RT-15/43)

A workflow is `workflows/<id>/workflow.json` in the registry:
`{specification: str, states: [{checks: [{type, params}], actions:
[{type, params}], end_state: str}], parameters: [str]}` with
`workflows/<id>/manifest.json` `{name, description, version, type:
browser|shell, main}`. Parameter placeholders `{{name}}` are substituted at
run time from `Application.params`. Resolution: fetch
`{artifact_base}/{id}/workflow.json`; the sha256 of the raw fetched bytes MUST
equal the pin (`id@sha256:…`) or the worker refuses — `409 problem+json type=…/pin-mismatch` (same contract as
/v1/work §4) and the deployment fails with error `workflow_pin_mismatch`. Engine trust (RT2-6): the capability file's `engine` field is authoritative
and validated at compile; at run time the fetched `manifest.json` `type` MUST
equal it, else the worker refuses (`engine_mismatch`). The sha pin covers
`workflow.json` bytes only; `manifest.json` is advisory beyond the type check.
The runner interface:
`netgent-runner run <workflow.json> --type <manifest.type> --param k=v …`;
exit 0 = success, nonzero = workflow failure (stderr tail becomes
`DeploymentStatus.log_tail`).

### 8.8b Service nodes on the wire (RT2-2)

Service nodes reuse the same Deployment/WorkItem machinery with three fixed
rules: (1) `Deployment.experiment_id = "svc_" + node.name` — service
deployments live outside experiment identity and produce no ResultEnvelopes;
(2) the WorkItem carries a synthetic Experiment: `application.workflow` = the
node's `pipeline[0]` (pinned), `params` = the node's `params`,
`dynamic.mode = "none"`, `iterations = 1`, all `telemetry` switches false,
`verify.probe = false`, `static` = a FIXED documented default block (capacity 1 gbps both ways,
latency 0 ms, queue pfifo/"", cca cubic) — recorded, never applied (the
service endpoint runs outside the shaped namespace); deterministic regardless
of dependent leaves (RT6-9); (3) `Deployment.kind = "service"`
distinguishes them; and (4) v1 validators REQUIRE `len(pipeline) == 1` for
`kind: service` nodes (multi-step service pipelines are v2) (RT3-9) — service deployments are exempt from experiment timeouts
and the ingest path.

### 8.9 Service-node dependency model (RT-14)

A leaf depends on service node N iff any of its params has type `node_ref`
resolving to N (e.g. `server: broadcaster`). The scheduler dispatches service
nodes first; a dependent leaf is claimable only after N has emitted
`stage: service_ready` (its workflow's post-launch check). If N's deployment
reaches `failed`, all leaves depending on N fail with error
`service_node_failed` — no automatic service-node restart in v1 (re-run the
set). Service nodes are exempt from the experiment timeout; their liveness is
the normal poll + their container health check.

### 8.10 Session contract (RT-24)

`POST /v1/intent` creates a session: `{session_id: uuid, questions: [Question, ...]}` (Question model incl. the
closed `kind` enum: §8.10b — the single source). If
`questions` is empty, the SAME response already carries `{echo, spec}` — no
`/answers` call needed (RT2-10). A direct-spec `POST /v1/experiment-sets`
returning `409 needs-input` ALSO creates a session — the 409 body is
`{session_id, questions}`; resumption uses the same
`POST /v1/sessions/{id}/answers`, whose response is the §4 shape —
`{echo, defaults, sweep_axes, spec}` (all four fields required; RT7-8) — and
the client re-POSTs the returned spec (RT2-9). Sessions
live 1 h, in the Core's Postgres. `POST /v1/sessions/{id}/answers` body
`{answers: {<name>: <value>}}` — names must match the question list; values
are validated against `kind` (secret answers: the CLI writes the value into the LOCAL secrets file under
key `<name>` and submits the literal string `"$secrets.<name>"` as the answer
— the single canonical wire form, same as §8.10b; the Core never sees values). One round in v1: after answers, the
session returns the echo + compiled spec, or errors.

### 8.10b Question model and secret answers (RT3-5)

```python
class Question(BaseModel):
    name: str            # answer key; charset [a-z0-9_]
    pointer: str         # RFC 6901 JSON Pointer into the draft spec. Syntax,
                         # restated: "/"-separated reference tokens from the
                         # document root; "~" escapes as "~0", "/" in a token
                         # as "~1". Examples: /experiments/0/static/latency ;
                         # /nodes/1/params/meeting~1code (a key containing "/")
    prompt: str          # template-rendered text (never free-form model output
                         #   for validation-sourced questions)
    kind: Literal["string","seconds","rate","int","float","bool",
                  "choice","secret"]
    # Mapping from capability param types (§8.15) and validation failures:
    # enum -> choice (choices = declared values); node_ref -> choice (choices =
    # declared node names); url -> string (allow-list validated on answer);
    # seconds/rate/int/float/bool -> same-named kind; secret -> secret.
    # Validation-rejection questions reuse the failing field's mapped kind.
    choices: list[str] | None = None
```
Answers: `{answers: {<name>: <value>}}`, coerced/validated by `kind`.
**Secret answers never carry the value to the Core:** the CLI writes the value
into the LOCAL secrets file under key `<name>` and submits the literal string
`"$secrets.<name>"` as the answer.

### 8.11 Closed enums and required keys (RT-20/21/22)

`DeploymentStatus.state` ∈ the §3 table's states. `stage` ∈ {docker_up,
prepare, service_ready, verify, run, publish, reset}. `Verification.per_factor`
keys are exactly {envelope, ctp_realized, cca_negotiated, app_content} with
verdicts {verified, failed, characterized, unverified, n/a} — unknown keys are
a 422 in v1. `metrics` required keys: `transport` (from the capture:
`{throughput_mbps_ts: [...], rtt_ms_ts: [...], retransmits: int}`) and `app`
(workflow-dependent; browser workflows: `{qoe: {...}}`, shell: `{stdout_summary}`).
`context` required keys (RT3-16, and the design spec's taxonomy defers here):
`{static: {...as specced}, dynamic (per mode: replay→{mode, ctp};
load→{mode, load}; both→{mode, ctp, load}; none→{mode}),
application: {workflow_sha, params_sans_secrets}, worker_id}`. Producers may
add keys under `metrics.extra` only.
### 8.11b Identity payload layout + golden vector (BP-3/7/13 — normative)

The EXACT object hashed by `identity(e)` (before RFC 8785 serialization):

```json
{"dynamic": {"ctp": [...], "load": [...], "mode": "..."},
 "params":  { ...resolved Application.params; $secrets.* references kept
              verbatim as strings (BP-4); Quantities as {"unit","value"}
              post-normalization... },
 "static":  { ...ALL Static fields incl. null jitter/impair... },
 "workflow_sha": "<full pinned string, id@sha256:...>"}
```

Only `mode`, `ctp`, `load` from Dynamic participate (`source`, `local_dir`,
`min_available` are sourcing/placement concerns, outside identity). The
`set_hash` payload is `{"schema_version", "nodes", "mapping", "secrets",
"leaves": [identity payloads in list order]}` — the key is literally
`"leaves"`; `capability_pins`, `intent_ref`, and `id` are INTENTIONALLY
excluded so identical content recompiled against newer pins deduplicates.

**Golden vector #1** (any conforming implementation MUST reproduce this):
payload = a leaf with static {capacity_down/up 10 mbps, latency 10 ms, queue
codel/"", cca cubic, no jitter/impair}, application {workflow
"wget_client@sha256:aabbccdd", params {duration 30 s → normalized
{"unit":"ms","value":30000}, url "https://example.com/f.bin"}}, dynamic
{mode none}. Canonical bytes:

```
{"dynamic":{"ctp":[],"load":[],"mode":"none"},"params":{"duration":{"unit":"ms","value":30000},"url":"https://example.com/f.bin"},"static":{"capacity_down":{"unit":"mbps","value":10},"capacity_up":{"unit":"mbps","value":10},"cca":"cubic","impair":null,"jitter":null,"latency":{"unit":"ms","value":10},"queue":{"args":"","qdisc":"codel"}},"workflow_sha":"wget_client@sha256:aabbccdd"}
```

identity = `982f550e78fbede222f1fdf18c71d457b741280b9dc3e0f69968ac9e61b3c05d`.
This vector lives in `shared/models/fixtures/` and is CI-enforced (card C-104).

### 8.12 Connector API (RT3-2)

```python
class Connector(Protocol):
    def get_nodes(self) -> list[NodeDescriptor]: ...
    def deploy(self, spec: PoolSpec) -> list[NodeDescriptor]: ...
    def recycle(self, node_id: str) -> NodeDescriptor: ...   # fresh-per-experiment
    def stop(self, node_id: str) -> None: ...
    def health(self, node_id: str) -> Literal["healthy","suspect","down"]: ...
    def refresh_ingress(self) -> None: ...   # AWS: re-scope SG to operator IP;
                                             # no-op for other connectors
```
Mapping-string resolution: `local_docker` and `ssh:<user@host>` → built-ins;
`aws[:profile[@region]]` → built-in AWS with config profile/region (bare `aws`
= `connectors.aws.profile/region` from config); any other token → Python
entry-point lookup in group `pramana.connectors`.

### 8.13 Config schema (RT3-12) — `~/.pramana/config.yaml`

```yaml
llm:        {provider: anthropic|openai_compatible|none, model: str,
             endpoint: str|null, key_ref: str|null}   # key_ref = secrets-file key
connectors: {default: local_docker, aws: {profile: default, region: us-west-2}}
images:     {core: snlhub/core, substrate_worker: snlhub/substrate-worker,
             netgent_runner: snlhub/netgent-runner}
artifacts:  {bucket: pramana-artifacts, endpoint: "http://minio:9000",
             access_key_ref: minio_access, secret_key_ref: minio_secret}
ctp:        {endpoint: "http://ctp-service:8001"}
telemetry:  {endpoint: "http://telemetry-service:8004"}
pool:       {size: null}          # null = min(cores-2, 8)
capabilities: {sources: ["./capabilities", "~/.pramana/capabilities",
               "/opt/pramana/capabilities-snapshot"]}   # ordered; first hit wins
```
Env override naming: `PRAMANA_` + upper-snake path (`PRAMANA_LLM_PROVIDER`,
`PRAMANA_ARTIFACTS_BUCKET`); env > file > defaults above.

### 8.14 Artifact storage contract (RT3-10)

Bucket = `artifacts.bucket` (created by compose init). Auth from
`artifacts.*_ref` secrets-file keys. Content-Type
`application/octet-stream`. Overwrite policy: PUT to an existing key with the
SAME sha256 = no-op success; with a DIFFERENT sha256 = error
`artifact_conflict` (a bug — keys embed iteration+attempt uniqueness).
Telemetry verifies existence + sha on first artifact read; a missing object
flags the envelope `artifacts_missing` (result kept, per annotate-never-
discard).

### 8.15 Parameter type system + lexicon schema (RT3-13/14)

Capability param types (closed set): `string | seconds | rate | int | float |
bool | enum | node_ref | url | secret`. Wire representation in
`Application.params`: `seconds`/`rate` → `Quantity` object; `int/float/bool` →
native JSON; everything else → string (`node_ref` = a declared node name,
validated; `url` = allow-list checked). Answer coercion follows the same
table.

`lexicon.yaml`: `entries: [{phrase: "moderately bursty",
applies_to: "/dynamic", criteria: {burstiness_pmr_range: [2, 5]}}]` —
`resolve_lexicon(phrase)` returns the `criteria` dict (the `CriteriaTemplate`)
which Match merges into the CTP select query; `applies_to` scopes which spec
subtree the phrase may bind to.

### 8.16 problem+json fields + pagination (RT3-17, inlined)

Error body fields (all errors): `{type: str (URI suffix per the §4 catalog),
title: str, status: int, detail: str, instance: str|null}` + documented
extension members only (`session_id`, `questions`, `pointer`, `current_fence`).
Paginated endpoints (exactly three, one shape `{items, next_cursor}`):
`GET /v1/experiment-sets?limit&cursor` → items = `{id, state, created_at}`;
`GET /v1/results?spec_hash=&set_id=&limit&cursor` (telemetry) → items =
ResultEnvelope summaries `{spec_hash, deployment_id, iteration, attempt,
within_tolerance}`; and the deployments sublist of `GET /v1/experiment-sets/{id}` via `?deployments_limit=<1..200, default 50>&deployments_cursor=<opaque>` (the two LIST endpoints use plain `?limit&cursor`);
response `{items: [...], next_cursor: str|null}`.
