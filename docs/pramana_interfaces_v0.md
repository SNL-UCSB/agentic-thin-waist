# Pramana Interface & Abstraction Spec — v0

> **⚠️ HISTORICAL DOCUMENT — SUPERSEDED.** The current, authoritative
> specification is **`PRAMANA_DESIGN_SPEC.md`**. Decisions recorded here were
> revised during later reviews — in particular, all "rendezvous channel",
> broker, S3-importer, and mesh/tunnel transport designs were **rejected**:
> the shipped model is the current implementation (workers made reachable via
> operator-scoped security groups; the Core only dials out; results pulled by
> the Core). Read this file as design history and evidence, not as the spec.



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
3. **Outbound-initiation at trust/NAT boundaries (scoped, A3).** Whoever is
   unreachable never needs to be dialed into. Concretely per binding: direct
   binding (T1/T2) = the Core dials reachable workers (workers are HTTP servers);
   broker binding (T3) = a sidecar pulls from the rendezvous. The KB always pulls
   capabilities. "Workers pull work" holds only in the T3 binding.
4. **Additive evolution.** Every artifact carries `schema_version`. Consumers ignore
   unknown fields; producers never repurpose a field. Removing a field is a major
   version and requires a capability-file announcement.
5. **One source of truth for schemas.** All artifact schemas live in
   `shared/models/` as JSON Schema + generated dataclasses. Services validate at
   their boundary and reject, never coerce. (This fills the currently-empty
   `shared/models/__init__.py` with the thing it was always meant to hold.)
6. **Interfaces are profile-invariant; transports are bindings.** (clarified 07-02)
   The laptop and scale profiles swap *transport bindings* (localhost HTTP vs. a
   remote broker), never *call signatures*. Worker code says `claim()`/`publish()`
   everywhere; which channel carries them is configuration. Invariance applies at
   the interface level, not the wire level.
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
T1 binding: write-through to Telemetry REST + local buffer. T2 binding:
**object-store rendezvous** — the worker writes artifacts + envelopes outbound to
S3; a laptop-side importer polls the bucket and ingests into Telemetry (both sides
outbound-only; replaces today's `telemetry_capture_pull`, which double-hops every
pcap through the laptop's uplink mid-experiment). T3 binding: broker, if ever
needed. Same signature at every tier (rule 6).

## 2.5 The Capability Protocol (S3, fully specified — 2026-07-02)

The contract that lets NetGent, NetReplica, and CTP evolve independently.
Four parts:

1. **Describable-CLI convention.** Every (application, role) CLI answers
   `--describe`, emitting machine-readable self-description: flags (name/flag/
   type/required/default), prerequisites (with `kind: secret | secret_or_param`),
   `node_requirements`, version. This is the *entire* integration burden on an
   upstream project. (NetGent's `manifest.json` + `workflow.json.parameters`
   already carry these facts; the synthesizer reads them directly today.)
2. **Capability-document synthesizer** — a Pramana-provided tool run **in the
   publisher's CI**, not in Pramana: enumerate CLIs/manifests → read
   `--describe` → assemble capability file → schema-of-schemas validation →
   human review + **signature** (H3: a model may draft, only a human signs).
   Non-adopting publishers: Pramana runs the synthesizer against their public
   surface at refresh time and a Pramana-side maintainer signs; the trust label
   records the signer.
3. **Capability file kinds.** `kind: static` (NetGent workflow entries with
   per-entry `workflow_sha`; NetReplica knob ranges + realization modes + the
   ≤8-regime ceiling) vs. `kind: live` (CTP: **query schema + endpoint only**,
   never data — the KB holds a pointer to the database, not the database).
4. **Well-known location + registry.** Each publisher serves
   `capabilities.yaml` + detached signature at a fixed path (repo raw URL or
   `GET /capabilities`). The KB's bootstrap **registry** is
   `{name, url, pubkey, parser_version}` per publisher; adding a publisher is
   one registry line + (at most) a parser — never a Core code change.

### KB lifecycle: three phases

- **BOOTSTRAP** (once): config-validate → image-ensure → pool deploy → KB
  ingest (fetch → verify signature → schema-check → parse → **hash-addressed
  snapshot**). Offline T1: a capability snapshot ships inside the images;
  ingest degrades to use-bundled-refresh-later.
- **REFRESH** (explicit `pramana refresh` or timer; **never** per-experiment):
  conditional GET (ETag) → re-verify → **diff report to the user** ("netgent
  2.3→2.4: +zoom_server; duration now optional") → atomic snapshot swap; old
  snapshots retained (in-flight sets reference them by hash).
- **RUNTIME**: Match/Planner/SpecGen read the snapshot only. The sole runtime
  contacts with publishers: Match → CTP pointer queries (declared in CTP's
  capability file), and workers fetching CTP payloads by pointer / workflows by
  pinned sha over the data plane (U24: sha mismatch = refusal).

### The three-channel model (what "starting Pramana pulls")

| Channel | Content | Cadence |
|---|---|---|
| 1. Capability documents | small signed YAML → KB | bootstrap + explicit refresh |
| 2. Code/engines | NetReplica logic **is** the substrate image; NetGent engine is the runner sidecar — baked at image build | image release → image-ensure at bootstrap |
| 3. Artifacts | individual workflow JSONs + CTP payloads | runtime, lazily, by pinned sha/pointer only |

**No codebase is ever cloned at startup.** (Rejects the pull-latest-submodule
pattern; per-request `index.json` fetches are the named anti-pattern.)

**Independent-evolution invariant:** *a publisher may change anything at any
time; Pramana's behavior changes only at a refresh or image boundary, visibly
(diff report / image tag), and never affects an in-flight experiment set
(hash pinning).*

## 3. The seams (the verbs)

| Seam | Contract (complete method set) | Notes |
|---|---|---|
| S1 User ⇄ UI | `POST /intent` → `{session_id}` · `GET /session/{id}` → status ∪ Clarifications · `POST /session/{id}/answers` · `POST /experiment-sets` (API-direct A5 submission) · `GET /experiment-sets/{id}/status` | The API-direct route is T1-critical: the LLM path is optional per §1 principle |
| S2 Parser → Match → Planner → SpecGen | in-process typed calls passing A1 → draft spec → A5; **not** HTTP | modules of one service; the artifact types are the interface |
| S3 KB ⇄ publishers | `GET capability file` (+ `ETag`/`If-None-Match` for refresh) | pull @ bootstrap + explicit refresh; never per-experiment |
| S4 Match ⇄ CTP | `POST /ctp/query {criteria}` → `{pointers[], available, requested}` | partial counts are valid answers, not errors |
| S5 Scheduler ⇄ workers | A7/A8 over a **channel** with per-tier bindings. **Direct binding (default, implemented):** scheduler dials reachable workers over HTTP — localhost containers at T1; public-IP EC2 with laptop-scoped security group at T2 (the current `connectivity.py` model: laptop is a pure outbound client, workers are servers). **Broker rendezvous binding (T3 only):** when workers sit behind NAT (residential edge), a broker ships with the pool and a *sidecar poller* on each node claims work and replays it into the worker's unchanged HTTP API. | Constraint: the laptop orchestrator is never reachable (no netUnicorn-style public core). The implemented insight: at T2, *worker* reachability is cheap (public IP + SG), so direct beats rendezvous there; the rendezvous is reserved for tiers where nothing is reachable. |
| S6 Core ⇄ connectors | `get_nodes() → PoolSpec/NodeDescriptors` · `deploy(pool_spec)` · `execute(worker, bootstrap_cfg)` · `stop(worker)` | netUnicorn's protocol verbatim; one connector = one plug-in |
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

All four resolved 2026-07-02 (Arpit):

| # | Resolution |
|---|---|
| I1 | **Iterative Q&A** for clarification — conversational, one question at a time, recompile as answers land. Riders: a round cap with batch-the-rest fallback (LLM-cost guard, per the Zoom-sweep API-credit lesson) and a "use defaults for everything else" escape hatch. Match is stateful per session. |
| I2 | **Channel abstraction with three bindings** (revised again 07-02 after auditing `connectivity.py`/`aws_provisioner.py` — the current implementation already solves T2 reachability by *inverting* it: workers get public IPs + a security group scoped to the laptop's IP; the laptop is a pure outbound HTTP client). Bindings: **(a) direct** — scheduler dials reachable workers (localhost at T1, public-IP EC2 at T2; implemented today, worker stays an HTTP server); **(b) object-store rendezvous for results at T2** — workers write outbound to S3, laptop reads outbound from S3 (replaces `telemetry_capture_pull` double-hop through the laptop uplink; uses existing `shared/s3/`); **(c) broker rendezvous, T3 only** — for workers behind NAT (residential edge), implemented as a **sidecar poller** that claims from the broker and replays into the co-located worker's existing HTTP API, so worker code never changes. RabbitMQ's scope shrinks to binding (c) — possibly never needed. Implementation fixes required: the SG `0.0.0.0/0` fallback must hard-fail (privileged worker on the open internet), and the provisioner needs `refresh-ingress` for laptop IP changes. |
| I3 | **User-level dedupe tool** — no automatic skipping; a CLI diffs a spec against telemetry (`spec ∩ existing = residual spec`) so intentional repeats are always possible. Rider: the planner may *warn* on overlap (never auto-skip); the tool must be prominent, or the 07-01 "don't repeat data" requirement becomes empty discipline. |
| I4 | **Annotate, never discard** — every ResultEnvelope carries measured-vs-requested + `within_tolerance`; collection always completes; filtering is analysis-time. Riders: the flag must be loud in exports, and the scheduler alarms on per-worker tolerance-failure *rates* (a systematically broken worker must not annotate garbage all night). |

## 7. Adversarial-review resolutions and glossary (2026-07-02)

Twenty-five underspecification findings (U1–U25) and fifteen red-team defenses
(H1–H15) were resolved normatively in
`pramana_adversarial_review_2026-07-02.md`; the resolutions in that register are
**binding on the schemas in this document** and land in `shared/models/` with the
first implementation pass. Highest-order ones: advisory-with-affinity assignment
(U1), reap⇒requeue with `attempt` (U2), secrets transit rules (U3), CLI flag
mapping in A3 (U4), flat A5 with client-side `sweeps:` (U5), one CTP per leaf
(U6), canonical content-hash ids (U7), idempotent telemetry upsert (U8),
`service_ready` stage (U10), units grammar (U11), cancel endpoint (U15),
two-axis completion (U16), workflow@sha + capability-hash pinning (U24),
scheduler as sole A6 writer (U25), and the operational defaults table (U21).

**Glossary (normative, one term per concept — review A19):**
**workflow** — one NetGent artifact (never "pipeline"). **pipeline** — the ordered
list of workflows a node can run. **regime** — static envelope ⊗ dynamic pressure
(conditions only; the application context is *not* part of the regime).
**context** (in results) — the full label set: static + dynamic + application.
**iterations** — the A5 field name (never `num_iterations`). **Core** — the
intelligent module set (never "orchestrator" in new text).
