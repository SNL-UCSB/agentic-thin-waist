# PRAMANA — Complete Design Specification v1.0

**UCSB SNL · 2026-07-02 · CANONICAL.** This document supersedes and consolidates
`pramana_spec_v0.md`, `pramana_interfaces_v0.md`, `pramana_abstraction_v0.md`,
`pramana_vs_netunicorn.md`, and the adversarial/grounding registers — those remain
as history and evidence; **an engineer implements from this document alone.**
Working name in code: `agentic-thin-waist` repo; system name: **Pramana**
(Sanskrit: *evidence*).

---

## 0. Rationale — why this system, why this shape

Networking research moves at the speed of its experiments. Reproducing one study
costs weeks of bespoke setup: topology, conditions, application scripting,
telemetry. Prior substrates each fixed one piece — Mininet made the *topology* a
laptop-scale object (and Mininet-HiFi made fidelity a monitored per-run property);
netUnicorn made the *experiment* portable across infrastructures (relaxing
fidelity to "best-effort"); NetReplica/NetForge made the *conditions* first-class
(bottleneck regime = static envelope ⊗ trace-mined pressure); NetGent made
*application behavior* a compiled, replayable artifact (NL → NFA). None composed
them, and netUnicorn's cautionary tale is why composition must be usability-led:
it was hard to run on a laptop, operated like a platform, and demanded manual
authorship of tasks and pipelines — which did not sustain.

**Pramana is the composition**: netUnicorn's composition rule, with the pipeline
production automated (NetGent), a conditions production added (NetReplica/CTP),
and a validation-gated intent compiler on top — so the only thing a human still
produces is the question, and the only thing they must trust is measured.

## 1. Design philosophy and principles, by granularity

**The philosophy (one sentence):** *Spend intelligence above the waist, never
below it — every concern of an experiment (behavior, conditions, placement) is
progressively disaggregated into a compiled, parameterized, replayable artifact,
so that everything below the waist is composition and replay, never authorship.*

Model use above the waist is split: **offline authoring** (workflow generation,
capability drafting — always human-gated) and exactly one **per-request** site,
`compile()`.

### P-SYS: system-level principles

1. **Usability is the ordering principle — three tiers.**
   T1 laptop (primary): one command → data in minutes; keyless path = direct spec
   submission; NL path needs an LLM binding (cloud key or local model). T2 cloud:
   same spec, only `mapping:` changes. T3 any infrastructure: connectors.
   *Rule: a feature helping T2/T3 but weighing on T1 goes to the scale profile.*
2. **Minimum viable intelligence.** The harness (CLIs → capability docs → KB →
   match → template) reduces the LLM to schema-constrained form-filling; a
   self-hosted model must suffice; the LLM is a pluggable binding configured once.
3. **Hallucination containment.** Enumerable fields closed-world; free-form
   fields validated/allow-listed/backflowed; fuzzy quantifiers via versioned
   lexicon; field provenance; plain-language echo before execution; offline AI
   surfaces human-signed. (Not "immunity": intent fidelity is formally
   unverifiable — translation-validation-with-human-judge + metamorphic
   paraphrase testing is the ceiling. Grounded verdicts: verification_gap.md.)
4. **Logical disaggregation, physical packaging by profile.** Module boundaries
   enforced by artifact-only interfaces + the must-not-know table — never by
   containers. Core = one process at T1.
5. **Brownfield rule.** Reuse existing code wherever it satisfies a contract;
   this spec maps every module to existing files (§8) and every change to a
   migration step (§12). Nothing is rewritten that can be refactored.

### P-PLANE: plane-level principles

6. Pointers in the control plane, payloads in the data plane; nothing bulky
   transits the Core.
7. Outbound-initiation at every unreachable boundary; the laptop is never
   assumed reachable; at T2 *workers* are made reachable (existing SG model).
8. Everything below the waist is AI-free by type: only `compile()` may invoke a
   model per-request.
9. Capability sync is never in the per-experiment path (bootstrap/refresh only).

### P-MOD: module-level principles

10. A module's interface may reference only artifacts it produces or consumes
    (Table §5.1); each module has one owner of each piece of state (§5.2).
11. Every artifact is versioned (`schema_version`), validated at the boundary
    (reject, never coerce), JSON-serializable, and logged with a timestamp at
    the seam — tracing is a property of the interfaces.
12. Interfaces are profile-invariant; transports are bindings.

### P-METHOD: method-level principles

13. Idempotency at every sink (telemetry upsert key; claim-once work items).
14. Fail fast and loud: insufficient storage, missing signature, sha mismatch,
    SG `0.0.0.0/0` fallback → hard error, never warn-and-continue.
15. Deterministic code only below the waist; no `Date.now()`-style hidden
    nondeterminism in identity computation (canonical serialization, §4.4).

## 2. Grammar, taxonomy, glossary

### 2.1 The grammar (post-adversarial, grounded)

```
Evidence      = collect(ExperimentSet)
ExperimentSet = fix(λA. compile(Intent, A)) | user-written Spec (same gate)
                  where A grows by Clarification (backflow)
ExperimentSet = ⟨ nodes, mapping, secrets, leaves ⟩          (leaves flat/expanded)
sweep         : Experiment × dim → ExperimentSet              (client-side expansion)
Experiment    = ⟨ Workflow(params) ⊗ Regime ⟩ @ Roles × iterations
identity(e)   = H(workflow@sha, params, static, dynamic)      (placement/iterations/
                                                               attempts OUTSIDE identity)
Roles         = ⟨ client: Node, server: Node? ⟩
Workflow      = CLI(app, role) ▸ NFA⟨states, {{params}}⟩
Regime        = Static⟨capacity↓↑, latency, queue⟩ ⊗ Dynamic⟨pressure⟩
pressure      = replay(ctp) | load(Workflow* ↦ Node*) | both  (open-|closed-loop)
select        : criteria → ℘(corpus)                          (query, not algebra)
ctp           ∈ closure(corpus; transform, merge)             (closed; ctp-service code)
Nodes         = Pool.{active|latent}.filter(attrs).take(n)
Node          ∈ Nodes; persistence ∈ {set, experiment, fresh-per-experiment}
mapping       : nodes → connectors
collect       = deploy ; prepare ; verify ; run ; publish     (sequenced, AI-free)
⊗             = independent late binding
```

Regime realization modes: **imposed** (emulated; probe *verifies*) |
**inhabited** (real link via connector; probe *characterizes*). Every published
claim names its quadrant of (imposed|inhabited × replay|load).

### 2.2 Taxonomy

| Term | Definition |
|---|---|
| Intent | NL or structured request; compiles to one experiment set |
| Experiment set | flat list of leaves + nodes + mapping, from one intent |
| Experiment (leaf) | unique ⟨workflow+params, static, dynamic⟩; same identity hash ⇒ same experiment |
| Iteration | re-run of a leaf; no teardown by default (persistence may override) |
| Deployment | one worker×experiment execution record with lifecycle state |
| Attempt | retry counter after reap; outside identity, inside results |

### 2.3 Normative glossary (one term per concept)

**workflow** = one NetGent artifact (never "pipeline") · **pipeline** = ordered
list of workflows a node can run · **regime** = static ⊗ dynamic conditions only
· **context** (in results) = static + dynamic + application labels · **Core** =
the intelligent module set (never "orchestrator" in new text) · **iterations** =
the field name (never `num_iterations`) · **worker unit** = {substrate +
browserless + netgent-runner} namespace-sharing trio.

## 3. The Capability Protocol (how independent projects plug in)

1. **Describable-CLI convention.** Every (application, role) CLI answers
   `--describe` → `{app, role, version, flags[{name,flag,type,required,default}],
   prerequisites[{name,kind: secret|secret_or_param}], node_requirements[]}`.
   NetGent's `manifest.json` + `workflow.json.parameters` already carry these
   facts; the synthesizer reads them directly until `--describe` lands.
2. **Synthesizer** (Pramana-provided, runs in the *publisher's* CI): enumerate →
   describe → assemble capability file → schema-of-schemas validation → human
   review + **signature** (a model may draft; only a human signs). Non-adopting
   publishers: Pramana runs it against their public surface; Pramana-side signer;
   trust label records who.
3. **File kinds.** `kind: static` (NetGent entries with per-entry
   `workflow_sha`; NetReplica knob ranges, realization modes, ≤8-regime ceiling)
   | `kind: live` (CTP: query schema + endpoint only).
4. **Registry + location.** Publisher serves `capabilities.yaml` + detached sig
   at a fixed path. KB registry = `{name, url, pubkey, parser_version}` per
   publisher. New publisher = one registry line, never a Core change.

**KB lifecycle:** BOOTSTRAP (fetch→verify sig→schema→parse→hash-addressed
snapshot; offline T1 uses image-bundled snapshot) · REFRESH (explicit
`pramana refresh` or timer; ETag; **diff report**; atomic swap; old snapshots
retained) · RUNTIME (snapshot reads only; sole publisher contacts = CTP pointer
queries + data-plane fetches by pinned identity).

**Three pull channels — no codebase is ever cloned at startup:**
capability YAML → KB (bootstrap/refresh) · engines baked into prebuilt images
(NetReplica logic *is* the substrate image; NetGent engine is the runner sidecar)
· artifacts (workflow JSONs, CTP payloads) lazily at runtime by pinned sha/pointer.

**Invariant:** a publisher may change anything anytime; Pramana behavior changes
only at refresh/image boundaries, visibly, and never affects an in-flight set.

## 4. The waist artifact — complete spec template (A5)

### 4.1 Full schema (YAML; JSON Schema lives in `shared/models/experiment_set.py`)

```yaml
schema_version: 1
experiment_set:
  id: es_<slug>_<hash8>            # assigned at compile; hash8 = first 8 hex of set hash
  intent_ref: string|null          # provenance; null for API-direct
  capability_pins:                 # REQUIRED: hashes this spec was validated against
    netgent: sha256:…
    netreplica: sha256:…
    ctp_schema: sha256:…
  secrets: [zoom_meeting_code]     # KEYS only; values resolve from local secrets file
                                   # at dispatch, only if declared as prerequisites
                                   # of the leaf's workflow (H12)
  nodes:
    - name: string                 # unique
      kind: pool|service           # pool workers vs long-running service node
      count: int                   # pool only; default profile-derived (§10)
      pool: fixed|elastic          # fixed = bootstrap-created; elastic = connector
                                   # materializes on demand up to `count`
      persistence: set|experiment|fresh-per-experiment
      pipeline: [workflow_id]      # capability constraint: what this node CAN run
      requirements: [attr]         # e.g. browser, audio, public_reach, cca_host
      params: {k: literal|$secrets.<key>}   # service nodes; nothing else legal
  mapping:                         # node name -> connector id (ONLY per-tier change)
    <node_name>: local_docker | aws | ssh:<host> | <connector_id>
  experiments:                     # FLAT, fully expanded leaves
    - id: e_<hash8>                # = identity hash prefix (§4.4); no UUIDs
      static:
        capacity_down: {value: 10, unit: mbps}    # canonical numeric+unit (§4.3)
        capacity_up:   {value: 10, unit: mbps}
        latency:       {value: 10, unit: ms}
        queue: {qdisc: codel, args: ""}           # args verbatim tc string, e.g.
                                                  # "limit 100kb" for bfifo buffer
        cca: cubic                                 # applied at endpoint stack;
                                                  # part of identity; not a
                                                  # bottleneck property
      application:
        workflow: zoom_client@sha256:…             # PINNED at compile (U24)
        params: {server: broadcaster, duration: {value: 30, unit: s},
                 meeting_code: $secrets.zoom_meeting_code}
      dynamic:
        mode: replay|load|both|none
        ctp: [ctp-id]              # replay: len==1, or len==iterations
                                   # (i-th iteration ↦ i-th pointer); in identity
        source: ctp_service|local_dir   # local corpus officially supported
        min_available: int         # H10: fewer matches than this at compile
                                   # = backflow, never silent
        load: [{workflow: id@sha, node: name, params: {…}}]   # closed-loop
      iterations: 1
      telemetry: {pcap: true, qtrace: false, app_metrics: true}
      verify:
        probe: true                # imposed regimes: verify; inhabited: characterize
        tolerance: {capacity_pct: 5, latency_ms: 2}
        policy: annotate           # ONLY annotate in v1 (I4); never discard
# Client-side only (pramana CLI expands BEFORE submission; never reaches the Core):
sweeps:
  - over: static.latency
    values: [{value: 10, unit: ms}, {value: 100, unit: ms}]
  - over: dynamic.ctp
    select: {intensity_mbps: [4, 8], burstiness_pmr_min: 2, n: 100}  # resolved to
                                                                     # pointers via S4
                                                                     # by the CLI
```

### 4.2 Validation rules (Match rejects; never coerces)

- Every field validates against schema + the pinned capability snapshot (ranges,
  enums, dependencies). Unknown/out-of-range → Clarification (backflow).
- Every leaf's `application.workflow` must appear in its target node's `pipeline`.
- Every `$secrets.<key>` must be a declared prerequisite of that workflow.
- Provenance: every field carries `intent|capability_default|user_answer|
  external_unverified` (API-direct path runs the same gate; fields marked
  `external_unverified`). Un-attributable field ⇒ compile fails.
- Fuzzy quantifiers ("moderately bursty") resolve only via
  `shared/models/lexicon.yaml` (versioned; entry = phrase → criteria template).
- Endpoint-like free-form values (URLs, hosts) resolve against the capability
  file's allow-list or force backflow (H1).
- Compile ends with the **plain-language echo**; defaults applied via the
  escape hatch are itemized loudly (H8); sweep axes shown as realized value
  lists (H9). User confirms before dispatch.

### 4.3 Units grammar (parsed at validation into canonical `{value, unit}`)

```
rate    = number ("kbps"|"mbps"|"gbps")          canonical: mbps (float)
time    = number ("ms"|"s"|"min")                canonical: ms (float)
percent = number "%"                             canonical: pct (float)
```
Bare strings like `"10mbps"` are accepted on input and normalized; the stored
spec always holds canonical form.

### 4.4 Identity hash

`identity(e) = sha256(canonical_json({workflow_sha, application.params_resolved_
sans_secrets, static, dynamic.mode, dynamic.ctp, dynamic.load}))` where
canonical_json = sorted keys, no whitespace, canonical units, secrets replaced by
key names. Excluded: nodes, mapping, iterations, telemetry, verify, attempts.
Dedupe (user CLI tool `pramana diff-collected`) and telemetry upserts key on it.

## 5. Architecture — artifacts, ownership, modules & methods

### 5.1 Artifacts (complete family; anything new = a field here, not an endpoint)

A1 Intent · A2 Clarification (Q&A session; questions only from declared
prerequisites; answers type-validated) · A3 CapabilityFile · A4 CTPQuery/
PointerSet (partial counts valid) · **A5 ExperimentSetSpec (§4)** · A6 Deployment
· A7 WorkItem · A8 StatusEvent · A9 ResultEnvelope · A10 NodeDescriptor/PoolSpec.
Below the waist consumes A5–A10 only; NL stops at Match.

**A6 Deployment** `{deployment_id, experiment_id, node, state, attempt,
prepare:{ctp_batch, workflow_sha, skipped}, error, timestamps{assigned,
preparing, ready, running, reporting, done}}`.
**A7 WorkItem** `{deployment_id, leaf(A5 experiment), secrets_resolved(in-memory
only), channel_binding}` — claimed-once.
**A8 StatusEvent** `{worker_id, deployment_id, state, stage, ts, log_tail}`;
stages include `service_ready` (mandatory for service-role workflows; scheduler
gates dependents on it).
**A9 ResultEnvelope** `{deployment_id, experiment_id, iteration, attempt,
spec_hash, artifacts[{kind,key,bytes}], metrics{app,transport},
verification{probed, per_factor:{envelope:verified|failed|n/a,
ctp_realized:{measured, declared, within}, cca_negotiated, app_content:
unverified}, tolerance_requested, tolerance_applied}, ctp_realized_count,
context{static, dynamic, workflow_sha}}` — `verified` is scoped, never blanket.

### 5.2 State ownership / must-not-know (the anti-monolith table)

| Module | Owns | Must NOT know |
|---|---|---|
| CLI/REST | sessions | workflows, CTPs, workers |
| IntentParser | nothing (stateless) | infrastructure |
| KnowledgeBase | capability snapshots+registry | workers, results |
| Match | clarification sessions | execution mechanics |
| Planner | deployments, pool assignment | NL, secret values |
| Scheduler | work queue, liveness, locks; **sole writer of A6** | metric meanings |
| Connector | node materialization | spec contents beyond bootstrap cfg |
| Worker | own lifecycle + caches | other workers, the set, NL |
| CTP svc | corpus + query index | who runs experiments |
| Telemetry | results, artifacts, provenance | how to reach workers |
| Secrets file | credential values (local only) | — |

### 5.3 Modules and methods (with reuse mapping)

**M1 — `pramana` CLI** *(grow from `services/orchestration/scripts/orch_cli.py`)*
`init()` (wizard: LLM binding {provider,endpoint,model,key_ref}; image pull;
secrets scaffold; registry write) · `doctor()` · `intent(text) → session loop`
(renders A2 questions, collects answers, shows echo, confirms) ·
`run(spec.yaml)` (expand `sweeps:` incl. client-side S4 CTP query; submit) ·
`status(set_id)` (two axes: execution + ingested n/m) · `cancel(set_id)` ·
`refresh()` (KB) · `diff-collected(spec)` (I3 dedupe tool).

**M2 — REST façade** *(reuse Flask app in `services/orchestration/app/api/`)*
`POST /intent → {session_id}` · `GET /session/{id}` · `POST /session/{id}/answers`
· `POST /experiment-sets` (A5 direct; same gate) · `GET /experiment-sets/{id}`
· `POST /experiment-sets/{id}/cancel` · `GET /health`.
*(Retire `services/experiment-api` (:8000): 65-line stub; keep container as a
redirect/alias one release, then remove from compose. Its README's controller
role is absorbed here.)*

**M3 — IntentParser** *(reuse `app/engine/intent_parser.py`; LangGraph loop in
`app/agent/` slims to the fixpoint session)*
`parse(intent, answers) → DraftSpec` — via **M3a LLMBinding** *(refactor
`claude_client.py`)*: `complete(prompt, output_schema) → dict` +
`ask(question_context) → str`; providers: anthropic|gemini|openai_compatible
(vLLM/Ollama). Config-selected; grammar-constrained decoding where the provider
supports it.

**M4 — KnowledgeBase** *(new, small; kills the runtime `index.json` fetch in
`app/engine/tools.py`)*
`ingest(registry) → SnapshotSet` · `refresh() → DiffReport` · `snapshot(hash)`
· `capabilities(service)` · per-publisher parsers (netgent from manifest/
describe; netreplica; ctp-schema). Storage: rows in the existing Postgres.

**M5 — Match** *(refactor the checker inside `experiment_generator.py`/agent)*
`match(draft, snapshot) → Matched | Clarifications` (schema+range+dependency
checks; provenance stamping; lexicon resolution; CTP `query()` via S4;
allow-list checks; SMT-backed constraint check is a later drop-in behind the
same signature).

**M6 — SpecGenerator** *(reuse `experiment_generator.py` — Cartesian expansion
already exists)*
`compile(matched) → A5` (pins capability hashes + workflow shas; computes
identity hashes; emits echo text). LLM-free.

**M7 — Planner** *(new)*
`plan(A5, node_descriptors) → [Deployment]` (attribute filter incl. `cca_host`,
≤8-regimes/host packing, affinity assignment, CTP prefetch batches, node startup
precedence).

**M8 — Scheduler** *(new; replaces the ThreadPoolExecutor + create/destroy loop
in `app/engine/executor.py`; salvage its worker-HTTP client code)*
Direct binding (T1/T2): `dispatch(deployment)` = POST to worker `/work`;
`poll_status()` folds worker replies into A6 via the published transition table
(`assigned→preparing→ready→running→reporting→done`; any→`failed`; any→
`cancelled`); `reap()` on 3 missed heartbeats → requeue attempt+1 (cap 2,
iterations restart, U2); set-granularity FIFO (one set drains before the next);
per-worker locks; `cancel(set)` directive on next status exchange. T3 binding:
same A7/A8 via broker + sidecar poller — worker code unchanged.

**M9 — Connectors** *(refactor `app/engine/connectivity.py` to the protocol; keep
`LocalDockerBackend`, `AWSBackend` + `aws_provisioner.py` nearly verbatim)*
Protocol: `get_nodes() → [NodeDescriptor]` · `deploy(pool_spec) → {workers[],
channel_endpoint}` · `execute(worker, bootstrap_cfg)` · `stop(worker)` ·
`refresh_ingress()` *(new — filed)*. Fixes: SG `0.0.0.0/0` fallback → hard fail
*(filed)*. `gcp`/`remote` stubs stay `NotImplementedError` with a pointer to the
plug-in contract. Pip-installable third-party connectors resolve by entry-point.

**M10 — Worker** *(reuse `services/substrate-worker/src/substrate/main.py`
(1905 lines) almost entirely: `/health /shape /capture /replay /qtrace
/ctp/fetch`, CCA preload shim, namespace scripts)*
Additions: `POST /work` (accept A7; run `prepare → verify → run → publish`
sequence) · `/prepare` internals: CTP batch fetch outside shaped ns with
skip-if-cached; workflow fetch by pinned sha (refuse mismatch) ·
`verify()`: 5 s iperf3/direction + 10 pings after net-setup, strictly before
capture, 2 s drain; tolerances from A5 flow into existing `/shape` verification;
CTP realized intensity/burstiness computed during replay (H15) ·
`publish(A9)` via **binding**: T1 direct telemetry REST (salvage
`telemetry_capture_pull.py` logic, inverted to worker-push local) | T2 S3 write
(reuse `shared/s3/client.py`), laptop importer ingests · stage timestamps on
every transition (waterfall tracing) · `GET /status` for scheduler polls ·
`/reset` between experiments per persistence policy. Worker unit = the existing
compose trio {substrate + browserless + netgent-worker} — `count` counts trios;
`browser` attribute iff sidecars present.

**M11 — CTP Service** *(reuse `services/ctp-service` as-is: extract/select/
transform/merge/export, trees, Postgres)*
Additions: `GET /capabilities` (query schema, `kind: live`) · officialize
`local_dir` source (promote Haarika's flag). Global instance URL moves from
hardcoded `128.111.5.236` into the registry entry.

**M12 — Telemetry** *(reuse `services/telemetry-service` incl. migrations, S3
artifacts)*
Additions: upsert on `(spec_hash, deployment_id, iteration, attempt)` ·
`GET /results?spec_hash=` and `?orchestration_id=` filters (the latter is a
documented gap) · ingest-marker objects for the S3 importer · two-axis set
status endpoint.

**M13 — NetGent surface** *(reuse `services/netgent-service` + worker and the
`netgent-workflow` registry)*
Additions: capability synthesizer (reads manifests/params; emits capability
file draft) · signing gate for new workflows: golden-trace replay + human
review + content-hash pin with reviewer provenance (H4) · registry CI publishes
`capabilities.yaml` + sig alongside the existing `index.json` (which becomes
internal-only).

**M14 — shared/** *(fill the empty `shared/models/`)*
`experiment_set.py` (A5 schema + validation + canonical serialization + hash) ·
`capability.py` (schema-of-schemas) · `artifacts.py` (A6–A10) · `units.py` ·
`lexicon.yaml` · `defaults.py` (§10) · reuse `shared/db/client.py`,
`shared/s3/client.py` as-is.

### 5.4 Bootstrap sequence (exact order; each step blocks the next)

1. Load `~/.pramana/config.yaml` (LLM binding, registry, profile); validate.
2. Image ensure: pull `snlhub/*`; build only if image absent AND registry
   unreachable.
3. Connectors: `deploy(pool_spec)` per mapping defaults → pool + channel.
4. KB ingest per §3 (offline: bundled snapshot).
5. Ready: `pramana doctor` green = REST up, pool healthy, KB snapshot loaded.

## 6. Security & secrets

Local secrets file `~/.pramana/secrets.yaml` (0600, gitignored); specs carry
keys; values resolve at dispatch **only** against the leaf workflow's declared
prerequisites (namespaced); transit in-memory in A7 over TLS; never persisted
server-side, never in logs (NetGent masking retained), scrubbed from A6/A8/A9.
Cloud workers: SG ingress scoped to operator IP; `0.0.0.0/0` fallback is a hard
error; `refresh-ingress` for IP changes. Workflow repo entry is gated (H4);
capability files are signed (H3); allow-listed endpoint catalogs bound free-form
URL/host fields (H1).

## 7. Verification posture (grounded)

Per-factor, scoped verdicts in every A9 (§5.1). Tools: constrained decoding
(syntactic validity by construction) · schema/range validation now, SMT with
unsat-core-driven backflow later, same interface · STL-style checks are the
formal upgrade path for envelope + windowed CTP descriptors · TLA+/PlusCal model
of the M8 claim/reap/retry/cancel protocol **before** implementation (highest-ROI
formal step; AWS precedent). Honest residuals (never overclaim): intent fidelity
(echo + metamorphic paraphrase-invariance is the ceiling), ensemble-level
distributional conformance, verdict composition — research agenda, gated on
surveying statistical model checking.

## 8. Reuse map (complete disposition of the existing codebase)

| Existing | Disposition |
|---|---|
| `orchestration/app/engine/intent_parser.py` | **KEEP** → M3 |
| `orchestration/app/engine/claude_client.py` | **REFACTOR** → M3a provider binding |
| `orchestration/app/agent/` (LangGraph) | **SLIM** → fixpoint session loop only |
| `orchestration/app/engine/experiment_generator.py` | **KEEP** → M5 checker extracted, M6 core |
| `orchestration/app/engine/connectivity.py` | **REFACTOR** → M9 protocol; LocalDocker+AWS kept |
| `orchestration/app/engine/aws_provisioner.py` | **KEEP** + 2 filed fixes |
| `orchestration/app/engine/executor.py` | **SUPERSEDE** by M8; salvage worker-HTTP client |
| `orchestration/app/engine/telemetry_capture_pull.py` | **INVERT** → T1 publish binding; T2 → S3 importer |
| `orchestration/app/engine/orchestration_store.py` | **KEEP** → deployment/A6 store |
| `orchestration` skills/tools | **KEEP** (off critical path) |
| `services/experiment-api` | **RETIRE** (alias one release; absorb into M2) |
| `services/substrate-worker/src/**` | **KEEP ~all** + M10 additions |
| `services/ctp-service/**` | **KEEP as-is** + `/capabilities` + local_dir |
| `services/telemetry-service/**` | **KEEP** + upsert/filters/markers |
| `services/netgent-service`+worker | **KEEP** + synthesizer + signing gate |
| `netgent-workflow` registry | **KEEP**; capabilities.yaml added; index.json internal |
| `shared/db`, `shared/s3` | **KEEP** |
| `shared/models`, `shared/clients` READMEs | **REPLACE** by M14 implementations |
| docker-compose | **KEEP** + `profiles:` (laptop/scale) |
| CI workflows | **KEEP**; add shared-models job |

## 9. Deployment profiles

**laptop** (default): postgres, minio, Core (one container/process), worker
unit(s), telemetry, ctp(optional/local_dir), netgent-service. No broker.
**scale** overlay: elastic connectors, S3 rendezvous importer, broker (T3 only).

## 10. Operational defaults (in `shared/models/defaults.py`)

status-poll 5 s · heartbeat 30 s, reap at 3 misses · retry cap `attempt ≤ 2` ·
prepare timeout 10 min · experiment timeout 3×duration+120 s · CTP batch 100 ·
importer poll 30 s · clarification round cap 5 (then batch + defaults escape) ·
pool default `min(cores−2, 8)` in-container regimes/host (NetReplica v2 §5.5) ·
probe 5 s/direction + 10 pings + 2 s drain · verify policy annotate.

## 11. Acceptance criteria (the golden paths; all must pass to call v1 done)

1. **T1 keyless:** fresh laptop → `pramana init` (skip LLM) → `pramana run
   examples/iperf_sweep.yaml` → data + labels in telemetry, `verified` scoped
   fields present, in ≤ 10 min wall clock including image pulls.
2. **T1 NL:** `pramana "compare cubic and bbr at 10 and 50 mbps over wget"` →
   iterative backflow if needed → echo → confirm → 4 leaves → results.
3. **Zoom class:** broadcaster service node + 50-leaf set with local CTP dir;
   broadcaster gated on `service_ready`; no 1M-second hack.
4. **T2:** same spec, `mapping: pool: aws` → SG scoped to caller IP (hard-fail
   on unknown IP) → results land via S3 importer; laptop never accepts inbound.
5. **Kill a worker mid-set:** deployment shows `failed→requeued attempt=2`;
   set completes; telemetry has no duplicate `(hash, iter, attempt)`.
6. **Publisher evolution:** bump a workflow in the registry → running set
   unaffected (pins); `pramana refresh` shows the diff; next compile uses it.
7. **Cancel:** `pramana cancel <set>` stops dispatch, reaps in-flight, releases
   the broadcaster.

## 12. Migration plan (patchwork order; each step ships alone)

M-1 (**now, Manni**): PlusCal model of claim/reap/retry/cancel → then M8+A6 on
the direct binding, workers persistent (pool = long-lived endpoints), executor
loop retired. M-2: `shared/models` (A5, units, hash, defaults) + CI. M-3: KB +
capability files (hand-authored first; kills runtime index.json). M-4: Match +
backflow + echo. M-5: telemetry upsert + S3 importer (retire capture-pull
double-hop). M-6: CLI (`init/doctor/run/status/cancel/refresh/diff-collected`) +
profiles. M-7: scoped verify + CTP realized check. M-8: synthesizer + signing
gate. Owners for M-3..M-5: assign at the team meeting (open D7).

## 13. Decision log (condensed; full registers in history docs)

D1 netUnicorn nodes now · D2 all four summer tracks · D3→superseded: channel
bindings (direct T1/T2; S3 results rendezvous T2; broker T3-only) · D4 ephemeral
deleted (pool-of-1 policy) · D5 local secrets file · D6 minimal verification in
scope · D7 owners at meeting · R1 usability tiers/profiles · R2 two endpoint
configurations · R5 minimum viable intelligence · R6 CLI contract · R7 LLM
binding · R8 CLI-only UX · R9 "Core" · R10 logical disaggregation/physical
packaging · I1 iterative backflow (+cap, escape) · I2 channel bindings · I3
user-level dedupe (+planner warn) · I4 annotate-never-discard (+worker alarm) ·
U1–U25, H1–H15, A1–A19: adversarial register · G: grounding verdicts.
