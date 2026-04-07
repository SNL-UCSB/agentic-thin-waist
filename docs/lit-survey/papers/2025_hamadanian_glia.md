---
title: "Glia: A Human-Inspired AI for Automated Systems Design and Optimization"
authors: Pouya Hamadanian, Pantea Karimi, Arash Nasr-Esfahany, Kimia Noorbakhsh, Joseph Chandler, Ali ParandehGheibi, Mohammad Alizadeh, Hari Balakrishnan
venue: arXiv:2510.27176v4 (Apr 2026)
year: 2025
category: systems-building
pass: 1
relevance: very-high
---

# [Pass 1]

**CATEGORY:** Systems-building (agentic AI framework for systems design)

**PROBLEM:** Can AI autonomously design and optimize networked systems, producing solutions on par with PhD-level systems engineers? Prior ML-for-systems approaches (RL, evolutionary code search) produce opaque, fragile policies that fail outside training regimes. Direct LLM prompting also fails — it produces "code monkey" behavior without understanding *why* designs work.

**CONTRIBUTION:** Glia is a multi-agent LLM framework that mirrors how human researchers approach systems design: forming hypotheses, running experiments, analyzing results, and iterating. It produces *interpretable, explainable* designs grounded in analytical reasoning, not black-box optimization.

**ARCHITECTURE — Three Components:**

1. **Researcher Agent** — proposes ideas, implements code changes, runs experiments on the evaluation playground, analyzes results. Has shell access to the simulator codebase. Uses "agentic search" (ls, grep, find) to navigate code. Taught general systems research principles via system prompt.

2. **Supervisor Agent** — provides strategic guidance through questioning and feedback. Has NO access to the codebase — only observes Researcher's outputs. Asks clarifying questions, encourages exploration when Researcher plateaus, recalls prior findings. Mirrors the advisor/PI role.

3. **Evaluation Playground** — simulator/testbed where designs are tested empirically. In their case study: Vidur (LLM serving simulator). This is the component the thin-waist could replace.

**KEY DESIGN CHOICES:**
- **White-box reasoning over black-box search**: Glia reasons about *why* designs work at the idea level, not just mutating code. This is the core differentiator from FunSearch/AlphaEvolve/OpenEvolve/EoH.
- **Hypothesis → Experiment → Analysis loop**: The Researcher forms hypotheses (e.g., "memory imbalance → restarts → wasted execution time"), designs experiments to test them, and refines understanding. This IS the agentic research loop.
- **Supervisor as cognitive prosthetic**: Prevents the Researcher from getting stuck in local optima. Encourages revisiting earlier ideas, composing mechanisms, running more experiments.
- **Multi-Context Glia (MCG)**: Runs N independent Researcher+Supervisor trajectories in parallel, selects best result. Addresses context window limitations. Sequential MCG vs. Parallel MCG-N.

**EVALUATION — GPU Cluster Scheduling for LLM Inference:**
- Applied to request routing, batch scheduling, and autoscaling in a distributed vLLM cluster
- Simulator: Vidur on 4 NVIDIA A10 GPUs, ShareGPT workload
- **Headline results:**
  - Request routing: mean RT 22.7s vs. 40s baseline (42.5% improvement)
  - Matched expert-designed algorithm in 20 simulations / 2 hours vs. 100+ simulations / 2 weeks for human
  - Outperforms EoH by 1.3-1.4x, FunSearch by 1.6-1.7x, OpenEvolve by 1.3x
  - Discovered novel Head-Room Admission (HRA) router — principled, interpretable
  - Full stack (router + scheduler + autoscaler) reduces GPU-hours by 40%
  - Transfers to real vLLM deployment (cloud experiments confirm simulator results)

**KEY REFERENCES:**
1. AlphaEvolve (Novikov et al. 2025) — evolutionary code search baseline
2. FunSearch (Romera-Paredes et al. 2024) — LLM-guided program search
3. OpenEvolve — open-source AlphaEvolve implementation
4. Vidur (Agrawal et al. 2024) — LLM serving simulator (the evaluation playground)
5. NetReplica (Daneshamooz et al. 2025) — cited as [11], same UCSB group

**CRITICAL OBSERVATION FOR THIN-WAIST RELEVANCE:**

Glia **assumes the evaluation playground exists**. Section 1 defines it as "a simulator, emulator, or testbed for running experiments and generating data for the AI agents to reason about." The paper uses Vidur — a well-instrumented, API-clean LLM serving simulator.

**This is exactly the gap the thin-waist fills.** For networking research, there is no "Vidur equivalent" — you need real infrastructure with controlled bottleneck regimes, traffic shaping, application workflows, and telemetry collection. The agentic thin-waist IS the evaluation playground for network experiments.

Glia's open challenges (Section 6) explicitly call out:
- (3) **Generalization across systems** — their approach "holds promise for optimizing a broad range of complex computer systems" but currently only tested on LLM inference
- (4) **Abstractions and architectural discovery** — "Designing a new abstraction such as an API, transport semantic, or queueing primitive is qualitatively different from optimizing a heuristic policy"

**LIMITATIONS:**
- Only tested on one domain (LLM serving) with one simulator (Vidur)
- Simulator must be well-instrumented with clear APIs and metrics
- $30 budget per optimization run (using OpenAI o3) — cost scales with problem complexity
- No handling of multi-objective optimization or safety constraints
- Supervisor has no codebase access — purely advisory based on text outputs
- Context window limitations addressed by MCG but not fundamentally solved

**PAPERS WORTH CHASING FROM REFERENCES:**
- [9] "Barbarians at the Gate: How AI is Upending Systems Research" (Cheng, Stoica et al. 2025) — arXiv:2510.06189
- [11] NetReplica (Daneshamooz et al. 2025) — arXiv:2507.13476
- [17] "Towards an AI co-scientist" (Gottweis et al. 2025) — arXiv:2502.18864
- [77] Agent-System Interface (Wei et al. 2024) — arXiv:2410.15625
- [15] "Man-Made Heuristics Are Dead. Long Live Code Generators!" (POLICYSMITH, 2025)
