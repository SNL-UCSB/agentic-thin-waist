# PRAMANA — Complete Design Specification v1.1

**UCSB SNL · 2026-07-02 · CANONICAL.** Supersedes v1.0 after the software-engineering
adversarial review (3 lenses, 47 findings — triaged in
`pramana_adversarial_review_2026-07-02.md` §SE) and five owner decisions (E1–E5,
§14). An engineer implements from this document alone. System name: **Pramana**
(Sanskrit: *evidence*); repo: `agentic-thin-waist`.

---

## 0. Goals — the language we use, elevated then derived

### 0.1 The invariant core (stable across every venue)

> **Pramana is an empirical backend: it turns a stated research intent into
> trustworthy, labeled evidence — empirical data from real or emulated networks,
> never synthetic — with the AI serving as interface, never as data generator.**

### 0.2 The per-audience views (each paper's qualifier is a projection, not a fork)

| Venue | Designation | Pramana's role there |
|---|---|---|
| HotNets '26 | ***generative* empirical backend** | the contribution: closing the *ideation-to-data gap* |
| SIGCSE TS '27 | ***AI-assisted* empirical backend** | educational instrument: "students reason about experiment design, not tooling" |
| NTC-R '26 (CoNEXT) | **"*Pramana-like* empirical backend"** | instrument for the *data-refinement* half of shoring up network foundation models (vs. NeMo-ATC's architecture-refinement half) |
| CPUC | **research accelerator** bridging the *intent-to-execution gap* | policy-facing evidence generation (broadband quality) |

Design consequence: nothing below privileges one framing. The system must be
*qualifier-stable* — the same artifact-generating machine reads as generative,
AI-assisted, or accelerating depending on who is asking.

### 0.3 Goals → data-generation requirements (HotNets R1–R8, extended)

From the HotNets draft's requirements backbone, plus what CPUC/NTC add:

R1 bottleneck control · R2 real applications · R3 flexible telemetry ·
R4 NL intent · R5 modularity · R6 portability · R7 speed & scale ·
R8 robustness · **R9 trustworthy evidence** (realized conditions measured and
shipped with the data — CPUC "not synthetic"; the verification thesis) ·
**R10 data refinement** (datasets deliberately densified in intent-chosen
regions — NTC; NetForge's intent-weighted vs frequency-weighted claim).

### 0.4 Requirements → system requirements → traceability

| Req | System requirement | Satisfied by |
|---|---|---|
| R1 | regime = static envelope ⊗ dynamic pressure, imposed or inhabited | Regime (§2), M10 worker, NetReplica-in-image |
| R2 | deterministic replay of real apps, client+server roles | Workflow/NetGent (§2), service nodes |
| R3 | pcap + transport + app metrics + qtrace, contextual labels | A9 envelope, M12 telemetry |
| R4 | intent → validated spec with backflow; simple model suffices | M3 parser, M5 match, §1 P-SYS 2 |
| R5 | artifact-only interfaces; capability protocol; must-not-know table | §3, §5 |
| R6 | one spec, tiers differ only in `mapping:`; connectors | A5, M9 |
| R7 | persistent pool, prefetch, set-scale scheduling | M7/M8/M10 |
| R8 | fenced lifecycle, idempotent sinks, crash-only Core, annotate-never-discard | M8 (§5.3), acceptance 5 & 8 |
| R9 | scoped per-factor verification in every result | verify (§4), A9 |
| R10 | CTP algebra (select/transform/merge) + sweep generators | M11, §4 sweeps |

## 1. Design philosophy and principles

**The philosophy:** *Spend intelligence above the waist, never below it — every
concern of an experiment (behavior, conditions, placement) is progressively
disaggregated into a compiled, parameterized, replayable artifact, so that
everything below the waist is composition and replay, never authorship.* Model
use above the waist: offline authoring (human-gated) + exactly one per-request
site, `compile()`.

**P-SYS** (system): 1 Usability tiers T1 laptop / T2 cloud / T3 any-infra;
T1-weight rule. 2 Minimum viable intelligence (schema-constrained form-filling;
pluggable LLM binding). 3 Hallucination containment (closed-world where
enumerable; validated/allow-listed/backflowed where not; lexicon; provenance;
echo; human-signed offline AI). 4 Logical disaggregation, physical packaging by
profile. 5 Brownfield rule (reuse mapped in §8; changes mapped in §12).
**P-PLANE**: 6 pointers in control plane, payloads direct. 7 outbound-initiation
at unreachable boundaries; at T2 *workers* are made reachable (the implemented SG model); the Core only dials out (E5-revised).
8 AI-free below the waist by type. 9 capability sync never per-experiment.
**P-MOD**: 10 artifact-only interfaces + state ownership. 11 **validation strict
at the compile gate; must-ignore-unknown below the waist** (K8s convention;
additive fields never bump `schema_version`, semantic changes do; modules declare
accepted version ranges). 12 interfaces profile-invariant, transports are
bindings. **P-METHOD**: 13 idempotency at every sink; POSTs with content-derived
ids are idempotent upserts (200 + existing). 14 fail fast and loud (perms,
signatures, sha and fence mismatches, SG fallbacks). 15 determinism below the
waist; identity via one shared RFC 8785 function only.

**P-EVIDENCE (E1 — the paths rule):** *HotNets/Zoom evidence runs on TODAY'S
pipeline* (executor loop, duration hack, Haarika's flags — frozen, bugfix-only);
the v1 build is the NSDI-Frontiers/classroom artifact and proceeds in parallel.
A5 + echo may appear in papers as design artifacts, never as shipped claims.

## 2. Grammar, taxonomy, glossary

```
Evidence      = collect(ExperimentSet)
ExperimentSet = compile(Intent, Answers)  | user-written Spec (same gate)
                  v1: ONE batched clarification round (E3); iterative fixpoint = v2
ExperimentSet = ⟨ nodes, mapping, secrets, leaves ⟩          (leaves flat/expanded)
sweep         : Experiment × dim → ExperimentSet              (client-side)
Experiment    = ⟨ Workflow(params) ⊗ Regime ⟩ @ Roles × iterations
identity(e)   = H_rfc8785(workflow@sha, params, static, dynamic)
Roles         = ⟨ client: Node, server: Node? ⟩
Workflow      = CLI(app, role) ▸ NFA⟨states, {{params}}⟩      (NetGent)
Regime        = Static⟨capacity↓↑, latency, queue⟩ ⊗ Dynamic⟨pressure⟩
pressure      = replay(ctp) | load(Workflow* ↦ Node*) | both
select        : criteria → ℘(corpus);  ctp ∈ closure(corpus; transform, merge)
Nodes         = Pool.{active|latent}.filter(attrs).take(n); persistence ∈
                {set, experiment, fresh-per-experiment}
mapping       : nodes → connectors
collect       = deploy ; prepare ; verify ; run ; publish     (AI-free)
⊗             = independent late binding
```

Regime modes: **imposed** (probe verifies) | **inhabited** (probe characterizes).
Taxonomy: intent · experiment set · experiment (leaf; identity-hashed) ·
iteration (no teardown by default) · deployment (worker×leaf record + lifecycle)
· attempt (post-reap counter) · **fence** (monotonic per-deployment epoch, §5.3).
Glossary: workflow ≠ pipeline (node's runnable list) · regime = conditions only ·
context (results) = static+dynamic+application · Core (never "orchestrator") ·
worker unit = {substrate + browserless + netgent-runner} trio.

## 3. Capability Protocol

**v1 (federation of one):** hand-authored `capabilities.yaml` per project,
**in-repo, git-versioned; PR review is the human gate; commit/content sha is the
pin.** Loader (~100 lines, in `shared/`) reads a configured directory/URL set at
bootstrap, content-hashes each file, pins hashes into every compiled spec. No
registry service, no signing machinery, no synthesizer, no refresh daemon in v1.
**v2:** signatures = **minisign or SSHSIG** (never a DIY envelope) with TUF-style
freshness (signed timestamp + max-age) and monotonic version anti-rollback;
synthesizer runs in the publisher's CI reading `--describe`/manifests; ETag
refresh + diff reports. The *file format* is identical in v1 and v2.

File kinds: `static` (NetGent entries incl. per-entry `workflow_sha`, flag
mappings `{name, flag, positional?, arity?, type, required, default}`,
prerequisites `{name, kind}`, node_requirements; NetReplica knob ranges +
realization modes + ceiling) | `live` (CTP: query schema + endpoint only).
Three pull channels — **no codebase cloned at startup**: capability YAML → loader
· engines baked into images · artifacts lazily by pinned sha/pointer.
Invariant: publisher changes affect Pramana only at refresh/image boundaries,
never in-flight sets (pins).

## 4. The waist artifact (A5) — complete template

Schema source of truth = **Pydantic v2 models** in `shared/models/` (already a
repo dependency); JSON Schema is a **build artifact** emitted by CI from the
models. `extra="forbid"` at the compile gate; `extra="ignore"` in all consumers
below the waist (P-MOD 11).

```yaml
schema_version: 1
experiment_set:
  id: es_<slug>_<hash8>              # content-derived; duplicate POST ⇒ 200 + existing
  intent_ref: string|null
  capability_pins:                   # lockfile-shaped records, NOT bare hashes
    netgent:    {version: "2.4.0", url: "...", sha256: "...", pinned_at: ts}
    netreplica: {version: "...",   url: "...", sha256: "...", pinned_at: ts}
    ctp_schema: {version: "...",   url: "...", sha256: "...", pinned_at: ts}
    lexicon:    {version: "...",   sha256: "..."}      # lexicon participates in compile
  secrets: [zoom_meeting_code]       # keys; values local-only; resolvable ONLY from
                                     # the leaf workflow's declared prerequisites
  nodes:
    - {name: str, kind: pool|service, count: int, pool: fixed|elastic,
       persistence: set|experiment|fresh-per-experiment,
       pipeline: [workflow_id], requirements: [attr],
       params: {k: literal|$secrets.<key>}}            # service nodes only
  mapping: {<node>: local_docker|aws|ssh:<host>|<connector_id>}
  experiments:                       # FLAT leaves
    - id: e_<hash8>                  # = identity-hash prefix; UUID format retired
      static:
        capacity_down: {value: 10.0, unit: mbps}       # canonical decimal (§4.2)
        capacity_up:   {value: 10.0, unit: mbps}
        latency:       {value: 10.0, unit: ms}
        queue: {qdisc: codel, args: ""}                # args = verbatim tc string
        cca: cubic                                     # endpoint-applied; in identity
      application:
        workflow: zoom_client@sha256:...               # pinned at compile
        params: {server: broadcaster, duration: {value: 30.0, unit: s},
                 meeting_code: $secrets.zoom_meeting_code}
      dynamic:
        mode: replay|load|both|none
        ctp: [id]                    # len 1 or == iterations (i-th ↦ i-th); in identity
        source: ctp_service|local_dir
        min_available: int           # below floor at compile ⇒ backflow
        load: [{workflow: id@sha, node: name, params: {...}}]
      iterations: 1
      telemetry: {pcap: true, qtrace: false, app_metrics: true}
      verify: {probe: true, tolerance: {capacity_pct: 5, latency_ms: 2},
               policy: annotate}     # annotate-only in v1
# Client-side only; expanded by `pramana run` before submission:
sweeps:
  - {over: static.latency, values: [...]}
  - {over: dynamic.ctp, select: {intensity_mbps: [4,8], n: 100}}   # CLI runs the
                                                                   # S4 query
```

**4.1 Validation (Match; reject, never coerce):** schema + pinned capability
ranges/enums/dependencies; leaf workflow ∈ node pipeline; `$secrets.*` ∈ declared
prerequisites; fuzzy quantifiers only via pinned `lexicon.yaml`; endpoint-like
free-form values against capability allow-lists or backflow. **One batched
clarification round** (questions only from declared prerequisites; answers
type-validated), then loud itemized defaults + plain-language **echo**; sweep
axes shown as realized value lists; user confirms.
**4.2 Units:** rate(kbps|mbps|gbps→mbps) · time(ms|s|min→ms) · pct. Canonical =
fixed-precision decimal string before hashing; `parse∘format` idempotent
(hypothesis property tests). No pint (float behavior would leak into identity).
**4.3 Identity:** `sha256(rfc8785(...))` — **RFC 8785 JCS** via the `rfc8785`
package, wrapped once in `shared/models/hashing.py`; **reimplementation
prohibited**; golden hash vectors in fixtures. Includes {workflow_sha,
resolved params sans secret values, static, dynamic.mode/ctp/load}. Excludes
nodes, mapping, iterations, telemetry, verify, attempts, provenance.
**4.4 Provenance:** out-of-band sidecar map, **JSON Pointer (RFC 6901) → source
∈ {intent, capability_default, user_answer, external_unverified}**, derived at
Match (not plumbed through layers), feeds the echo, excluded from identity.

## 5. Architecture

### 5.1 Artifacts

A1 Intent · A2 Clarification (one batched round v1) · A3 CapabilityFile ·
A4 CTPQuery/Pointers (partial counts valid) · **A5 (§4)** · A6 Deployment
`{deployment_id, experiment_id, node, state, attempt, fence, start_iteration,
prepare{...}, cancel_requested, error, timestamps{...}}` · A7 WorkItem
`{deployment_id, fence, leaf, start_iteration, secrets_resolved(in-memory)}` ·
A8 StatusEvent `{worker_id, deployment_id, fence, state, stage, ts, log_tail}`
(stages include `service_ready`) · A9 ResultEnvelope `{..., iteration, attempt,
fence, spec_hash, artifacts[{kind,key,bytes}], metrics, verification{scoped
per-factor}, ctp_realized_count, context}` · A10 NodeDescriptor/PoolSpec.
Correlation rule (new): `deployment_id` propagates as a header/field across
every seam — one ID connects Core ↔ substrate capture ↔ netgent run ↔ telemetry
row.

### 5.2 State ownership (unchanged must-not-know table) — with one correction:
**the Scheduler owns A6 rows directly in Postgres via `shared/db`** (compare-and-
set transitions); telemetry owns results only. `orchestration_store.py`'s
persist-via-telemetry-REST pattern is retired.

### 5.3 Execution lifecycle (M8 contract — bespoke, capped, fenced [E4])

- **One lifecycle owner.** Procrastinate is **removed from the execution path**:
  `netgent-runner` is invoked synchronously inside `/work` (library call or
  local subprocess), `max_attempts=1`, no queue. This also removes the worker
  trio's central-Postgres dependency (it could not deploy to T2 otherwise).
  The netgent-service generation queue may keep Procrastinate (dev-time tool).
- **Fencing.** A6 carries a monotonic `fence`, bumped on every requeue; A7/A8/A9
  carry it; telemetry rejects stale-fence envelopes; a worker whose status
  exchange returns `fenced` **self-terminates the experiment** (kills replay +
  workflow, resets namespaces). Zombies must not pollute other experiments'
  physics.
- **Claims.** Work queue = Postgres table; claim = `SELECT ... FOR UPDATE SKIP
  LOCKED`; connections via `psycopg_pool` (ceiling in defaults); per-statement
  `statement_timeout`; heartbeat-update bloat mitigated (fillfactor/HOT note).
- **Dispatch (direct binding).** Scheduler dials worker `POST /v1/work` over the
  binding transport; **idempotent-accept**: re-delivery of same
  `(deployment_id, fence)` returns current state, never a second run. One
  persistent async HTTP client; per-worker deadline ≪ poll interval; exponential
  backoff; per-worker circuit breaker; ±20% jitter on all polls.
- **Liveness (one direction per binding).** Direct binding: scheduler-initiated
  `GET /v1/status` polls (5 s, jittered); "3 missed" = 3 failed polls. **Reap
  requires corroboration** (no recent envelope/artifact activity from that
  worker) and a **mass-reap brake**: >50% of fleet failing in one window ⇒
  suspect the observer (laptop wifi), pause reaping. Reap ⇒ requeue
  `attempt+1` (cap 2), `fence+1`, `start_iteration` = last durably completed +1
  (per-iteration resume; envelopes are the durability record).
- **Transitions** keyed by `(fence, state)`; stale-epoch observations dropped;
  published table: assigned→preparing→ready→running→reporting→done; any→failed;
  any→cancelled. Cancellation is an A6 field (`cancel_requested`), delivered on
  the next status exchange and honored by fence semantics if the worker is deaf.
- **Crash-only Core.** Recovery *is* startup: load non-terminal A6, re-poll all
  workers, reconcile by (fence, state), resume FIFO position from the table.
  Nothing scheduler-critical lives only in memory.
- **Scale cap:** the queue+lifecycle layer has a ~500-line budget; if it grows
  past that, the build-vs-adopt decision (E4) reopens by prior agreement.
- **PlusCal model** (Manni, in parallel — not an implementation gate): must
  include `attempt` and `fence` variables and the reap/cancel/stale-observation
  races; it is paper material for the verification story either way.
- Set-granularity FIFO; per-worker locks; service-node startup precedence gated
  on `service_ready`.

### 5.4 Modules (Δ from v1.0; unchanged text elided, reuse map in §8)

- **M1 CLI** (typer/click): `init` (pydantic-settings config: env `PRAMANA_*` >
  file > defaults; secrets scaffold with **enforced 0600** — doctor and dispatch
  hard-fail otherwise; `PRAMANA_SECRET_<KEY>` env override for CI), `run`
  (sweep + S4 expansion), `status`, `cancel`, `doctor`. Machine conventions:
  `--json` on read verbs, documented exit codes (**3 = backflow required**),
  `--yes` / `--answers-file` for non-interactive, completion, `NO_COLOR`.
  Deferred: `refresh`, `diff-collected` (v1.1+), keyring backend.
- **M2 REST (FastAPI — the repo standard; only the retiring stub was Flask):**
  `/v1` prefix; **RFC 9457 problem+json** errors; cursor pagination on
  collections; idempotent POSTs (content-derived ids); cancel verb kept.
  `services/experiment-api` **deleted in one commit** when M2 lands.
- **M3/M3a Parser + LLM binding:** two providers v1 — `anthropic` +
  `openai_compatible` (covers cloud + vLLM/Ollama); JSON-schema-in-prompt +
  validate + retry-once; grammar-constrained decoding optional per provider.
- **M4 KB-lite:** the §3 loader. No service.
- **M5 Match:** as §4.1. Honest sizing: ~95% new code (the "refactor" framing
  was wrong); the checker in `experiment_generator.py` is 113 lines. SMT slots
  behind the same signature later.
- **M6 SpecGen:** existing Cartesian expansion + pins + hashes + echo.
- **M7 Planner-lite:** greedy round-robin + service-precedence + `min(cores−2,8)`
  packing behind the full `plan(A5, descriptors) → [Deployment]` signature.
- **M8 Scheduler:** §5.3.
- **M9 Connectors:** keep `LocalDockerBackend`/`AWSBackend` + provisioner
  (with the two filed fixes). **T2 transport = the current implementation
  (E5-revised):** workers made reachable (EC2 public IP + SG scoped to the
  operator's IP), Core dials out over HTTP — proven code, zero new
  dependencies. Known limitation (recorded, not redesigned): SG scoping is
  access control, not encryption; a pinned self-signed cert is the cheap v1.1
  fix if secrets-bearing T2 runs demand it. No mesh, no tunnels, no broker.
  T3 NAT'd infra remains the one case needing a rendezvous — deferred with it.
- **M10 Worker:** substrate `main.py` kept; add `/v1/work` (idempotent-accept;
  synchronous prepare→verify→run→publish; netgent-runner in-process),
  `/v1/status`, fence handling + self-termination, prepare-phase heartbeats,
  per-iteration durable completion, stage timestamps.
- **M11 CTP-lite:** `local_dir` officialized; global URL moves to config;
  `/capabilities` endpoint deferred (hand-authored file covers v1).
- **M12 Telemetry:** upsert on `(spec_hash, deployment_id, iteration, attempt)`
  + fence rejection; `?spec_hash=` filter; two-axis set status. **T2 ingest = the
  current implementation:** the Core's poll loop collects envelopes (small
  JSON) and pulls artifacts from workers over the same SG-scoped HTTP it
  already uses — today's proven path. S3-for-bulk-artifacts is a v1.1
  optimization if the laptop uplink becomes the measured bottleneck, not a v1
  component.
- **M13 NetGent:** runner embedded (§5.3); workflow-repo entry gate = PR review
  + golden-trace replay (signing v2); capability file hand-authored.
- **M14 shared/ (FIRST, owned, frozen):** Pydantic v2 models, units, RFC 8785
  hashing, defaults, lexicon; golden fixtures + hash-stability property tests;
  **mypy --strict + ruff gate on `shared/` in CI (non-negotiable)**; JSON Schema
  emitted as build artifact. Repo-wide: **uv workspace** (root pyproject +
  single lock; per-service `requirements.txt` retired — root file already
  drifted from CI).

### 5.5 Observability (replaces "tracing falls out of the interfaces")

Stage timestamps stay, and: `deployment_id` correlation across all seams;
structured JSON logs; Prometheus `/metrics` on the Core (queue depth, claim
latency, reap rate, ingest lag, per-worker tolerance-failure rate — the I4
alarm's actual home); Grafana/OTel in the scale profile only.

## 6. Security

T1 = localhost. T2 = SG-scoped direct HTTP (the current implementation); encryption gap recorded as a known limitation with pinned-cert as the v1.1 option.
Secrets: local file 0600 (enforced), keys-in-specs, resolve-at-dispatch against
declared prerequisites only, in-memory transit, scrubbed from A6/A8/A9/logs.
SG fallback `0.0.0.0/0` = hard fail (SG mode only). Workflow entry gate (PR +
golden trace); capability files via PR review (v1) / minisign|SSHSIG + freshness
(v2). Allow-listed endpoint catalogs bound URLs/hosts.

## 7. Verification posture

Scoped per-factor verdicts in every A9; envelope probe (5 s iperf3/direction +
10 pings, post-net-setup, pre-capture, 2 s drain) verifies imposed /
characterizes inhabited; CTP realized-descriptor check fast-follows. Grounded
tool verdicts + research residuals: `verification_gap.md`. PlusCal per §5.3.

## 8. Reuse map (v1.1 corrections marked ★)

Unchanged from v1.0 except: ★ orchestration/API is **FastAPI** (spec error
fixed; CLAUDE.md "Flask for all services" is stale — update it) ·
★ `orchestration_store.py`: retired as scheduler store (A6 → Postgres direct);
salvage for orchestration-metadata reads · ★ `experiment-api`: deleted in one
commit, no alias · ★ Match reuse claim corrected (~95% new) · ★ netgent-worker
Procrastinate: out of execution path; kept only for dev-time generation ·
★ per-service `requirements.txt` → uv workspace · ★ CI: add shared-models job
(mypy strict + ruff + fixtures) with fan-out on `shared/` changes + a compose
acceptance job (criteria 1, 3; criterion 2 via recorded LLM responses).

## 9. Profiles

**laptop**: postgres, minio, Core (one process), worker unit(s), telemetry,
ctp(local_dir ok), netgent-service. No broker, no tailscale requirement.
**scale**: + elastic connectors, Grafana/OTel; S3 artifacts optional (v1.1).

## 10. Operational defaults (`shared/models/defaults.py`)

poll 5 s ±20% jitter · heartbeat-equivalent = 3 failed polls + corroboration ·
mass-reap brake at 50% · retry cap attempt ≤ 2 · per-iteration resume ·
prepare timeout 10 min (with prepare-phase liveness) · experiment timeout
3×duration+120 s (leaves; **service nodes**: health-based liveness, exempt from
experiment timeout, reaped only by cancel/set-teardown) · CTP batch 100 ·
clarification: one batched round (round cap n/a in v1) · pool default
min(cores−2, 8) · psycopg_pool ceiling 20 · statement_timeout 30 s · probe
5 s+10 pings+2 s drain · verify policy annotate.

## 11. Acceptance criteria

1–7 as v1.0 (T1 keyless ≤10 min; T1 NL; Zoom class w/ service_ready; **T2 via the current SG-scoped direct model** — committed scope [E2]; kill-a-worker (now also asserts fence: zombie
envelopes rejected); publisher evolution via pins; cancel) **+ 8: `kill -9` the
Core mid-set → restart → set completes, no duplicates beyond attempt semantics.**

## 12. Migration plan (revised order; each ships alone)

**M-0 (now):** freeze evidence path (E1); Zoom/HotNets data on today's pipeline.
**M-1: `shared/models` first** — Pydantic models, units, RFC 8785 hashing,
defaults, lexicon, golden fixtures, mypy/ruff CI, uv workspace. Named owner
required. **M-2:** capability files (hand-authored) + loader + pinning.
**M-3:** M8 scheduler per §5.3 (bespoke/capped/fenced) + A6 Postgres store +
crash-only recovery; PlusCal in parallel (Manni). **M-4:** M10 worker `/v1/work`
path (synchronous netgent-runner; fence; per-iteration resume). **M-5:**
telemetry upsert + fence rejection. **M-6:** M5 match + batched backflow + echo;
M6 pins; M3a binding. **M-7:** CLI. **M-8:** T2 — harden the existing SG model (two filed
fixes), acceptance 4. **M-9:** scoped verify probe + CTP realized check.
v2 parking lot: signing/freshness, synthesizer, KB refresh/diff, iterative
sessions, SMT match, third provider, broker binding, keyring, `diff-collected`.

## 13. Testing strategy (per SE review; before M-1 completes)

Golden A5 fixtures + RFC 8785 hash vectors + hypothesis property tests (units
round-trip, hash stability) in `shared/tests` · table-driven Match cases
(accept/reject/backflow triples) · scheduler transition-table tests incl.
reap/requeue/cancel/stale-fence races · `tests/acceptance/` compose harness
running criteria 1 & 3 in CI; criterion 2 with recorded LLM responses (no keys
in CI) · per-service suites remain; a `shared/` change fans out to all service
jobs.

## 14. Decision log

D1–D7 · R1–R10 · I1 (amended by E3: batched v1, iterative v2) · I2–I4 ·
U1–U25 · H1–H15 · A1–A19 · G (grounding) · SE-1…SE-47 (register §SE) ·
**E1 split evidence/build paths · E2 T2 committed in summer scope · E3 batched
backflow v1 · E4 bespoke capped+fenced scheduler, Procrastinate out of the
execution path · E5 (revised same day, Arpit): T2 transport = the current
implemented SG-scoped direct model; no mesh/tunnels/broker — do not
overcomplicate a solved problem. Encryption = known limitation, pinned-cert
v1.1 option. + E6: dependency manifest (§15) — execution path touches only
boring, battle-tested tools; bleeding-edge is dev-time-only, swappable, or
vendorable.**

## 15. External dependency manifest (E6 — the Achilles'-heel audit)

**Rule: the execution path may depend only on Tier 1.**

- **Tier 1 (boring, battle-tested; runtime allowed):** Docker/Compose,
  PostgreSQL, Linux tc/netem/netns/iproute2, tcpreplay, tshark, iperf3,
  FastAPI, Pydantic v2, httpx, psycopg(+pool), SQLAlchemy, pytest+hypothesis,
  Playwright, boto3, MinIO, typer/click.
- **Tier 2 (modern-stable; contained):** uv/ruff/mypy (dev+CI only; mechanically
  revertible), `rfc8785` (frozen IETF spec, sigstore-maintained, **vendorable**),
  Browserless (replaceable by plain Playwright).
- **Tier 3 (churn risk; fenced):** LLM APIs (R7 binding + API-optional rule —
  total LLM failure leaves T1 keyless intact) · LangGraph/LangChain (slimming to
  plain code around M3a in v1) · browser-use (dev-time only by architectural
  rule; failure stops new workflow authoring, never execution).
- **Rejected/deferred on this ground:** RabbitMQ/Kafka, Tailscale, Temporal,
  Celery, Kubernetes, Z3 (v2 optional), minisign (v2).

Adding any dependency requires stating its tier and fence in this section.
