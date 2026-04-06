# Invariant Matrix: First-Principles Architecture for the Agentic Research Loop

**Source:** NLM cross-corpus synthesis, grounded in 25-source notebook (2026-04-04)

## Four Invariant Components (Domain-Independent)

Every agentic research system requires these four, regardless of domain:

| Component | Function | Examples from Corpus |
|-----------|----------|---------------------|
| **Planner** (Semantic Intent) | Idea generation, experimental design, hypothesis formation | Glia's Reasoner, AI Scientist's idea bank, Confucius's DAG planner |
| **Experimenter** (Executor) | Bridges abstract plans to executable actions; disaggregates intents into tasks | AI Scientist's code generator, netUnicorn's task disaggregation |
| **Verifier** (Evaluation Substrate) | Provides empirical feedback — the "reliable verifier" ADRS assumes exists | Vidur (Glia), Python+GPU (AI Scientist), NAPT/ODS/Robotron (Confucius), **thin-waist** (netUnicorn/NetForge) |
| **Knowledge Base** (Persistence) | Accumulates insights across context windows and runs | Engram's Research Digest + Archive, Confucius's RAG |

## Three Minimal Interfaces

| Interface | What Crosses It | Realization |
|-----------|----------------|-------------|
| **Intent → Representation** | Formal experiment description (DSL, MOP, spec) | Confucius DSLs (TML/ODS/Robotron), NetForge bottleneck regime specs |
| **Representation → Substrate** | Executable plan → empirical feedback | Glia → Vidur, thin-waist Experiment API → Substrate Worker |
| **Substrate → Digest** | Raw results → distilled insights for next cycle | Engram's Research Digest, Telemetry Service contextualized storage |

## The Thin Waist Emerges at Intent-to-Execution

The narrowest, most reusable abstraction layer is the **interface between intent and execution** — standardized DSLs or specs that decouple what to investigate from how to execute it.

Evidence:
- netUnicorn: "hourglass model implemented as its thin waist to simplify data collection"
- Confucius: three foundational DSLs (TML, ODS, Robotron) allow one agent to interact with hundreds of tools
- NetForge: Cross-Traffic Profiles as composable, reusable pressure signals

## Decomposed > Monolithic (Strong Evidence)

| Evidence | Source | Argument |
|----------|--------|----------|
| Single-step LLM fails for complex tasks | Confucius | "Simply relying on LLMs in a single step is not effective" |
| Template dependency limits autonomy | AI Scientist v1→v2 | v1 required human templates; v2 eliminated them via decomposition |
| Context degradation over long horizons | Engram | Decoupling into sequential agents with persistent digest solves coherence ceiling |
| Safety requires decomposition | Confucius | Validation (dry-run, graph validators) only works with separated plan/execute phases |
| Generalizability requires composability | netUnicorn | Prevents overfitting to single execution environment |

## First-Principles Vision Statement (NLM-synthesized)

> "A first-principles agentic research loop is a **decoupled, multi-agent system** that communicates through **standardized DSLs (the thin waist)**, grounds its reasoning in a **reliable evaluation substrate**, and accumulates intelligence in a **persistent research digest** that outlives any individual agent's context window."

## Comparison Matrix (STATE / TIME / COORDINATION / INTERFACE)

| System | STATE | TIME | COORDINATION | INTERFACE |
|--------|-------|------|-------------|-----------|
| **Glia** | Reasoning state across agents | Hours (20 sims → expert-level) | Multi-agent (Researcher+Supervisor) | Evaluation Playground API |
| **AI Scientist v2** | Idea bank + experiment tree | Days (full paper cycle) | Agentic tree search + Experiment Manager | Python script execution |
| **Confucius** | Workflow DAGs + hierarchical memory | Minutes (production queries) | Multi-agent + human-in-the-loop | DSL-mediated tool orchestration |
| **AlphaEvolve** | Solution population (code snippets) | Hours (evolutionary cycles) | Autonomous evolutionary pipeline | Evaluator scalar feedback |
| **PolicySmith** | Instance-optimal heuristics | Hours (search cycles) | Single-agent LLM synthesis | Kernel sandbox / trace simulator |
| **Engram** | Persistent Archive + Research Digest | Days (cross-run accumulation) | Sequential agents with shared digest | Decoupled context windows |
| **AdaEvolve/EvoX** | Adaptive populations + meta-strategies | Hours (100 iterations) | Hierarchical bandit + meta-evolution | Four-component modular loop |
| **POPPER** | Falsification evidence chain | Hours (sequential tests) | Agent-designed experiments | Statistical testing framework |
| **Confucius** | Production network state | Minutes (operational) | Multi-agent + validation + human approval | DSL translation to tools |
| **netUnicorn** | Composable task pipelines | Hours-days (data collection) | Disaggregated intent-mechanism | Thin-waist hourglass API |
| **NetForge** | Bottleneck regime specs + CTPs | Minutes-hours (experiment runs) | Controller orchestrates execution plane | Progressive disaggregation |
