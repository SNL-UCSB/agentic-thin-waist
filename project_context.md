# Agentic Thin Waist — Project Context

> **Last updated:** 2026-03-29
> **Owner:** Arpit Gupta (arpitgupta@ucsb.edu)
> **Repo:** [github.com/SNL-UCSB/agentic-thin-waist](https://github.com/SNL-UCSB/agentic-thin-waist)

---

## 1. Problem

Progress in networking research depends on data that captures how applications and protocols respond to diverse, time-varying bottleneck conditions. Generating such data systematically remains hard — bottleneck dynamics are simultaneously behavior-defining and execution-dependent, making them difficult to replicate, vary, or reuse across environments. Today, every experiment is a one-off script. There is no composable, reusable substrate that lets researchers describe what they want and get reproducible results.

## 2. Vision

Apply the **hourglass design** from netUnicorn (CCS '23) to network data generation. The "thin waist" is a composable set of services that bridges diverse **research intents** (top of the hourglass) with diverse **infrastructure** (bottom). Researchers describe what they want in natural language; agents orchestrate execution end-to-end.

The platform implements **progressive disaggregation** — separating intent from execution, static from dynamic bottleneck attributes, and trace context from demand structure. This is what makes experiments composable, reproducible, and portable.

The agentic thin waist is the engineering substrate for three papers: **NetForge** (SIGCOMM '26), **BQT+** (SIGCOMM '26), and the agentic systems work building on netUnicorn. Beyond these immediate papers, it is designed as **community research infrastructure** — once deployed on physical testbeds (ESnet, NSF-hosted infrastructure), any researcher can express an intent and generate controlled data without manual orchestration. This enables closed-loop agentic research: synthesize hypothesis → generate data → analyze results → refine. Downstream targets include a **HotNets** paper on agentic data generation (scoped to synthesizing application traffic patterns from network conditions) and a broader **SIGCOMM** paper on cross-application counterfactual QoE analysis.

## 3. Architecture — The Three Planes

```
┌─────────────────────────────────────────────────────┐
│                   INTENT PLANE                       │
│   Researcher's natural-language experiment intent     │
│   → Orchestration Service (Claude + OpenClaw)        │
│   → Experiment API                                   │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│               REPRESENTATION PLANE                   │
│   CTP Service  — extract, select, transform, merge   │
│   Telemetry Service — queryable, tagged results      │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│                 EXECUTION PLANE                      │
│   Substrate Worker — tc/HTB/netem, tcpreplay, tshark │
│   NetGent — NFA-based application workflows          │
│             (browser agent, shell agent)              │
└─────────────────────────────────────────────────────┘
```

### Service → Research-Concept Mapping

| Service | Owner(s) | Research Concept | Paper |
|---|---|---|---|
| **CTP Service** | Jaber (+IIT Delhi) | Representation Plane — CTP storage, extraction, statistical descriptors, cluster filtering, transformation | NetForge |
| **Substrate Worker** | Jaber (+IIT Delhi) | Execution Plane — traffic shaping (tc/HTB/netem), PCAP capture (tshark), replay (tcpreplay), bandwidth/latency verification | NetForge |
| **NetGent** | Eugene (+Jaber) | NFA abstraction — composable, reproducible application workflows (browser-based via Playwright/Browserless, shell-based via subprocess) | BQT+ |
| **Telemetry Service** | Manni | Four-layer contextual tagging (static config, dynamic state, application context, transport details); queryable result storage; S3 artifact management | Cross-cutting |
| **Orchestration Service** | Haarika | Intent parsing (NL → structured experiment), Claude/OpenClaw integration, experiment lifecycle management | Agentic systems / D5 |
| **Experiment API** | Haarika | Cross-service wiring: orchestration → CTP → substrate → netgent → telemetry | Cross-cutting |
| **CI / Infra** | Sylee | GitHub Actions, unified docker-compose, health checks, Black formatting, CONTRIBUTING.md, integration tests | Cross-cutting |

### Key Architectural Decisions (from integration reviews)

- **CTP Service is a database/processing engine only** — it does *not* apply CTPs to links. That is the substrate worker's job. (Sylee's integration question #1, resolved.)
- **Telemetry belongs on the Representation Plane**, not the Execution Plane — it stores finished experiment results on centralized infra alongside CTP Service and orchestration. Only NetGent and substrate worker live on Docker execution infra. (Sylee's integration question #2, resolved.)
- **Single docker-compose** for the entire stack, with per-service health checks and dependency declarations.
- **Shared infrastructure** (PostgreSQL, MinIO/S3, S3 client) lives in `shared/` and the root compose file, not duplicated per-service.

## 4. Demo Target (Original Vision)

> "Compare YouTube QoE (startup time, bitrate, rebuffering) across bottleneck regimes of 10, 25, 50 Mbps with 50ms base latency under CUBIC congestion control."

**End-to-end:** natural language in → stored, queryable results out. This single demo exercises every service and validates the full progressive disaggregation pipeline.

### What This Requires

1. Orchestration parses the NL intent into structured experiment parameters (3 bandwidth regimes × static attributes).
2. CTP Service selects appropriate CTPs matching each regime.
3. Substrate Worker applies traffic shaping and CTP replay for each experiment.
4. NetGent executes a YouTube workflow under each shaped condition, collecting QoE metrics (startup time, bitrate, rebuffering).
5. Telemetry ingests all results with four-layer contextual tags, making them queryable.
6. The researcher can query: "show me YouTube QoE under CUBIC across 10–50 Mbps."

## 5. Current State (Week 4 — March 29, 2026)

### What's solid

- **CTP Service (~85%):** All 7 endpoints implemented (extract, select, transform, merge, replay, list, detail) with PostgreSQL, Pydantic models, and 45+ unit tests. PCAP ingestion pipeline and statistical descriptors are production-quality.
- **Substrate Worker (~90%):** Most mature service — 850+ lines, 11 endpoints. Traffic shaping, PCAP capture, replay, and bandwidth/latency verification all work.
- **Telemetry Service (~85%):** 8 endpoints for result storage, filtered querying, tagging, CSV export, and S3 artifact management. PostgreSQL + MinIO integration solid.
- **CI/Infra:** 8 GitHub Actions workflows, unified docker-compose with health checks, Black formatting enforcement, CONTRIBUTING.md, integration tests (PR #85).
- **NetGent:** Browser agent working via Playwright + Browserless pool. Shell-based agent implemented for ping, iperf, NDT with structured JSON output. Controller API merged. YouTube workflow producing screenshots + HAR files.

### Where it's lagging

- **Orchestration Service (~40–60%):** Lifecycle management added (March 22), intent-to-pcap generation tested without NetGent. NetGent integration PR still in progress. Experiment API was flagged as thin scaffolding (66 lines, in-memory dict) — Sylee noted it could be replaced with a DB table. SQLite fallback being removed in favor of proper DB.
- **Cross-service integration:** Orchestration → CTP → substrate calls are being wired. NetGent ↔ substrate worker connectivity (Browserless ↔ shaped link) still needs finalization. Telemetry ingestion hookup from substrate worker and NetGent not confirmed end-to-end.
- **QoE metric extraction:** Issue #43 (YouTube QoE metrics — startup time, bitrate, rebuffering) is still open and not yet implemented in NetGent.

## 6. Gap Analysis: Demo Plan vs. Original Vision

The demo proposed for March 30 (Jaber's plan) deviates from the original vision in several ways:

| Original Vision | Current Demo Plan | Gap |
|---|---|---|
| **3 bandwidth regimes** (10, 25, 50 Mbps) exercising the parameter sweep | Single regime (6 Mbps shaping, 100ms latency) | Does not demonstrate progressive disaggregation across conditions |
| **YouTube QoE comparison** (startup time, bitrate, rebuffering) as the scientific output | Ping (100 probes) + YouTube (30s watch) as two separate experiments | No QoE metric extraction; no comparison across regimes |
| **Telemetry integrated** — results queryable with contextual tags | Telemetry may demo separately; "zero complaints" but unclear if hooked up | End-to-end telemetry flow not confirmed |
| **Natural language drives everything** — the agent decomposes intent into a parameter sweep | Agent does CTP selection + runs two fixed experiments | Intent decomposition into multiple regimes not demonstrated |
| NL query of results: "show me YouTube QoE under CUBIC across 10–50 Mbps" | Not in demo plan | Query-side of the pipeline absent |

### Core concern

The demo shows individual components working (CTP database, agent-triggered experiments, substrate worker) but does not demonstrate the **progressive disaggregation pipeline** — which is the intellectual contribution. The original demo target was specifically designed so that a single natural-language intent triggers a structured sweep across conditions, with results stored in a queryable telemetry layer. That end-to-end arc is what maps to the paper contributions.

## 7. Team

| Name | Role | Slack |
|---|---|---|
| **Arpit Gupta** | PI / Vision | @Arpit |
| **Jaber Daneshamooz** | CTP Service, Substrate Worker, NetForge architecture | @Jaber |
| **Haarika Manda** | Orchestration Service, Experiment API, agent integration | @Haarika |
| **Eugene Vuong** | NetGent (browser agent, shell agent, NFA workflows) | @Eugene |
| **Manni Moghimi** | Telemetry Service | @Manni |
| **Sylee Beltiukov** | CI/CD, infrastructure, integration testing, architecture review | @Sylee |
| **Satyam Kumar** | Substrate worker endpoints (IIT Delhi) | @Satyam |
| **Snithik Thode** | CTP preprocessing (IIT Delhi) | @Snithik |
| **Walter Willinger** | Advisor | @Walter |
| **Tarun Mangla** | Advisor (contextual dataset design) | @Tarun |

## 8. Downstream Applications

The agentic thin waist is not an end in itself — it is infrastructure for multiple research threads:

- **NetForge (SIGCOMM '26):** Controlled counterfactual data generation across bottleneck regimes.
- **BQT+ (SIGCOMM '26):** Agent-driven application workflow generation with NFA-based composability.
- **Contextual dataset (HotNets → SIGCOMM):** Synthesizing application traffic patterns from network conditions; cross-application QoE divergence analysis using shared condition spines.
- **Digital twins at Argonne National Lab / ESnet:** Using NetReplica + NetGent to generate training data for ML-accelerated surrogate models of network components.
- **NetBurst representations:** Cluster assignments as a bridge between network state and application-specific QoE outcomes.
- **Automated paper replication (collaboration with Sangita):** Using knowledge graphs of measurement papers (SIGCOMM, IMC, CoNEXT, SIGMETRICS) to extract experimental intents, then feeding them into the thin waist for automated reproduction. Sangita's framework handles intent extraction; the thin waist handles data generation. Target: HotNets '26 → SIGCOMM.
- **Community infrastructure (CIRC funding trajectory):** Deploy the thin waist on NSF-hosted testbeds as a service — any researcher expresses an intent, the system generates controlled data. Enables closed-loop agentic research: synthesize hypothesis → generate data → analyze → refine.

## 9. Key Principles

1. **Progressive disaggregation** — intent, representation, and execution are strictly separated. No service should conflate these layers.
2. **Hourglass architecture** — the thin waist (composable services) must support diverse intents above and diverse infrastructure below. No hardcoded experiment logic.
3. **Composability over scripts** — every experiment should be expressible as a composition of service calls, not a bespoke script.
4. **Queryable results** — telemetry with contextual tags is what makes data reusable. Files on disk are not acceptable as an end state.
5. **Agent-first design** — the orchestration layer uses LLMs to decompose natural-language intents. The system should be usable by researchers who never write code.

## 10. Repository Structure

```
agentic-thin-waist/
├── services/
│   ├── ctp-service/          # CTP extraction, selection, transformation
│   ├── substrate-worker/     # Traffic shaping, capture, replay
│   ├── netgent/              # Browser + shell agent workflows
│   ├── telemetry-service/    # Result storage, querying, tagging
│   ├── orchestration/        # NL intent → structured experiments
│   └── experiment-api/       # Cross-service experiment lifecycle
├── shared/                   # Shared clients, S3, DB utilities
├── netforge-setup/           # NetForge deployment (AWS, Docker, distributed)
├── docker-compose.yml        # Unified stack with health checks
├── CONTRIBUTING.md
├── AGENTIC_CODING_GUIDE.md
└── tests/                    # End-to-end integration tests
```

## 11. For New Contributors / AI Coding Agents

When working with this codebase, keep these invariants in mind:

- Each service has a README with: Purpose, Input, Output, Interfaces, and a YouTube MVP example.
- The `shared/` directory contains cross-service utilities (DB clients, S3 client). Services import from here — do not duplicate.
- Docker builds use repo root as context: `docker build -f services/your-service/Dockerfile .`
- All PRs require review from Sylee. Branch naming: `<name>/<service>/<feature>`.
- Tests live with their service in `tests/`. Top-level `tests/` is for integration only.
- Format with `black`. CI enforces this.
