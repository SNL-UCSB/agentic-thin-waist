---
title: "NetArena: Dynamic Benchmarks for AI Agents in Network Automation"
authors: Yajie Zhou, Jiajun Ruan, Eric S. Wang, Sadjad Fouladi, Francis Y. Yan, Kevin Hsieh, Zaoxing Liu
venue: ICLR 2026
year: 2026
category: benchmarking
pass: 1
relevance: very-high
---

# [Pass 1]

**CATEGORY:** Benchmarking (dynamic evaluation framework for LLM agents on network automation tasks)

**PROBLEM:** Evaluating AI agents on network system operations is stalled by the **data scarcity problem**: hand-curated benchmarks are small (<300 queries), static, vulnerable to contamination, and measure only correctness — ignoring safety and latency. Existing benchmarks (NeMoCopilot 33 queries, AI4OpsLab 48, NetConfEval 3200) are static, domain-narrow, and cannot surface rare failure modes. Dynamic benchmark generation methods from math/logic (DyVal, KIEval) don't transfer because network tasks are non-deterministic, require multi-turn interaction, and ground truth depends on system execution.

**CONTRIBUTION:** NetArena is the first dynamic benchmark generation framework for network automation. It introduces a unified **state-action abstraction** that generalizes across diverse network tasks, integrates with high-fidelity emulators (Mininet, Kubernetes) for execution-time verification, and measures three metrics — correctness, safety, and latency — through unlimited dynamically-generated queries.

**ARCHITECTURE — Three-Layer Design:**

1. **Unified State-Action Abstraction** — Models each network task as a finite state transition system (S, A, E) where S = system states, A = atomic action functions, E = application-specific execution function. Each action a_t is parameterized by task-specific operands theta_t. To add a new task, developers define S (e.g., routing topology with connectivity status) and A (e.g., IP assignment, link-level error). This formalism enables both query generation and ground-truth derivation.

2. **Dynamic Query Generation** — Two task types:
   - **Constructive tasks** (white-box): Sample initial state s_0 and action sequence A* from large space; execute to produce target state s_T; generate NL prompt (s_0, A*, s_T). Agent must synthesize action sequence reaching s_T. Example: datacenter capacity planning.
   - **Reactive tasks** (black-box): Inject hidden fault sequence A_inj into healthy state s_0 to produce faulty state s_faulty; agent must diagnose and recover to s_0. Multiple valid recovery paths. Example: routing misconfiguration.

3. **Emulator Integration** — Actions executed end-to-end in Mininet (routing) or Kubernetes (microservice policy). Emulator feedback enables three metrics:
   - **Correctness**: Final state matches ground truth (graph isomorphism or functional equivalence)
   - **Safety**: Every intermediate state satisfies task constraints C_Q (no cross-layer violations, no unauthorized changes, no service disruption) — checked per step
   - **Latency**: Command count and wall-clock time to resolution

**THREE REPRESENTATIVE TASKS:**

1. **Datacenter Capacity Planning (CP)** — Constructive. Google-style multi-layer topology (Rack/Chassis/Switch/Port). 12 action types (add, update, rank). Safety = structural constraints + bandwidth minimums. Evaluated with up to 5000 queries.

2. **Routing Misconfiguration (Routing)** — Reactive. Mininet emulator. Broken links, invalid forwarding rules. Multi-turn: agent issues diagnostic commands (ping, traceroute), interprets outputs, applies fixes. Safety = no new connectivity breaks. Up to 2250 queries.

3. **Microservice Policy Deployment (K8s)** — Reactive. Google's open-source Kubernetes microservice demo. Misconfigured network policies. Agent identifies incorrect ports/restrictive rules. Up to 2000 queries.

**KEY DESIGN CHOICES:**
- **State-action as the universal interface**: By requiring only (S, A) per task, NetArena can onboard new network domains without redesigning the benchmark pipeline. This is a thin-waist for benchmark generation.
- **Emulator-in-the-loop, not static matching**: Ground truth is verified by execution, not string matching. This captures safety violations and side effects invisible to output-only evaluation.
- **Complexity-controlled generation**: Each query tagged with action types and difficulty level (L1-L3), enabling fine-grained analysis of where agents break.
- **Stochastic sampling**: Each evaluation round uses randomized query generation, reducing contamination risk.

**KEY FINDINGS:**

- **Agent performance is strikingly low**: Average correctness across tasks only 24%. Best agent stays below 60%. On large-scale realistic queries, as low as 3%.
- **Small benchmarks are unreliable**: At <200 queries, confidence intervals overlap 85% of the time. At 5000+ queries, overlap drops to 0% — revealing GPT+ReAct as the clear winner.
- **Correctness alone is insufficient**: Some models produce correct answers that violate safety constraints; others act conservatively (safe but slow). NetArena's 2D correctness-vs-safety plots expose these tradeoffs.
- **SFT overfits to training difficulty**: Models fine-tuned on one complexity level fail on others. Only mixed-level training generalizes (>0.96 correctness). Safety transfers more readily than correctness across levels.
- **RL is feasible**: Preliminary GRPO training of QWen-0.5B in Mininet routing shows learning curve breakthrough at episode 36. Post-RL, model generates valid diagnostic commands instead of gibberish.

**CRITICAL OBSERVATION FOR THIN-WAIST RELEVANCE:**

NetArena's state-action abstraction is a **thin-waist for benchmarking** — it provides a unified interface between diverse network tasks (above) and emulator backends (below). This is structurally isomorphic to the agentic thin-waist's role between research intents (above) and diverse infrastructure (below).

**The deep synergy**: NetArena answers "how well does an agent perform on network tasks?" while the agentic thin-waist answers "how do I generate the empirical conditions the agent operates in?" They are complementary layers:
- NetArena generates **queries** (task descriptions + ground truth) but treats the emulator as a fixed, pre-configured environment
- The agentic thin-waist generates **environments** (bottleneck regimes, traffic profiles, substrate configurations) that the agent will operate within

NetArena explicitly acknowledges its emulator-only scope (Section 5.3): "emulator performance should be interpreted as a measure of an agent's ability to reason over structured operational tasks under realistic, but still simplified, conditions." The thin-waist can provide the **realistic, diverse conditions** that NetArena's emulators currently lack — real traffic, real bottlenecks, real application behavior.

Furthermore, NetArena's finding that agents achieve only 13-38% on realistic tasks is strong evidence for the thin-waist thesis: if agents can't even handle emulated networks reliably, the quality and diversity of the training/evaluation environment (the thin-waist's job) is load-bearing for progress.

**LIMITATIONS:**
- Emulator-only — no real-network validation; sim-to-real gap acknowledged but not addressed
- Three tasks only — capacity planning, routing, K8s policy; no traffic engineering, no performance optimization, no measurement tasks
- Static topology within each query — no dynamic topology changes or workload shifts during evaluation
- NL templates are manually written per task type
- RL results are preliminary (QWen-0.5B only, routing task only)
- No multi-agent evaluation — single agent per query

**PAPERS WORTH CHASING FROM REFERENCES:**
- MeshAgent (Maryland/Microsoft, SIGMETRICS 2026) — already in corpus #30, LLM agent for reliable network management
- NetConfEval (Wang et al., CoNEXT 2024) — already in corpus #14, configuration evaluation
- AI4OpsLab (Chen et al., 2025b) — 48 DevOps tasks, static benchmark baseline
- NeMoCopilot (Mani et al., 2023) — graph-based network code generation
- Chkirbene et al. 2024 — sim-to-real gap in network agent deployment
