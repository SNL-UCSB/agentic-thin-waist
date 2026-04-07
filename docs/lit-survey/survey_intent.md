---
topic: Agentic Systems for Accelerating Systems and Networking Research
slug: agentic-systems-research
archetype: Examiner
created: 2026-04-04
last_updated: 2026-04-04
---

# Survey Intent: Agentic Systems for Accelerating Systems and Networking Research

## Archetype

**Examiner** — Comprehensive mastery of an emerging area, with a dual purpose: (1) understand how the community is thinking about using agentic AI to accelerate systems research, and (2) validate whether the agentic-thin-waist (empirical backend) is the right artifact to invest in.

| Parameter | Value |
|-----------|-------|
| Triage scope | 80-150+ papers |
| Deepen targets | 15-25 at Pass 2 |
| Pass 3 count | 5-8 foundational papers |
| Synthesize output | Full narrative survey + positioning argument |

## Surveyor Profile

**Role:** PI at SNL-UCSB. Builder of netUnicorn (CCS '23) and the agentic-thin-waist platform. Deep expertise in network measurement, composable experiment infrastructure, progressive disaggregation (intent/representation/execution planes).

**Expertise in this area:**
- **Deep:** Network measurement infrastructure, composable experiment pipelines, bottleneck-centric data generation (NetForge), NFA-based workflow automation (NetGent/BQT+), hourglass/thin-waist architecture for bridging research intents to infrastructure
- **Developing:** LLM-based orchestration, multi-agent system design, how the broader community is structuring the "agentic research loop"
- **New to:** Evolutionary search approaches (SkyDiscover/AlphaEvolve), production-scale LLM-for-ops deployments (Confucius), fully autonomous research agents (AI Scientist)

## Mental Model at Survey Start (Baseline for WYSIATI Comparison)

The agentic research loop for systems problems is fundamentally different from an ML pipeline. An ML pipeline optimizes models for generalizability or performance on fixed benchmarks. The agentic research loop is about **synthesizing, refining, and optimizing hypotheses and system designs** — a creative, iterative process where the agent must reason about trade-offs, propose experiments, interpret results, and refine understanding.

Current mental model of the landscape:
- **Glia (MIT):** Automates the design optimization loop with Researcher+Supervisor agents. Focuses on *designing better systems* (e.g., GPU schedulers). Does not address the empirical infrastructure question — assumes a simulator/testbed exists.
- **SkyDiscover (Berkeley):** Evolutionary search for algorithm discovery. Powerful for optimization, but operates on well-defined objective functions. Systems research often requires defining the objective *as part of the research*.
- **Confucius (Meta/Harvard):** Production network management, not research. But shows that intent-driven agent orchestration works at scale.
- **AI Scientist (Sakana):** Full autonomy from idea to paper. Impressive but domain-general — unclear if it can handle the infrastructure-heavy requirements of systems research.
- **Agentic Thin Waist (this project):** The empirical backend — composable infrastructure that translates research intents into executable experiments with controlled bottleneck regimes. Positioned as the "execution plane" that agentic research systems need but don't build.

**Hypothesis entering the survey:** Most agentic research systems assume the existence of a clean experimental interface (a simulator, a benchmark, an API). The hard, unsolved problem in systems/networking is *building that interface* — making real infrastructure experimentally controllable, composable, and reproducible. The thin-waist is that interface.

## Core Questions

### Q1: Does the field need a composable empirical backend?
Are people building monolithic end-to-end systems (idea → experiment → paper in one blob), or is there demand for a modular empirical layer that different agentic systems can plug into? Is the thin-waist architecture generalizable, or does every domain need its own bespoke execution substrate?

### Q2: Is the intent → representation → execution decomposition emerging elsewhere?
Progressive disaggregation is the core design principle of the thin-waist. Do other systems decompose the research loop similarly? Or do they use different abstractions (e.g., Glia's Researcher/Supervisor split, SkyDiscover's evolutionary population model)?

### Q3: Where is demand concentrating?
- Design optimization (Glia) — "make this system better"
- Algorithm discovery (SkyDiscover) — "find a better algorithm for this objective"
- Operations automation (Confucius) — "manage this network"
- Full-loop research (AI Scientist) — "do the research for me"
- Empirical infrastructure (thin-waist) — "give me controlled experiments"

Which of these has the most traction, the most unsolved problems, the most future demand?

### Q4: What are the real pain points?
If the future of research requires agentic tools, what are the actual bottlenecks? Is it:
- Intent specification (how do you tell an agent what experiment to run?)
- Execution fidelity (can agents actually control real infrastructure reliably?)
- Result interpretation (can agents reason about noisy systems data?)
- Reproducibility (can agent-driven experiments be replicated?)
- Composability (can you mix and match components across systems?)
- Something else entirely?

### Q5: What's fundamentally missing from the first-principles perspective?
What would a first-principles architecture for the agentic research loop look like? What invariants must hold? What are the right abstractions? Is there a "thin waist" for the agentic research loop itself?

## Success Criteria

| Criterion | Target |
|-----------|--------|
| **Deliverable** | Full narrative survey that doubles as a vision/position piece. Should articulate the first-principles architecture for agentic systems research and position the thin-waist within it. Potentially a survey paper or the framing for a grant proposal. |
| **Scope** | 80-150 papers across systems, networking, AI/ML, and HCI |
| **Timeline** | Usable draft within 3-4 weeks (by ~2026-05-02) |
| **Time budget** | Flexible (PI-level, can delegate reading to students) |

## Seed Corpus

### Tier 1: Core Systems (Pass 3 required)
| Paper | Authors | Venue | Key Idea |
|-------|---------|-------|----------|
| Glia | Hamadanian, Karimi, Alizadeh, Balakrishnan et al. | arXiv:2510.27176 | Multi-agent LLM for systems design optimization |
| Confucius | Wang et al. | SIGCOMM 2025 | Production multi-agent LLM for hyperscale network ops |
| SkyDiscover (AdaEvolve, EvoX) | Liu, Cemri et al. | Berkeley Sky Lab 2025 | LLM-driven evolutionary search for systems optimization |
| AI Scientist v2 | Lu, Lu, Clune, Ha et al. | Sakana AI, arXiv:2504.08066 | Full autonomous research loop |
| netUnicorn | Beltiukov, Guo, Gupta, Willinger | CCS 2023 | Thin-waist for composable network data collection |

### Tier 2: Important Context (Pass 2 recommended)
| Paper | Authors | Venue | Key Idea |
|-------|---------|-------|----------|
| NetConfEval | Wang et al. | CoNEXT 2024 | LLM benchmark for network configuration |
| POPPER | — | arXiv:2502.09858 | Agentic falsification-based hypothesis testing |
| Agent Laboratory | Schmidgall et al. | JHU, arXiv:2501.04227 | Multi-agent research automation |
| DiscoveryWorld | Allen AI | AI2 | Benchmark for scientific discovery agents |

### Tier 3: To Be Expanded (via citation/author search)
- Papers citing Glia, Confucius, AI Scientist, netUnicorn
- Recent papers by Alizadeh/Balakrishnan (MIT), Minlan Yu (Harvard), Stoica (Berkeley), Clune/Ha (Sakana)
- "AI for Systems" workshop papers (MLSys, SOSP, OSDI, HotNets)
- Self-driving networks / autonomous network management
- LLM-driven experiment orchestration
- Automated systems benchmarking

## Expansion Strategy

Follow citation chains and author trails:
1. **Forward citations** of core papers — who is building on this?
2. **Backward references** — what foundations do these systems share?
3. **Author tracking** — what are the core authors working on next?
4. **Adjacent communities** — AI4Science, AutoML, self-driving networks, LLM-for-code

## Advisor/Collaborator Input

Self-directed (PI). Key collaborators to consider perspectives from:
- Walter Willinger (co-author on netUnicorn, measurement methodology)
- The NetForge/BQT+ team (systems that form the thin-waist building blocks)
