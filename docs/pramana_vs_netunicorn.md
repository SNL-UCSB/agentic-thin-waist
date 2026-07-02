# Pramana vs. netUnicorn — Architectural Comparison

**UCSB SNL · 2026-07-02**

Sources: `docs/pramana_spec_v0.md` (v0.1 converged draft) vs. netUnicorn
(Beltiukov, Guo, Gupta, Willinger, CCS '23; arXiv:2306.08853v2; `netunicorn` GitHub
org). Written to inform the spec meeting and the HotNets "NetUnicorn-style execution
substrate" positioning.

---

## 1. Same DNA, different waist

Both systems are explicitly hourglass designs, but **what sits at the waist is
different in kind**:

|  | netUnicorn (CCS '23) | Pramana (spec v0.1) |
|---|---|---|
| **The waist is…** | a **programming abstraction**: Task / Pipeline / Nodes / Experiment, expressed in Python (17–35 LLoC per experiment) | a **declarative artifact**: the intent specification — a compiled experiment-set spec (JSON + node declarations) that "doesn't need any AI assistance… whatsoever" |
| **Above the waist** | ML learning problems (an expert writes Python intents) | research intents in natural language (or direct spec submission), parsed by the only LLM in the system |
| **Below the waist** | network *infrastructures* reached via connectors (SaltStack, ACI, Fargate, K8s, Docker, Containernet, SSH) | network *conditions + applications*: NetReplica knobs, CTP replay, NetGent workflows on Docker/AWS/testbed |
| **Decoupling claim** | "decouples data-collection **intents** (what/where) from **mechanisms** (how)" | same principle, plus decoupling *intent expression* (NL) from *intent compilation* (spec) — a layer netUnicorn never attempts |

The one-line version: **netUnicorn is a general executor of user-authored tasks over
heterogeneous infrastructure; Pramana is a domain-specific generative backend where
the conditions, the applications, and the telemetry are the product.** netUnicorn
answers "run my Python pipeline on 300 nodes"; Pramana answers "give me 20k Zoom
data points under a 10 Mbps / 10 ms bottleneck with realistic cross-traffic."

## 2. Component-by-component mapping

| Function | netUnicorn | Pramana (spec §) | Note |
|---|---|---|---|
| User surface | Python client (`deploy/execute/status`) | UI REST (`/intent`, `/experiment-status`) + API-optional direct spec | Pramana adds NL; netUnicorn is code-first |
| Intent → executable | **Compiler service**: (pipeline, node-type) → Dockerfile → image in registry | **Spec Generator**: intent → experiment JSONs + node declarations | Different compilation targets: image vs. spec |
| Per-node implementation choice | **TaskDispatcher**: `dispatch(node)` picks task impl per node attributes | **Knowledge Base + Match**: capability files, live CTP query, backflow to user | Pramana lifts dispatch to a system-level match with a user feedback loop — netUnicorn has no equivalent of backflow |
| Infra heterogeneity | **Connector protocol** (`get_nodes/deploy/execute/stop`), pip-installable, YAML-configured, REST-hostable; 7 connectors, 138–242 LLoC each | `ConnectivityManager` with hardcoded backends; `local_docker` ✅, `aws` hybrid, `gcp`/`remote` = `NotImplementedError` | **netUnicorn is strictly ahead here** — adopt its connector contract |
| Behind-NAT nodes | **Gateway + pull executors**: nodes only need outbound reach; heartbeat 30 s; exponential backoff | Historically: pcaps piped *through* the orchestrator (the §6.3 deviation); spec v0.1 answer: RabbitMQ | netUnicorn solved Pramana's NAT problem in 2023 with pull semantics — RabbitMQ is a heavier answer to the same constraint |
| Worker abstraction | **Node** + `CountableNodePool`/`UncountableNodePool`; `filter().take(N)` | **Persistent worker pool** + **service nodes**, persistence ∈ {iteration, experiment, experiment-set} (D1 adopts netUnicorn's node/pipeline model) | Pramana adds *persistence levels* and *typed* pools — netUnicorn nodes are persistent by nature (the executor is what's ephemeral) |
| Execution granularity | Control offloaded to node executor; results reported **at pipeline end** ("best-effort" fidelity, minimal comms) | Same conclusion re-derived 07-01: telemetry decoupled, sync at experiment-set end | Convergent evolution — the meeting re-discovered netUnicorn's §4.2 trade |
| Environment reuse | One image per (pipeline, node-type) reused across nodes; deployment skippable if image present; cleanup scripts restore nodes across experiments | Prebuilt `snlhub/*` images; persistent containers; pool-of-1 recycling | Same optimization, one level lower (netUnicorn reuses *images*, Pramana reuses *live containers*) |
| Results | cloudpickled task Results + logs → gateway → processor → Postgres; pcaps shipped by *user tasks* to user sinks (WebDav) | Telemetry Service: contextual storage, query API, S3/MinIO artifacts, RabbitMQ ingestion | netUnicorn explicitly lists "data analytics platform integration" as future work — Pramana built it |
| Multi-tenancy | Yes: auth service, per-user node views, device locking | Single-user v1 | netUnicorn ahead; Pramana consciously deferred |
| Iterations | `CyclePipeline` (repeat all stages N times) | `iterations` field, no teardown between | Equivalent |
| Cross-node sync | In-band readiness-flag tasks (no central barrier) | Node startup precedence (service nodes before pool dispatch) | Pramana's is coarser but sufficient for client/server |

## 3. Taxonomy alignment

| netUnicorn | Pramana | Comment |
|---|---|---|
| Experiment = list of Deployments (whole user intent) | Experiment **set** (one intent, tree of leaves) | Same scope, different name |
| Deployment = pipeline ↦ node + environment | node declaration + mapping in the spec (§5.2) | D1 imports this directly |
| Pipeline = staged DAG of tasks | pipeline = ordered NetGent workflows on a node | Pramana pipelines are flat lists; netUnicorn generalized to `ExecutionGraph` (full DAG) — Pramana explicitly rejected DAG as overkill for v1 |
| Task (atomic, `requirements`, per-node dispatch) | NetGent workflow + params (capability file declares prerequisites) | netUnicorn task `requirements` = shell setup commands ≈ Pramana capability *prerequisites* (credentials, endpoints) — but Pramana's are matched against the user, not silently executed |
| — | Iteration (same experiment, re-run, no teardown) | netUnicorn approximates with CyclePipeline |

## 4. What Pramana adds that netUnicorn never had

1. **The conditions axis as a product.** netUnicorn does **no** tc/netem, no capacity/
   latency/AQM control, no cross-traffic. Conditions are whatever the infrastructure
   provides; shaping would be a user-authored Task. Pramana's core claim — bottleneck
   regime = static knobs + CTP dynamic pressure — has no netUnicorn counterpart.
2. **A workflow library as a service.** netUnicorn tasks are user-contributed Python
   (`netunicorn-library`); Pramana ships deterministic, pre-validated NetGent
   workflows (~100 apps) discovered via capability files.
3. **NL intent + match + backflow.** netUnicorn's user is a Python-writing expert.
   Pramana's intent parser, knowledge base, and ask-the-user backflow (never emit a
   spec the orchestrator doesn't understand) are all new layers.
4. **Queryable telemetry.** netUnicorn persists pickled results for bookkeeping;
   artifact storage/analytics is future work there, built here.
5. **Verification of realized conditions.** netUnicorn offers "best-effort" fidelity
   and never checks that intended conditions were realized. Pramana's Spec→Substrate
   active probing (D6, in summer scope) is exactly the layer
   `docs/verification_gap.md` says the field lacks — and it's a *differentiator vs.
   our own prior system*, which is a strong paper sentence.

## 5. What netUnicorn has that Pramana should steal (or already is)

1. **The connector protocol.** Pip-installable, YAML-configured, REST-hostable,
   ~150–240 LLoC per infrastructure. Pramana's `gcp`/`remote`
   `NotImplementedError`s are the cost of not having it. Adopting the contract
   (`get_nodes/deploy/execute/stop`) would make the portability claim in the HotNets
   draft concrete.
2. **Pull-based gateway for NAT.** Executors poll for work and POST results with
   heartbeats + backoff; the core never needs inbound access to nodes. Worth
   re-examining whether the worker-pool patchwork should adopt pull semantics at the
   worker (worker polls scheduler queue) — it composes with RabbitMQ rather than
   competing with it, and it is *less* infrastructure than broker-per-deployment.
3. **TaskDispatcher-style per-node dispatch** — capability files answer "does the
   system support X"; dispatch answers "which implementation of X on *this* node"
   (Linux vs. Windows, arch-specific). The spec's capability model should absorb this.
4. **Deployment-skip optimization** as an explicit, named step (Appendix G): if the
   image/workflow is already present, skip shipping. Pramana's prefetch plan is the
   analog; make the skip check explicit in §5.3.
5. **Multi-tenancy primitives** (auth, per-user views, device locking) — deferred in
   v1, but the classroom (46 students) is de facto multi-tenant; netUnicorn's device
   locking is the minimal viable piece.
6. **A quantified effort evaluation.** 17–35 LLoC vs. 113–237 LLoC (5–13×) against
   SaltStack-direct is the evaluation template the HotNets E4 "time comparison"
   needs.

## 6. The cautionary-tale tension (flag for the team)

The Apr 1 taskforce called netUnicorn "the cautionary tale" for persistent-service
maintenance, and Pramana's principles demand local-first + minimal dependencies.
netUnicorn's core is 6 Python services + Postgres + a Docker registry (~240 MB).
Pramana is now: 6 services + Postgres + MinIO, **plus RabbitMQ (D3), plus a
persistent worker pool, plus service nodes**. We are architecturally converging on
the operational weight we defined ourselves against — with the difference that
`docker compose up` hides it. That is defensible (compose makes 9 containers as easy
as 3), but it should be a *conscious* trade recorded in the spec, and it sharpens Q1
of `verification_gap.md` thinking: every added always-on service is maintenance
surface the Mininet-bar principle must absorb.

## 7. One-paragraph summary (paper-ready)

netUnicorn established the thin-waist *shape* for network data collection: decouple
intents from mechanisms, disaggregate intents into reusable tasks, and reach
heterogeneous infrastructures through a connector layer with pull-based, NAT-tolerant
executors. Pramana keeps the shape and the node/pipeline abstraction but moves the
waist up a level — from a Python programming abstraction to a compiled intent
specification — and makes the two things netUnicorn deliberately left to its users
(network conditions and application workflows) into first-class, capability-published
services, closing the loop with realized-condition verification that netUnicorn's
best-effort model never attempted.
