# Grammar v2 — Rationale and Spec-Change Map

**Why this document exists.** The grammar in `PRAMANA_DESIGN_SPEC.md` §2 was
validated against real demand: an intent corpus built by capability-matching the
grammar against **111 experiment sets across 13 published measurement papers**
(gold-verified, gate-checked; see `SNL-UCSB/agentic-replication`
`arpit/intent-corpus/`). Each paper's experiments were extracted, translated into
the grammar, and matched three ways (design capability / current implementation /
Mininet baseline). The match surfaced a small, precise set of places where the
grammar could not express a real intent. This document records those findings,
the resulting grammar changes, and exactly how they change the spec — so the
implementation has a complete target.

**Headline.** The abstraction held up. Of everything the corpus surfaced, there
is **one genuine design refinement (per-flow latency)**, **one principled
re-addition (event-triggered actions)**, and the rest is **interface/notation
tightening**. Two candidate changes were considered and deliberately **not**
made (one rejected, one relocated to intent-extraction). No fundamental design
flaw was found.

---

## Accepted grammar changes

### G1 — Per-flow latency: decouple path delay from the bottleneck (was SR-1)

**Finding.** Prudentia normalizes each competing service to a common 50 ms RTT
by adding a *different* delay per service (§3.1). The grammar carried one
`Static.latency` for the whole regime, so it could not express per-flow delay.

**Principle (the real point).** Latency is a *flow-level* entity: it is the
property of the path to each endpoint. Delay that arises *at the bottleneck from
dynamic congestion* is the bottleneck link's behavior and is already produced by
`Dynamic.pressure`. Bundling propagation latency into the shared `Static`
envelope conflated a path property with a link property — an unprincipled
disaggregation. This is the correct fix, not merely a new knob.

**Change.** Move `latency` out of `Static` and onto each endpoint role.
- `Regime.Static`: `⟨capacity↓↑, latency, queue⟩` → `⟨capacity↓↑, queue⟩`.
- `Roles`: each `Node` gains `added_latency: Quantity?` (per-role one-way path
  delay). A single top-level latency remains accepted as the uniform special
  case (all roles equal) for back-compat.
- Identity: per-role `added_latency` joins the hashed condition context.

**Spec-change map.** `PRAMANA_DESIGN_SPEC.md` §2 (Regime, Roles);
`PRAMANA_INTERFACE_DEFINITIONS.md` `shared/models/spec.py` (`Static` drops
`latency`; `Node` gains `added_latency`) and §8.2 capability
(`added_latency` becomes a per-role knob). **Realization:** tc-netem per veth or
per-egress delay — implementation detail.

### G2 — Structured congestion control (was SR-3; interface tightening)

**Finding.** `cca: str` (flat enum) cannot say *whose* CCA. Cambrian-QUIC's whole
result is that the same algorithm behaves differently across QUIC stacks
(`mvfst`/`xquic`/`quiche`/`chromium`); papers also need CCA parameters
(`cwnd_gain`, `pacing_gain`), feature flags (`HyStart off`, `RFC 8312 off`),
kernel-build qualifiers (BBR@4.15 vs 5.15), and per-flow CCA. This was an
over-simplified field, not a design flaw.

**Change.** `cca: str` → structured, per-role:
```
cca = ⟨ algo, stack?, version?, params?{…}, flags?{…}, build?{kernel?, patch?} ⟩
```
Moves to the per-role `Node` (with G1's latency) so competing flows can differ.
`cca: "cubic"` == `⟨algo:"cubic"⟩` (back-compat).

**Spec-change map.** `PRAMANA_INTERFACE_DEFINITIONS.md` `spec.py` (`cca` becomes
a `Cca` model on `Node`, removed from `Static`); §8.2 capability publishes the
structured surface (supported stacks / param ranges / flags) so a match is
precise: design may admit `(xquic, BBR, cwnd_gain sweep)` while the impl wires
only kernel CCAs — a clean implementation gap.

### G3 — Structured AQM (was SR-4; interface tightening)

**Finding.** `queue: {qdisc, args:str}` — the discipline is already a closed
enum (good), but parameters hide in an opaque, unvalidated `args` string, so they
are not capability-matched or sweepable, and there is no first-class ECN toggle.
CAKE (DiffServ modes) and cclinguist (RED-with-ECN) study the AQM directly and
need it structured.

**Change.** Promote params out of the string; keep `args` as an exotic-knob
passthrough:
```
queue = ⟨ discipline, size?, params?{target, interval, thresholds, …}, ecn?, mode? ⟩
```

**Spec-change map.** `PRAMANA_INTERFACE_DEFINITIONS.md` `spec.py` `Queue` gains
`size`, `params`, `ecn`, `mode`; §8.2 capability publishes disciplines + param
ranges + ECN.

### G4 — Event-triggered actions (was SR-6, generalized)

**Finding.** Papers run *until converged* (Prudentia: 10–30 trials until the 95%
CI is within ±0.5 Mbps; cclinguist). The grammar's `iterations` is a fixed int.

**Principle.** The real gap is the absence of **event-triggered actions** — an
event (a metric threshold, elapsed time, convergence) triggers an action (stop,
capture, mark). netUnicorn had this; Pramana left it out and was never
principled about it. Adaptive stopping is the first and simplest instance.

**Boundary.** Event-triggered actions act *within* a run. Choosing the *next
experiment's* configuration from the last result is strategic search, which
stays *above* the waist (the intent-producer's job), not in the grammar.

**Change.** `iterations = int` → `int | ⟨until: event(metric, target), min,
max⟩`, as the first event/action production. Identity is unaffected: the spec
already excludes `iterations` from the identity payload, so adaptive counts
change nothing about identity, dedupe, or portability. The general event→action
production follows as a design item against the netUnicorn precedent.

**Spec-change map.** `PRAMANA_DESIGN_SPEC.md` §2 (`iterations`);
`PRAMANA_INTERFACE_DEFINITIONS.md` `spec.py` (`iterations: int | StopCriterion`).

### G5 — Multi-endpoint foreground (was SR-7; notation catch-up)

**Finding.** CAKE's host-isolation runs 2 source × 4 destination hosts and the
result is the per-flow goodput of each. The grammar's foreground is one
`Workflow @ Roles⟨client, server?⟩`, so it could not state an n-party foreground
with per-endpoint result attribution.

**This is NOT a capability limit.** The abstraction already maps arbitrary
workflows to arbitrary node sets; the *grammar notation* simply failed to say
so. This is a notation fix, not a new capability.

**Change.** `Experiment` foreground becomes a set:
```
Foreground = Workflow @ role                              (2-party default)
           | { Workflow_i @ role_i } with per-role telemetry   (n-party)
```

**Spec-change map.** `PRAMANA_DESIGN_SPEC.md` §2 (Experiment/Foreground);
`PRAMANA_INTERFACE_DEFINITIONS.md` context/telemetry shape gains per-role result
attribution.

---

## Considered and deliberately NOT changed

Recording these is part of the rationale: they mark the grammar's intended
boundary.

- **Measure-then-configure (was SR-2) — extraction, not grammar.** Prudentia's
  per-flow RTT normalization is "measure each service's native RTT, then set the
  pad." The *result* is per-flow latency (G1, in-grammar). *How the pad values
  are obtained* (a calibration measurement feeding the main experiment) is a
  matter of how intent is extracted from a paper, handled at the corpus /
  intent-extraction layer, **not** a grammar production. No design change.
- **Temporal / scheduled envelopes (was SR-5) — rejected.** NetMicroscope and
  ndt_rr vary the static envelope within a session ("random intervals"). Adding
  scheduled envelope reconfiguration to *create pressure* is the antithesis of
  Pramana's native dynamic-pressure synthesis (`Dynamic.pressure` = trace replay
  + real-app load). Those hacks existed *because* prior tools could not control
  dynamic pressure; Pramana can. Such intents are re-expressed as
  `Dynamic.pressure`; the grammar is **not** extended to reproduce the hack.
- **Closed-loop adaptive search — above the waist.** Iteratively choosing the
  next config from the last result (cclinguist's adaptive walk) is the
  researcher's/agent's exploration logic, which the design places above the
  waist. Building it into the grammar would pull intelligence below the waist.
- **Inhabited / edge reach — connector, not grammar.** Reaching household RPis
  or deployed-service paths is a connector plug-in. Design-general,
  implementation-roadmap; never claim an unrun result.

---

## Spec-change map (summary)

| Change | `PRAMANA_DESIGN_SPEC.md` §2 | `PRAMANA_INTERFACE_DEFINITIONS.md` (`spec.py` + §8.2) |
|---|---|---|
| G1 per-flow latency | Regime, Roles | `Static` −`latency`; `Node` +`added_latency`; cap knob per-role |
| G2 structured CCA | Roles/Node | `cca` → `Cca` model on `Node`, −from `Static`; cap struct |
| G3 structured AQM | Regime | `Queue` +`size,params,ecn,mode`; cap struct |
| G4 event-triggered | `iterations` | `iterations: int \| StopCriterion` |
| G5 n-party foreground | Experiment/Foreground | context +per-role attribution |

## Why this completes the implementation

The corpus turned "design capability vs implementation capability" from a slogan
into a checklist. G1–G5 close every grammar gap the 111-set corpus surfaced;
the remaining deltas are **implementation** items (unwritten NetGent workflow
files; closed-loop `load` co-scheduling; QUIC userspace stacks) that the
capability files already name. With G1–G5 in the spec and the capability files
publishing the structured surfaces, the implementation target is complete and
the design-reach-vs-implementation-reach coverage the paper reports is precisely
computable.
