# Pramana Architectural Spec — v0 (Convergence Draft)

**UCSB SNL · 2026-07-01 · Status: DRAFT for team convergence**

Synthesized from: 07-01 meeting (orchestrator architecture, persistent worker pool, Zoom
data collection), `docs/vision.md` (April 1), `docs/thin_waist_one_pager.md` (April 10),
`docs/verification_gap.md` (May 12), and the current implementation state of this repo.

Purpose: this is the "very complete spec of what the software needs to do" that the
meeting closed on. Sections marked **[OPEN]** are unresolved forks that need an explicit
team decision — they are collected in §9.

---

## 1. Design principles (re-affirmed 07-01)

1. **Dumb services, smart controller.** All intelligence lives in the orchestrator's
   intent-facing layer. Every downstream service is a deterministic executor.
2. **LLM only at the intent boundary.** The intent parser may use an LLM. The planner,
   scheduler, and all execution paths are deterministic code ("we can use LLM to
   generate the code, but I want deterministic code at any case").
3. **Orchestrator facilitates communication, never carries data.** Bulk data (pcaps,
   CTPs, workflows) moves directly between services; the orchestrator moves pointers.
   *(Known deviation today: pcaps flow through the orchestrator — see §6.3.)*
4. **API-optional operation.** The system must be drivable without any LLM/API call:
   a user (or a for-loop) can submit fully-specified experiment JSONs directly. The
   LLM path is a convenience layer on top, never a dependency of the execution path.
5. **No spec the orchestrator doesn't understand.** If required information is missing
   (credentials, meeting codes, server endpoints), the orchestrator must ask the user —
   backflow — rather than emit a spec that will fail downstream.
6. **Disaggregation with chosen granularity, not maximal disaggregation.** Per-iteration
   teardown is an extreme point of the design space we explicitly reject.

## 2. Taxonomy (agreed 07-01)

| Term | Definition |
|---|---|
| **Intent** | User's natural-language or structured request. May expand into an experiment set. |
| **Experiment set** | The set of experiments produced by one intent. Tree-structured; internal nodes are parameter sweeps. |
| **Experiment** | A leaf node: one unique combination of *static context* (NetReplica knobs: capacity, latency, buffer, AQM, CC) + *application context* (one NetGent workflow + args) + *dynamic context* (one CTP). Same spec ⇒ same experiment. Different application ⇒ different experiment. |
| **Iteration** | A repeated run of the same experiment (`num_iterations` field in the experiment JSON). No teardown between iterations. |
| **Spec** | The compiled, fully-concrete artifact: a list of experiment JSONs (the "filled-out form"). Post-spec execution requires no AI assistance. |

## 3. Intent plane — module decomposition

User-facing flow (order is normative):

```
User ──> UI (REST: /intent, /experiment-status, ...)
           │
           v
   ┌──────────────────── Orchestrator ────────────────────┐
   │ 1. Intent Parser   (LLM-backed; extracts application │
   │       workflow, network condition, CTP criteria)     │
   │ 2. Knowledge Base  (storage + process; per-service   │
   │       capability parsers; see §4)                    │
   │ 3. Match           (intent vs. capabilities → yes/no │
   │       + backflow queries to user for missing info)   │
   │ 4. Planner         (deterministic; grouping,         │
   │       worker-pool assignment, prefetch plan)         │
   │ 5. Spec Generator  (emits experiment-set spec:       │
   │       list of experiment JSONs from spec template)   │
   │ 6. Scheduler       (dispatch experiments to worker   │
   │       pool; simple queue + semaphore)                │
   └───────────────────────────────────────────────────────┘
```

Notes:

- **UI is not the orchestrator.** The current implementation overloads "orchestrator"
  to mean UI + controller + everything. These are separate modules even if co-deployed.
- **Match is a distinct module** producing (a) a boolean per requirement, (b) concrete
  values filled into the spec template, (c) a query list for the user (backflow) when
  required parameters are unknowable (passwords, meeting codes, endpoints).
- **Planner is rule-based v1.** Grouping rules: iterations of an experiment always
  colocate sequentially on one worker (no teardown); experiments sharing sticky context
  (same CTP batch, same static config) group for prefetch benefit. No dynamic/LLM
  planning yet.
- **Scheduler v1 = FIFO over the worker pool with a semaphore.** Whoever finishes takes
  the next experiment. **[OPEN — §9.Q1]** queuing policy beyond v1.

## 4. Knowledge base & capability publishing

Each downstream service publishes a **capability file**; the knowledge base ingests all
of them at bootstrap and refreshes by **pull** (NAT forbids broadcast to workers; a
persistent connection may later enable push, but pull is the v1 contract).

| Service | Capability representation | Refresh model |
|---|---|---|
| **NetGent** | Per-workflow metadata: application, client/server workflow files, CLI-style parameters (duration, video, resolution, …), which are mandatory vs. optional + defaults, and *prerequisites* (account, meeting code, password, server endpoint). | Public repo/service; pull at bootstrap, re-pull on demand. Substrate workers pull workflow files directly by URL derived from the index. |
| **NetReplica** (static knobs) | Static file: supported knobs and value ranges (capacity, latency, buffer, AQM, CC). Ships with the substrate; pulled from master at bootstrap. Changes at low cadence. | One-time at bootstrap. |
| **CTP Service** | *Not* a static file — a **pointer to a queryable database**. Capability = the query schema (criteria: throughput range, active users, burstiness, direction, cluster id, transformed-or-not). Match queries it live; responses are pointers, possibly partial ("3,000 of the 10,000 you asked for"). | Live query at match time. |
| **Telemetry** | Storage/query API; capacity constraints (disk, connection pool). | Static config. |

Rules:

- Capability sync is **not** in the per-experiment runtime path. Runtime never blocks on
  capability discovery; it happens at bootstrap and on explicit refresh.
- The capability file is authored by the service developer today (the "capability doc");
  automated synthesis is future work.
- The knowledge base has a per-service **parser**; adding a service means adding a
  parser + capability file, not modifying match/planner.

## 5. Execution plane

### 5.1 Persistent worker pool (the headline change)

- Substrate workers are **persistent Docker containers created at bootstrap**, not
  ephemeral per-experiment containers. Pool size is a bootstrap parameter with a sane
  default derived from host resources; user-configurable, never exceeded.
- Docker images are **prebuilt and pulled from a registry** (Docker Hub / ECR). Build
  happens at most once at bootstrap if no image is available. Build is never in the
  runtime path.
- Measured motivation: per-experiment overhead today is 150–200 s of a 250–300 s
  container lifetime (Zoom: 30 s of useful experiment). Ephemeral→persistent is the
  single biggest efficiency win identified.
- **Ephemeral mode** may remain behind a flag for isolation-critical studies.
  **[OPEN — §9.Q2]**
- Single-user model for v1. Interference between concurrent experiment sets on one pool
  is acknowledged and not solved in v1.

### 5.2 Worker categories & service nodes (netUnicorn node abstraction)

Worker pools are **typed by persistence level**: a worker can be bound at the
*iteration*, *experiment*, or *experiment-set* level. This is expressible in the spec.

Long-running **service endpoints** (Zoom broadcaster, Puffer server, iperf server) are
*not* pool workers. They are separate **nodes** with their own workflow specification
(netUnicorn's node/pipeline decoupling), persistent for the lifetime of the experiment
set that declares them. Client workflows reference them by endpoint parameter.

- Every application capability declares which roles it needs: client-only, or
  client+server. (Peer-to-peer reduces to "the listener is the server".)
  Two workflows per application is the v1 ceiling; a DAG-structured workflow spec was
  considered and rejected as overkill for now. **[OPEN — §9.Q3]**
- Server/broadcaster workflows live in the official NetGent repo like any other
  workflow ("anything you do on a host from a workflow perspective is NetGent").
- How the persistent node is *declared in the spec template* is unresolved.
  **[OPEN — §9.Q4]**

### 5.3 Per-experiment execution sequence (worker-local)

1. Receive experiment JSON (pointerized: CTP pointers, workflow URL, static knobs).
2. Prefetch: download CTP batch **outside the shaped namespace** (unshaped path);
   cache locally (Redis or plain disk cache). Prefetch is plannable ahead of dispatch
   because the planner pre-assigns experiments to workers.
3. Network setup: apply static knobs inside the namespaces (~1 s; cheap).
4. Pull NetGent workflow by URL (cheap, cacheable).
5. Run iterations 1..N with no teardown between them; CTP replay per iteration.
6. Buffer telemetry locally (provisioned disk); publish results asynchronously (§6).
7. Reset network config between experiments; container persists.

## 6. Representation plane

### 6.1 CTP service — two-step contract

- **Step 1 (match):** query by criteria → pointers + availability count (may be
  partial; partial counts are a valid response, not an error).
- **Step 2 (fetch):** worker downloads CTP payloads directly by pointer.
- A **local CTP source** must be an officially supported step-1 bypass (pointer to a
  local/user-provided corpus) — currently a Zoom-sweep hack, to be promoted to a
  feature.
- Batch semantics: an experiment set carries the full CTP pointer list; workers download
  in batches (e.g., 100 at a time), not one-per-iteration.

### 6.2 Telemetry service

- Non-ephemeral, user-accessible; never torn down as part of experiment lifecycle.
- Worker-side results are deleted only after confirmed upload (no duplicates kept).
- **Decoupled upload:** telemetry transfer is asynchronous to experiment execution via a
  pub/sub queue (Kafka/RabbitMQ class; exact choice open **[OPEN — §9.Q5]**). Sync
  point is end-of-experiment-set, not end-of-experiment. Horizontally scalable uploader.
- Provisioning is spec-relevant: Postgres connection pool sized ~10–20× concurrent
  experiment count; disk sized for the experiment set; experiments must fail fast if
  storage is insufficient (no silent stall).

### 6.3 Known deviation

Today pcaps flow substrate→orchestrator→telemetry (NAT-driven). Target: substrate
publishes directly to the telemetry queue; orchestrator only carries the pointer.

## 7. Observability & verification

- **Stage-level tracing is mandatory**, not best-effort: docker-up, host-setup,
  CTP-fetch, net-setup, workflow-pull, run, telemetry-publish, teardown — each
  timestamped so waterfall diagrams fall out of logs. (Today's numbers are ±10 s
  polling estimates; that is not acceptable for the optimization loop.)
- Success metric: **non-experiment overhead ≪ experiment duration** per experiment.
- Spec→Substrate verification (per `docs/verification_gap.md`): post-hoc active probing
  that the requested bottleneck regime was realized, implemented inside the substrate
  worker. This is the tractable first verification layer and should be in the spec now.
- Intent→Spec verification: the match/backflow mechanism (§3) is the v1 answer; deeper
  verification is a named open problem, not overclaimed.

## 8. Data-collection commitments (context, from 07-01)

- Zoom: 20k data points (10 Mbps × {10 ms, 100 ms}; capacity sweep dropped), ~10k
  already collected; 3 servers in parallel; data by **Monday 07-06**, hard by mid-week.
  Persistent-worker patchwork proceeds in parallel on a branch — no holistic rewrite
  on the critical path.
- Puffer: India team runs collection (~8k/8 h); sanity-check their upstream bandwidth;
  embeddings come back to us, raw data stays there.
- Undergrad track (off critical path): more applications, CTP service maturation,
  telemetry features (queue occupancy, QoE extraction), analysis tooling.

## 9. Open questions for convergence **[the ask]**

| # | Question | Options / current lean |
|---|---|---|
| Q1 | Scheduler policy beyond v1 FIFO: do users ever need completion-order control (per-experiment-set priority, fair-share)? | Lean: FIFO + semaphore is enough for single-user v1; revisit only with evidence. |
| Q2 | Keep ephemeral mode behind a flag, or delete it to simplify? ("the code is insane") | Meeting leaned keep-a-flag (Jaber) vs. delete (Eugene). Unresolved. |
| Q3 | Is client+server (2 workflows/app) sufficient, or do we need N-role workflows now (multi-party conferencing with heterogeneous roles)? | Lean: 2 roles for v1; broadcaster+receivers already fits (broadcaster=server-role). |
| Q4 | Spec-template syntax for persistent nodes: how does the spec declare "this node runs workflow W for the lifetime of the experiment set"? (Today: hacked via 1M-second experiment duration.) | Undesigned. Needs a proposal — likely a `services:` block at experiment-set scope. |
| Q5 | Telemetry transport: RabbitMQ, Kafka, Redis streams, or plain S3-multipart + retry? | Undecided; "don't over-engineer" was voiced. |
| Q6 | Who sizes fan-out (rooms, server instances): user-supplied via UI prompt, or planner heuristic? | Meeting: push to user for v1 (e.g., Zoom max 2 rooms/account). |
| Q7 | Credentials/secrets: in-intent (masked), a secrets file, or env-var store? Constraint: never persist user credentials server-side. | Undecided; NetGent already masks passwords as workflow params. |
| Q8 | Rewrite vs. patchwork trajectory: after the worker-pool patch, what is the sequence for decomposing the orchestrator into §3's modules? | Meeting deferred; needs an ordered migration plan with owners. |
| Q9 | Verification scope for v1: is Spec→Substrate active probing in or out of the summer scope? | `verification_gap.md` argues in; not discussed 07-01. |

## 10. Delta vs. current implementation

Audit of this repo (2026-07-01). Legend: ✅ done · 🟡 partial · ❌ missing.

| Spec element (§) | Current state | Δ |
|---|---|---|
| Intent parser (§3.1) | LangGraph agent in `services/orchestration` (`parse_intent → generate_experiments → execute_experiments → respond`); 21 test files; the most mature module. | ✅ |
| UI ≠ orchestrator (§3) | One service does UI+controller+everything; `orch_cli.py` is the only separate surface. Meanwhile `services/experiment-api` (:8000) — the "smart controller" of CLAUDE.md — is a 65-line in-memory stub whose role was absorbed by orchestration (:8005). | 🟡 |
| Knowledge base + capability publishing (§4) | ❌ as designed. Workflow discovery queries `netgent-workflow/index.json` **at runtime per request** (exactly the anti-pattern the meeting rejected); no capability files, no bootstrap ingest, no per-service parsers. NetReplica knobs are hardcoded in orchestration knowledge/prompt files. | ❌ |
| Match + backflow (§3, §7) | Monolithic "experiment checker"; on missing info it **fails** ("specification not provided") instead of querying the user. Classroom-reported mismatch between intent and generated spec, no verification loop. | 🟡 |
| Planner (§3) | Does not exist. No grouping, no prefetch planning, no worker pre-assignment. | ❌ |
| Spec generator (§2, §3) | `experiment_generator` emits list of experiment JSONs; deterministic `context` overrides supported. No stable, versioned spec-template schema; no persistent-node declaration; no ordering/roles. | 🟡 |
| Scheduler + **persistent worker pool** (§5.1) | ❌. `ConnectivityManager.create_worker()`/`destroy_worker()` is strictly ephemeral per-spec; parallelism = `ThreadPoolExecutor(max_parallel_workers)`. No `worker_pool` concept anywhere in code. This is the agreed patchwork priority. | ❌ |
| Worker categories / service nodes (§5.2) | ❌. Zoom broadcaster hack = 1M-second experiment blocking a worker; not in main. | ❌ |
| Prebuilt images, no runtime build (§5.1) | `docker-compose.public.yml` overlay with `snlhub/*` prebuilt images just landed (PR #157). | ✅ |
| CTP two-step + local-source flag (§6.1) | CTP service substantially implemented (extract/select/transform/merge); orchestration treats CTP as opt-in and defaults to a **hardcoded global instance** (`128.111.5.236:8001`). Local-corpus bypass is Haarika's Zoom hack, unsupported officially. Batch prefetch ❌. | 🟡 |
| Telemetry decoupled upload (§6.2, §6.3) | ❌ as designed: orchestrator **pulls** pcaps from substrate and pushes to telemetry (`telemetry_capture_pull`) — the acknowledged deviation. No queue, no async uploader, sync is per-experiment. Telemetry service itself is solid (6 test files, migrations, S3 artifacts) but `GET /results` can't filter by `orchestration_id`. | ❌ |
| Stage-level tracing (§7) | 🟡. `/qtrace` queue-occupancy tracing landed (CCAnalyzer-style analysis notebook); but lifecycle stage timing is still pre-up/post-down polling (±10 s) — no per-stage timestamps. | 🟡 |
| Spec→Substrate verification (§7) | 🟡 seed exists: substrate `/shape` does post-hoc iperf3/ping verification (`verified`/`verification_log`). Not systematized per `verification_gap.md`. | 🟡 |
| API-optional operation (§1.4) | 🟡. Deterministic overrides + per-request `workflow_source`/`workflow_id` + CLI exist, but there is no documented "submit a fully-formed spec, skip the LLM" entry point; classroom sweeps required hacking parsing out. | 🟡 |
| Substrate portability (paper claim) | `local_docker` ✅, `aws` hybrid 🟡, `gcp`/`remote` raise `NotImplementedError`. | 🟡 |
| Shared contracts (`shared/`) | `shared/models/__init__.py` is **empty** and `shared/clients/` is a docstring, versus 500-line READMEs specifying `Experiment`, `BaseHTTPClient`, etc. Each service defines its own schemas — no single spec-template source of truth. | ❌ |
| Substrate worker execution (§5.3) | Strongest execution-plane component: 15-CCA support with LD_PRELOAD shim + strict CI sweep, namespaces, capture, replay, qtrace. Recent work concentrated here. | ✅ |

**Reading of the delta:** the *execution* half of the thin waist (substrate worker,
CTP ops, telemetry storage, NetGent workflows) is in decent shape; the *intent* half
matches the papers' narrative but not the meeting's module decomposition — knowledge
base, match-with-backflow, planner, scheduler-over-pool are all missing or fused into
one hard-to-modify service. The persistent worker pool is both the biggest measured win
(150–200 s overhead per 30 s experiment) and the smallest architectural step, which is
why it is the agreed patchwork.

### Naming/terminology alignment (papers ↔ code)

- Papers (HotNets draft `Pramana_Hotnets`, SIGCSE `SIGSCE_Pramana`) call the system
  **Pramana**, a *generative empirical backend*; "empirical thin waist" is the shape,
  and the waist artifact is the **intent specification**. The codebase should adopt
  "intent spec / experiment spec" naming to match.
- Papers credit **NetReplica** as the conditions layer; the code implements it as
  CTP Service + Substrate Worker and never says NetReplica. The capability file for
  static knobs (§4) should be named NetReplica capabilities to keep the vocabulary
  consistent with the writing.
- The paper's six-service table says "only the orchestrator holds intelligence" — the
  meeting's module decomposition (§3) is the *internal* structure of that one
  intelligent box and does not contradict the published architecture.
