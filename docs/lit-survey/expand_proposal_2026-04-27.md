# Corpus Expansion Proposal — 2026-04-27

**Trigger:** User wants to defend Pramana for HotNets 2026 against the criticism that it is "just applying existing agentic frameworks to a niche networking problem." The defense requires positioning Pramana's abstractions as contributions to **agentic systems generally** — i.e., showing that the thin-waist / progressive-disaggregation principle helps OpenClaw-class agents (web, code, lab-science, robotics) that current frameworks serve poorly.

**Gap analysis vs current corpus.** The corpus is well-stocked on (a) LLM-for-networking, (b) scientific-discovery agents, (c) lab-science infrastructure (Osprey, Flowcept, Academy). It is **thin** on the systems-research framing of agents themselves: action-space / environment design, agent-OS, protocol-layer abstractions (MCP, A2A, tool-use), compound-AI systems, sandboxing and durable execution. That body of work is where Pramana's contribution to *general* agentic systems must be positioned.

The proposal below is grouped by the five argumentative threads Pramana needs in HotNets §2 (Background) and §3 (Positioning). For each candidate: source of discovery, reason for inclusion, suggested pass, and an Add/Bookmark/Skip recommendation. Numbers continue from corpus_log.md (last entry #79).

---

## Thread A — Environment & Action-Space Design (the "execution substrate" angle for general agents)

This is the strongest defensive thread. **Web/desktop/code agents have explicit notions of action space and environment**, and the SOTA is converging on the idea that *environment design is a first-class research problem*, not a thin wrapper around an LLM. Pramana's claim that infrastructure controllability is the unsolved problem in research-agent stacks is the same claim, applied to a different domain. Without these, reviewers will not see the analogy.

| #  | Paper / System | Authors / Venue | Why it matters for the defense | Suggested pass | Recommendation |
|----|----------------|-----------------|-------------------------------|----------------|----------------|
| 80 | **OSWorld: Benchmarking Multimodal Agents in Real Computer Environments** | Xie et al., NeurIPS 2024 | Canonical citation for "the environment is the bottleneck, not the model." Provides the language we need: *operable scope*, *task-environment grounding*, *executable rubric*. | Pass 2 | **Add** |
| 81 | **SWE-bench: Can Language Models Resolve Real-World GitHub Issues?** | Jimenez et al., ICLR 2024 | Foundational example that fidelity of the execution environment determines what agents can be evaluated for. Pairs naturally with our "controlled bottleneck regime" framing. | Pass 2 | **Add** |
| 82 | **τ-bench (TauBench): Tool-Agent-User Interaction** | Yao et al., Sierra 2024 (arXiv:2406.12045) | Argues that *interface design* dominates agent success. Direct analogue: thin-waist defines the agent↔infra interface. | Pass 2 | **Add** |
| 83 | **WebArena / VisualWebArena** | Zhou et al., ICLR 2024 / Koh et al., ACL 2024 | Establishes "self-hosted controllable environment" as a methodological norm. Strengthens the analogy to controllable network infrastructure. | Pass 1 | **Add** |
| 84 | **Agent S / Agent S2: Compositional Generalist-Specialist for Computer Use** | Agashe et al. (Salesforce), 2024–2025 | Closest external analogue to progressive disaggregation: explicit decomposition of a generalist controller and specialist executors. Reviewer-bait for "this is just X." | Pass 2 | **Add** |
| 85 | **Voyager: Open-Ended Embodied Agent (NVIDIA)** | Wang et al., NeurIPS 2023 | Already in corpus (#24, pending). Reclassify to **Pass 2** under this thread — its skill-library abstraction is the canonical "composable execution substrate" prior. | Pass 2 (upgrade) | **Already in corpus — upgrade priority** |

**Defense move enabled:** "Web/desktop/code agents have already learned that controllable environments are the bottleneck (OSWorld, WebArena, τ-bench). Pramana asserts the same for systems research, where the environment is real network infrastructure rather than a browser tab. This is not a one-off: it is the same architectural pattern in a domain where the environment is harder to virtualize."

---

## Thread B — Compound AI Systems / Agent-as-Systems-Research

The user's framing — "what fundamental abstractions does Pramana contribute?" — needs the *Compound AI Systems* essay as scaffolding. That essay is the canonical "agentic systems IS systems research" manifesto from Sky Lab. Without citing it, the HotNets paper looks naive about the broader framing.

| #  | Paper / System | Authors / Venue | Why it matters | Suggested pass | Recommendation |
|----|----------------|-----------------|----------------|----------------|----------------|
| 86 | **The Shift from Models to Compound AI Systems** | Zaharia, Khattab, Chen, Davis, Stoica et al. — Berkeley AI Research blog, 2024 | The reference text for treating agents as a systems-research artifact. Lets us cite *"agentic = systems-research"* without the reviewer thinking we made it up. | Pass 2 | **Add** (note: blog, treat as canonical) |
| 87 | **DSPy: Compiling Declarative LM Calls into Self-Improving Pipelines** | Khattab et al., ICLR 2024 | Concrete embodiment of Compound AI Systems: declarative interfaces over LLMs. Pramana's thin-waist is a declarative interface over infrastructure — direct structural analogue. | Pass 2 | **Add** |
| 88 | **Cognitive Architectures for LLM Agents (CoALA)** | Sumers, Yao, Narasimhan, Griffiths — TMLR 2024 | First widely-cited *abstraction-level* framework for agents. Useful target for our "what abstraction is missing?" argument. | Pass 2 | **Add** |
| 89 | **Generative Agents: Interactive Simulacra of Human Behavior** | Park et al., UIST 2023 | Less directly relevant but still a canonical citation for "agent stacks need explicit memory/reflection layers." Cite if a memory/state argument lands; otherwise skip. | Pass 1 | **Bookmark** |
| 90 | **AI Engineering / Specifications-as-Engineering-Discipline** | Already #72 in corpus. | Reclassify under this thread; it is the rigor argument for compound AI. | upgrade | **Already in corpus — upgrade priority** |

**Defense move enabled:** "The community already accepts that agentic systems are a compound-systems research problem (Zaharia 2024, DSPy, CoALA). What it has not solved is the *execution substrate* layer of that compound system. Pramana names that layer and provides a concrete instantiation."

---

## Thread C — Protocol-Layer Abstractions (MCP, A2A, tool-use)

This is the single most important thread for the defense. Pramana is explicitly a *thin-waist*, i.e., a protocol-layer claim. The strongest reviewer attack will be: "Why is this not just MCP?" We must cite MCP and A2A and explain the difference precisely (MCP = tool↔agent protocol; Pramana = experiment-intent↔infrastructure protocol — orthogonal, complementary).

| #  | Paper / System | Authors / Venue | Why it matters | Suggested pass | Recommendation |
|----|----------------|-----------------|----------------|----------------|----------------|
| 91 | **Model Context Protocol (MCP) Specification** | Anthropic, 2024 (modelcontextprotocol.io) | Mandatory citation. Pramana must position itself as a *peer protocol* to MCP, not a competitor. Without this, the HotNets paper appears unaware of the protocol-layer landscape. | Pass 2 | **Add** (note: spec doc, treat as primary) |
| 92 | **Agent-to-Agent (A2A) Protocol** | Google, 2025 (a2a.dev) | The other live protocol-layer effort. Same defense purpose as MCP: shows we have read the protocol landscape and can articulate where Pramana sits. | Pass 1 | **Add** |
| 93 | **Toolformer: Language Models Can Teach Themselves to Use Tools** | Schick et al., NeurIPS 2023 | Origin paper for tool-use as a primitive. Useful one-citation grounding for the protocol-layer narrative. | Pass 1 | **Add** |
| 94 | **ToolBench / API-Bank / Tool Learning Survey** | Qin et al., ICLR 2024 | Background; covers the function-calling ecosystem. Pick one survey, not all three. | Pass 1 | **Bookmark** |
| 95 | **Gorilla** | Already #28 in corpus. | Reclassify under this thread (currently Pass 2 recommended). It is the empirical anchor for "tool-use protocol matters." | upgrade | **Already in corpus — upgrade priority** |

**Defense move enabled:** "MCP standardizes the agent↔tool boundary; A2A standardizes agent↔agent. Neither addresses the agent↔infrastructure boundary, which is where research and lab-science workloads live. Pramana fills this layer. The hourglass is incomplete without it."

---

## Thread D — Sandboxing, Durable Execution, Reproducibility for Agents

The HotNets paper claims that *real* infrastructure execution (vs. simulated) is what distinguishes Pramana from existing agent stacks. We need to cite the existing sandboxing/durability community to show we are not reinventing — we are tackling a harder version of their problem.

| #  | Paper / System | Authors / Venue | Why it matters | Suggested pass | Recommendation |
|----|----------------|-----------------|----------------|----------------|----------------|
| 96 | **GoEx: Gorilla Execution Engine** | Already #71 in corpus. | Reclassify; central to this thread. | upgrade | **Already in corpus — upgrade priority** |
| 97 | **MemGPT / Memento — agent memory as OS abstraction** | Packer et al., 2023 | Memory as a tier-managed OS resource — direct analogue to "infrastructure as a tier-managed substrate." | Pass 1 | **Add** |
| 98 | **Temporal / durable execution for agent workflows** | Various industry write-ups (Temporal, Restate, Procrastinate) | Background. Pramana already uses Procrastinate. Cite to show agent-workflow durability is a real engineering discipline. | Pass 1 | **Bookmark** (one citation, not paper-grade) |
| 99 | **AutoGPT post-mortems / agent failure-mode taxonomies** | e.g., AgentFail (Wu et al., 2024); LLM Agent Failure Modes survey | Documents the gap that motivates Pramana — agents fail when their environments are not engineered. | Pass 1 | **Bookmark** |
| 100 | **PROV-AGENT** | Already #77 in corpus. | Reclassify under this thread. | upgrade | **Already in corpus — upgrade priority** |

**Defense move enabled:** "Existing agent stacks treat the environment as a black box: a browser, a Python REPL, an API. When the environment is real infrastructure under measurement, every guarantee that sandboxing and durable execution provide for software environments must be reconstructed from scratch. Pramana is the first attempt to do so."

---

## Thread E — Scientific-Agent Environments (Pramana's peer systems in other domains)

The corpus has the *outputs* (AI Scientist, Agent Laboratory) but is light on the *environment-side* peers — i.e., systems that, like Pramana, build a controlled experimental substrate for science agents in other domains. These are Pramana's strongest analogues.

| #  | Paper / System | Authors / Venue | Why it matters | Suggested pass | Recommendation |
|----|----------------|-----------------|----------------|----------------|----------------|
| 101 | **SciCode: A Research Coding Benchmark Curated by Scientists** | Tian et al., NeurIPS 2024 | Closest sibling to Pramana in the *code-for-science* domain — a curated, executable substrate. | Pass 1 | **Add** |
| 102 | **ScienceAgentBench: Toward Rigorous Assessment of Language Agents for Data-Driven Scientific Discovery** | Chen et al., ICLR 2025 | Same role, broader scope. Important for cross-domain framing. | Pass 1 | **Add** |
| 103 | **LAB-Bench: Measuring Capabilities of Language Models for Biology Research** | Laurent et al. (FutureHouse), 2024 | Biology-domain analogue of Pramana's controllability claim. | Pass 1 | **Add** |
| 104 | **Eureka: Human-Level Reward Design via Coding LLMs (NVIDIA)** | Ma et al., ICLR 2024 | Robotics-side analogue — agent-driven environment shaping. Useful for the "agents need shapeable environments" point. | Pass 1 | **Bookmark** |
| 105 | **MLE-Bench / RE-Bench** | Already #68/#69 in corpus. | Reclassify under this thread for the "ML/research-engineering substrate" angle. | upgrade | **Already in corpus — upgrade priority** |

**Defense move enabled:** "Across domains — coding (SciCode), data science (ScienceAgentBench), biology (LAB-Bench), robotics (Eureka) — the 2024–2025 trend is the same: build a controllable, executable substrate that agents can act on. Pramana is the networking-side instantiation of this trend, not an isolated artifact."

---

## Summary of Add / Bookmark / Skip

**Strong Adds (12 papers, target Pass 2):**
- #80 OSWorld
- #81 SWE-bench
- #82 τ-bench
- #84 Agent S / S2
- #86 Compound AI Systems essay (Zaharia et al.)
- #87 DSPy
- #88 CoALA
- #91 MCP spec
- #92 A2A protocol
- #101 SciCode
- #102 ScienceAgentBench
- #103 LAB-Bench

**Add at Pass 1 (3 papers):**
- #83 WebArena/VisualWebArena
- #93 Toolformer
- #97 MemGPT

**Reclassify / upgrade priority on existing corpus (5):**
- #24 Voyager → Pass 2 (Thread A)
- #28 Gorilla → already at Pass 2; tag Thread C
- #71 GoEx → tag Thread D, target Pass 2
- #72 Specifications-as-Engineering → tag Thread B, target Pass 2
- #77 PROV-AGENT → tag Thread D, target Pass 2

**Bookmark (5):**
- #89 Generative Agents
- #94 ToolBench/API-Bank survey
- #98 Temporal/durable-execution citations
- #99 AutoGPT failure-mode write-ups
- #104 Eureka

**Skip rationale (none here, but for the record):** I considered but rejected adding LangGraph/AutoGen internals (already framework-level entries #50, #51), HuggingGPT (superseded by tool-use literature), and Tree/Graph-of-Thoughts (orchestration patterns, not abstraction contributions).

---

## Budget check

Current corpus: 79 papers. Strong Adds + Pass-1 Adds = 15 new entries → total 94. Bookmarks do not enter corpus until pulled. Examiner archetype budget is 80–150, so this expansion lands at 94/150 — comfortable, with room for a second pass after these are read.

## Reading-order recommendation if accepted in full

The defensive argument needs Threads C, A, B in that order. Suggested 3-week read schedule:
- **Week 1 (protocol-layer):** MCP spec, A2A, Toolformer → defines the "what is Pramana not?" boundary
- **Week 2 (environment design):** OSWorld, SWE-bench, τ-bench, Agent S, WebArena → defines the "what is Pramana like?" analogy
- **Week 3 (compound AI / scientific peers):** Compound AI essay, DSPy, CoALA, SciCode, ScienceAgentBench, LAB-Bench → defines the "what is Pramana's contribution?" frame

This is the corpus needed for HotNets §2/§3. The synthesis pass (`/survey synthesize`) should follow.

---

# Round 2 — Big-Picture Defensive Threads (added 2026-04-27, same day)

The user's follow-up sharpened the defensive ask. The HotNets paper has to clear two bars beyond "Pramana works":

1. **Avoid the NetReplica trap** — reviewers flagging this as engineering rather than innovation. Innovation has to land either as (a) new *use cases* not previously possible, or (b) general *lessons* for agentic systems design.
2. **Articulate two general insights from Pramana that transcend networking:**
   - **Insight A — Grounding:** Stochastic natural-language intent → deterministic / imperative configuration spec is a *general* agentic-systems bottleneck. Pramana names and instantiates the mapping.
   - **Insight B — Amortization:** LLM reasoning is good for first-time exploration but wasteful and non-deterministic for redundant runs. The thin-waist captures structure once so repeat exploration becomes cheap and reproducible.

The five threads below extend the corpus along these lines. They are additive to Threads A–E above.

---

## Thread F — Stochastic Intent → Deterministic Spec (Grounding as a general bottleneck)

This thread directly supports Insight A. The literature already recognizes that getting LLMs to commit to a discrete, executable specification — rather than free-form reasoning — is the rate-limiting step for reliable agents. Pramana's experiment-spec layer is one instance of a general pattern.

| #   | Paper / System | Authors / Venue | Why it matters | Suggested pass | Recommendation |
|-----|----------------|-----------------|----------------|----------------|----------------|
| 106 | **Code-as-Policies: Language Model Programs for Embodied Control** | Liang et al. (Google), ICRA 2023 | The cleanest analogue: NL intent → executable code → reproducible robot action. Same shape as Pramana's intent → experiment spec. Mandatory citation. | Pass 2 | **Add** |
| 107 | **ProgPrompt: Generating Situated Robot Task Plans using LLMs** | Singh et al., ICRA 2023 | Companion to Code-as-Policies, simpler grounding mechanism. Cite once for the family. | Pass 1 | **Add** |
| 108 | **LLMs Can't Plan, But Can Help Planning in LLM-Modulo Frameworks** | Kambhampati et al., ICML 2024 | Explicit, citable thesis: LLMs are unreliable as autonomous reasoners but powerful as front-ends to deterministic systems. Direct support for "thin-waist as the deterministic backbone." | Pass 2 | **Add** |
| 109 | **Chain-of-Code: Reasoning with a Language Model–Augmented Code Emulator** | Li et al., ICML 2024 | Reasoning compiled into deterministic code execution. Reinforces Pramana's framing: don't reason at runtime when you can compile. | Pass 1 | **Add** |
| 110 | **LMQL / Outlines / Guidance — constrained-generation for structured output** | Beurer-Kellner et al., PLDI 2023 (LMQL) — pick one survey/representative | Engineering layer for forcing LLMs into deterministic schemas. Pramana's experiment-spec is the next layer up: a *domain-aware* constraint surface. | Pass 1 | **Add (one citation)** |
| 111 | **Self-Discover: LLMs Self-Compose Reasoning Structures** | Zhou et al., NeurIPS 2024 | Counter-thread: agents discovering their own decomposition. Useful contrast to Pramana's *fixed, principled* decomposition. Helps frame why a thin-waist is not a substitute for emergent reasoning but a complement. | Pass 1 | **Bookmark** |
| 112 | **DSPy** | Already #87 (Round 1). | Reclassify under Thread F as the *compile-time* analogue of intent grounding. Single most important sibling to Pramana in this thread. | upgrade | **Already in corpus — upgrade priority** |

**Defense move enabled (Insight A):** "The agentic-systems community has identified — across robotics (Code-as-Policies, ProgPrompt), reasoning (Chain-of-Code, LLM-Modulo), and software (DSPy, LMQL) — that the rate-limiting step is the mapping from open-ended natural-language intent to a discrete, executable specification. Pramana names this mapping for the experiment-design domain and shows what its discipline-specific structure looks like. The lesson generalizes: every agentic stack needs a domain-aware grounding layer, and the design of that layer is research, not glue."

---

## Thread G — Amortization, Caching, Skill Libraries (Repeatability over redundant exploration)

This thread supports Insight B. The literature has begun to formalize the observation the user articulated: LLM reasoning is appropriate for *novel* exploration but is the wrong tool when the same exploration recurs. The right pattern is to capture the *outcome* of one successful reasoning trace as a reusable artifact.

| #   | Paper / System | Authors / Venue | Why it matters | Suggested pass | Recommendation |
|-----|----------------|-----------------|----------------|----------------|----------------|
| 113 | **MetaGPT: Meta Programming for Multi-Agent Collaborative Framework** | Hong et al., ICLR 2024 | Codifies "Standard Operating Procedures" as the amortization mechanism: encode known successful workflows so agents don't re-derive them every run. Direct precedent for Pramana's "lock the thin waist, vary the heads" architecture. | Pass 2 | **Add** |
| 114 | **Voyager** | Already #24 (Round 1, Thread A). | Reclassify primary motivation under Thread G: skill library as accumulated-amortization artifact. The skill library *is* the captured exploration. | upgrade | **Already in corpus — upgrade priority** |
| 115 | **Agent Workflow Memory / Reflective Agent Memory papers** | e.g., Wang et al. 2024 (AWM, arXiv:2409.07429) | Recent thread: agents store and reuse traces of successful workflows. Sibling to Voyager skill library, focused on reasoning-trace reuse. | Pass 1 | **Add** |
| 116 | **Reflexion: Language Agents with Verbal Reinforcement Learning** | Shinn et al., NeurIPS 2023 — already #53 in corpus | Reclassify under Thread G: failure-driven amortization. Currently catalogued as "agent scaffolding." | upgrade | **Already in corpus — upgrade priority** |
| 117 | **Prompt caching / KV-cache reuse for agent workloads** | Anthropic (prompt-cache docs, 2024); also academic: SGLang (Zheng et al., 2024) | Engineering substrate for amortization. Pramana provides the *workflow-level* analogue of what prompt caching does at the token level. One citation. | Pass 1 | **Add (one citation)** |
| 118 | **CALM / Agent Workflow Compilation / DSPy compilation** | DSPy (already #87) — emphasize the compile-and-cache aspect | DSPy's compile step is the canonical "amortize the reasoning trace into a fixed program" example. Cite under both Thread F and Thread G. | upgrade | **Already in corpus — upgrade priority** |

**Defense move enabled (Insight B):** "Skill libraries (Voyager), SOPs (MetaGPT), workflow memory (AWM), reflection (Reflexion), and compile-time prompt programs (DSPy) are all instances of the same pattern: amortize successful reasoning into reusable structure so redundant exploration becomes cheap and deterministic. Pramana provides this pattern at the experiment-infrastructure layer. The thin-waist *is* the amortization artifact: an LLM derives an experiment spec once, and the spec is then re-executable across environments without re-reasoning."

---

## Thread H — First-Principles Decomposition (when LLMs help, when they don't)

Foundational meta-thread. Supports the user's framing that "we are decomposing big problems into smaller problems where agents are effective." Without this thread, the HotNets paper sounds like it just *claims* good decomposition without engaging with the literature on when decomposition works.

| #   | Paper / System | Authors / Venue | Why it matters | Suggested pass | Recommendation |
|-----|----------------|-----------------|----------------|----------------|----------------|
| 119 | **LLM-Modulo (Kambhampati)** | Already proposed as #108 in Thread F. | Same paper, also load-bearing for Thread H. Tag both threads. | Pass 2 | (covered) |
| 120 | **Specifications-as-an-Engineering-Discipline (Berkeley)** | Already #72 in corpus. | Reclassify under Thread H. The Berkeley argument is that agentic systems need *specifications* as a research discipline — Pramana's experiment spec is one. | upgrade | **Already in corpus — upgrade priority** |
| 121 | **Cognitive Architectures for LLM Agents (CoALA)** | Already #88 (Round 1, Thread B). | Tag also under Thread H — CoALA is the abstraction-level proposal for *how* to decompose agent stacks. | upgrade | **Already in corpus — upgrade priority** |
| 122 | **The Bitter Lesson and its Discontents (recent essays)** | Multiple — pick a representative HotOS / position piece, e.g., Schwarzkopf 2024 or recent Stoica/Patterson | The HotOS-tradition argument that systems-research innovation comes from naming the right abstractions, not from scale alone. Useful framing-level citation. | Pass 1 | **Bookmark** |

**Defense move enabled:** "Decomposition is not a free win — LLM-Modulo, CoALA, and the spec-discipline argument all show that a *principled* decomposition is the research contribution. Pramana's intent / representation / execution decomposition is principled because it isolates the parts where LLMs help (intent compression, result interpretation) from the parts where determinism is essential (substrate execution, telemetry). This is the contribution, not the orchestration code."

---

## Thread I — Innovation-by-Use-Case (defense against the NetReplica trap)

The most important defensive thread for the *engineering vs research* worry. The systems community has a well-established tradition of arguing innovation through the use cases an artifact unlocks (Mininet, Emulab, CloudLab, ns-3). Pramana belongs in that lineage.

| #   | Paper / System | Authors / Venue | Why it matters | Suggested pass | Recommendation |
|-----|----------------|-----------------|----------------|----------------|----------------|
| 123 | **Mininet: Rapid Prototyping for Software-Defined Networks** | Lantz et al., HotNets 2010 | The canonical "infrastructure paper enables a new research class" precedent — at HotNets, no less. Mandatory citation for the framing. | Pass 2 | **Add** |
| 124 | **Emulab: An Integrated Experimental Environment for Distributed Systems** | White et al., OSDI 2002 | Older, broader sibling to Mininet. Same argument: testbed innovation justified by the experiment classes it unlocked. | Pass 1 | **Add** |
| 125 | **CloudLab / Chameleon / FABRIC** | Ricci & Eide ;login: 2014 — pick one | Modern testbed-paper canon. Useful for direct positioning: "Pramana is to agentic measurement what FABRIC is to programmable networks." | Pass 1 | **Bookmark** |
| 126 | **ns-3 / OMNeT++ / gem5 — simulator-as-research-artifact papers** | Multiple — pick one | Demonstrates the same argument applies to simulators. Pramana spans real + simulated, so positioning against both lineages strengthens the case. | Pass 1 | **Bookmark** |
| 127 | **Reproducibility / Credibility Crisis literature in networking** | Credibility Crisis (already #19), Bajpai et al. 2019, ACM ROC 2020+ | Pramana's strongest *new use case*: reproducible-by-construction research. Frame as use-case innovation, not engineering. | Pass 1 | **Add (one citation, beyond #19 which is pending)** |
| 128 | **Differential / Counterfactual Network Testing** | e.g., NetDiff (Lopes et al.), Hoffman et al. (already #20) | Pramana enables differential experiments by construction — same workload across multiple bottleneck regimes. New use case. | Pass 1 | **Bookmark** |

**Defense move enabled:** "The HotNets, OSDI, and SIGCOMM canon contains a clear lineage of *infrastructure papers* whose innovation is measured by the experiment classes they unlock — Mininet (SDN research), Emulab (distributed-systems testbeds), gem5 (architecture simulation). Pramana is the agentic-era entry in this lineage. The innovations are: (a) reproducible-by-construction research, (b) controlled bottleneck-regime sweeps that are infeasible without programmable substrates, (c) cross-vertical replication studies, (d) differential experiments at scale. None of these are possible with current agentic stacks."

---

## Thread J — Lessons-Learned Touchstones (the canon Pramana should be in conversation with)

The user wants Pramana's lessons "general enough to inform first-principles agentic systems design." That conversation has a small number of canonical artifacts. The HotNets paper should engage with them explicitly.

| #   | Paper / System | Authors / Venue | Why it matters | Suggested pass | Recommendation |
|-----|----------------|-----------------|----------------|----------------|----------------|
| 129 | **Building Effective Agents** | Schluntz, Zhang et al. (Anthropic), 2024 — engineering blog post | The most-cited industry artifact distilling lessons from agent deployment. Frames the "workflow vs agent" distinction Pramana sits exactly atop. | Pass 2 | **Add (treat as canonical)** |
| 130 | **A Practical Guide to Building Agents** | OpenAI, 2025 — guide | Companion to the Anthropic piece. Emphasizes the same "deterministic spine, LLM heads" pattern Pramana embodies. | Pass 1 | **Add** |
| 131 | **What We Learned from a Year of Building with LLMs** | Yan et al. (O'Reilly), 2024 | Cross-team practitioner synthesis. Useful for engaging the "lessons" register without sounding like a single vendor. | Pass 1 | **Add** |
| 132 | **The Shift from Models to Compound AI Systems (Zaharia et al.)** | Already #86 (Round 1). | Tag also under Thread J as the academic-side companion to the practitioner posts above. | upgrade | **Already in corpus — upgrade priority** |

**Defense move enabled:** "The cross-industry consensus — Anthropic's *Building Effective Agents*, OpenAI's *Practical Guide*, the Sky Lab *Compound AI Systems* essay — converges on a shared design discipline: deterministic workflow spine, LLM-driven heads, explicit grounding boundaries. Pramana extends this discipline to a domain where the spine controls *real infrastructure*, not just software tools. The lessons we report from doing so — about intent compression, telemetry typing, and amortization — are intended to feed back into that conversation."

---

## Round 2 Summary

**Strong Adds (Pass 2, 6 papers):** #106 Code-as-Policies, #108 LLM-Modulo, #113 MetaGPT, #123 Mininet, #129 Anthropic *Building Effective Agents*

**Pass 1 Adds (10 papers):** #107 ProgPrompt, #109 Chain-of-Code, #110 LMQL, #115 Agent Workflow Memory, #117 prompt-caching ref, #124 Emulab, #127 reproducibility-crisis citation, #130 OpenAI guide, #131 O'Reilly

**Reclassifications / upgrade priorities (5):** #87 DSPy → Threads F + G; #24 Voyager → Thread G primary; #53 Reflexion → Thread G; #72 Spec-as-Discipline → Thread H; #88 CoALA → Threads B + H

**Bookmarks (5):** #111 Self-Discover, #122 Bitter-Lesson HotOS pieces, #125 CloudLab/FABRIC, #126 ns-3/gem5, #128 differential-testing literature

**New corpus total after both rounds:** 79 + 15 (Round 1 strong + pass-1) + 16 (Round 2 strong + pass-1) = **110** papers. Examiner budget 80–150 — still in range, but tight enough that the next pass should be synthesize, not expand.

---

## Mapping threads to HotNets paper sections

If the paper outline becomes:

- **§1 Intro** — opens with the NetReplica-trap concession and pivots: Pramana's contribution is a class of use cases + two general insights.
- **§2 Background** — Threads A (environments), B (compound AI), C (protocols).
- **§3 Why now** — Threads I (use-case lineage: Mininet → Pramana) and J (lessons canon).
- **§4 Architecture / Thin-Waist** — Threads C (protocol-layer), F (grounding), G (amortization).
- **§5 Vignettes** — concrete use cases enabled (replication at scale, differential experiments, controlled bottleneck sweeps).
- **§6 Lessons / Implications for Agentic Systems** — Insights A and B explicitly distilled, with Thread H as the framing.
- **§7 Related Work** — combine Threads A, B, C, E with explicit positioning sentences.

This is the corpus needed to write that paper without leaving any reviewer attack unanswered.

---

# Round 3 — Expansive Inclusion Pass (added 2026-04-27)

User instruction: do not be myopic at this stage. Add an extensive set of candidates so the survey covers every adjacent thread. Pruning happens later. The entries below are organized by thread and intentionally inclusive — many will be skipped or downgraded after Pass 1, but missing them now creates blind spots.

Counters resume at #133. **Status convention:** all Round-3 entries default to "Pass 1, Add" unless flagged otherwise — Examiner archetype with explicit "extensive" instruction.

---

## Thread A+ — Environment / Action-Space (expanded)

| #   | Paper / System | Provenance | Note |
|-----|----------------|-----------|------|
| 133 | Mind2Web | Deng et al., NeurIPS 2023 | Web agents at scale; complement to WebArena |
| 134 | WebShop | Yao et al., NeurIPS 2022 | Earliest grounded web-task env, foundational |
| 135 | WebVoyager | He et al., ACL 2024 | Real-website agent eval |
| 136 | BrowserGym / AgentLab | ServiceNow et al., 2024 | Modular env stack — closest "thin-waist for web agents" |
| 137 | OSWorld-Verified / OSAtlas | various 2024–2025 | OSWorld follow-ups; environment hardening |
| 138 | AndroidWorld | Rawles et al. (Google), 2024 | Mobile agent env; same controllability claim, different OS |
| 139 | Mobile-Agent / AppAgent | various 2024 | App-domain action space |
| 140 | ALFWorld / ALFRED | Shridhar et al., ICLR 2021 / CVPR 2020 | Text+vision grounded action; long-standing env-design canon |
| 141 | GAIA Benchmark | Mialon et al. (Meta), ICLR 2024 | "Real-world AI assistant" benchmark |
| 142 | AssistantBench | Yoran et al., 2024 | Web-task suite emphasizing real-world reproducibility |
| 143 | OSWorld-Bench / WorkArena | ServiceNow, 2024 | Enterprise-task env |
| 144 | Anthropic Computer Use (CUA) | Anthropic, 2024 docs + paper | Production deployment of computer-use agents — engineering canon |
| 145 | OpenAI Operator | OpenAI, 2025 | Same — production browser-use deployment |
| 146 | The AgentCompany | Xu et al., 2024 (already #67 in corpus) | Reclassify under Thread A |
| 147 | AgentBench | Liu et al., ICLR 2024 (already #66) | Reclassify under Thread A |

## Thread B+ — Compound AI / Agent-as-Systems-Research (expanded)

| #   | Paper / System | Provenance | Note |
|-----|----------------|-----------|------|
| 148 | LLM Compiler / Multi-step Function-Calling Compiler | Kim et al., ICLR 2024 | Treats LLM calls as DAGs to be compiled — direct sibling to thin-waist as compilation target |
| 149 | Sky Computing essays | Stoica, Patterson et al., CACM/ASPLOS keynotes | Position pieces; cite the ones explicitly framing AI as a sky-computing workload |
| 150 | TextGrad / Optimizers via Agent-System Interfaces | Yuksekgonul et al., 2024 (already #78) | Reclassify — gradient-style optimizers over compound-AI graphs |
| 151 | EFFE / Efficient Foundation-Function Execution lit | misc 2024–2026 | Survey-level coverage of compound-AI system design |
| 152 | Karpathy "Software 2.0/3.0" essays | Karpathy 2017–2024 | Canonical context; cite once |
| 153 | "AI Engineering" (Chip Huyen) | 2024 book / O'Reilly | Practitioner-grade synthesis of AI-as-systems-engineering discipline |
| 154 | Dean / Ghemawat-style position pieces on AI infra | Dean 2024 keynotes | Foundation citations for "AI changes systems requirements" |

## Thread C+ — Protocol-Layer / Tool-Use (expanded)

| #   | Paper / System | Provenance | Note |
|-----|----------------|-----------|------|
| 155 | ToolLLM / ToolBench | Qin et al., ICLR 2024 | Largest-scale tool-use training/eval canon |
| 156 | API-Bank | Li et al., EMNLP 2023 | Earlier sibling; cite for the lineage |
| 157 | Berkeley Function-Calling Leaderboard (BFCL) | Patil group, 2024 | Live leaderboard — the empirical anchor for "function calling matters" |
| 158 | StableToolBench / ToolSandbox | misc 2024 | Reproducibility-focused tool-use benchmarks |
| 159 | NexusRaven / Octopus / Granite-FunctionCall | various 2024 | Open-source function-calling models — engineering canon |
| 160 | A2A Protocol Spec (deep) | Google 2025 | Already #92 — pull deeper, treat as primary doc |
| 161 | Anthropic MCP — server/client SDK papers | Anthropic 2024–2026 | Already #91 — pull associated tutorials/specs |
| 162 | Computer-Use Protocols (Anthropic + OpenAI) | various 2024–2025 | The "screen-as-action-surface" protocol family |

## Thread D+ — Sandboxing / Durability / Reliability (expanded)

| #   | Paper / System | Provenance | Note |
|-----|----------------|-----------|------|
| 163 | E2B / Modal / Daytona — code-sandbox infra | various 2023–2025 | Engineering references for agent code execution |
| 164 | Cradle | Tan et al., 2024 | Game-environment agent with explicit sandboxing protocol |
| 165 | Ray | Moritz et al., NSDI 2018 | Durable distributed execution — frequently invoked as agent backbone |
| 166 | vLLM | Kwon et al., SOSP 2023 | Inference-serving canon; cite for the prompt-caching/KV-reuse argument |
| 167 | SGLang | Zheng et al., 2024 | Programmable LLM serving — closest to "deterministic spine for LLM workflows" |
| 168 | AgentSafetyBench / AgentDojo / InjecAgent | various 2024–2025 | Safety eval for agent execution |
| 169 | Reliability / failure-mode taxonomies | AgentFail (#99 already), Bommasani et al. surveys | Reclassify; expand under Thread D |
| 170 | LangSmith / Helicone / Phoenix / AgentOps | engineering | Observability stack — Pramana's telemetry plane has these as peers |

## Thread E+ — Scientific Agents / Self-Driving Labs (expanded — major gap)

This is the strongest cross-domain lineage for Pramana. Self-driving labs in chemistry/biology/materials are the *exact* analogue: domain-aware controllable substrates feeding autonomous research loops. Should not be skimped.

| #   | Paper / System | Provenance | Note |
|-----|----------------|-----------|------|
| 171 | Coscientist (Boiko et al.) | Nature 2023 | LLM-driven autonomous chemistry — direct sibling system |
| 172 | ChemCrow | Bran et al. (Aspuru-Guzik), Nat Mach Intell 2024 | LLM + chemistry tools agent |
| 173 | ChemOS / ChemOS 2.0 | Aspuru-Guzik group, Matter 2024 | Self-driving-lab software architecture — direct thin-waist analogue |
| 174 | Cooper Group autonomous chemists | Burger et al., Nature 2020 | Robot chemist canon |
| 175 | Granda / Steiner autonomous synthesis | Nature 2018, 2019 | Earlier autonomous-chemistry canon |
| 176 | gpCAM | Noack et al. (LBNL), Nat Rev Phys 2021 (already #46) | Pull deeper — Bayesian-driven autonomous data acquisition |
| 177 | Colmena | Ward et al. (Argonne), MLHPC 2021 (already #47) | Pull deeper — ML-steered HPC simulation campaigns |
| 178 | INTERSECT | ORNL 2024 (already #48) | Autonomous experiment architecture — federated lab control |
| 179 | Polybot / Argonne autonomous-lab platforms | various 2023–2025 | Materials self-driving lab |
| 180 | IBM RoboRXN | IBM Research 2020+ | Industrial autonomous chemistry |
| 181 | Materials Acceleration Platforms (MAPs) survey | Aspuru-Guzik et al., Nat Rev Mater 2024 | Cross-MAP synthesis; ideal touchstone for "domain-aware substrates" |
| 182 | Autonomous Discovery in the Chemical Sciences | Coley et al., Angew Chem 2020 | Foundational survey |
| 183 | LAB-Bench | FutureHouse 2024 (already proposed #103) | Pull deeper |
| 184 | SciCode | Tian et al., NeurIPS 2024 (already #101) | Pull deeper |
| 185 | ScienceAgentBench | Chen et al., ICLR 2025 (already #102) | Pull deeper |
| 186 | CRISPR-GPT | Huang et al., 2024 | LLM agent for genome editing — domain-grounding example |
| 187 | DiscoveryWorld | Allen AI (already #49) | Reclassify under Thread E |
| 188 | Eureka (NVIDIA) | Ma et al., ICLR 2024 (already proposed #104) | Pull deeper — robotics-domain reward shaping |
| 189 | SayCan / VIMA / RT-1 / RT-2 | Google/DeepMind, 2022–2024 | Robotics action-grounding canon |
| 190 | Bluesky (BNL) / funcX / Globus / Parsl | DOE, various (already #73) | Reclassify under Thread E — federated-execution canon |

## Thread F+ — Stochastic→Deterministic Grounding (expanded)

| #   | Paper / System | Provenance | Note |
|-----|----------------|-----------|------|
| 191 | NL-to-SQL: Spider / BIRD / WikiSQL | various, 2018–2023 | Foundational analogue to Pramana's NL→spec — cite one representative |
| 192 | Text-to-API / Gorilla / NexusRaven | already in corpus #28 | Reclassify under Thread F |
| 193 | TypeChat | Microsoft 2023 | Engineering tool — schema-constrained NL-to-spec |
| 194 | Outlines / Guidance / LMQL | already proposed #110 | Pull deeper |
| 195 | DSPy | already #87 | Pull deeper |
| 196 | Constrained / grammar-guided decoding survey | various 2024 | One survey entry |
| 197 | Symbolic + LLM hybrids: LLM+ASP, LLM+TLA+ | misc 2024–2025 | Niche but directly supports the "deterministic spine" framing |
| 198 | Spec-driven AI engineering / Picky / Spec | Berkeley + others 2024 (overlaps #72) | Reclassify under Thread F |
| 199 | World models / JEPA / Dreamer | LeCun, Hafner | Theoretical foundations for grounding — cite one |

## Thread G+ — Amortization / Memory / Skill Reuse (expanded)

| #   | Paper / System | Provenance | Note |
|-----|----------------|-----------|------|
| 200 | MemGPT | Packer et al., 2023 (already proposed #97) | Pull deeper |
| 201 | MemoryBank / A-Mem | various 2024 | Memory-as-OS-resource canon |
| 202 | Generative Agents | Park et al., UIST 2023 (already proposed #89) | Pull deeper — explicit memory/reflection |
| 203 | Agent Workflow Memory (AWM) | Wang et al., 2024 (already proposed #115) | Pull deeper |
| 204 | Cradle (skill library aspects) | already proposed #164 | Reclassify under Thread G as well |
| 205 | DSPy compile-and-cache | already #87 | Tag under Thread G |
| 206 | MetaGPT SOPs | Hong et al., ICLR 2024 (already #113) | Pull deeper |
| 207 | Voyager skill library | already #24 | Pull deeper |
| 208 | Reflexion | already #53 | Pull deeper |
| 209 | Mooncake / KV-cache-centric serving | Moonshot 2024 | Engineering substrate for amortization |
| 210 | Anthropic prompt-caching docs | already proposed #117 | Treat as canonical engineering ref |

## Thread H+ — Decomposition / First-Principles (expanded)

| #   | Paper / System | Provenance | Note |
|-----|----------------|-----------|------|
| 211 | Tree of Thoughts / Graph of Thoughts | Yao et al. NeurIPS 2023; Besta et al. 2024 | Reasoning-pattern canon — useful as foil ("emergent decomposition vs principled decomposition") |
| 212 | ReWOO / LATS / Reasoning frameworks | various 2023–2024 | Cite one representative for the orchestration-pattern landscape |
| 213 | Self-Discover | Zhou et al., NeurIPS 2024 (already proposed #111) | Pull deeper |
| 214 | LLM-Modulo (Kambhampati) | already #108 | Pull deeper |
| 215 | Stochastic Parrots (Bender et al.) | FAccT 2021 | Foundational critique; useful for setting up "what LLMs cannot do alone" |
| 216 | Sutton Bitter Lesson | 2019 essay | Canonical context — cite once for the meta-argument |
| 217 | Subbarao Kambhampati position pieces | various 2024–2026 | Critical voice; one citation |

## Thread I+ — Innovation-by-Use-Case (expanded — defends NetReplica trap)

This thread should be over-stuffed. Reviewer attacks of the form "this is engineering not innovation" are answered by *over-citing* the precedent for infrastructure-as-research.

| #   | Paper / System | Provenance | Note |
|-----|----------------|-----------|------|
| 218 | Mininet | Lantz et al., HotNets 2010 (already #123) | Pull deeper — flagship precedent at the same venue |
| 219 | Emulab | White et al., OSDI 2002 (already #124) | Pull deeper |
| 220 | PlanetLab | Peterson et al., HotNets 2002 / SIGOPS 2006 | Earlier infra-as-research canon |
| 221 | GENI | Berman et al., Computer Networks 2014 | Federated testbed canon |
| 222 | CloudLab | Ricci & Eide, ;login: 2014 (already proposed #125) | Pull deeper |
| 223 | Chameleon | Keahey et al., USENIX ATC 2020 | Modern testbed-as-research-platform paper |
| 224 | FABRIC | Baldin et al., Networking 2020 | Flagship NSF substrate |
| 225 | EdgeNet / Ahoy / DETERLab | misc | Background on testbed lineage |
| 226 | ns-3 / OMNeT++ / gem5 | already proposed #126 | Pull deeper — pick one as representative |
| 227 | Ray | already proposed #165 | Tag under Thread I as well — Ray's NSDI '18 paper is a "we built this so others can do new things" innovation argument |
| 228 | Spark | Zaharia et al., NSDI 2012 | Same pattern — infrastructure paper whose innovation is the workload class enabled |
| 229 | TensorFlow / JAX | various — Abadi 2016 / Bradbury 2018 | ML-platform innovation-by-use-case canon |
| 230 | Reproducibility crisis in networking | Bajpai et al., SIGCOMM CCR 2019; ACM ROC 2020+ | Use-case pillar: reproducible-by-construction |
| 231 | NetMicroscope / NetUnicorn replication studies | UCSB lab work + collaborators | Direct proximate cases |
| 232 | Differential testing of network protocols | NetDiff (Lopes), Coyote, MAX | Use-case pillar: differential experiments |
| 233 | Counterfactual measurement / causal networking | Hoffman et al. (already #20), Spider, Coyote | Use-case pillar: counterfactuals |
| 234 | Self-driving labs as use-case-innovation precedent | (cross-ref Thread E) | Over-citation: same argument has been won in chemistry/biology |

## Thread J+ — Lessons-Learned Canon (expanded)

| #   | Paper / System | Provenance | Note |
|-----|----------------|-----------|------|
| 235 | Anthropic *Building Effective Agents* | already #129 | Pull deeper |
| 236 | OpenAI *Practical Guide to Building Agents* | already #130 | Pull deeper |
| 237 | O'Reilly *What We Learned from a Year of Building with LLMs* | already #131 | Pull deeper |
| 238 | Compound AI Systems essay (Zaharia et al.) | already #86 | Pull deeper |
| 239 | Sierra / Klarna / production-deployment case studies | misc 2024–2025 | Use one as a "reality check" citation |
| 240 | "AI for Networking" surveys | Sahay et al., Hong et al. (already #29) | Reclassify under Thread J |
| 241 | HotOS recent essays on systems-research innovation | misc 2023–2026 | Citation backbone for "what counts as innovation" |

## NEW Thread K — Foundations of Hourglass / Layering / Narrow Waist

Not in earlier rounds, but now load-bearing because Pramana's name and structure invoke the hourglass model. Reviewers will check whether the paper engages with the foundations.

| #   | Paper / System | Provenance | Note |
|-----|----------------|-----------|------|
| 242 | "End-to-End Arguments in System Design" | Saltzer, Reed, Clark — TOCS 1984 | Foundational layering principle. Mandatory if §4 invokes architectural layering. |
| 243 | "Design Philosophy of the DARPA Internet Protocols" | Clark, SIGCOMM 1988 | Foundational. Provides vocabulary for narrow-waist arguments. |
| 244 | On the Hourglass Model | Akhshabi & Dovrolis, arXiv:1607.07183 (already #74) | Pull deeper — load-bearing. |
| 245 | "On the Hourglass Model" CACM 2019 | Beck | Modern essay; cite alongside #244 |
| 246 | "Layering Considered Harmful" | various older positions | Foil — when narrow waists are wrong. Cite to show awareness. |
| 247 | Spinellis et al. on cross-layer protocol design | misc | Background on when boundaries are renegotiated |

## NEW Thread L — Agent Infrastructure / Platform Engineering

Most are non-academic, but they form the *engineering canon* that HotNets reviewers will assume the authors know.

| #   | Paper / System | Provenance | Note |
|-----|----------------|-----------|------|
| 248 | LangChain / LangGraph | already #50 | Pull deeper for current state |
| 249 | AutoGen | already #51 | Pull deeper |
| 250 | CrewAI | engineering | Modern multi-agent framework — cite as ecosystem evidence |
| 251 | Semantic Kernel (Microsoft) | engineering | Same |
| 252 | AutoGen Studio | Microsoft Research, 2024 | Workflow-design front-end — direct contrast to Pramana's thin waist |
| 253 | DSPy compiler | already #87 | Tag under Thread L |
| 254 | Inferless / BentoML / Modal — agent serving | engineering | Production-deployment canon |
| 255 | Sierra (Yao Fu's work) | engineering / 2024 papers | Production agent platform |

## NEW Thread M — Autonomous Experimentation in Other Domains (parallel thin-waist stories)

Already heavily added under Thread E+. Repeated here as a cross-cut so the user can prune by *thread* rather than by paper. (No new entries; cross-references E+ above.)

---

## Round 3 Summary

| Thread | New entries this round (numbered) | Notes |
|--------|----------------------------------|-------|
| A+ Environments | 133–147 (15) | 13 net-new + 2 reclassifications |
| B+ Compound AI | 148–154 (7) | mostly position pieces / engineering canon |
| C+ Protocols | 155–162 (8) | tool-use deep canon |
| D+ Sandboxing | 163–170 (8) | engineering + safety eval |
| E+ Scientific agents / SDLs | 171–190 (20) | **major gap closed** — self-driving-labs lineage |
| F+ Grounding | 191–199 (9) | broader NL→spec literature |
| G+ Amortization | 200–210 (11) | memory, skill, caching expanded |
| H+ Decomposition | 211–217 (7) | reasoning patterns + critical voices |
| I+ Use-case innovation | 218–234 (17) | **NetReplica defense thread, over-cited deliberately** |
| J+ Lessons canon | 235–241 (7) | broader practitioner canon |
| K Hourglass foundations | 242–247 (6) | **new thread — load-bearing for §4** |
| L Agent platforms | 248–255 (8) | engineering ecosystem |
| M (cross-cut, no new) | — | — |

**Total Round 3 new entries: ~123 (with overlap and reclassification — net new ≈100, the rest are pull-deeper on existing).**

**New corpus total: 79 (existing) + 31 (Rounds 1+2 net-new) + ~100 (Round 3 net-new) = ~210 candidates.**

This deliberately overshoots the 80–150 Examiner budget. The user asked for inclusion at this stage; pruning will happen at the next pass with explicit criteria (relevance to defense thread + uniqueness — i.e., does it carry an argument no other paper in the corpus does?).

## Suggested next steps

1. **Ingest in batches.** NLM throughput is the bottleneck. Batch by thread (A+, then E+, then I+ are highest leverage for the HotNets defense). Defer M and L until after Pass 1 of A/E/I.
2. **Keep the prune criteria explicit.** Each survivor should answer one of: (a) supplies a defensive argument no other source does, (b) is a *foundational* citation reviewers expect, (c) is an *adjacent peer system* (Coscientist, ChemOS, OSWorld) whose lineage Pramana joins.
3. **Run `/survey synthesize`** after the highest-leverage threads have Pass 1 complete. Synthesis can drive a second round of pruning.

