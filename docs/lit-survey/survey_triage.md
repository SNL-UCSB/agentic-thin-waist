---
topic: Agentic Systems for Accelerating Systems and Networking Research
created: 2026-04-04
last_updated: 2026-04-04
status: in-progress (3/5 core papers read, corpus expansion pending)
---

# Survey Triage: Landscape Map

## Thread 1: Agentic Design Optimization — "Make this system better"

**Core paper:** Glia (MIT CSAIL, 2025)

**Pattern:** Researcher+Supervisor multi-agent loop. Agent reasons about system behavior at the idea level, not code level. Forms hypotheses, runs experiments on a simulator, analyzes results, iterates. Produces interpretable, explainable designs.

**Key systems:** Glia, AlphaEvolve (Google DeepMind), FunSearch, OpenEvolve, Evolution of Heuristics (EoH), ShinkaEvolve, POLICYSMITH

**Evaluation substrate:** Always a simulator (Vidur for LLM serving). The simulator IS the experimental interface.

**Relevance to thin-waist:** Very high. Glia **assumes the evaluation playground exists**. For networking domains, the thin-waist IS the evaluation playground. Glia's Researcher agent could call the thin-waist API instead of shell commands on a simulator repo.

**Gap:** None of these systems build their own experimental infrastructure. They all assume a clean simulator API or codebase exists.

---

## Thread 2: LLM-Driven Evolutionary Search — "Find a better algorithm"

**Core paper:** SkyDiscover / AdaEvolve / EvoX (UC Berkeley Sky Lab, 2025)

**Pattern:** Evolutionary search where the LLM is the mutation/crossover operator. Population of candidate solutions, evaluate on objective function, select and evolve. Well-defined optimization target.

**Key systems:** SkyDiscover, AlphaEvolve, GEPA, AdaEvolve, EvoX, CALM

**Systems-domain results:** MoE load balancing (514ms→55ms), GPU placement (29% KV-cache reduction), multi-cloud data transfer (41% cost reduction via Steiner-like relay trees)

**Evaluation substrate:** Benchmark functions, simulators, or production systems with clear metrics.

**Relevance to thin-waist:** Medium-high. These systems need well-defined objective functions. For networking research, the thin-waist could provide the evaluation function: "run this algorithm on a 10Mbps bottleneck with bursty cross-traffic and report throughput/RTT/loss." The thin-waist converts a networking experiment from an open-ended infrastructure problem into a callable function.

**Gap:** Evolutionary search is objective-driven, not hypothesis-driven. Systems research often requires *defining* the objective as part of the research. Thread 1 (Glia) handles this; Thread 2 does not.

---

## Thread 3: Intent-Driven Network Operations — "Manage this network"

**Core paper:** Confucius (Meta/Harvard, SIGCOMM 2025)

**Pattern:** Multi-agent framework decomposes management tasks into DAGs of subtasks. Each subtask uses domain-specific tools via DSLs (TML, ODS, Robotron). RAG for knowledge retrieval. Validation and human-in-the-loop for safety.

**Key systems:** Confucius, NetLLM, NetConfEval, PROSPER, ShieldGPT, LLo11yPop, Ciri

**Evaluation substrate:** Production networks (Meta). Not research infrastructure — operational infrastructure.

**Relevance to thin-waist:** Medium. Confucius validates the **architectural patterns** the thin-waist needs (intent → structured spec via Translator; DAG-based workflow; DSL-mediated tool integration; validation as first-class concern). But Confucius is operations-focused (manage existing networks), not research-focused (design and test new systems).

**Gap:** Operations ≠ research. Managing a production network doesn't involve forming hypotheses, controlling variables, or interpreting experimental results. The thin-waist addresses a fundamentally different user: the researcher, not the operator.

---

## Thread 4: Full-Loop Autonomous Research — "Do the research for me"

**Core paper:** AI Scientist v2 (Sakana AI, 2025)

**Pattern:** End-to-end: idea generation → tree-based experimentation → paper writing → reviewing. Experiment Progress Manager coordinates 4 stages (feasibility → tuning → research agenda → ablation). Each stage uses agentic tree search to explore hypothesis space.

**Key systems:** AI Scientist v2, Agent Laboratory, CycleResearcher, AI-Researcher (HKUDS), Google AI Co-Scientist (Gottweis et al.), Intology Zochi, Carl (AutoScience AI)

**Evaluation substrate:** Local Python scripts + Hugging Face datasets + GPU. Self-contained ML experiments.

**Relevance to thin-waist:** **Critical.** AI Scientist v2 exposes the fundamental limitation: full-loop autonomous research works for ML because experiments are self-contained Python scripts. For systems/networking, experiments require **orchestrated infrastructure** — traffic shaping, application execution, multi-point telemetry. The thin-waist makes systems research accessible to autonomous agents by providing the same clean experiment interface that ML researchers get for free.

**Gap:** No full-loop autonomous research system handles hardware-in-the-loop, infrastructure-dependent, or multi-component experiments. This is the biggest gap in the field and the thin-waist's primary value proposition.

---

## Thread 5: Empirical Infrastructure & Composable Experiment Platforms

**Core paper:** netUnicorn (UCSB SNL, CCS 2023)

**Pattern:** Hourglass/thin-waist design. Disaggregate data-collection intents from mechanisms. Composable pipelines across diverse infrastructure (Mininet, PINOT, AWS, Azure).

**Key systems:** netUnicorn, NetForge/NetReplica, BQT+, NetGent, the agentic thin-waist itself

**Evaluation substrate:** This thread BUILDS the evaluation substrate that all other threads assume exists.

**Relevance to thin-waist:** This IS the thin-waist thread. The question is whether the rest of the field recognizes the need.

**Gap:** No other group is building composable empirical infrastructure designed to be called by agentic systems. This is either a massive opportunity or a warning sign.

---

## Emerging Pattern: The Evaluation Playground Problem

Across all threads, a clear pattern emerges:

| System | Evaluation Substrate | Who builds it? |
|--------|---------------------|---------------|
| Glia | Vidur simulator | Exists (Agrawal et al.) |
| SkyDiscover | Benchmark functions | Hardcoded per task |
| Confucius | Meta production network | Exists (decades of tooling) |
| AI Scientist v2 | Python + HuggingFace | Trivially available |
| Agent Laboratory | Python + arXiv + HF | Trivially available |
| **Thin-waist** | **Controlled network testbed** | **Must be built** |

**The evaluation playground is the bottleneck for applying agentic research tools to systems/networking.** Every system above either (a) uses a simulator that someone else built, (b) uses production infrastructure that already exists, or (c) uses ML's trivially-available experiment loop. None of them address the problem of *creating* a composable experimental interface for real infrastructure.

---

## Prioritized Reading List (initial — to be expanded from corpus agent results)

### Pass 3 Required (5-8 foundational)
1. **Glia** — Hamadanian et al. 2025 ✅ Pass 1 done
2. **Confucius** — Wang et al. SIGCOMM 2025 ✅ Pass 1 done
3. **AI Scientist v2** — Yamada et al. 2025 ✅ Pass 1 done
4. **SkyDiscover/AdaEvolve** — Liu, Cemri et al. 2025 — Pass 1 pending
5. **netUnicorn** — Beltiukov et al. CCS 2023 — (own work, deep knowledge)
6. **"Barbarians at the Gate"** — Cheng, Stoica et al. 2025 (arXiv:2510.06189) — TBD
7. **Google AI Co-Scientist** — Gottweis et al. 2025 (arXiv:2502.18864) — TBD
8. **"Transforming Science with LLMs" survey** — Eger et al. 2025 (arXiv:2502.05151) — TBD

### Pass 2 Recommended (15-25)
- AlphaEvolve — Novikov et al. 2025
- Agent Laboratory — Schmidgall et al. 2025
- POPPER — arXiv:2502.09858
- NetConfEval — Wang et al. CoNEXT 2024
- AIDE — Jiang et al. 2025
- NetReplica/NetForge — Daneshamooz et al. 2025
- POLICYSMITH — Rohit et al. 2025
- He et al. 2024 — "Designing Network Algorithms via LLMs" (HotNets)
- Zhou et al. 2023 — "Interactive Research Agents for Internet Incident Investigation" (HotNets)
- NetLLM / NetFlowGen — SIGCOMM 2024
- ADRS (AI-Driven Research for Systems) — mentioned in Glia
- Agent-System Interface — Wei et al. 2024
- MLEBench — Chan et al. 2025
- RE-Bench — Wijk et al. 2024
- CycleResearcher — Weng et al. 2025

### Pass 1 Only (background)
- LangChain/LangGraph — framework context
- AutoGen — multi-agent baseline
- FunSearch — Romera-Paredes et al. 2024
- OpenEvolve — open-source baseline
- Reflexion — Shinn et al. 2024
- DiscoveryWorld — Allen AI benchmark
- AssetOpsBench — industrial asset management
- ShieldGPT, Ciri, LLo11yPop — networking-specific LLM tools

---

## WYSIATI Check (to be completed after corpus expansion)

**What's potentially missing from this landscape:**
1. **HCI/human-AI collaboration perspective** — how do researchers actually want to interact with agentic tools? User studies?
2. **Reproducibility/provenance** — how do you trust and reproduce agent-driven experiments?
3. **Safety/validation for infrastructure experiments** — Confucius has dry-run, but what about experiments that could damage infrastructure?
4. **Cost/efficiency analysis** — what does it actually cost to run these systems? Glia mentions $30/run.
5. **Domain-specific evaluation** — benchmarks for agentic systems research (DiscoveryWorld is general)
6. **The "simulation gap" literature** — sim-to-real transfer is well-studied in robotics; does it apply here?
