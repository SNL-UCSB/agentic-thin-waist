# HotNets 2026 Paper Outline

**Working Title:** The Verification Wall: Why Agentic Research Needs a Composable Empirical Backend

**Format:** 6-page vision paper (HotNets)
**Core argument:** Every agentic system assumes its evaluation substrate exists. None builds it as a composable, agent-callable service. The thin waist is the missing infrastructure layer.

---

## Section 1: Introduction (~1 page)

**Opening hook:** AI agents are designing scheduling algorithms that match human experts (Glia: 42.5% improvement in 2 hours vs. 2 weeks), producing peer-reviewed workshop papers (AI Scientist v2: scores 6/7/6 at ICLR), and discovering the first improvement to Strassen's algorithm in 56 years (AlphaEvolve). But strip away the evaluation substrate, and agents produce hypotheses into the void.

**The verification wall:** Every success story has a hidden dependency — a domain-specific evaluation substrate that someone spent months or years building:
- Glia needs Vidur (LLM inference simulator)
- AlphaEvolve needs Google's evaluation harnesses
- Confucius needs Meta's decades of internal tooling (NAPT, ODS, Robotron)
- AI Scientist needs Python + PyTorch + GPUs (and still fails 42% of the time)

**The problem for networking:** Reproducing a single IMC paper requires weeks of manual infrastructure setup. Each new question demands a bespoke pipeline. Innovation is bottlenecked not by ideas but by experiment overhead.

**Thesis:** A *composable empirical backend* — a thin-waist service layer that decouples research intent from evaluation substrate — is the critical missing infrastructure for the agentic era. We argue this is not a domain-specific solution but a fundamental architectural requirement, and we demonstrate it concretely for networking.

**Contributions:**
1. A landscape analysis showing the verification wall across 5 threads of agentic systems research
2. A first-principles architecture (the thin waist) derived from cross-domain convergence
3. A working prototype and initial evidence from paper replication

---

## Section 2: The Verification Wall (~1.5 pages)

**Framing:** Organize the landscape into 5 threads (from full_synthesis.md), each with a different relationship to its evaluation substrate.

### 2.1 The Landscape (compact table)

| Thread | Representative Systems | Evaluation Substrate | Who Built It? |
|--------|----------------------|---------------------|---------------|
| Design Optimization | Glia, Engram, PolicySmith | Vidur sim, kernel sandbox, trace sims | Domain experts |
| Evolutionary Search | AlphaEvolve, FunSearch, SkyDiscover | Google harnesses, benchmark functions | Platform teams |
| Network Operations | Confucius, NIKA | Meta production tools (2+ yrs), curated benchmarks | Decades of infra |
| Full-Loop Research | AI Scientist, POPPER, Agent Lab | Python/PyTorch/GPUs | Open-source community |
| **Empirical Infrastructure** | **netUnicorn, NetForge** | **Builds the substrate itself** | **This work** |

**Key observation:** Threads 1-4 *consume* evaluation substrates. Thread 5 *builds* one. Only Thread 5 addresses transferability.

### 2.2 What Happens Without the Substrate

Three failure modes, grounded in quantitative evidence:

1. **Hallucination and fabrication.** AI Scientist: hallucinated numerical results, placeholder text. Confucius: fabricates responses when data sources are inadequate — violates fail-early principle.

2. **The coherence ceiling.** Engram: context degradation over long horizons. Confucius: specific constraints (e.g., "packet loss between 7-8pm") lost as troubleshooting steps grow. Without persistent grounding in empirical data, agents lose track of what they've learned.

3. **Domain locking.** netUnicorn: ML models fail to generalize across network environments because training data is "unrealistic or poor-quality." NetArena: static benchmarks suffer from contamination and high variance. FunSearch: works only when "rich scoring feedback" exists — fails at theorem proving.

**The punchline:** Barbarians at the Gate (Cheng, Stoica et al.) names this precisely: ADRS "crucially assumes the existence of a reliable verifier." We argue the verifier is the bottleneck, not the agent.

---

## Section 3: A First-Principles Architecture (~1.5 pages)

### 3.1 Four Invariant Components

Synthesized across all systems in the corpus:

1. **Planner** — hypothesis generation, experiment design (Glia's Reasoner, Confucius's DAG planner)
2. **Experimenter** — bridges plans to executable actions (netUnicorn's task disaggregation)
3. **Verifier** — provides empirical feedback (the thin waist)
4. **Knowledge Base** — accumulates insights across runs (Engram's Research Digest)

### 3.2 Where the Thin Waist Emerges

Following Beck's formal theory: a spanning layer "sufficient for necessary applications but as weak as possible" maximizes deployment scalability. The thin waist sits at the **interface between intent and execution** — standardized specifications that decouple what to investigate from how to execute it.

Evidence of convergence:
- netUnicorn: hourglass model as thin waist for data collection
- Confucius: three DSLs (TML, ODS, Robotron) as thin waist for network management
- SED-ML: five-component experiment specification as thin waist for computational biology
- CWL: "reduced set of abstractions used in practice and implemented in many systems"

### 3.3 The Three-Layer Stack

```
Layer 1: AGENT HARNESS (Glia, AI Scientist, SkyDiscover, Claude Code)
         ↕ skills, tools, MCP
Layer 2: EMPIRICAL BACKEND (thin-waist services)
         ↕ instrument APIs, DSLs
Layer 3: DOMAIN INSTRUMENTS (tc, tshark, pgbench, EPICS)
```

**The empirical backend is the middle layer.** It provides composition, safety, and reproducibility that the agent harness lacks and raw instruments can't provide alone.

### 3.4 Cross-Domain Convergence (figure/table)

The same pattern appears independently:

| Domain | System | Thin Waist |
|--------|--------|------------|
| Networking | Agentic Thin Waist | Experiment API |
| Chemistry | ChemOS 2.0 | Fog computing kernel |
| Accelerators | Osprey (LBNL) | Plan-first orchestrator |
| Materials | INTERSECT (ORNL) | Pub-sub message layer |
| Biology | SED-ML | XML schema |

This convergence suggests the composable empirical backend is not domain-specific but a **fundamental infrastructure requirement** for the agentic era.

---

## Section 4: The Agentic Thin Waist (~1 page)

### 4.1 Architecture

Six composable microservices organized into three planes:

- **Intent Plane:** Experiment API (accepts NL or structured JSON) + Orchestrator (LLM-driven coordination)
- **Representation Plane:** CTP Service (cross-traffic profiles — composable, reusable pressure signals) + Telemetry Service (structured results)
- **Execution Plane:** Substrate Worker (tc/netem traffic shaping) + NetGent Service (deterministic application workflows)

**Key design decisions:**
- **Dumb services, smart controller.** All intelligence in the orchestrator. Every other service is a deterministic executor.
- **No data through the orchestrator.** Substrate workers communicate directly with CTP and Telemetry services. The orchestrator sends messages, never data.
- **Local-first.** `git clone` → `docker compose up` → generating data. Cloud for scale only.

### 4.2 Progressive Disaggregation

NetForge's key contribution: separating bottleneck intent from execution:
1. **Intent vs. mechanism:** what network conditions to create vs. how to create them
2. **Static vs. dynamic:** link capacity/latency/buffer vs. cross-traffic intensity/burstiness
3. **Demand vs. context:** observed traffic patterns vs. original trace provenance

Cross-Traffic Profiles (CTPs) transform passive packet traces into reusable, composable pressure signals. This gives agents a structured vocabulary: "Apply CTP cluster 7 (bursty, 80% utilization) to a 10 Mbps link with 50ms RTT."

---

## Section 5: Initial Evidence (~0.5 pages)

### 5.1 Paper Replication Pipeline

The "killer app": reproduce published measurement papers automatically.

1. Query knowledge graph (2,000+ papers) for papers matching platform capabilities
2. Extract experimental setup (network conditions, applications, metrics)
3. Translate to thin-waist intent specification
4. Execute and collect telemetry
5. Compare against published results
6. Iterate if results diverge

### 5.2 Results (placeholders — to be filled from E1-E4)

- **Coverage:** X of Y candidate papers have experimental setups within the thin waist's current capabilities
- **Reproduction fidelity:** 2-3 papers reproduced end-to-end, with comparison to published results
- **Speedup:** Manual setup took N hours; thin waist took M minutes (headline number)
- **Portability:** Same specification runs on Docker (laptop) and PINOT testbed (60 nodes)

---

## Section 6: Open Questions and Vision (~0.5 pages)

1. **Provenance for agent-driven experiments.** What is the minimal provenance schema? How to track intent → hypothesis → experiment → result → insight → next hypothesis? (PROV-AGENT provides a starting point.)

2. **Safety for infrastructure-touching actions.** How to sandbox experiments that modify kernel state, network config, or physical instruments? Confucius has dry-run validators; most agentic systems have none.

3. **The objective-function construction problem.** Evolutionary methods require well-defined objectives. In research, defining the objective IS part of the research. Can rich telemetry help agents construct their own evaluation criteria?

4. **Self-evolving infrastructure.** Can the backend grow more capable as agents use it — where each experiment enriches the repertoire of tools, skills, and workload profiles?

5. **Towards a universal experiment specification.** Is there a single "SQL for experiments" or must each domain define its own DSL with shared structural patterns?

---

## Figures (planned)

1. **The verification wall table** (Section 2.1) — systems × substrate × who built it
2. **Three-layer stack diagram** (Section 3.3) — agent harness / empirical backend / domain instruments
3. **Cross-domain convergence table** (Section 3.4) — independent emergence of the same pattern
4. **Thin waist architecture diagram** (Section 4.1) — six services, three planes
5. **Replication pipeline** (Section 5.1) — knowledge graph → intent → execution → comparison

---

## Key References (prioritized for citation)

### Must-cite (defining the argument)
- Barbarians at the Gate (Cheng, Stoica et al., 2025) — "reliable verifier" framing, ADRS
- netUnicorn (Beltiukov et al., CCS 2023) — thin-waist origin
- NetForge (Daneshamooz et al., 2025) — progressive disaggregation, CTPs
- Beck "On the Hourglass Model" — formal theory of thin waists

### Must-cite (landscape systems)
- Glia (Hamadanian et al., 2025) — design optimization
- AI Scientist v2 (Yamada et al., 2025) — full-loop research
- Confucius (Wang et al., SIGCOMM 2025) — network operations
- AlphaEvolve (Novikov et al., 2025) — evolutionary search
- Engram (Karimi et al., 2026) — coherence ceiling

### Should-cite (evidence and cross-domain)
- Evaluating AI Scientist (Beel et al., 2025) — 42% failure rate
- PolicySmith (Dwivedula et al., 2025) — instance-optimal heuristics
- NIKA (Cornacchia et al., 2025) — benchmarking gap
- FunSearch (Romera-Paredes et al., Nature 2024) — rich feedback requirement
- ArachNet (Sangeetha et al., HotNets 2025) — reasoning layer
- POPPER (Stanford, 2025) — sequential falsification
- ChemOS 2.0, SED-ML, CWL, Osprey, INTERSECT — cross-domain convergence

---

*Outline produced from: full_synthesis.md, design_principles.md, vision.md, deepening_notes.md, and 3 targeted NLM queries (2026-04-06).*
