# Pramana Architectural Spec — v0.1 (Convergence Draft)

**UCSB SNL · 2026-07-01, refined 07-02 · Status: CONVERGED DRAFT — 7 of 9 forks
resolved (D1–D7) + 4 refinements from the netUnicorn comparison (R1–R4, §9); 2
questions remain open with accepted leans. Ready as agenda for the team spec
meeting.**

Synthesized from: the 07-01 architecture meeting (Arpit, Jaber, Haarika, Manni;
transcript in #pramana-v2), the March–April taskforce decisions
(#agentic-thin-waist-taskforce), `docs/vision.md`, `docs/thin_waist_one_pager.md`,
`docs/verification_gap.md`, the HotNets draft (`Pramana_Hotnets`), the SIGCSE draft
(`SIGSCE_Pramana`), and an implementation audit of this repo.

Purpose: the "very complete spec of what the software needs to do" that the 07-01
meeting closed on. **[OPEN]** marks unresolved forks, collected in §9.
**[RESOLVED 07-01]** marks decisions made during convergence review of this draft.

---

## 0. Decision lineage (how we got here)

| Date | Decision | Status |
|---|---|---|
| Mar 30 | Only two persistent services (orchestrator + CTP); **ephemeral per-iteration data-gen Dockers**; push-based status; telemetry co-located with orchestrator. | Ephemeral part **reversed 07-01** |
| Apr 1 | Seven design principles (§1); local-first beats full-cloud; NetGent demoted to dumb executor. | Standing |
| Apr 2 | Hub-and-spoke: every service talks only to the orchestrator; services location-agnostic; NetGent = "a registry of capabilities… a catalog of CLI tools." | Standing (data-plane exception §6.3) |
| Apr 7 | From Osprey analysis: adopt typed events, retriable errors, connector abstraction; **never** LLM-generated code in the execution path. | Standing |
| Jul 1 | Persistent worker pool ("a bit of a no-brainer — these dockers don't need to be ephemeral" — Arpit); orchestrator decomposition (§3); taxonomy (§2); capability publishing (§4); telemetry decoupling (§6.2). | This spec |

## 1. Design principles

### 1.0 Usability is the ordering principle (added 07-02)

netUnicorn's cautionary tale is a *usability* tale: hard to run on a laptop, bloated
as a service, and unsustainable manual authorship of tasks/pipelines. Pramana is
what netUnicorn envisioned, with the authorship automated — and every architectural
decision is ordered by three usability tiers:

- **T1 — Laptop (primary goal).** On a single laptop: `git clone` →
  `docker compose up` → a simple data-collection request → data, in minutes. No
  cloud account, no API key required (the API-optional path is a T1 requirement,
  not a convenience). The **laptop profile** runs the minimal service set; both
  experiment endpoints can live inside one Docker via NetReplica's single-container
  namespace compilation (§5.2).
- **T2 — Cloud scale-up.** The *same spec*, scaled: prebuilt images + a connectivity
  backend flag move the worker pool to cloud resources. Nothing about the intent or
  the spec changes; only the mapping does.
- **T3 — Infrastructure interfacing.** Easily reach different infrastructures
  (testbeds, K8s, other clouds) for extensive use cases — via a netUnicorn-style
  connector contract (§5.4), which is precisely the piece netUnicorn got right.

A feature that improves T2/T3 but adds weight to T1 defaults to the scale profile.

### 1.1 The constitution

The seven taskforce principles (Apr 1, verbatim) remain the constitution:

1. Mininet bar for onboarding
2. Minimal long-term maintenance dependencies
3. All intelligence in orchestrator, everything else is dumb
4. Separation of concerns (dev workflows ≠ production service)
5. No data through orchestrator
6. Portability via configuration, not code changes
7. User simplicity > implementation simplicity

Refinements re-affirmed or added 07-01:

- **LLM only at the intent boundary.** The intent parser may use an LLM. Planner,
  scheduler, and all execution paths are deterministic ("we can use LLM to generate
  the code, but I want deterministic code at any case" — Arpit). Corollary of the
  Apr 7 rule: never LLM-generated code in the execution path.
- **API-optional operation.** The system must be drivable without any LLM/API call: a
  user (or a for-loop) can submit fully-specified experiment JSONs directly. The LLM
  path is a convenience layer, never a dependency of execution (Jaber's opening item).
- **No spec the orchestrator doesn't understand.** If required information is missing
  (credentials, meeting codes, endpoints), the orchestrator must ask the user
  (backflow) rather than emit a spec that will fail downstream (Arpit).
- **Disaggregation with chosen granularity.** Per-iteration teardown is "an extreme
  point in the design space, we should not go [to]" (Arpit). Persistence level is a
  parameter, not a fixed property.

### 1.2 Minimum viable intelligence (added 07-02)

The intelligence required from the LLM agent must be **as minimal as possible**, with
enough harness that a simple — eventually self-hosted — model delivers effectively.
No architectural function may *depend* on frontier-model capability. Consequences,
several already decided:

- The abstraction ladder (per-application CLIs → capability documents → knowledge
  base → match → spec template) exists precisely so intent parsing reduces to
  **constrained form-filling against a published schema**, not open-ended reasoning.
- Backflow (ask the user) replaces cleverness (guess the user): a small model that
  asks one question at a time (I1, iterative Q&A) beats a large model that infers.
- Everything below the waist is AI-free (§2); the planner is deterministic rules;
  workflow generation uses AI only at development time, never at run time.
- API costs and API dependence are usability failures (the Zoom-sweep credit
  exhaustion): the LLM path must degrade gracefully to direct spec submission.

## 2. Taxonomy (agreed 07-01)

| Term | Definition |
|---|---|
| **Intent** | User's natural-language or structured request. May expand into an experiment set. |
| **Experiment set** | The set of experiments produced by one intent. Tree-structured; internal nodes are parameter sweeps; leaves are experiments. |
| **Experiment** | A leaf: one unique combination of *static context* (NetReplica knobs: capacity, latency, buffer, AQM, CC) + *application context* (one NetGent workflow + args) + *dynamic context* (one CTP). Same spec ⇒ same experiment. Different application ⇒ different experiment. |
| **Iteration** | A repeated run of the same experiment (`num_iterations` in the experiment JSON). No teardown between iterations. |
| **Spec** | The compiled, fully-concrete artifact: a list of experiment JSONs plus node declarations (§5.2) — "that filled-out form doesn't need any AI assistance… whatsoever" (Manni). |

## 3. Intent plane — module decomposition

User-facing flow (order is normative):

```
User ──> UI (REST: /intent, /experiment-status, ...)   ── UI is NOT the orchestrator
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
   │       node/worker assignment, prefetch plan)         │
   │ 5. Spec Generator  (emits experiment-set spec from   │
   │       the spec template)                             │
   │ 6. Scheduler       (dispatch experiments to worker   │
   │       pool; simple queue + semaphore)                │
   └───────────────────────────────────────────────────────┘
```

- The current implementation overloads "orchestrator" to mean UI + controller +
  everything ("our orchestrator is essentially an orchestrator and controller in the
  same" — Manni). These are separate modules even if co-deployed.
- **Match** produces (a) a boolean per requirement, (b) concrete values filled into
  the spec template, (c) a query list for the user (backflow) when required parameters
  are unknowable (passwords, meeting codes, endpoints).
- **[RESOLVED 07-01] Secrets live in a local, gitignored secrets file** on the user's
  machine, referenced from the spec by key (e.g. `$secrets.netflix_password`).
  Backflow asks once, writes locally; specs stay shareable; nothing credential-shaped
  is ever persisted server-side or in telemetry. NetGent continues masking secret
  params in logs.
- **Planner is rule-based v1**: iterations of an experiment colocate sequentially on
  one worker; experiments sharing sticky context (CTP batch, static config) group for
  prefetch. No dynamic/LLM planning.
- **Scheduler v1 = FIFO over the worker pool with a semaphore.** Whoever finishes takes
  the next experiment. Policy beyond v1: **[OPEN — §9.Q1]**.
- Vocabulary note: the team's operative framing is **hub-and-spoke + disaggregation**;
  the Intent/Representation/Execution "planes" wording in `CLAUDE.md` appears nowhere
  in the papers or Slack and should be retired in favor of the paper vocabulary
  (*generative empirical backend*; *empirical thin waist*; the **intent specification**
  is the waist).

## 4. Knowledge base & capability publishing

Each downstream service publishes a **capability file**; the knowledge base ingests all
of them at bootstrap and refreshes by **pull** (workers behind NAT forbid broadcast;
a persistent connection may later enable push, but pull is the v1 contract).

| Service | Capability representation | Refresh model |
|---|---|---|
| **NetGent** | **The CLI is the per-application contract (refined 07-02).** Each (application, role) pair exposes a concrete CLI — e.g. `youtube-client -v <url> -d 30s`; roles are client always, server only where meaningful (Zoom/Puffer/NDT yes; YouTube no). Applications own their CLIs independently — custom flags per usage pattern. The **capability-document synthesizer** is the named module that looks *across* all CLIs, understands their configurability (flags, types, mandatory/optional/defaults, prerequisites like accounts/meeting codes), and emits the capability file the KB ingests. Hand-authored today; the synthesizer automates it later. | Public repo/service; pull at bootstrap, re-pull on demand. Workers pull workflow files directly by URL derived from the index. |
| **NetReplica** (static knobs) | Static file: supported knobs and value ranges (capacity, latency, buffer, AQM, CC). Ships with the substrate; pulled from master at bootstrap. Low cadence. | One-time at bootstrap. |
| **CTP Service** | *Not* a static file — a **pointer to a queryable database**. Capability = the query schema (throughput range, active users, burstiness, direction, cluster, transformed-or-not). Match queries it live; responses are pointers, possibly partial ("3,000 of the 10,000 you asked for" is a valid answer, not an error). | Live query at match time. |
| **Telemetry** | Storage/query API; capacity constraints (disk, connection pool). | Static config. |

Rules:

- Capability sync is **never** in the per-experiment runtime path ("you should not be
  bloating up the runtime workflow with things that don't need actions" — Arpit).
  Bootstrap + explicit refresh only. The current per-request `index.json` fetch is the
  named anti-pattern.
- Capability files are hand-authored by service developers for now; automated
  synthesis is future work.
- The knowledge base has a per-service **parser**; adding a service means adding a
  parser + capability file, not modifying match/planner.

## 5. Execution plane

### 5.1 Persistent worker pool (the headline change)

- Substrate workers are **persistent Docker containers created at bootstrap**, not
  ephemeral per-experiment containers. Pool size is a bootstrap parameter with a
  resource-derived default (laptop ≈ 10, server up to ~1000); user-configurable,
  never exceeded silently.
- Docker images are **prebuilt and pulled from a registry** (Docker Hub `snlhub/*` /
  ECR). Build happens at most once at bootstrap if no image is available; never in the
  runtime path.
- Measured motivation: 150–200 s non-experiment overhead per 250–300 s container
  lifetime (Zoom: 30 s useful experiment; Docker daemon overload at 50–100 concurrent
  containers). Expected ~3× speedup.
- **[RESOLVED 07-01] Ephemeral mode is deleted, not flagged.** Isolation-critical
  studies get *fresh-worker-per-experiment* as a **pool recycling policy** (pool-of-1
  semantics): one dispatch path, persistence level expressed in the spec, no second
  code path.
- Single-user model for v1. Cross-experiment interference on a shared pool is
  acknowledged and not solved in v1.

### 5.2 Node abstraction **[RESOLVED 07-01: adopt netUnicorn nodes now]**

The spec template adopts the **netUnicorn node/pipeline abstraction** immediately,
rather than a minimal client/server annotation:

- A **node** is any execution endpoint: a pool worker, a long-running service endpoint
  (Zoom broadcaster, Puffer server, iperf server), or a remote host.
- Every node carries a **pipeline** (an ordered list of NetGent workflows + parameters)
  and a **persistence level** (`iteration` | `experiment` | `experiment_set`).
- The spec declares nodes and a **mapping** of pipelines → nodes → substrate
  (connectivity backend). Client workflows reference service nodes by name; the
  orchestrator resolves name → endpoint at dispatch.
- This subsumes the client/server question (client+server = two nodes; multi-party
  conferencing = N nodes; peer-to-peer = symmetric nodes: "the one who is listening
  and waiting would be considered the server" — Jaber). A DAG-structured workflow
  language remains rejected as overkill; ordering needs are covered by pipeline order
  within a node plus node startup precedence (service nodes start before pool
  dispatch).
- Sketch:

```yaml
experiment_set:
  nodes:
    - name: broadcaster
      pipeline: [zoom_broadcaster_av]
      persistence: experiment_set
      params: {meeting_code: $ASK_USER, video: local_loop.mp4}
    - name: pool
      count: 50
      persistence: experiment        # recycle per experiment; pool-of-1 => iteration
      pipeline: [zoom_client]        # + ctp_replay applied by substrate
  mapping:
    pool: local_docker
    broadcaster: snl-server-5
  experiments:                        # leaves; each fills the spec template
    - static: {capacity: 10mbps, latency: 10ms, aqm: codel}
      application: {workflow: zoom_client, server: broadcaster, duration: 30s}
      ctp: [c303, c304, ...]          # pointer list, batch-prefetched
      iterations: 1
```

- Rationale for going straight to nodes: it is the abstraction netUnicorn already
  validated ("we already had that implemented in NetUnicorn. All we have to think
  about is how do we integrate" — Arpit), it kills the 1M-second-experiment
  broadcaster hack, and it prevents a second spec-schema migration two months from
  now.
- Server/broadcaster workflows live in the official NetGent repo like any workflow
  ("anything you do on a host from a workflow perspective is NetGent"). Haarika's
  broadcaster A/V workflow gets upstreamed.

**Pipeline = NetGent workflow (refined 07-02).** In netUnicorn, the pipeline-per-node
was hand-authored: manually specified tasks, manually composed pipelines — the
unsustainable part. In Pramana, the pipeline for a node *is* the NetGent workflow,
and the wrapper actions around the application (pre/post: start capture, launch app,
collect data, emit telemetry) are **part of NetGent itself**, not a second
abstraction. Workflow generation is AI-assisted at development time (NetGent's
generative mode as an authoring tool), never in the execution path. This is the
lineage claim in one line: *Pramana = netUnicorn's node/pipeline vision, with the
authorship of the pipeline automated by NetGent and the authorship of the intent
automated by the LLM.*

**Two endpoint configurations (refined 07-02).** Every experiment has two endpoints
around the bottleneck; the spec supports both placements:

1. **In-Docker pair (T1 default).** NetReplica's full setup is compiled into a
   *single Docker instance* using network namespaces — both endpoints and the
   reconfigurable bottleneck link live inside one container. This is what makes the
   laptop tier real: one container = one complete experiment environment.
2. **Split pair.** The client-side worker holds the reconfigurable bottleneck link
   and connects to an **external endpoint node**: a separate container on the same
   machine, or a remote container/host (T2/T3). The external endpoint is a named
   service node in the spec (§5.2 sketch); the client workflow references it by
   name.

The planner chooses placement per experiment set; the spec's `mapping:` block makes
it explicit and overridable.

### 5.3 Per-experiment execution sequence (worker-local)

1. Receive experiment JSON (pointerized: CTP pointers, workflow URL, static knobs).
2. **Prefetch**: download CTP batch outside the shaped namespace (unshaped path);
   cache locally. Plannable ahead of dispatch because the planner pre-assigns
   experiments to workers.
3. Network setup: apply static knobs inside the namespaces (~1 s; cheap).
4. Pull NetGent workflow by URL (cheap, cacheable).
5. Run iterations 1..N with no teardown between them; CTP replay per iteration.
6. Buffer telemetry locally (provisioned disk); publish asynchronously (§6.2).
7. Reset network config between experiments; container persists per its persistence
   level.

### 5.4 Connector contract for T2/T3 (adopted from netUnicorn, 07-02)

The one piece of netUnicorn's architecture that directly serves usability tiers 2–3
is its connector layer, and we adopt its shape rather than reinvent it:

- A minimal protocol per infrastructure: `get_nodes / deploy / execute / stop`
  (netUnicorn's `NetunicornConnectorProtocol`; each of its seven connectors is
  ~140–240 LLoC). Pramana's `ConnectivityManager` backends (`local_docker`, `aws`,
  the `NotImplementedError` `gcp`/`remote`) are refactored to this contract so a new
  infrastructure is a small plug-in, not a code change in orchestration.
- Connectors are configuration-selected (the spec's `mapping:` names them), keeping
  principle 6 (portability via configuration).
- The laptop profile ships with exactly one connector (`local_docker`); everything
  else is opt-in. T1 never pays for T3's generality.
- **Channel bindings (revised 07-02 after auditing the current implementation).**
  The implemented model already solves T2 reachability by inversion: workers are
  made reachable (EC2 public IP + security group scoped to the laptop's IP,
  `aws_provisioner.py`), and the laptop orchestrator is a pure *outbound* HTTP
  client. This is kept as the **direct binding** — it is proven, and it lets the
  substrate worker remain an HTTP server through the persistent-pool change.
  Results at T2 move to an **object-store rendezvous** (worker writes outbound to
  S3; laptop importer reads outbound), retiring the pcap double-hop through the
  laptop uplink. A **broker rendezvous** is reserved for T3 (workers behind NAT —
  residential edge), implemented as a sidecar poller replaying into the worker's
  unchanged HTTP API. RabbitMQ's scope therefore shrinks to T3-only, possibly
  never. Required fixes in the current code: hard-fail the SG `0.0.0.0/0` fallback
  (privileged worker exposed to the internet) and add `refresh-ingress` for laptop
  IP changes. Full contract: `docs/pramana_interfaces_v0.md` S5/S8/I2.

## 6. Representation plane

### 6.1 CTP service — two-step contract

- **Step 1 (match):** query by criteria → pointers + availability count (partial
  counts are valid responses).
- **Step 2 (fetch):** worker downloads CTP payloads directly by pointer.
- A **local CTP source** is an officially supported step-1 bypass (pointer to a
  local/user-provided corpus) — promoted from Haarika's Zoom-sweep hack.
- Batch semantics: the experiment set carries the full CTP pointer list; workers
  download in batches (e.g., 100 at a time), never one-per-iteration.

### 6.2 Telemetry service **[RESOLVED 07-01: RabbitMQ · refined 07-02: scale profile only]**

- Non-ephemeral, user-accessible; never torn down as part of experiment lifecycle.
- **Decoupled upload via RabbitMQ — in the scale profile**: workers publish
  result-ready events + artifacts to a queue; a horizontally-scalable uploader
  consumes and persists to telemetry (Postgres + S3/MinIO). Execution never blocks
  on upload; sync point is end-of-experiment-set, not end-of-experiment. Durability
  across worker death is the reason a broker won over buffer-and-retry at scale.
- **Laptop profile (R3):** no broker. Workers write through the *same publish
  interface* to a local buffer + direct-upload path (everything is on one machine;
  broker durability buys nothing there). The interface is identical so specs and
  worker code don't change between profiles — only the compose profile does. This
  amends D3 in scope, not in substance, per the §1.0 usability ordering.
- Worker-side results are deleted only after confirmed upload.
- Provisioning is spec-relevant: Postgres connection pool ~10–20× concurrent
  experiment count; disk sized for the experiment set; experiments fail fast if
  storage is insufficient (no silent stall — the observed telemetry-full hang is a
  bug class this eliminates).

### 6.3 Known deviation (data plane)

Today pcaps flow substrate→orchestrator→telemetry (NAT-driven), violating principle 5.
Target: substrate publishes directly to the RabbitMQ/telemetry path; the orchestrator
only ever carries pointers.

## 7. Observability & verification

- **Stage-level tracing is mandatory**: docker-up, host-setup, CTP-fetch, net-setup,
  workflow-pull, run, telemetry-publish, teardown — each timestamped by the component
  doing the work, so waterfall diagrams fall out of logs. (Today's ±10 s pre-up/post-
  down polling is not acceptable for the optimization loop.)
- Success metric: **non-experiment overhead ≪ experiment duration**.
- **Spec→Substrate verification** (per `docs/verification_gap.md`):
  **[RESOLVED 07-01: in summer scope, minimal form.]** Systematize what `/shape`
  already half-does: after network setup, actively probe capacity/latency/queue,
  record `verified` + measured-vs-requested values into telemetry with **every**
  experiment. Every dataset then ships with realized-regime ground truth — the
  cheapest credibility primitive available for HotNets/NSDI. The full verification
  layer (per-stage checks, tolerance policies, failure semantics) stays post-HotNets.
- **Intent→Spec verification**: the match/backflow mechanism (§3) is the v1 answer —
  it directly addresses the classroom-reported intent/spec mismatch. Deeper
  verification is a named open problem (do not overclaim in papers).

## 8. Commitments, owners, deadlines (07-01)

| Track | Owner | Deadline |
|---|---|---|
| Zoom data: 20k points (10 Mbps × {10 ms, 100 ms}; capacity sweep dropped; ~10k done), ~3 servers in parallel, on the current suboptimal system | Haarika | **Mon Jul 6** (hard: mid-week) |
| Persistent worker pool patchwork, on a branch, no holistic rewrite on the critical path | Manni | with/just after Zoom data |
| Orchestrator code cleanup (dead code, comments) after eval write-up | Haarika | ~Jul 2–3 |
| Puffer: India team collects (~8k/8h); sanity-check their upstream bandwidth; embeddings come back, raw data stays | Jaber (liaison: Haarika) | before HotNets analysis |
| SIGCSE paper: submit current draft on EasyChair, pull latest from GitHub before compiling | Jaber | **Jul 3** |
| Undergrad track (off critical path): more applications, CTP service maturation, telemetry features (queue occupancy, QoE), analysis tooling | Jaber coordinates | summer |
| This spec: converge, then "identify in the spec who needs to do what" | all | next architecture meeting |

**[RESOLVED 07-01] Summer scope = all four tracks**, sequenced so the pool patchwork
never blocks data collection:

1. **Persistent worker pool** (patchwork, branch) — Manni.
2. **Capability files + knowledge base** (author NetGent/NetReplica capability files;
   bootstrap ingest replaces runtime index.json queries).
3. **Match + backflow** (split the experiment checker; missing-info queries to the
   user instead of "specification not provided" failures).
4. **Telemetry decoupling via RabbitMQ** (§6.2).

**[RESOLVED 07-01]** Owners for tracks 2–4 are assigned at the next team spec meeting
— first agenda item, with this document as the agenda. (Capability-file authoring
naturally splits per service owner.)

## 9. Decision register

Resolved during convergence review (2026-07-01, Arpit):

| # | Fork | Decision |
|---|---|---|
| D1 | Persistent-node declaration in the spec template | **Adopt netUnicorn node/pipeline abstraction now** (§5.2) — not a minimal `services:` annotation, not the duration hack. |
| D2 | Summer decomposition scope | **All four tracks** (§8): worker pool, capability files + KB, match + backflow, telemetry decoupling. |
| D3 | Telemetry transport | **RabbitMQ** (§6.2) — durability across worker death won over buffer-and-retry. |
| D4 | Ephemeral mode | **Delete; pool-of-1 recycling policy** covers isolation (§5.1). One dispatch path. |
| D5 | Secrets | **Local gitignored secrets file**, spec references by key (§3). |
| D6 | Spec→Substrate verification | **In summer scope, minimal form** (§7). |
| D7 | Track 2–4 ownership | **Assign at next meeting**; this doc is the agenda. |

Refinements from the netUnicorn comparison review (2026-07-02, Arpit —
`docs/pramana_vs_netunicorn.md`):

| # | Refinement | Content |
|---|---|---|
| R1 | Usability is the ordering principle | Three tiers: T1 laptop (primary), T2 cloud scale-up, T3 infra interfacing (§1.0). netUnicorn's cautionary tale = usability, not maintenance. Deployment **profiles** bound T1 weight. |
| R2 | Two endpoint configurations in the spec | In-Docker pair (NetReplica single-container namespaces — T1 default) vs. split pair (client-side bottleneck + external endpoint node, local or remote) (§5.2). Pipeline-per-node = NetGent workflow incl. pre/post actions; authorship automated, not manual. |
| R3 | D3 scoped to the scale profile | RabbitMQ only in the scale profile; laptop profile uses local buffer + direct upload behind the same publish interface (§6.2). |
| R4 | Adopt netUnicorn's connector contract for T2/T3 | `get_nodes/deploy/execute/stop` plug-ins; laptop ships `local_docker` only; evaluate pull-based executor semantics during the pool patchwork (§5.4). |
| R5 | Minimum viable intelligence (§1.2) | LLM burden shrunk to schema-constrained form-filling; harness (CLIs → capability docs → KB → match → template) carries the complexity; target: a simple self-hosted model suffices. |
| R6 | CLI is the per-application contract (§4) | Each (application, role) has a concrete CLI; the **capability-document synthesizer** module bridges independent CLIs to the knowledge base. Server role only where meaningful (Zoom/Puffer/NDT, not YouTube). |

Remaining open, with accepted leans (revisit only with evidence):

| # | Question | Accepted lean |
|---|---|---|
| Q1 | Scheduler policy beyond v1 FIFO (per-set priority, fair-share)? | FIFO + semaphore suffices for single-user v1. |
| Q2 | Fan-out sizing (rooms/server instances per experiment set): user or planner? | Push to user via UI for v1 (Zoom caps 2 rooms/account anyway); the node abstraction makes the count an explicit spec field. |

## 10. Delta vs. current implementation

Audit of this repo (2026-07-01). Legend: ✅ done · 🟡 partial · ❌ missing.

| Spec element (§) | Current state | Δ |
|---|---|---|
| Intent parser (§3.1) | LangGraph agent in `services/orchestration` (`parse_intent → generate_experiments → execute_experiments → respond`); 21 test files; the most mature intent-plane module. | ✅ |
| UI ≠ orchestrator (§3) | One service does UI+controller+everything; `orch_cli.py` is the only separate surface. `services/experiment-api` (:8000) — the "smart controller" of CLAUDE.md — is a 65-line in-memory stub whose role was absorbed by orchestration (:8005). | 🟡 |
| Knowledge base + capability publishing (§4) | ❌ as designed. Workflow discovery queries `netgent-workflow/index.json` **at runtime per request** (the named anti-pattern); no capability files, no bootstrap ingest, no per-service parsers. NetReplica knobs hardcoded in prompt/knowledge files. | ❌ |
| Match + backflow (§3, §7) | Monolithic "experiment checker"; on missing info it **fails** ("specification not provided") instead of querying the user. Classroom-reported intent/spec mismatch; no verification loop. | 🟡 |
| Planner (§3) | Does not exist. No grouping, no prefetch planning, no pre-assignment. | ❌ |
| Spec generator (§2, §3) | `experiment_generator` emits experiment JSONs; deterministic `context` overrides supported. No stable versioned spec-template schema; no node declarations; no roles/ordering. | 🟡 |
| Scheduler + **persistent worker pool** (§5.1) | ❌. `ConnectivityManager.create_worker()`/`destroy_worker()` is strictly ephemeral per-spec; parallelism = `ThreadPoolExecutor(max_parallel_workers)`. No `worker_pool` concept anywhere in code. The agreed patchwork priority. | ❌ |
| Node abstraction (§5.2) | ❌. Zoom broadcaster hack = 1M-second experiment blocking a worker; lives on `Haarika-zoom` branch, not main. | ❌ |
| Prebuilt images, no runtime build (§5.1) | `docker-compose.public.yml` overlay with `snlhub/*` prebuilt images landed (PR #157). | ✅ |
| CTP two-step + local-source flag (§6.1) | CTP service substantially implemented (extract/select/transform/merge); orchestration treats CTP as opt-in and defaults to a **hardcoded global instance** (`128.111.5.236:8001`). Local-corpus bypass is the unsupported Zoom hack. Batch prefetch ❌. | 🟡 |
| Telemetry decoupled upload (§6.2, §6.3) | ❌ as designed: orchestrator **pulls** pcaps from substrate and pushes to telemetry (`telemetry_capture_pull`) — the acknowledged deviation. No queue, no async uploader; sync is per-experiment. Telemetry service itself solid (6 test files, migrations, S3 artifacts) but `GET /results` can't filter by `orchestration_id`. | ❌ |
| Stage-level tracing (§7) | 🟡. `/qtrace` queue-occupancy tracing landed (CCAnalyzer-style notebook); lifecycle timing is still pre-up/post-down polling (±10 s) — no per-stage timestamps. | 🟡 |
| Spec→Substrate verification (§7) | 🟡 seed: substrate `/shape` does post-hoc iperf3/ping verification (`verified`/`verification_log`). Not systematized per `verification_gap.md`. | 🟡 |
| API-optional operation (§1) | 🟡. Deterministic overrides + per-request `workflow_source`/`workflow_id` + CLI exist, but no documented "submit a fully-formed spec, skip the LLM" entry point; classroom sweeps required hacking parsing out. | 🟡 |
| Substrate portability (paper claim) | `local_docker` ✅, `aws` hybrid 🟡, `gcp`/`remote` raise `NotImplementedError`. | 🟡 |
| Shared contracts (`shared/`) | `shared/models/__init__.py` is **empty** and `shared/clients/` is a docstring, versus 500-line READMEs specifying `Experiment`, `BaseHTTPClient`, etc. Each service defines its own schemas — no single spec-template source of truth. The spec template (§5.2) should land here. | ❌ |
| Substrate worker execution (§5.3) | Strongest component: 15-CCA support with LD_PRELOAD shim + strict CI sweep, namespaces, capture, replay, qtrace. Recent work concentrated here. | ✅ |

**Reading of the delta:** the *execution* half of the thin waist (substrate worker,
CTP ops, telemetry storage, NetGent workflows) is in decent shape; the *intent* half
matches the papers' narrative but not this spec's module decomposition — knowledge
base, match-with-backflow, planner, and scheduler-over-pool are missing or fused into
one hard-to-modify service ("this is a mega effort… essentially removing all of what
orchestrator does right now" — Manni). The persistent worker pool is both the biggest
measured win (150–200 s overhead per 30 s experiment) and the smallest architectural
step — hence the patchwork-first sequencing.

### Naming/terminology alignment (papers ↔ code)

- Papers (HotNets `Pramana_Hotnets`, SIGCSE `SIGSCE_Pramana`) call the system
  **Pramana** (Sanskrit: *evidence*), a *generative empirical backend*; "empirical
  thin waist" is the shape; the waist artifact is the **intent specification**. Code
  and docs should adopt this vocabulary ("we are pivoting to Pramana more
  aggressively" — Arpit, 07-01).
- Papers credit **NetReplica** as the conditions layer; the code implements it as CTP
  Service + Substrate Worker and never says NetReplica. The static-knob capability
  file (§4) should be named NetReplica capabilities to match the writing.
- The papers' six-service table ("only the orchestrator holds intelligence") is
  compatible with this spec: §3 is the *internal* structure of the one intelligent
  box.
- Related external artifacts: Eugene's design doc (Google Docs, MCP-based variant at
  `EugeneVuong/agentic-thin-waist`) should be reconciled with or superseded by this
  spec.
