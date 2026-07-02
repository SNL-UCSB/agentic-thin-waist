# Pramana Interface & Abstraction Spec — v0

**UCSB SNL · 2026-07-02 · Companion to `docs/pramana_spec_v0.md` (architecture) and
`docs/pramana_vs_netunicorn.md` (lineage). This document defines the contracts:
what modules exchange, over which seams, and who owns what state.**

---

## 0. Interface design rules (how we decide every contract below)

1. **Nouns over verbs.** Modules exchange a small family of *versioned artifacts*
   (specs, capability files, deployments, results), not chatty RPC. If two modules
   need a new conversation, first ask: which artifact is missing a field?
2. **Pointers in the control plane, payloads in the data plane.** Anything that
   crosses the orchestrator is a pointer (CTP id, workflow URL, artifact key).
   Payload movement is always worker ⇄ publisher/telemetry, direct.
3. **Pull at trust/NAT boundaries.** Wherever one side may be unreachable
   (workers behind NAT, infrastructure services), the unreachable side initiates:
   workers pull work and push results; the KB pulls capabilities. Push is allowed
   only inside one machine/profile.
4. **Additive evolution.** Every artifact carries `schema_version`. Consumers ignore
   unknown fields; producers never repurpose a field. Removing a field is a major
   version and requires a capability-file announcement.
5. **One source of truth for schemas.** All artifact schemas live in
   `shared/models/` as JSON Schema + generated dataclasses. Services validate at
   their boundary and reject, never coerce. (This fills the currently-empty
   `shared/models/__init__.py` with the thing it was always meant to hold.)
6. **Interfaces are profile-invariant.** The laptop and scale profiles swap
   *implementations* (direct upload vs. RabbitMQ), never *interfaces*. If a profile
   needs a different call signature, the abstraction is wrong.
7. **Every seam is inspectable.** Each artifact is JSON-serializable and logged at
   the seam with a timestamp — stage-level tracing (§7 of the architecture spec)
   falls out of the interfaces, not out of instrumentation added later.

## 1. The artifact family (the nouns)

| # | Artifact | Producer → Consumer | Transport | Mutability |
|---|---|---|---|---|
| A1 | **Intent** | User/agent → Intent Parser | REST | immutable |
| A2 | **Clarification** | Match → User → Match | REST (session) | append-only Q&A |
| A3 | **CapabilityFile** | each service dev → Knowledge Base | pull @ bootstrap | versioned file |
| A4 | **CTPQuery / CTPPointerSet** | Match → CTP Service → Match | REST | immutable response |
| A5 | **ExperimentSetSpec** (the waist) | Spec Generator → Planner/Scheduler/user | file/REST | immutable once compiled |
| A6 | **Deployment** | Planner → Scheduler/workers | DB record | state machine |
| A7 | **WorkItem** | Scheduler → worker (pulled) | queue/poll | claimed-once |
| A8 | **StatusEvent** (heartbeat) | worker → Scheduler | push (outbound) | stream |
| A9 | **ResultEnvelope** | worker → Telemetry | publish() | immutable |
| A10 | **NodeDescriptor / PoolSpec** | Connector → Planner | REST | refreshed |

Everything below the waist consumes A5–A10 only. Nothing below the waist ever sees
A1–A2 (natural language stops at the Match boundary).

## 2. Schema sketches

### A3 — CapabilityFile (NetGent example)

```yaml
schema_version: 1
service: netgent
service_version: 2.3.0
workflows:
  - id: zoom_client
    application: zoom
    role: client                # client | server | symmetric
    peer: zoom_broadcaster_av   # required peer workflow, if any
    engine: browser             # browser | shell
    params:
      - {name: duration, type: seconds, required: true}
      - {name: server,   type: node_ref, required: true}
      - {name: resolution, type: enum, values: [720p, 1080p], default: 720p}
    prerequisites:              # things Match must resolve or backflow
      - {name: meeting_code, kind: secret_or_param}
      - {name: meeting_password, kind: secret}
    node_requirements: [browser, audio]   # attribute filter for placement
```

NetReplica's file is the same shape with `knobs:` instead of `workflows:`
(`{name: capacity, type: rate, range: [100kbps, 10gbps]}`, AQMs, CCAs — including
`host_kernel` caveats the placement filter needs). CTP's file declares no data,
only its **query schema** and endpoint (rule 2: the DB is reached live, A4).

### A5 — ExperimentSetSpec (the waist artifact, full shape)

```yaml
schema_version: 1
experiment_set:
  id: es_2026-07-02_zoom_sweep      # content-addressed hash suffix
  intent_ref: intent_abc123          # provenance; null for API-direct submission
  secrets: [zoom_meeting_code]       # keys resolved from LOCAL secrets file at dispatch
  nodes:
    - {name: broadcaster, pipeline: [zoom_broadcaster_av],
       persistence: experiment_set, requirements: [browser, audio, public_reach]}
    - {name: pool, kind: fixed, count: 50, persistence: experiment,
       pipeline: [zoom_client]}
  mapping:                           # node → connector (T1: all local_docker)
    pool: local_docker
    broadcaster: local_docker        # or ssh:snl-server-5 (split pair, R2)
  experiments:                       # leaves; one entry per unique context triple
    - id: e_001
      static:  {capacity: 10mbps, latency: 10ms, aqm: codel, cca: cubic}
      application: {workflow: zoom_client, server: broadcaster, duration: 30s}
      dynamic: {ctp: [c303, c304], source: ctp_service}   # or source: local_dir
      iterations: 1
      telemetry: {pcap: true, qtrace: true, app_metrics: true}
      verify: {probe: true, tolerance: {capacity: 5%, latency: 2ms}}
```

Properties: fully concrete (no AI needed below this line), pointerized (CTP ids,
workflow ids), portable (only `mapping:` changes across T1/T2/T3), and hashable
(same spec ⇒ same experiment ⇒ dedupe against already-collected data).

### A6 — Deployment (per worker×experiment, netUnicorn's lesson)

```json
{"deployment_id": "d_0042", "experiment_id": "e_001", "node": "pool/worker-07",
 "state": "assigned|preparing|ready|running|reporting|done|failed",
 "prepare": {"ctp_batch": ["c303","c304"], "workflow": "zoom_client@sha", "skipped": false},
 "error": null, "timestamps": {"assigned": "...", "ready": "...", "done": "..."}}
```

### A7/A8 — WorkItem claim + StatusEvent

```
GET  /work?worker_id=w07&attrs=browser,audio   → WorkItem (deployment_id, spec leaf,
                                                  secrets injected) | 204 (nothing)
POST /status   {worker_id, deployment_id, state, stage, ts, partial_log_tail}
                 every 30s while active (heartbeat; missing 3 → scheduler reaps)
```

### A9 — ResultEnvelope (one publish interface, both profiles)

```json
{"deployment_id": "d_0042", "experiment_id": "e_001", "iteration": 1,
 "spec_hash": "…", "artifacts": [{"kind": "pcap", "key": "s3://…", "bytes": 123}],
 "metrics": {"app": {...}, "transport": {...}},
 "verification": {"probed": true, "capacity_measured": "9.7mbps", "within_tolerance": true},
 "context": {"static": {...}, "ctp": "c303", "workflow": "zoom_client@sha"}}
```

`publish(envelope)` is the entire telemetry-facing interface a worker knows.
Laptop profile: implementation = write-through to Telemetry REST + local buffer.
Scale profile: implementation = RabbitMQ producer. Same signature (rule 6).

## 3. The seams (the verbs)

| Seam | Contract (complete method set) | Notes |
|---|---|---|
| S1 User ⇄ UI | `POST /intent` → `{session_id}` · `GET /session/{id}` → status ∪ Clarifications · `POST /session/{id}/answers` · `POST /experiment-sets` (API-direct A5 submission) · `GET /experiment-sets/{id}/status` | The API-direct route is T1-critical: the LLM path is optional per §1 principle |
| S2 Parser → Match → Planner → SpecGen | in-process typed calls passing A1 → draft spec → A5; **not** HTTP | modules of one service; the artifact types are the interface |
| S3 KB ⇄ publishers | `GET capability file` (+ `ETag`/`If-None-Match` for refresh) | pull @ bootstrap + explicit refresh; never per-experiment |
| S4 Match ⇄ CTP | `POST /ctp/query {criteria}` → `{pointers[], available, requested}` | partial counts are valid answers, not errors |
| S5 Scheduler ⇄ workers | A7 claim + A8 status (pull; workers initiate everything) | replaces orchestrator→container push; NAT-proof by construction |
| S6 Orchestrator ⇄ connectors | `get_nodes() → PoolSpec/NodeDescriptors` · `deploy(pool_spec)` · `execute(worker, bootstrap_cfg)` · `stop(worker)` | netUnicorn's protocol verbatim; one connector = one plug-in |
| S7 Worker ⇄ CTP/NetGent | `GET` by pointer (CTP payload, workflow file), local cache, skip-if-cached | data plane; outside shaped namespaces |
| S8 Worker ⇄ Telemetry | `publish(ResultEnvelope)` | profile-swappable implementation |
| S9 Worker self-verification | probe after net-setup; results ride **inside** A9 | no new service; D6 minimal form |

## 4. Functional disaggregation: state ownership

| Module | Owns (authoritative state) | Must NOT know |
|---|---|---|
| UI | sessions, auth (later) | anything about workflows, CTPs, workers |
| Intent Parser | nothing (stateless transform A1→draft) | infrastructure, worker state |
| Knowledge Base | capability snapshots + versions | live worker inventory, results |
| Match | clarification sessions (A2) | how experiments execute |
| Planner | deployments (A6), pool assignment | natural language, credentials *values* |
| Scheduler | work queue, worker liveness, locks | what the metrics mean |
| Connector | node materialization for its infra | spec contents beyond bootstrap cfg |
| Worker | its own lifecycle + local caches | other workers, the experiment set, NL |
| CTP Service | profile corpus + query index | who runs experiments, why |
| NetGent repo | workflow definitions + versions | network conditions |
| Telemetry | results, artifacts, provenance | how to reach workers |
| Secrets file (local) | credential values | — (never leaves the user's machine; specs carry *keys*) |

Litmus test used throughout: **a module's interface may reference only artifacts it
consumes or produces in Table 1.** If a proposed feature makes, say, the scheduler
read CTP contents, the feature belongs elsewhere.

## 5. One experiment set, traced through every seam

1. `POST /intent` "20k Zoom points at 10 Mbps, 10/100 ms" → A1, session opens (S1).
2. Parser drafts; Match consults KB snapshot (A3s), queries CTP (S4, A4), finds
   `meeting_code` unresolved → A2 clarification back through the session (S1).
3. User answers; SpecGen emits A5 (immutable, hashed); session returns
   `experiment_set_id`. *Everything after this line is AI-free.*
4. Planner filters node requirements against NodeDescriptors (S6 `get_nodes`),
   creates A6 deployments incl. CTP prefetch batches; asks connector to `deploy`/
   `execute` any missing pool members or the broadcaster node (S6).
5. Broadcaster worker pulls its WorkItem first (node startup precedence), heartbeats
   (S5); pool workers claim experiment WorkItems, prefetch by pointer (S7),
   `prepare→ready→running`.
6. Each iteration ends with `publish(ResultEnvelope)` (S8) carrying verification
   (S9); worker claims next item without waiting on upload.
7. Scheduler marks deployments `done`; set completes when all leaves report or
   time out; `GET /experiment-sets/{id}/status` shows per-deployment states —
   failures are node-granular, never "the set is stuck."

## 6. Open interface questions

| # | Question |
|---|---|
| I1 | Clarification session shape: single round (all questions at once, netUnicorn-style fail-fast) vs. iterative rounds? Lean: single batched round per compile attempt. |
| I2 | WorkItem transport in the scale profile: same RabbitMQ instance as results, or plain HTTP polling against the scheduler everywhere? Lean: HTTP polling everywhere (S5 stays profile-invariant), broker for results only. |
| I3 | Where does the spec hash → already-collected-data dedupe check live: Planner (skip dispatch) or Telemetry (reject duplicate)? Lean: Planner asks Telemetry (`GET /results?spec_hash=`), keeping Telemetry passive. |
| I4 | Does `verify.tolerance` failure fail the iteration or annotate it? Lean: annotate + flag; the researcher decides — hard-fail is a paper-killer if tolerances are miscalibrated. |
