# Osprey vs. Agentic Thin Waist: Code-Level Architectural Comparison

**Date:** 2026-04-07
**Sources:** Thin waist repo (services/, shared/), Osprey repo (als-apg/osprey), genesis-20c analysis

---

## 1. Current State of the Thin Waist

Six services. Three are working (CTP Service ~90%, Substrate Worker ~95%, Telemetry ~85%). Two are partial (Orchestration ~70%, NetGent ~60%). One is a stub (Experiment API ~10%).

**What actually runs end-to-end today:** The orchestration workflow (`orchestration_workflow.py`, 821 lines) can: parse intent → generate experiment specs → run preflight checks (CTP readiness, application support, worker availability) → iterate through specs calling shape → capture → replay → (optional) NetGent workflow → save to telemetry. This is a synchronous, imperative pipeline — no LLM in the execution loop, no state machine, no conditional branching.

**What doesn't work yet:** Experiment API has no persistence (in-memory dict). Intent parsing is 101 lines wrapping a single Claude API call. NetGent execution is behind a feature flag (`ORCH_NETGENT_EXECUTION_ENABLED=0`). No event streaming. No approval workflow. No error recovery beyond catch-all try/except.

---

## 2. Current State of Osprey

Production-grade LangGraph pipeline deployed at ALS (Advanced Light Source, LBNL). 618 Python files. Comprehensive test suite. BSD-3 licensed.

**What actually runs:** NL → task extraction → capability classification → plan synthesis → human approval (LangGraph interrupt) → code generation → static analysis → execution against EPICS → PV readback verification. Full state machine with a central router that re-evaluates after every node. 4-level error recovery (RETRIABLE → REPLANNING → RECLASSIFICATION → CRITICAL). PostgreSQL checkpointing for session persistence. 20+ typed events streamed in real-time. 8 independently configurable LLM roles.

---

## 3. Structural Comparison

### 3.1 Orchestration Architecture

| | Thin Waist | Osprey |
|---|---|---|
| **Pattern** | Imperative pipeline (`run_orchestration()` → sequential function calls) | LangGraph state machine (router → conditional edges → nodes) |
| **Control flow** | Linear: preflight → for-loop over specs → shape → capture → replay → netgent → telemetry | Graph: router re-evaluates state after every node; can retry, replan, reclassify, or terminate |
| **State** | `orch_record` dict, mutated in place, saved to SQLite/Telemetry after each iteration | `AgentState(TypedDict)` with custom reducers for persistence across turns; PostgreSQL checkpointing |
| **LLM integration** | Single Claude call for intent parsing (101 lines). No LLM in execution loop. | 8 LLM roles: orchestrator, code generator, classifier, approval evaluator, etc. LLM is in every node. |
| **Error handling** | try/except per iteration; failed iterations logged, orchestration continues | 4-level severity: RETRIABLE (retry same, max 3), REPLANNING (new plan, max 2), RECLASSIFICATION (new capabilities, max 1), CRITICAL (terminate) |
| **Concurrency** | Sequential for-loop. One experiment at a time. | Async-first. `asyncio.to_thread()` for sync operations. |

**What this means:** Our orchestration is a batch job dispatcher. Osprey's is a reactive agent. These are fundamentally different architectures. We don't necessarily need Osprey's complexity — our experiments are long-running (minutes), not interactive (seconds) — but the error recovery and state machine patterns are worth studying.

### 3.2 Service Decomposition

| | Thin Waist | Osprey |
|---|---|---|
| **Services** | 6 independent Docker containers communicating via HTTP | Monolithic Python process with internal module decomposition (registry, services, connectors) |
| **Discovery** | Docker Compose hostnames (`http://ctp-service:8001`) | Registry pattern (`RegistryManager.get_capability(name)`) |
| **Communication** | Synchronous HTTP (httpx) with polling for async operations | Internal function calls; async/await within LangGraph |
| **Domain instruments** | tc/netem, tshark, tcpreplay, Browserless (subprocess calls from Substrate Worker) | EPICS Channel Access via pyepics (from EPICS connector) |

**What this means:** We made the right call using microservices — it gives us cross-substrate portability that Osprey can't do. But our HTTP polling loops (`_wait_and_stop_capture`, `_run_netgent_workflow`) are fragile. Osprey avoids this entirely because everything is in-process.

### 3.3 The "Thin Waist" Interface

| | Thin Waist | Osprey |
|---|---|---|
| **Intent format** | NL string → Claude parses → `GeneratedExperiment` Pydantic model (capacity_mbps, latency_ms, application, cc_algorithm, aqm_policy, duration_seconds, num_trials) | NL string → task_extraction node → capability classification → `PlannedStep` list (capability, context_key, task_objective, expected_output, success_criteria, inputs) |
| **Execution primitive** | `_build_shape_payload()` → POST to Substrate Worker; `_build_capture_payload()` → POST to Substrate Worker; `_build_replay_payload()` → POST to Substrate Worker | `write_channel(channel_address, value, verification_level)` → EPICS Channel Access |
| **The narrow interface** | Experiment spec JSON (7 fields) → three HTTP calls (shape, capture, replay) | `PlannedStep` → capability node → EPICS read/write |

**What this means:** Our thin waist is the experiment spec. Osprey's thin waist is `write_channel()` / `read_channel()`. Both decouple intent from execution. But our spec is more declarative ("I want 10 Mbps, 50ms latency") while Osprey's is more imperative ("write this value to this PV, then read that PV"). Our approach is better for reproducibility; Osprey's is more flexible.

### 3.4 Safety / Validation

| | Thin Waist | Osprey |
|---|---|---|
| **Pre-execution validation** | `run_preflight()`: checks CTP readiness, application support, worker health. Three boolean gates. | 4-layer: master switch → human-in-the-loop approval (LangGraph interrupt) → limits validation (min/max/step/writable per PV) → write verification (readback) |
| **Runtime validation** | None. If shape/capture/replay fails, the iteration is marked failed. | Pattern detection on generated code (regex-based AST scan). Limits validator wraps `write_channel()`. Readback verification after every PV write. |
| **Approval workflow** | None. | LangGraph interrupt mechanism. Human reviews full plan + generated code. Cannot be bypassed at runtime. |
| **What can go wrong** | Bad experiment spec produces bad data silently. No bounds checking on parameter values. | Code injection via dynamic imports bypassing regex detector. Direct `epics.caput()` bypassing limits validator. Cross-session behavioral drift. |

**What this means:** We have almost no validation. Our `run_preflight()` checks service availability, not parameter validity. Nothing prevents "YouTube at 0.001 Mbps with 10000ms latency" from executing. The knowledge/constraints.md in the integration plan describes constraints that should exist but don't yet.

### 3.5 Observability / Events

| | Thin Waist | Osprey |
|---|---|---|
| **Orchestration events** | `OrchestrationRunRecorder` — a flat list of `(stage, timestamp, iteration, detail)` tuples. 30+ stage enum values. Written to orch_record and saved. | 20+ typed event classes with structured fields (duration_ms, success, cost_usd, tokens, etc.). Streamed via `astream(stream_mode="custom")`. Multi-mode: events, LLM tokens, state updates. |
| **Experiment telemetry** | Telemetry Service stores results with `contextual_tree` (c_app, c_bottleneck, c_ctp). Artifacts (PCAP, HAR) stored in MinIO/S3. | EPICS connector logs every PV write with channel, value, verification result. Full code generation/execution audit trail via events. |
| **Cross-session** | `OrchestrationStore` saves each orchestration run. No cross-run analysis. | PostgreSQL checkpointer saves full LangGraph state per session. No cross-session aggregation (this is the gap AEGIS addresses). |

**What this means:** Our `OrchestrationRunRecorder` is the right idea — it's a provenance trail. But it's flat strings, not typed structured events. Osprey's typed event system is what ours should evolve into.

---

## 4. What to Learn from Osprey

### 4.1 ADOPT: Typed Event System

**Osprey pattern:** Every significant operation emits a typed event with structured fields.

```python
# Osprey: events/types.py
class CodeGeneratedEvent(BaseEvent):
    code: str
    attempt: int
    success: bool
    language: str

class PhaseCompleteEvent(BaseEvent):
    phase: str
    duration_ms: float
    success: bool
```

**Our current state:** `OrchestrationRunRecorder` records flat tuples:
```python
recorder.record(OrchestrationStage.BOTTLENECK_CONFIGURED, iteration=iteration_index)
```

**What to do:** Define typed event classes for our pipeline stages. Fields should include duration_ms, success/failure, the actual payloads sent/received (shape config, capture params, CTP resolution). This costs a day of work and immediately enables: (a) structured logging, (b) performance profiling, (c) automated anomaly detection, (d) the provenance chain from intent to result.

**Priority: HIGH.** This is low-effort, high-value.

### 4.2 ADOPT: Structured Error Recovery

**Osprey pattern:** 4-level error severity with different recovery strategies per level. Router re-evaluates after every node and can retry, replan, or reclassify.

**Our current state:** Single try/except per iteration. Failed = failed. No retry. No replan.

```python
# Our code: orchestration_workflow.py line 593
except Exception as exc:
    item["status"] = "failed"
    item["error"] = str(exc)
    lifecycle.mark_failed(str(exc))
```

**What to do:** At minimum, add retry logic for transient failures (substrate worker timeout, HTTP 503). The Substrate Worker already has health checks — use them to distinguish transient vs. permanent failures. Don't need Osprey's full 4-level system; 2 levels (retriable vs. fatal) would be sufficient.

**Priority: MEDIUM.** Matters when running batches of 50+ experiments where a single transient failure shouldn't abort everything.

### 4.3 ADOPT: Connector Abstraction for Cross-Substrate Portability

**Osprey pattern:** `ControlSystemConnector` ABC with `EPICSConnector` and `MockConnector` implementations. Swap via config: `control_system.type: "mock"`.

**Our current state:** `DownstreamClients` in `executor.py` hardcodes HTTP URLs to Docker services. No abstraction for running against different substrates.

**What to do:** The vision.md mentions a "connectivity manager abstraction" for Docker/PINOT/AWS/ESnet. This is the same pattern as Osprey's connector. Define an ABC for substrate operations (shape, capture, replay) and implement DockerSubstrate, PINOTSubstrate, etc. The `MockConnector` pattern is also valuable for testing — we should have a `MockSubstrate` that returns synthetic results without requiring tc/tshark.

**Priority: HIGH** for the HotNets portability demo (E3).

### 4.4 STUDY: Approval Workflow for High-Stakes Operations

**Osprey pattern:** LangGraph interrupt mechanism. Human reviews full plan before any hardware action. Cannot be bypassed.

**Our current state:** No approval workflow. Orchestration dispatches directly.

**What to do:** Not needed now — our experiments are low-stakes (emulated networks, not production hardware). But if/when the thin waist controls real testbed infrastructure (PINOT, ESnet), an approval gate before `shape` makes sense. Study Osprey's `approval/evaluators.py` for the pattern.

**Priority: LOW** now, **HIGH** for production deployment.

### 4.5 STUDY: LangGraph State Machine (for future orchestrator upgrade)

**Osprey pattern:** Central router that inspects state and routes to the appropriate next node. Conditional edges. Custom reducers for selective state persistence.

**Our current state:** Imperative for-loop. No branching. No state machine.

**What to do:** Our current sequential pipeline is appropriate for batch experiment dispatch. But if the orchestrator needs to handle interactive refinement (user says "try lower latency"), clarification loops, or multi-step reasoning, a state machine becomes necessary. The INTEGRATION_PLAN.md (Step 9-10) already describes tool/skill declarations — that's the path toward an agentic loop. When we get there, study Osprey's `graph_builder.py` and router pattern.

**Priority: LOW** now. The imperative pipeline works for MVP.

---

## 5. What NOT to Learn from Osprey

### 5.1 DO NOT ADOPT: Arbitrary Code Generation

**Osprey's approach:** LLM generates Python code → regex-based pattern detection → execution via subprocess. This is their biggest security liability. The pattern detector misses dynamic imports, getattr, exec, subprocess escapes. The limits validator only wraps the approved API path; direct `epics.caput()` bypasses it entirely.

**Our approach is better:** We generate structured configurations (experiment specs), not arbitrary code. The `_build_shape_payload()` function constructs a fixed JSON schema from spec parameters. There is no path from LLM output to arbitrary code execution in our pipeline. **Keep it that way.**

**Rule:** The LLM should produce structured data (experiment specs, parameter selections), never executable code. If we need to generate tc commands, template them from the spec — don't have the LLM write shell commands.

### 5.2 DO NOT ADOPT: Monolithic Architecture

**Osprey's approach:** Everything in one Python process. Registry-based discovery of internal modules. No service boundaries.

**Our approach is better:** Independent Docker containers with HTTP APIs. Each service can be developed, tested, deployed, and scaled independently. The Substrate Worker runs privileged (NET_ADMIN); the CTP Service doesn't need to. The microservice boundary enforces this isolation.

**Osprey can't do cross-substrate portability** because its connector is in-process — swapping from mock to real EPICS is a config change, but deploying on a different facility requires deploying the entire Osprey instance. Our architecture can dispatch the same experiment spec to Docker, PINOT, or AWS by changing the substrate client.

### 5.3 DO NOT ADOPT: 8 LLM Roles

**Osprey's approach:** Orchestrator, code generator, classifier, approval evaluator, response generator, etc. — each independently configurable with different models/providers.

**Our approach is simpler and correct for our use case:** One LLM call for intent parsing. Everything else is deterministic. Experiment generation is `itertools.product()`. Dispatch is HTTP calls. There is no need for an LLM in the execution loop — our experiments are parameterized, not generative.

**Exception:** If/when we add interactive refinement ("these results look wrong, try adjusting latency"), a second LLM role for result interpretation could be useful. But that's Step 12+, not now.

### 5.4 DO NOT ADOPT: Session-Scoped State Only

**Osprey's gap:** Each session is independent. No cross-session aggregation. The PostgreSQL checkpointer stores session state for replay, but nothing correlates across sessions.

**Our Telemetry Service already does better:** Results are stored with `experiment_id`, `application`, `capacity`, `latency`, `cc_algorithm`, `tags`, and full contextual trees. The query API supports filtering across all of these. We can already answer "show me all YouTube experiments at 10 Mbps across all orchestrations." Osprey can't answer the equivalent.

**Keep building on this strength.** The contextual tree (`c_app`, `c_bottleneck`, `c_ctp`) is the right abstraction for cross-experiment analysis.

---

## 6. Revised Synthesis for the Team

Osprey (LBNL's agentic AI for DOE accelerator control, `github.com/als-apg/osprey`, BSD-3) and our thin waist solve the same structural problem — decoupling agent intent from domain instrument execution — but at very different maturity levels and with different design tradeoffs. Osprey is a production LangGraph state machine with 4-level error recovery, typed event streaming, human approval workflows, and 8 configurable LLM roles; our orchestration is an 821-line imperative pipeline that sequentially calls shape → capture → replay → telemetry with a single try/except per iteration. Three things are worth adopting now: (1) **typed events** — replace our flat `OrchestrationRunRecorder` stage tuples with structured event classes that include duration_ms, payloads, and success/failure, which costs a day and immediately enables structured logging and performance profiling; (2) **retriable error handling** — add at least transient/fatal distinction so a substrate worker timeout doesn't kill a 50-experiment batch; (3) **connector abstraction** — define an ABC for substrate operations so the same experiment spec dispatches to Docker, PINOT, or a MockSubstrate for testing, which is the same pattern as Osprey's `ControlSystemConnector` / `MockConnector` swap. Three things to explicitly *not* adopt: (1) **code generation** — Osprey has the LLM generate arbitrary Python that runs via subprocess, and their regex-based safety analysis is trivially bypassable; our configuration-only execution model (structured JSON specs, not code) is inherently safer and we should never allow LLM-generated code in the execution path; (2) **monolithic process** — our microservice decomposition gives us cross-substrate portability that Osprey fundamentally cannot achieve; (3) **multiple LLM roles** — one Claude call for intent parsing is sufficient for our batch-dispatch use case; adding LLMs to the execution loop adds latency, cost, and failure modes with no benefit for parameterized experiments.
