---
title: "Intent-Driven Network Management with Multi-Agent LLMs: The Confucius Framework"
authors: Zhaodong Wang, Samuel Lin, Guanqing Yan, Soudeh Ghorbani, Minlan Yu, Jiawei Zhou, Nathan Hu, Lopa Baruah, Sam Peters, Srikanth Kamath, Jerry Yang, Ying Zhang
venue: ACM SIGCOMM 2025
year: 2025
category: systems-building
pass: 1
relevance: very-high
---

# [Pass 1]

**CATEGORY:** Systems-building (production multi-agent LLM framework for network management)

**PROBLEM:** Network management at hyperscale (Meta) requires complex, multi-step tasks involving diverse domain-specific tools, DSLs, and databases. Single LLM prompting fails for sufficiently complex tasks. Existing tools require deep domain expertise. Engineers spend significant time on repetitive, manual workflows.

**CONTRIBUTION:** Confucius is a production-ready multi-agent LLM framework for intent-driven network management. First report on deploying multi-agent LLMs at hyperscale. Operational for 2+ years, 60+ applications, 4.16K users, 31.62M messages.

**ARCHITECTURE — Five Design Pillars:**

1. **Planning with Structured Network Procedures**: Decomposes tasks into DAGs of subtasks using existing MOPs (Methods of Processes) and workflows. RAG-based workflow/building-block retrieval.

2. **Tools via Domain-Specific Languages**: Three foundational DSLs:
   - **TML** (Topology Modification Language) — Python-based, for topology graph operations
   - **ODS** (Operations Data Store) — for time series network data queries
   - **Robotron** (Network Data Model) — relational model for BGP, interfaces, etc.

3. **Memory Management**:
   - Short-term: hierarchical tree of messages across Analects (their unit of computation)
   - Long-term: RAG over hundreds of thousands of network data models

4. **Validation & Safety**: Built-in parser validation, external API validation, dry-run mode, graph validators for topology invariants. Human approval for sensitive operations.

5. **Benchmarking Framework**: User-provided datasets, exact match / regex match / LLM-as-Judge evaluation criteria.

**PROGRAMMING MODEL — Analects:**
- Core abstraction: **Analect** — a lightweight wrapper for LangChain's Runnable with Pydantic typed I/O
- Primitives: **Translator** (NL → structured), **Selector** (subset from large dataset), **Collector** (gather user inputs, disambiguate), **Ensemble** (multi-agent parallel execution with composition modes: First, Merge, Filter-with-Validation, Return-all), **Orchestrator** (autonomous step-by-step DAG execution)
- Built on LangChain, uses MetaGen API for model access, FAISS for embeddings

**EVALUATION:**
- **DSL Translation**: Confucius outperforms fine-tuned baseline by 35% (TML), 22.4% (ODS transformation), 23% (ODS reduction) via domain-aware prompting
- **Ensemble**: Multi-model ensemble scores 0.87-0.98, reduces standard error 34-57%
- **RAG**: Outperforms fine-tuned model on all retrieval tasks; Hybrid RAG improves 3%+ over naive
- **Production stats**:
  - 4.16K total users, 2.63K monthly active
  - 241.38K sessions, 31.62M messages
  - AI-to-human message ratio: 20.54 overall (high autonomy)
  - Saves 17 engineer-hours/week on average per application
  - Performance diagnosis: 121 users, 835.58K total time spent (hrs)

**KEY DESIGN PRINCIPLES (Section 3.1):**
1. Separate reasoning from factual knowledge — LLMs reason, tools/databases provide facts
2. Leverage existing tools and expertise — don't build new tools, wrap existing ones
3. Orchestrate with carefully engineered prompts — "cognitive architectures"
4. Prioritize iterative improvement — ship basic, refine
5. Don't depend on fine-tuning — use foundation models with prompt engineering + RAG

**LESSONS LEARNED (Section 8):**
- **Iterative processes matter**: Network management tasks are complex workflows, not single-shot queries. Confucius shows intermediate steps in UI.
- **LLMs struggle with network troubleshooting**: Hardest problems can't be modeled as MOPs. Experts are masters of basics — LLMs can't replicate deep domain expertise.
- **Failure modes**: (1) Context propagation loss across long sessions, (2) Hallucination — LLMs fabricate answers instead of failing early, (3) Privacy concerns with network data

**RELEVANCE TO THIN-WAIST:**

Confucius is **operations-focused, not research-focused**. It manages existing production networks — it doesn't design new systems or run experiments to test hypotheses. Key differences:

1. **No experiment loop**: Confucius executes management tasks (topology changes, fault diagnosis, monitoring). It doesn't formulate hypotheses or design experiments.
2. **Assumes existing infrastructure**: All tools, DSLs, and databases already exist at Meta. Confucius *wraps* them. The thin-waist *creates* the experimental infrastructure.
3. **DAG decomposition ≠ progressive disaggregation**: Confucius DAGs are workflow decomposition (task A → task B → task C). The thin-waist's intent → representation → execution is a *conceptual* decomposition of the experimental process.

**But**: Confucius's architecture validates several patterns the thin-waist needs:
- Intent → structured specification via Translator primitives
- DAG-based workflow planning for multi-step experiments
- DSL-mediated tool integration (TML/ODS/Robotron ↔ tc/tshark/tcpreplay)
- Validation as a first-class concern (dry-run, external validators)
- RAG for large knowledge bases (network models ↔ CTP corpus)

**The thin-waist could be a "Confucius for experiments"** — same architectural patterns, but applied to research workflows instead of operational workflows.

**KEY REFERENCES:**
1. LangChain [13] / LangGraph [29] — agent framework foundation
2. AutoGen [50] — multi-agent baseline
3. Robotron (Yu et al. SIGCOMM '16) [46] — Facebook's network data model
4. Occam [51] — programming system for reliable network management (EuroSys '24)
5. NetFlowGen [53] — generative pre-training for network traffic dynamics (Minlan Yu group)

**PAPERS WORTH CHASING FROM REFERENCES:**
- [24] Karimi et al. 2023 — "A Holistic View of AI-driven Network Incident Management" (HotNets)
- [25] He et al. 2024 — "Designing Network Algorithms via Large Language Models" (HotNets)
- [33] Lian et al. — Ciri: LLM-based configuration validation
- [35] Mani et al. 2023 — "Enhancing network management using code generated by LLMs" (HotNets)
- [43] Sharma & Yegneswaran 2023 — PROSPER: Extracting Protocol Specs Using LLMs (HotNets)
- [48] ShieldGPT — LLM-based DDoS mitigation
- [49] NetLLM — Adapting LLMs for networking (SIGCOMM '24)
- [53] NetFlowGen — Leveraging Generative Pre-Training for Network Traffic
- [54] Zhou et al. 2023 — "Towards Interactive Research Agents for Internet Incident Investigation" (HotNets)
- [22] LLo11yPop — observability agentic framework
- [40] AssetOpsBench — benchmarking AI agents for industrial asset operations
