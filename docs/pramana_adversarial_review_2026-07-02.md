# Adversarial Review Register — 2026-07-02

Three independent adversarial reviews of the Pramana spec suite (architecture,
interfaces, abstraction, lineage): **A** = academic rigor (19 findings), **U** =
underspecification (25), **H** = hallucination red-team (15). Dispositions:
**FIXED** (doc edited same day) · **RESOLVED** (normative resolution recorded here;
schema/implementation follows) · **ACCEPTED** (real limitation, now stated) ·
**REJECTED** (with reason).

## A — Academic rigor

| # | Sev | Finding | Disposition |
|---|---|---|---|
| A1 | fatal | RabbitMQ scope contradicted 4× across docs | **FIXED**: §6.2/§6.3 rewritten to three bindings; D3 marked superseded-in-scope by R3+I2 |
| A2 | fatal | CCA both "not a regime knob" and in `static:` | **FIXED**: CCA is declared in static context (experiment identity, substrate-applied at the endpoint) but is *not* a property of the bottleneck; abstraction sentence corrected |
| A3 | fatal | Dispatch direction specified both ways (pull rule vs direct binding) | **FIXED**: A7/A8 are per-binding; interfaces rule 3 scoped to NAT tiers; direct binding = scheduler-initiated |
| A4 | fatal | "Closed-world generation" falsified by own examples (extracted values, PMR=2) | **FIXED**: §1.3(1) restated — enumerable fields closed-world; free-form fields type/range-validated or allow-listed or backflowed; fuzzy-quantifier mappings live in a versioned lexicon file |
| A5 | major | `collect = deploy ∘ verify ∘ replay ∘ publish` backwards, omits workflow run | **FIXED**: sequencing notation `deploy ; prepare ; verify ; run ; publish` |
| A6 | major | Experiment identity: Node/iterations inside the hash breaks cross-tier dedupe | **FIXED**: identity = H(workflow@sha, params, static, dynamic); nodes/mapping/iterations/attempts are execution annotations outside identity |
| A7 | major | CTP "closed algebra" misattributed to NetForge; select conflated with algebra | **FIXED**: `select : criteria → ℘(corpus)` separated; closure over {transform, merge} cited to ctp-service code, not the paper; filtering=select / trimming=transform corrected |
| A8 | major | Philosophy sentence false (LLM runs at run time); compile() not the only model site | **FIXED**: "above the waist, never below it"; compile() = the only *per-request* model site; authoring-time model use named |
| A9 | major | Sweep semantics undefined; example violates one-CTP-per-leaf | **FIXED**: `sweep : Experiment × dim → ExperimentSet` production added; `CTP.select(n=100)` defined as sweep generator; one CTP per leaf |
| A10 | major | `persistence: iteration` contradicts taxonomy "no teardown between iterations" | **FIXED**: taxonomy amended to "no teardown by default; persistence override for isolation-critical studies" |
| A11 | major | vs_netunicorn recommends worker-polls-scheduler its companion forbids | **FIXED**: recommendation scoped to T1/rendezvous framing |
| A12 | major | `mapping : pipelines → nodes → connectors` matches no artifact | **FIXED**: `mapping : nodes → connectors`; leaf workflow must appear in target node's pipeline (validation rule) |
| A13 | major | Grammar lacks secrets/telemetry/verify/clarification-fixpoint | **FIXED**: `ExperimentSet = fix(λA. compile(Intent, A))`; leaf carries telemetry+verify; secrets late-bound |
| A14 | major | `Node = …take(n)` doesn't typecheck; second endpoint smuggled via params | **FIXED**: `Nodes = pool.filter.take(n)`, `Node ∈ Nodes`; `Roles = ⟨client, server?⟩` in the experiment production; ⊗ defined |
| A15 | major | "~100 apps" is 6× overclaim (registry has 16) | **FIXED**: real number stated |
| A16 | minor | "Planes appear nowhere in papers" false (NetForge uses them) | **FIXED**: note corrected — retired *for Pramana* to avoid conflation |
| A17 | minor | Laptop pool default 10 exceeds measured ~8 regime ceiling | **FIXED**: default = min(cores−2, 8); ceiling published as node attribute |
| A18 | minor | T1 "no API key" vs NL door needing a model | **FIXED**: keyless T1 = spec-direct path (+ shipped example specs); NL door needs key or local model — stated |
| A19 | minor | Terminology drift (pipeline, context, iterations) | **RESOLVED**: normative glossary to be added to interfaces doc; one term per concept |

## U — Underspecification

| # | Sev | Resolution (normative) |
|---|---|---|
| U1 | blocker | Assignment is **advisory-with-affinity**: claim returns pre-assigned items first, falls back to any attr-match after staleness threshold; scheduler rewrites `deployment.node` on claim |
| U2 | blocker | Reap ⇒ requeue with `attempt += 1` (cap 2); iterations restart from 1; A6+A9 carry `attempt`; analysis dedupes on it |
| U3 | blocker | Secrets: values transit in-memory in WorkItems over TLS; never persisted server-side, never logged, scrubbed from A6/A8/A9; ownership table amended |
| U4 | blocker | A3 params gain `flag/positional/arity`; worker execution = argv construction from param dict |
| U5 | blocker | A5 is **flat/fully-expanded**; client-side `sweeps:` block expanded by `pramana run` before submission |
| U6 | blocker | One CTP per leaf; a list requires `len(ctp)==iterations` (i-th iteration ↦ i-th pointer); list participates in hash |
| U7 | major | Experiment id = hash of canonical-JSON leaf minus secrets/mapping (in `shared/models`); UUID format retired |
| U8 | major | Telemetry upserts on `(spec_hash, deployment_id, iteration, attempt)` — at-least-once wire, idempotent sink |
| U9 | major | S3 PUT = durability point; idempotent importer; objects persist until ingest-marker written |
| U10 | major | `stage: service_ready` = mandatory A8 event emitted by service-role workflows post-launch-check; scheduler gates dependents on it |
| U11 | major | Unit grammar defined once in `shared/models`; canonical numeric fields; explicit `capacity_down/up` |
| U12 | major | Node `pipeline:` = must-be-able-to-run constraint (prefetch/attrs); leaf `application.workflow` executes; validator rejects out-of-pipeline leaves |
| U13 | major | = A2 (CCA in static context; abstraction sentence fixed) |
| U14 | major | "Worker unit" = {substrate + browserless + netgent-runner} ns-sharing trio; `count` counts units; `browser` attr iff sidecars present |
| U15 | major | `POST /experiment-sets/{id}/cancel`; cancel directive on next heartbeat response; A6 gains `cancelled` |
| U16 | major | Set status = two axes: `execution: done` (scheduler) + `ingested: n/m` (telemetry); CLI reports complete when both close |
| U17 | major | Bootstrap order: config-validate → image ensure → pool deploy → KB ingest; capability+core-workflow snapshot bundled in images for offline T1 |
| U18 | major | = A17 (default ≤ 8) |
| U19 | major | A5 YAML is the sole normative artifact; Python API illustrative; `pramana run` resolves CTP criteria client-side (deterministic S4 query) |
| U20 | major | Probe = 5 s iperf3/direction + 10 pings, after net-setup, strictly before capture, 2 s drain gap; A5 tolerances flow into `/shape`; A9 records requested+applied |
| U21 | minor | Defaults table (in `shared/models` config): poll 5 s; prepare timeout 10 min; experiment timeout = 3×duration+120 s; CTP batch 100; importer poll 30 s; clarification round cap 5 |
| U22 | minor | v1 schedules at **set granularity** (one set drains before next starts) — only reading under which recycling policy is coherent |
| U23 | minor | `$ASK_USER` legal only pre-compile; A5 node params are literals or `$secrets.<key>` |
| U24 | minor | SpecGen pins `workflow@sha` + capability-file version hashes into A5 at compile; workers fetch exactly that sha; sha in identity hash |
| U25 | minor | Scheduler is the **single writer** of A6, folding A8 stages via a published transition table |

## H — Hallucination red-team

| # | Sev | Defense adopted |
|---|---|---|
| H1 | critical | Free-form endpoint fields (URL/host/IP) resolve against an allow-listed catalog in the capability file **or force backflow**; never accepted as closed-world |
| H2 | critical | Provenance ≠ fidelity: add **intent echo** — plain-language re-rendering of the compiled spec diffed against the intent; semantically-loaded fields require explicit acknowledgment |
| H3 | critical | Capability files are **human-signed artifacts** (schema-of-schemas validation + diff-review gate); a model may draft, never sign — the oracle is never model-authored |
| H4 | critical | Workflow repo entry gate: golden-trace replay + human review + content-hash pinning with reviewer provenance; "deterministic" bounds variance, not correctness — the gate supplies correctness |
| H5 | critical | `verified` is **scoped, never blanket**: A9 records which regime factors were verified (envelope) vs not (application-level, CCA negotiation via observer/qtrace where available, CTP realization) |
| H6 | major | Match may only ask questions for prerequisites declared in signed capability files; answers schema-validated before earning `user_answer` provenance |
| H7 | major | API-direct specs pass the same schema+capability gate; fields marked `provenance: external_unverified` |
| H8 | major | Defaults escape hatch surfaces a loud itemized "these N fields were guessed" confirmation — never silently folded into trusted provenance |
| H9 | major | Sweep axes surfaced as enumerated realized value lists for confirmation; sweep operator recorded as provenance-bearing derivation |
| H10 | major | CTP availability below spec-declared floor ⇒ backflow/hard-fail; realized-CTP-count recorded in A9 |
| H11 | major | = U24 (spec pinned to capability version hashes; workers refuse hash mismatch) |
| H12 | major | Secret keys resolvable only from the workflow's capability-declared prerequisite set; namespaced keys |
| H13 | major | = H2 (plain-language echo is the surfacing mechanism for the SIGCSE audience; raw YAML is not a gate) |
| H14 | minor | Dedupe hash computed over canonicalized fully-defaulted spec; pre-image logged |
| H15 | minor | Worker computes realized CTP intensity/burstiness during replay, asserts against descriptors, records measured-vs-declared in A9 |

## Residual accepted limitations (stated, not solved)

1. Intent→Spec fidelity has no formal verification — the echo (H2) is a UX
   mitigation, not a proof; this remains the open layer per `verification_gap.md`.
2. NetGent UI drift at replay time: fail-the-experiment vs invoke-repair semantics
   unspecified; **v1 = fail and flag** (no runtime LLM repair — R5/§1.3).
3. Inhabited-mode (wireless/LEO/cellular) deployments are designed-for but
   unevaluated.

## G — NotebookLM grounding pass (primary sources, same day)

Sources added to notebook `survey-agentic-systems-research`: Mininet (HotNets '10),
Mininet-HiFi (CoNEXT '12), NetForge v3 (arXiv:2507.13476), NetGent
(arXiv:2509.00625v2), netUnicorn full text (arXiv:2306.08853 — the prior source
was abstract-only). Claims checked with quote-demanding queries:

| Claim (doc) | Verdict |
|---|---|
| Mininet-HiFi made fidelity a monitored per-run property | **Confirmed** (§3.4: inter-dequeue times, CPU idle, "necessary conditions"). Caveat: the paper never says "network invariants" — do not use that phrase. |
| netUnicorn reports at pipeline end, "best-effort" fidelity | **Confirmed verbatim** (§4.2). |
| netUnicorn 17–35 vs 113–237 LLoC (5–13×) | **Confirmed** (Table 5, §6.2). |
| netUnicorn pull-based executors | **Attribution corrected**: pull semantics are the *implementation's* (executor polls gateway); the paper says instructions are "shipped" and motivates the gateway via "intermittent network connectivity" (App. H). |
| NetForge regime = static envelope + congestion-pressure process | **Confirmed verbatim** (§2.2). |
| Filtering=`select()` / trimming=`transform()` | **Confirmed verbatim** (§4) — validates fix A7. |
| "NetUnicorn separates where… NetForge separates the bottleneck regime…" | **Confirmed verbatim** (§3.1). |
| NetForge §4 uses intent/representation/execution planes | **Confirmed** — validates fix A16. |
| ~8 parallel regimes before netem degradation | **Confirmed in v2 only** (§5.5/A4: "eight parallel tasks", JSD < 0.14; limiting factor = "kernel scheduling in netem", not "timer granularity" — wording corrected in spec + abstraction). Not present in v3. |
| NetGent compiles NL rules → NFA; LLM-free cache-first replay | **Confirmed verbatim** (abstract + cache-hit/miss passage). |
| NetGent application count | **Corrected**: paper claims "50+ workflows spanning five domains"; public registry holds 16. Both numbers now stated (supersedes the bare A15 fix). |
