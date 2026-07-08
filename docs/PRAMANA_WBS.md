# Pramana v1 — Work Breakdown Structure (student onboarding)

**2026-07-02 · Derived from `PRAMANA_DESIGN_SPEC.md` v1.2 + `PRAMANA_INTERFACE_DEFINITIONS.md` (migration M-1…M-9).**
Team model: 3–4 rotating undergraduates + persistent 1–2; **supervisors: Manni &
Jaber**. Tracking: **GitHub Issues + Actions** (cards = issues from the template
below; sub-module gates = milestones; queue = labels `card` + `available` +
size). Beads is NOT part of this framework.

## Relationship to the spec-kit workflow (specs/)

Each sub-module SM-n gets a feature directory `specs/NNN-<name>/` (exemplar:
`specs/001-shared-models` for SM-1). The WBS tables here are the PLANNING
input; each feature's `tasks.md` is the execution source of truth and GitHub
Issues are generated from it one-way. On scope conflicts the WBS wins and
tasks.md is regenerated. Workflow order and conventions: `specs/README.md`.

## Rules of the framework

1. **Tests come first, from supervisors.** A card is assignable only when its
   failing test suite exists (`tests/cards/test_c<n>.py`, e.g. `test_c101.py`) plus fixtures. If the
   acceptance tests can't be written in advance, the interface isn't frozen —
   that's a spec defect, escalate.
2. **Done = CI green.** Card suite + `shared/models` contract tests are required
   status checks on protected branches. No judgment-based acceptance.
3. **Blast radius.** Every card names allowed paths; PRs touching other paths
   fail review automatically. No new dependencies without a §15 tier entry.
4. **Rotation-proof.** Card context ≤ 5 sentences; abandonment = unassign, next
   student starts from the same failing suite. Persistent students hold
   *sub-module continuity* (review incoming cards), not special cards.
5. **Supervisor-only zones:** scheduler state machine internals, fencing,
   anything touching the evidence path (frozen per E1), secrets handling.

## Issue template (`.github/ISSUE_TEMPLATE/task-card.md`)

```
CARD <id>: <one-line what>
CONTEXT   (≤5 sentences; a student never needs the whole system)
INTERFACE (verbatim from PRAMANA_INTERFACE_DEFINITIONS.md §<n>; DESIGN_SPEC for intent only)
INPUTS    skeleton file(s), fixtures, failing suite path
DONE WHEN pytest tests/cards/test_c<n>.py green in CI
MUST NOT  touch outside <paths>; add deps; change any schema
HANDOFF   PR body: what I did / surprises / anything flaky
```

## Sub-modules, gates, and cards

Sizes: S ≤ 1 day · M ≤ 3 days · L = supervisor. ✎ = undergrad-suitable.

### SM-1 `shared/models` foundations — *milestone: M-1 · gate: golden fixtures + hash vectors green; mypy strict + ruff pass* (OWNER-FIRST: Jaber authors suites before anything else starts)

| Card | What | Size |
|---|---|---|
| C-101 ✎ | units grammar: parse/format `{value,unit}` for rate/time/pct, canonical decimal; hypothesis round-trip tests provided | M |
| C-102 ✎ | Pydantic models for A5 `static:`/`application:`/`dynamic:` blocks against provided JSON fixtures | M |
| C-103 ✎ | Pydantic models for A6–A10 artifacts | M |
| C-104 | RFC 8785 wrapper + identity hash (include/exclude sets) + golden vectors | L (Jaber) |
| C-105 ✎ | `defaults.py` + pydantic-settings config loader (env > file > defaults) with tests | S |
| C-106 ✎ | `lexicon.yaml` v1 (10–15 fuzzy quantifiers → criteria templates) + loader + tests | S |
| C-107 ✎ | uv workspace conversion: root pyproject, per-service members, CI job swap | M |
| C-108 ✎ | JSON Schema build artifact: CI step emitting schemas from models, drift check | S |

### SM-2 Capability files + loader — *milestone: M-2 · gate: loader round-trips all three hand-authored files; pins appear in a compiled spec fixture*

| C-201 ✎ | schema-of-schemas (Pydantic) for capability files, `static|live` kinds | M |
| C-202 ✎ | hand-author `capabilities.yaml` for NetGent from manifest.json + workflow params (16 workflows) | M |
| C-203 ✎ | hand-author NetReplica knob file (ranges, qdiscs incl. buffer syntax, CCA host caveats, ≤8 ceiling) | S |
| C-204 ✎ | loader: read capability DIRECTORIES (URLs are v2), content-hash, expose snapshot API | M |
| C-205 ✎ | kill runtime `index.json` fetch in orchestration `tools.py`; read snapshot instead | M |

### SM-3 Scheduler + deployment store — *milestone: M-3 · gate: transition-table suite incl. reap/requeue/cancel/stale-fence races; crash-recovery test* (SUPERVISOR CORE: Manni; PlusCal in parallel)

| C-301 | A6 Postgres store: CAS transitions, SKIP LOCKED claim, pooled connections | L (Manni) |
| C-302 | dispatch client: idempotent-accept, deadlines, backoff, circuit breaker, jitter | L (Manni) |
| C-303 ✎ | transition-table data + table-driven test harness (Manni writes table; student builds harness + cases) | M |
| C-304 ✎ | Prometheus `/metrics` on the Core: queue depth, claim latency, reap rate, tolerance-failure rate | M |
| C-305 ✎ | structured JSON logging + `deployment_id` correlation across seams | M |
| C-306 | crash-only recovery path + acceptance-8 test | L (Manni) |

### SM-4 Worker `/v1/work` path — *milestone: M-4 · gate: single-leaf end-to-end on one worker unit (iperf leaf, local CTP), fence honored*

| C-401 | `/v1/work` sequence glue: prepare→verify→run→publish; synchronous netgent-runner invocation | L (Jaber) |
| C-402 ✎ | prepare: CTP batch fetch outside shaped ns + skip-if-cached; workflow fetch by pinned sha with mismatch refusal | M |
| C-403 ✎ | probe: 5 s iperf3 ×2 + 10 pings + drain; tolerances from A5 into `/shape`; scoped verification fields in A9 | M |
| C-404 ✎ | per-iteration durable completion + `start_iteration` resume | M |
| C-405 ✎ | stage timestamps on all transitions; prepare-phase liveness responses | S |
| C-406 | fence self-termination (kill replay+workflow, reset ns) | L (Manni) |

### SM-5 Telemetry hardening — *milestone: M-5 · gate: duplicate-envelope and stale-fence rejection tests*

| C-501 ✎ | upsert on `(spec_hash, deployment_id, iteration, attempt)` migration + tests | M |
| C-502 ✎ | fence rejection + `?spec_hash=` filter + two-axis set status endpoint | M |

### SM-6 Match + SpecGen + echo — *milestone: M-6 · gate: table-driven accept/reject/backflow suite; echo snapshot tests*

| C-601 ✎ | validators: ranges/enums/dependencies vs pinned snapshot; leaf-workflow-in-pipeline; secrets-in-prerequisites | M |
| C-602 ✎ | lexicon resolution + endpoint allow-list checks | S |
| C-603 | batched clarification round: question synthesis from unresolved prerequisites; answer type-validation | L (Jaber) |
| C-604 ✎ | provenance sidecar (JSON Pointer map) derived at Match | M |
| C-605 ✎ | plain-language echo renderer + itemized-defaults listing + sweep-axis enumeration (golden text fixtures) | M |
| C-606 ✎ | SpecGen: pin capability hashes + workflow shas; compute ids; RFC 9457 error responses; `/v1` prefix + pagination | M |
| C-607 ✎ | LLM binding: `openai_compatible` provider + validate-retry-once (anthropic path exists) | M |

### SM-7 CLI — *milestone: M-7 · gate: acceptance criterion 1 scripted in CI (compose harness)*

| C-701 ✎ | `pramana run`: client-side `sweeps:` expansion incl. S4 CTP query; submit; exit codes (3 = backflow) | M |
| C-702 ✎ | `pramana init` + `doctor` (config wizard, secrets scaffold with 0600 enforcement, image/pool/KB checks) | M |
| C-703 ✎ | `status`/`cancel` with `--json`; `--yes`/`--answers-file` non-interactive | M |
| C-704 ✎ | `examples/` spec set (iperf sweep, wget CCA compare, zoom class) + docs | S |
| C-705 ✎ | acceptance harness: compose profile, criteria 1 & 3 in CI; recorded-LLM replay for criterion 2 | M |

### SM-8 T2 (committed, existing transport) — *milestone: M-8 · gate: acceptance criterion 4*

| C-801 ✎ | SG hard-fail on unknown IP + `refresh-ingress` op (both already filed as bugs) | M |
| C-802 | pool-of-EC2 path through scheduler (persistent instances, not per-spec) | L (Manni) |
| C-803 ✎ | T2 acceptance script (single elastic worker, envelope + artifact pull) | M |

### SM-9 Verification fast-follows — *milestone: M-9*

| C-901 ✎ | CTP realized intensity/burstiness during replay, measured-vs-declared in A9 | M |
| C-902 ✎ | per-worker tolerance-failure-rate alarm off `/metrics` | S |

## Sequencing & staffing snapshot

Critical path: SM-1 → (SM-2 ∥ SM-3) → SM-4 → SM-5 → SM-6 → SM-7; SM-8/9 trail.
Week 1: Jaber writes SM-1 suites; students take C-101/102/105/106 immediately.
Manni: PlusCal + C-301/302. Persistent students: continuity on SM-1 and SM-4.
~29 undergrad-suitable cards ≈ 8–10 student-weeks of S/M work → fits 3–4
rotating students over 6–8 weeks with slack. Evidence path (Zoom/HotNets data)
remains frozen and untouched by every card (E1); nothing here gates the papers.
