---
title: "Principles for Autonomous System Design: OpenClaw Deep-Dive"
authors: Alexander Krentsel (akrentsel@berkeley.edu, UC Berkeley)
venue: Berkeley Systems gathering, March 30, 2026 (Rev. April 4, 2026)
year: 2026
category: systems-building / architecture analysis
pass: 1
relevance: very-high
---

# [Pass 1] — OpenClaw Architecture as a Lens on Tooling Abstractions

## Key Thesis

**"All systems boil down to LLM calls. The difference is the context provided."** (slide 5)

Progress = increasing "loopiness" — Matryoshka-doll recursion where each layer adds tooling and environment ownership:
- Phase 0: LLMs as next-token predictors (2018-2020)
- Phase 1: Fine-tuned assistants (2022-2024)
- Phase 2: LLM + tool-use as "scoped" agents (2024-2025) — LangChain, AutoGen, CrewAI
- Phase 3: LLM + tool-use + **dynamic tool discovery** as "autonomous" agents (2025-2026) — Claude Code, OpenClaw
- Phase 4 (speculative): Self-evolving systems (2026-2027) — agent controls its own implementation

## OpenClaw Three-Layer Architecture

### Layer 1: Connectors
**Goal:** Interface with the world (how to reach the agent)
- Plugin-based: WhatsApp, Gmail, iMessage, Discord, OpenClaw UI, `<plugin>`
- Reverse-engineers human interfaces (often hacky)
- Two modes: personal phone/email (more context) vs. dedicated (safer)

### Layer 2: Gateway Controller
**Goal:** Route messages, manage state, coordinate system services
- **Key abstraction: "Sessions" as processes**
  - Each session has its own context
  - Run in parallel, separate permissions
  - Inter-session communication enabled
  - Can be sandboxed
  - Multiple sub-agents per session
- **Cron Manager:** scheduled future events — "core magic sauce"
- **Memory Management:** vector-db over past conversations + daily summary docs
- **Session DB:** stores overflow history
- **Configuration:** markdown files (USER.md, SOUL.md, AGENTS.md, TOOLS.md) — all managed/updated by the agent itself

### Layer 3: Agent Runtime
**Goal:** Manage LLM calls, construct context, execute tools, interact with environment
- **Providers:** pluggable LLM backends (GPT 5.4, Opus 4.6, `<plugin>`)
- **Environment:** Claude Code, GCP, exe.dev — anything on the machine
- **Tools:** three types:
  1. Built-in (read, write, edit, grep, exec, web_search, browser, cron, etc.)
  2. MCP tools (user-provided plugins)
  3. LSP tools (auto-generated from codebase — hover, definition, references)
- **Skills:** purely text recipes (AgentSkills standard)
  - Header (3-4 lines, always in context) → Body (fetched on demand) → Linked Files
  - 150 max skills, 30K chars, intelligent filter
  - "For most users, by far the easiest and most effective option"
- Uses **Agent Client Protocol (ACP)** for launching sub-agents like Claude Code

## Four Plugin Types (Extensibility Model)

1. **Connector plugins** — new interfaces (how to reach the agent)
2. **Memory plugins** — different persistence strategies
3. **Tool plugins** — new capabilities for the agent
4. **Provider plugins** — custom LLMs

Plus: skills for guiding tool usage on tasks.

## Critical Observations from Krentsel

### "Implementation abstractions no longer matter. Design abstractions do." (slide 38)
- "Code quality is dead" — "I'd get fired for writing this code at Google"
- What matters: the design of interfaces, extension points, and composition mechanisms
- "Magic arises from a bundle of very straightforward bits"

### Four paradigms for providing capabilities (slide 39)
1. MCP servers — dedicated tooling
2. CLI tooling through `exec` — functionality via command line
3. Skills — functionality through in-context information
4. Harness — functionality through agent runtime itself

**Open question:** which is right for what? "Unclear what should be prompts vs skills vs tools"

### "Strange loops" (Hofstadter reference, slide 38)
- "The agent is becoming the interface for configuring itself"
- "Very close to a flywheel takeoff"

### Inter-agent communication (slide 31)
- Agents communicating via email, exchanging skills
- "Future where expert agents collaborate directly"

## Connection to the Author: Krentsel = SkyDiscover co-author

Alexander Krentsel is listed as a co-author on the SkyDiscover/ADRS work from Berkeley Sky Lab. His OpenClaw deep-dive connects directly to the "Barbarians at the Gate" vision: agentic systems that can discover and compose tools to solve problems autonomously.

---

# [Synthesis] — OpenClaw Abstractions → Empirical Backend Design

## The Tooling Stack as Architecture

OpenClaw's layered architecture (Connectors → Gateway Controller → Agent Runtime) maps directly onto the question of how to build a generalizable empirical backend:

| OpenClaw Layer | Empirical Backend Equivalent | Function |
|---------------|------------------------------|----------|
| **Connectors** | **Intent interfaces** — how researchers reach the backend | NL, API, notebook, CLI |
| **Gateway Controller** | **Experiment orchestration** — sessions, scheduling, memory | Experiment API, cron for long-running campaigns, telemetry DB |
| **Agent Runtime (Tools)** | **Execution primitives** — domain-specific instruments | tc/netem, pgbench, stress-ng, tshark, tcpreplay |
| **Agent Runtime (Skills)** | **Domain recipes** — how to use tools for specific experiment types | "How to set up a bottleneck regime", "How to run an ABR experiment" |
| **Agent Runtime (Providers)** | **LLM backends** for reasoning about experiments | Claude, GPT, Gemini for hypothesis generation |

## Key Design Principles from OpenClaw for the Empirical Backend

### Principle 1: Plugin-everything architecture
Every component in OpenClaw is pluggable (connectors, memory, tools, providers). The empirical backend should follow the same pattern:
- **Instrument plugins** (tc, pgbench, iperf, Terraform) — domain-specific execution
- **Telemetry plugins** (pcap, tcp-info, perf, eBPF) — domain-specific measurement
- **Workload plugins** (CTP profiles, TPC benchmarks, YCSB) — domain-specific load generation

### Principle 2: Skills as the "thin waist" for knowledge
Skills are purely text — they tell the agent *how* to use tools for a task. This is the crucial insight: **the knowledge of how to run an experiment is separable from the tools that execute it.**

For the empirical backend:
- A "bottleneck-regime skill" tells the agent how to compose tc + CTP + tshark for a networking experiment
- A "database-benchmark skill" tells it how to compose pgbench + WAL config + pg_stat for a DB experiment
- The tools are different; the skill structure is the same

### Principle 3: Sessions = Experiments
OpenClaw's "session" abstraction (isolated context, parallel execution, separate permissions, inter-session communication) maps perfectly to experiments:
- Each experiment = a session with its own context and configuration
- Experiments run in parallel (like sessions)
- Results flow between experiments (inter-session communication)
- Sandboxing prevents experiments from interfering with each other

### Principle 4: Cron = Experiment Campaigns
OpenClaw's cron manager enables scheduled, recurring actions. For research:
- Schedule experiment sweeps (run this at 10, 25, 50 Mbps overnight)
- Heartbeat monitoring of long-running experiments
- Automated re-runs for statistical significance

### Principle 5: Configuration-as-markdown, managed by the agent
OpenClaw's USER.md / SOUL.md / AGENTS.md / TOOLS.md pattern — configuration as markdown files that the agent itself manages — maps to experiment metadata:
- EXPERIMENT.md — what this experiment tests
- SUBSTRATE.md — what infrastructure is configured
- RESULTS.md — what was observed
- All managed by the orchestration agent, creating a self-documenting experiment pipeline

## The Four Capability Paradigms Applied to Empirical Backends

Krentsel's four paradigms for providing agent capabilities (slide 39) map directly:

| Paradigm | OpenClaw | Empirical Backend |
|----------|----------|-------------------|
| **MCP servers** | Dedicated tooling plugins | Substrate Worker API, CTP Service API, Telemetry API |
| **CLI via exec** | Command-line tools | `tc`, `tshark`, `tcpreplay`, `iperf`, `pgbench` |
| **Skills** | In-context recipes | Experiment templates, workflow specifications |
| **Harness** | Agent runtime itself | Experiment API orchestration layer |

**The empirical backend IS the harness.** It provides the runtime environment where tools, skills, and MCP services compose into executable experiments. This is what Krentsel calls "the biggest gap" — the custom harness.

## What OpenClaw Gets Right (and What's Missing)

**Right:**
- Plugin-everything design enables extensibility without architecture changes
- Skills separate *knowledge of how* from *mechanism of doing*
- Sessions provide isolation and parallelism for concurrent work
- Agent self-configures through markdown — minimal human setup

**Missing for empirical backends:**
- No concept of **safety/validation** for physical infrastructure actions (Osprey's multi-layer safety)
- No concept of **experiment provenance** (Flowcept's lineage tracking)
- No concept of **composable workload specifications** (NetForge's CTPs)
- No concept of **result contextualization** (thin-waist's Telemetry Service tagging)
- No concept of **reproducibility guarantees** — experiments must produce consistent results

These gaps are exactly what the empirical backend adds on top of OpenClaw's general-purpose agent architecture.

## References from the Presentation

- OpenClaw Architecture, explained — Paolo Palini
- How OpenClaw Works — MintMCP Blog
- OpenClaw Explained — Milvus (comparison table)
- OpenClaw Architecture Deep Dive — TowardsAI (performance tricks)
- AgentSkills standard
- Agent Client Protocol (ACP) — for sub-agent launching
- NanoClaw — lightweight OpenClaw
- PyClaw — 500 lines of Python
- AutoResearchClaw — "Chat an Idea. Get a Paper."
- OpenClaw Medical Skill — 869 curated skills for clinical, genomics, drug discovery
