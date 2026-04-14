# The Composable Empirical Backend: A Survey of Agentic Systems for Accelerating Research

**A literature synthesis grounded in 30+ papers via NotebookLM, 73+ papers tracked, 48 cross-domain papers analyzed.**

---

## 1. The Agentic Research Loop for Systems

The agentic research loop for systems — termed **AI-Driven Research for Systems (ADRS)** by Cheng, Stoica et al. — represents a fundamental shift from static ML pipelines to dynamic, closed-loop discovery frameworks that "iteratively generate, evaluate, and refine solutions" [Barbarians at the Gate]. While ML pipelines optimize models for generalizability on fixed benchmarks, the agentic research loop is about **synthesizing, refining, and optimizing hypotheses and system designs** — a creative, iterative process where the agent must reason about trade-offs, propose experiments, interpret results, and refine understanding.

Glia (Hamadanian et al., MIT) provides the clearest articulation: it is a "human-inspired multi-agent workflow" where agents specialize in "reasoning, experimentation, and analysis, collaborating through an evaluation framework that grounds abstract reasoning in empirical feedback." Systems research is uniquely suited for ADRS because verification "reduces to running these software artifacts against predefined workloads and measuring performance" — unlike many scientific domains where verification requires physical experiments or clinical trials.

The loop must overcome what Engram (Karimi et al., MIT) calls the **"coherence ceiling"** — where agents suffer from "context degradation over long horizons" or fail to "accumulate knowledge across independent runs." Engram addresses this by decoupling long-horizon exploration from context windows via a persistent "Research Digest" and "Archive."

**Invariant components** of the agentic research loop, synthesized across all systems in the corpus:
1. **Planner** — generates hypotheses, designs experiments (Glia's Reasoner, AI Scientist's idea bank, Confucius's DAG planner)
2. **Experimenter** — bridges abstract plans to executable actions (AI Scientist's code generator, netUnicorn's task disaggregation)
3. **Verifier** — provides empirical feedback (Glia's Evaluation Playground, PolicySmith's kernel sandbox, the thin-waist)
4. **Knowledge Base** — accumulates insights across runs (Engram's Research Digest, Confucius's RAG)

---

## 2. Landscape of Agentic Systems

The corpus organizes into five major threads, each with distinct methodologies and evaluation substrates.

### Thread 1: Design Optimization — "Make this system better"

**Systems:** Glia (MIT, 2025), Engram (MIT, 2026), PolicySmith (HotNets 2025)

Glia employs a Researcher+Supervisor multi-agent loop that mirrors how human researchers work: form hypotheses, run experiments on a simulator, analyze results at the *idea level* (not code level), iterate. Applied to LLM serving, Glia discovered a Head-Room Admission router that achieved 42.5% improvement over baselines in 20 simulations / 2 hours — matching a human expert who took 2 weeks. PolicySmith applies LLM-driven code generation to synthesize instance-optimal heuristics that "integrate directly into the Linux kernel" for congestion control and web caching.

**Evaluation substrate:** Simulators (Vidur for Glia, trace-driven sims for PolicySmith). Always domain-specific, always assumed to exist.

### Thread 2: Evolutionary Search — "Find a better algorithm"

**Systems:** AlphaEvolve (DeepMind, 2025), SkyDiscover/AdaEvolve/EvoX (Berkeley, 2026), FunSearch (DeepMind, Nature 2024)

LLMs function as "semantic mutation operators" within evolutionary loops. AlphaEvolve discovered a Strassen improvement (first in 56 years) and saved 0.7% of Google's worldwide compute via Borg scheduling. SkyDiscover decomposes the loop into four swappable components (Context Builder, Solution Generator, Evaluator, Solution Selector) and achieves 41% cost reduction in multi-cloud data transfer.

**Evaluation substrate:** Benchmark functions, cost models, or production systems with scalar metrics. Always requires a well-defined objective function.

**Key tension with Thread 1:** Engram explicitly challenges evolutionary methods: "Evolutionary methods often remain trapped in local optima by relying on scalar benchmark scores, failing when coordinated multi-step changes are required."

### Thread 3: Intent-Driven Network Operations — "Manage this network"

**Systems:** Confucius (Meta/Harvard, SIGCOMM 2025), NetLLM (SIGCOMM 2024), NIKA (KAUST, 2025)

Confucius decomposes management tasks into DAGs, translating NL to domain-specific languages (TML, ODS, Robotron). Operational for 2+ years at Meta with 60+ applications, saving 17 engineer-hours/week. Three key DSLs serve as a "thin waist" between human-friendly instructions and domain-specific tools.

**Evaluation substrate:** Meta's production network — decades of internal tooling. Not transferable.

**Key lesson for the empirical backend:** Confucius's principle of "leverage existing tools, rather than developing new ones" works for operations but fails for research, where netUnicorn argues existing tools produce "unrealistic or poor-quality datasets."

### Thread 4: Full-Loop Autonomous Research — "Do the research for me"

**Systems:** AI Scientist v2 (Sakana AI, 2025), Agent Laboratory (JHU, 2025), POPPER (Stanford, 2025), Google AI Co-Scientist (Google, 2025)

AI Scientist v2 produced the first fully AI-generated peer-reviewed workshop paper (ICLR 2025 ICBINB, scores 6/7/6) via agentic tree search with an Experiment Progress Manager coordinating four stages: feasibility → tuning → research agenda → ablation. POPPER introduces sequential falsification with Type-I error control for rigorous hypothesis validation.

**Evaluation substrate:** Python + GPU + HuggingFace datasets. Self-contained ML experiments. This fundamentally cannot work for systems/networking research where experiments require infrastructure configuration, traffic generation, and multi-vantage telemetry.

### Thread 5: Empirical Infrastructure — "Build the evaluation substrate"

**Systems:** netUnicorn (UCSB, CCS 2023), NetForge (UCSB, 2025), Agentic Thin Waist (UCSB, 2026)

This thread BUILDS the evaluation substrate that all other threads assume exists. netUnicorn provides the "thin waist" that decouples data-collection intents from deployment mechanisms. NetForge introduces progressive disaggregation: separating bottleneck intent from execution, static structure from dynamic pressure, and observed demand from trace context via Cross-Traffic Profiles (CTPs).

**This is the only thread that addresses the infrastructure layer itself as a research contribution.**

**The vertical trap:** When the infrastructure gap becomes acute, teams build domain-specific testbeds: Pantheon for congestion control, Puffer for ABR, NetSecBed (Bitzki et al., 2026) for cybersecurity dataset generation. These verticals share the same motivations — container-native execution, declarative specs, automated capture, reproducibility — but each serves one community and one application. NetSecBed's 60 attack containers cannot measure application QoE under controlled bottleneck regimes; Puffer cannot generate labeled security datasets. The composable backend subsumes these verticals by providing the shared infrastructure (controlled network conditions, automated capture, structured telemetry) as reusable services that any domain-specific experiment can plug into. The verticals prove the need; the thin waist is the horizontal that eliminates the need to keep rebuilding from scratch.

---

## 3. The Verification Wall

Every agentic system in the corpus hits the same wall: without its evaluation substrate, it cannot ground reasoning in reality.

| System | Evaluation Substrate | Who Built It? | Domain-Locked? |
|--------|---------------------|---------------|----------------|
| Glia | Vidur simulator + GPU cluster | Researchers | Yes — LLM serving |
| AI Scientist | Python + PyTorch + GPUs | Open-source community | Yes — ML training |
| Confucius | Meta production tools (NAPT, ODS, Robotron) | Meta (decades) | Yes — Meta networks |
| AlphaEvolve | Google evaluation harnesses | Google (internal) | Yes — Google infra |
| PolicySmith | Kernel sandbox + trace simulators | Domain experts | Yes — per-domain |
| POPPER | Domain-specific observations | Varies | Flexible but manual |
| **netUnicorn** | **Composable thin-waist** | **Builds the substrate** | **No — domain-general** |
| **NetForge** | **Programmable bottleneck generation** | **Builds the substrate** | **No — any bottleneck** |

NLM synthesis (grounded across all papers):

> "A skeptical systems researcher would conclude that until we have a standardized, composable backend that allows an agent to 'plug in' to any arbitrary network or system environment and begin falsifying hypotheses, agentic research will remain siloed in specific, high-resource domains like LLM inference or hyper-scale data centers."

The verification wall is the bottleneck. **The composable empirical backend removes it.**

---

## 4. Design Tensions

Five fundamental tensions emerge across the corpus:

### Tension 1: Scalar Fitness vs. White-Box Reasoning
- **AlphaEvolve/AdaEvolve:** "Using an evolutionary approach, continuously receiving feedback from one or more evaluators"
- **Glia:** "Unlike prior ML-for-systems methods that optimize black-box policies, Glia generates interpretable designs and exposes its reasoning"
- **Engram:** "Evolutionary methods often remain trapped in local optima by relying on scalar benchmark scores"

**Resolution:** Both are needed. Evolutionary search for well-defined optimization; white-box reasoning for hypothesis-driven exploration. The empirical backend must support both.

### Tension 2: Leverage Existing Tools vs. Build New Substrates
- **Confucius:** "Our key idea is to leverage the numerous existing network management tools, rather than developing new ones"
- **netUnicorn:** Existing methods are "generally ill-suited or even counterproductive"
- **NetForge:** "Bridging this gap requires a data-generation substrate that simultaneously provides controllability, composability, fidelity, and replicability — capabilities existing approaches struggle to achieve simultaneously"

**Resolution:** Operations can leverage existing tools; research must build composable infrastructure. Different problems, different requirements.

### Tension 3: Full Autonomy vs. Human-Guided
- **AI Scientist:** "The first comprehensive framework for fully automatic scientific discovery"
- **Agent Laboratory:** "Human involvement, providing feedback at each stage, significantly improves the overall quality"
- **Confucius:** For "mission-critical tasks," provides "primitives that facilitate frequent human feedback"

**Resolution:** Human-in-the-loop at the intent level (PI selects problems); autonomy at the execution level.

### Tension 4: Monolithic vs. Decomposed
- **Confucius:** "Simply relying on LLMs to handle [complex tasks] in a single step is not effective"
- **Engram:** Decoupling into sequential agents with persistent digest overcomes coherence ceiling
- **netUnicorn:** Composability prevents overfitting to single execution environment

**Resolution:** Strong evidence for decomposed. The thin-waist pattern — narrow interface between diverse intents and diverse substrates — requires decomposition by definition.

### Tension 5: General Code Execution vs. Specialized Playgrounds
- **AI Scientist:** experiments = writing and running Python scripts
- **Glia:** complex systems require specialized Evaluation Playgrounds to "ground abstract reasoning in empirical feedback"

**Resolution:** The empirical backend provides the specialized playground as a composable, agent-callable service — bridging the gap between general code execution and domain-specific infrastructure.

---

## 5. First-Principles Architecture

### The Four Invariant Components

Synthesized across all systems, every agentic research loop requires:

1. **Planner** (Semantic Intent) — idea generation, experimental design, hypothesis formation
2. **Experimenter** (Executor) — bridges abstract plans to executable actions
3. **Verifier** (Evaluation Substrate) — provides empirical feedback; the "reliable verifier" ADRS assumes
4. **Knowledge Base** (Persistence) — accumulates insights across context windows and runs

### The Three Minimal Interfaces

1. **Intent → Representation:** Formal experiment description (DSL, MOP, bottleneck regime spec)
2. **Representation → Substrate:** Executable plan → empirical feedback
3. **Substrate → Digest:** Raw results → distilled insights for next cycle

### Where the Thin Waist Emerges

Following Beck's formal theory ("a spanning layer sufficient for necessary applications but as weak as possible maximizes deployment scalability"), the thin waist emerges at the **interface between intent and execution** — standardized DSLs or specifications that decouple what to investigate from how to execute it.

Evidence:
- netUnicorn: "hourglass model implemented as its thin waist"
- Confucius: three foundational DSLs (TML, ODS, Robotron) allow one agent to interact with hundreds of tools
- NetForge: Cross-Traffic Profiles as composable, reusable pressure signals
- SED-ML: five-component experiment specification (model, change, simulation, data processing, output)
- CWL: "reduced set of abstractions that are both used in practice and implemented in many systems"

The thin waist is a **Minimal Experiment Specification** — a target-agnostic task graph specifying experimental parameters and success criteria without assuming the substrate.

**Critical clarification: the thin waist is the spec layer, not the infrastructure layer.** Heterogeneous substrates (Docker, AWS, FABRIC, ARK, Scamper-instrumented Raspberry Pis, edge nodes) sit *below* the waist. Diverse research intents sit *above* it. The waist is the spec language plus the orchestrator that translates an intent into the subset of substrate operations that satisfy it. Critics frequently confuse the substrate with the waist; this conflation is the source of most "thin waist won't work" objections, which are actually objections to specific substrate choices. Substrates are interchangeable; the waist is what makes them interchangeable.

### Decomposed > Monolithic (Strong Evidence)

| Evidence | Source |
|----------|--------|
| Single-step LLM fails for complex tasks | Confucius |
| Template dependency limits autonomy | AI Scientist v1→v2 |
| Context degradation over long horizons | Engram |
| Safety requires separated plan/execute phases | Confucius, Osprey |
| Composability prevents overfitting to single environment | netUnicorn |

NLM-synthesized vision: "A first-principles agentic research loop is a **decoupled, multi-agent system** that communicates through **standardized DSLs (the thin waist)**, grounds its reasoning in a **reliable evaluation substrate**, and accumulates intelligence in a **persistent research digest** that outlives any individual agent's context window."

---

## 6. Tooling as the Enabling Layer

### The OpenClaw Insight

Alexander Krentsel's OpenClaw deep-dive (Berkeley, April 2026) provides the key reframe: **"implementation abstractions no longer matter — design abstractions do."** The observation that "magic arises from a bundle of very straightforward bits" applies directly to the empirical backend: the value is not in any single tool but in the **composition framework** that makes tools agent-accessible.

### Four Capability Paradigms

OpenClaw identifies four ways to provide capabilities to agents:

| Paradigm | OpenClaw | Empirical Backend |
|----------|----------|-------------------|
| **MCP servers** | Dedicated tool plugins | Substrate Worker API, CTP Service API, Telemetry API |
| **CLI via exec** | Command-line tools | `tc`, `tshark`, `tcpreplay`, `iperf`, `pgbench` |
| **Skills** | In-context text recipes | Experiment templates, workflow specifications |
| **Harness** | Agent runtime itself | Experiment API orchestration layer |

**The empirical backend IS the harness** — it provides the runtime environment where tools, skills, and MCP services compose into executable experiments.

### The Experiment Skill Pattern

OpenClaw's skills — purely text markdown recipes that teach agents *how* to use tools — are the extensibility mechanism for the empirical backend:

- A **"bottleneck-regime skill"** teaches the agent how to compose tc + CTP + tshark for networking
- A **"database-benchmark skill"** teaches it how to compose pgbench + WAL config + pg_stat
- A **"cloud-autoscaling skill"** teaches it how to compose Terraform + load generator + CloudWatch

**The tools change per domain. The skill structure is universal.** Adding a new domain requires a new skill file, not new architecture.

### The Three-Layer Stack

```
Layer 1: AGENT HARNESS (OpenClaw, Claude Code, Glia, SkyDiscover)
         ↕ skills, tools, MCP
Layer 2: EMPIRICAL BACKEND (thin-waist, ChemOS, Osprey, INTERSECT)
         ↕ instrument APIs, DSLs
Layer 3: DOMAIN INSTRUMENTS (tc, pgbench, EPICS, mass spec, GPU cluster)
```

The empirical backend is the **middle layer**. It provides composition, safety, and reproducibility that the agent harness lacks and raw instruments can't provide alone.

---

## 7. Generalization Beyond Networking

### Intent-Mechanism Disaggregation is Universal

netUnicorn's core principle applies across all systems domains:

| Domain | Intent (What) | Mechanism (How) |
|--------|---------------|-----------------|
| Networking | "Test CUBIC at 10Mbps with bursty cross-traffic" | tc/netem, tcpreplay, tshark |
| Databases | "Benchmark OLTP under 10K TPS with skewed access" | pgbench, WAL tuning, query profiles |
| OS/Kernel | "Measure CFS scheduler under 1000 competing threads" | cgroup, stress-ng, perf/eBPF |
| Cloud | "Test autoscaler under diurnal load with 3x spike" | Terraform, load generator, CloudWatch |
| ML Infra | "Profile training at 4 GPUs with gradient compression" | NCCL, PyTorch DDP, CUDA profiling |

### Static-Dynamic Decomposition Generalizes

NetForge's decomposition of bottleneck regimes into static attributes + dynamic pressure has direct analogues:

| Domain | Static Structure | Dynamic Pressure |
|--------|-----------------|-----------------|
| Networking | Link capacity, base latency, buffer, AQM | Cross-traffic intensity, burstiness |
| Databases | Schema, indexes, buffer pool, isolation level | Query arrival rate, transaction mix |
| OS | Kernel config, scheduler params, memory limits | Process workload, I/O bursts |
| Cloud | Instance types, availability zones, topology | Demand patterns, failover events |

### Cross-Domain Analogues

The empirical backend pattern appears independently across scientific domains:

| Domain | System | Architecture | Thin Waist |
|--------|--------|-------------|------------|
| Networking | Agentic Thin Waist | Intent → CTP/Substrate → Telemetry | Experiment API |
| Chemistry | ChemOS 2.0 | Recipe → Instrument drivers → Analysis | Fog computing kernel |
| Accelerators | Osprey | NL → Execution plan → EPICS | Plan-first orchestrator |
| Materials | INTERSECT | AI intent → Message bus → Instruments | Pub-sub message layer |
| HPC | Colmena | AI planner → Task server → Simulation codes | Proactive task queue |
| Biology | SED-ML | Model spec → Simulator → Post-processing | XML schema |

### The Eight Design Principles

Distilled from 48 cross-domain papers:

1. **Intent/Mechanism Disaggregation** — separate what from how
2. **Minimal Spanning Layer** — thin waist as weak as possible (Beck's hourglass)
3. **Federation over Standardization** — federate diverse resources, don't homogenize
4. **Declarative Experiment Specification** — desired state, not step-by-step
5. **Embedded Provenance** — lineage tracking in the execution layer
6. **Fidelity-Aware Substrates** — expose approximations, enable validity reasoning
7. **Composable Microservice Architecture** — domain-specific leaves, domain-agnostic orchestration
8. **CI/CD for Experiments** — version-controlled, containerized, automatically validated

---

## 8. Open Questions and Future Directions

### 8.0 The Constraint Mapping Problem (the central unsolved challenge)

The MVP runs on Docker and AWS — substrates that impose few constraints on what experiments we can express. The interesting research begins when we try to port the same experiment specification onto real edge infrastructure (CAIDA's ARK, FABRIC slices, residential Raspberry Pis, scamper-instrumented home routers) where bandwidth is committed to hosts, kernel-level operations are forbidden, and operators cannot afford to reserve resources per Docker container.

Naïvely "shipping a Docker container to ARK" violates host commitments and is the model that killed Planet Lab and EdgeNet. Naïvely "rewriting every experiment as Scamper-callable code" defeats the point of a thin waist. The research is in designing the abstractions that bridge these worlds:

1. **Formal specification of infrastructure constraints** — what services each node type can host, what policies (rate limits, time windows, kernel access) apply.
2. **A many-to-many service-to-node mapping graph** — for each microservice in the experiment, which node types can host it, and at what cost.
3. **Intent satisfiability checking** — given a user intent and an infrastructure's constraint set, can this experiment run? If not, what is the minimal relaxation that makes it feasible?
4. **Constructive feedback to the user** — when the requested experiment cannot run on the chosen substrate, the orchestrator should explain why and propose alternatives.

**The edge fidelity imperative.** Cloud is convenient and easy to dispatch to. But for many measurement questions, *where* the experiment runs is part of *what* it measures. Running a residential broadband study from AWS loses the very thing the study was about. The thin waist must work on edge nodes — with their constraints — or it becomes irrelevant for the research it claims to enable. (As surfaced in the KC Claffy meeting, 2026-04-10: "Not cracking the code of how we make this work with edge infrastructure is going to be the silent death for this type of idea.")

**Open question:** What is the formal language for expressing infrastructure constraints, and what is the algorithm for computing intent satisfiability against those constraints?

### 8.1 Provenance for Agent-Driven Experiments

PROV-AGENT (ORNL) extends W3C PROV to capture agent-specific constructs — not just data lineage but **decision lineage**: why the agent chose each action. This is critical for trust: when an agent runs 100 experiments and claims a result, the provenance chain must be auditable. Flowcept demonstrates that provenance must be embedded in the execution layer, not bolted on.

**Open question:** What is the minimal provenance schema for agent-driven experiments? How do you track the full chain from intent → hypothesis → experiment → result → insight → next hypothesis?

### 8.2 Safety for Infrastructure-Touching Actions

Confucius provides dry-run, state validators, and human approval for production network operations. Osprey implements multi-layer safety for accelerator facilities. But most agentic research systems (Glia, AI Scientist, SkyDiscover) have no safety mechanisms at all — they assume the evaluation substrate is safe to operate on freely.

**Open question:** What safety guarantees does an empirical backend need? How do you sandbox experiments that modify kernel state, network configuration, or physical instruments?

### 8.3 The Objective-Function Construction Problem

SkyDiscover and AlphaEvolve require a well-defined, computable objective function. But in research, **defining the objective is part of the research.** Glia addresses this partially through white-box reasoning that identifies *what matters*, but the general case — an agent that can define its own evaluation criteria — remains unsolved.

**Open question:** Can the empirical backend help construct objective functions by providing rich, multi-dimensional telemetry that agents can query and reason about?

### 8.4 Self-Evolving Experiment Infrastructure

Krentsel's OpenClaw deep-dive identifies Phase 4 (2026-2027): "Self-evolving systems — agentic system that is given full control of its own implementation and configuration." Applied to the empirical backend, this means an agent that can not only run experiments but **design new experimental instruments** — writing new tc configurations, eBPF programs, or measurement scripts that didn't exist before.

**Open question:** How do you build an empirical backend that grows more capable as agents use it — where each experiment enriches the backend's repertoire of tools, skills, and workload profiles?

### 8.5 The Convergence Hypothesis

The convergence of thin-waist patterns across domains — networking (thin-waist), accelerators (Osprey), chemistry (ChemOS), materials (INTERSECT) — suggests that the composable empirical backend is not a domain-specific solution but a **fundamental infrastructure requirement** for the agentic era. If this convergence is real, we should expect to see standardization efforts around experiment specification (analogous to SED-ML or CWL), tool integration (analogous to MCP), and provenance (analogous to W3C PROV) emerging across scientific communities.

**Open question:** Is there a single "SQL for experiments" — a universal experiment specification language — or must each domain define its own DSL with shared structural patterns?

---

## Vision Statement

> **Autonomous discovery currently hits a "verification wall" where agentic reasoning remains ungrounded because researchers must custom-build monolithic simulators for every new problem. A composable empirical backend is the critical missing infrastructure because it provides a standardized "spanning layer" that allows agents to ground hallucination-prone reasoning in reproducible, physical ground truth across any systems domain. By decoupling scientific intent from heterogeneous substrates, we shift the bottleneck of research from infrastructure engineering back to creative problem formulation.**

---

*Synthesis produced from 39 NLM-grounded sources, 79 tracked papers, 48 cross-domain papers, and primary analysis of Glia, Confucius, AI Scientist v2, SkyDiscover, OpenClaw, Osprey, Flowcept, NetSecBed, netUnicorn, and NetForge. Updated 2026-04-07 with vertical-vs-horizontal framing and NetSecBed positioning. Updated 2026-04-10 with the specification-vs-substrate clarification, the constraint mapping problem as the central research challenge, and the edge fidelity imperative — all surfaced in the KC Claffy collaboration meeting.*
