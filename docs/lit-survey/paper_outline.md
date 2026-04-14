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

**The problem for networking:** Reproducing a single IMC paper requires weeks of manual infrastructure setup. Each new question demands a bespoke pipeline. Innovation is bottlenecked not by ideas but by experiment overhead. When teams build infrastructure to address this, they build verticals: Pantheon for congestion control, Puffer for ABR, NetSecBed for cybersecurity dataset generation. Each solves the problem for one community and one application, requiring years of engineering that cannot be reused elsewhere.

**Thesis:** A *composable empirical backend* — a thin-waist service layer that decouples research intent from evaluation substrate — is the critical missing infrastructure for the agentic era. The key insight is that existing solutions are verticals (one domain, one substrate, one pipeline) while the problem demands a horizontal: a composable layer that any agent or researcher can plug into for any networking experiment. **Critically, the thin waist is not the infrastructure itself — it is the minimal experiment specification that sits between diverse intents above and diverse substrates below.** Above the waist: research intents (replicate this paper, sweep this parameter, compare these algorithms). Below: heterogeneous substrates (Docker on a laptop, AWS cloud, FABRIC slices, residential edge nodes like ARK, scamper-instrumented Raspberry Pis). The waist itself is the spec language and the orchestrator that maps intents to substrates. We argue this is not a domain-specific solution but a fundamental architectural requirement, and we demonstrate it concretely for networking.

**Contributions:**
1. A landscape analysis showing the verification wall across 5 threads of agentic systems research
2. A first-principles architecture (the thin waist) derived from cross-domain convergence — framed as a *specification layer*, not an infrastructure layer
3. A working prototype with structured experiment specs over heterogeneous substrates (local Docker, AWS) and the constraint-mapping research problem this exposes
4. Initial evidence from paper replication and a roadmap to real edge infrastructure

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

### 2.1b The Vertical Trap

When the infrastructure gap becomes acute, teams build domain-specific testbeds:

| Vertical | Domain | What It Automates | What It Can't Do |
|----------|--------|-------------------|------------------|
| Pantheon | Congestion control | CC algorithm benchmarking | Anything beyond CC evaluation |
| Puffer | ABR streaming | ABR algorithm comparison | Anything beyond ABR |
| NetSecBed | Cybersecurity | Attack scenario execution + PCAP generation | No bottleneck control, no traffic shaping, no application QoE, no agentic loop |

These verticals prove the need — each team independently builds container-native, declarative, reproducible pipelines because the horizontal layer doesn't exist. But they are single-purpose: NetSecBed's 60 attack containers can't measure YouTube QoE under controlled bottleneck regimes; Puffer can't generate labeled cybersecurity datasets. **The composable backend subsumes these verticals by providing the shared infrastructure they each had to build from scratch** — controlled network conditions, automated capture, structured telemetry — as reusable services that any domain-specific experiment can plug into.

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

**An important clarification.** Critics of thin-waist proposals frequently confuse the *substrate* with the *waist*. They are different things. Docker, AWS, FABRIC, ARK, and Scamper-instrumented Raspberry Pis are all substrates — heterogeneous, evolving, each with its own constraints. The thin waist is **the minimal experiment specification language and the orchestrator that translates that specification onto whichever substrate can satisfy it**. The substrate is what the waist sits on top of; the waist is what makes the same intent portable across substrates that share no other interface.

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

**Scoping principle: one bottleneck link at a time.** The platform deliberately scopes each experiment to a single bottleneck link rather than a full network topology. The bottleneck dictates application performance; modeling it precisely with controllable static attributes (capacity, base latency, buffer, AQM) and controllable dynamics (cross-traffic intensity and burstiness via CTPs) is sufficient to study the vast majority of application-layer questions in a way that is reproducible across substrates. Multi-link topologies are out of scope for the spec language; once a multi-link experiment can be expressed as a composition of single-bottleneck experiments, it falls back into scope.

**Key design decisions:**
- **Dumb services, smart controller.** All intelligence in the orchestrator. Every other service is a deterministic executor — there is exactly one LLM in the system, and it sits in the orchestrator parsing intent.
- **No data through the orchestrator.** Substrate workers communicate directly with CTP and Telemetry services. The orchestrator sends messages, never data.
- **Local-first.** `git clone` → `docker compose up` → generating data. Cloud and remote substrates dispatch the same experiment spec; only the connectivity backend changes.

### 4.2 Progressive Disaggregation

NetForge's key contribution: separating bottleneck intent from execution:
1. **Intent vs. mechanism:** what network conditions to create vs. how to create them
2. **Static vs. dynamic:** link capacity/latency/buffer vs. cross-traffic intensity/burstiness
3. **Demand vs. context:** observed traffic patterns vs. original trace provenance

Cross-Traffic Profiles (CTPs) transform passive packet traces into reusable, composable pressure signals. This gives agents a structured vocabulary: "Apply CTP cluster 7 (bursty, 80% utilization) to a 10 Mbps link with 50ms RTT."

**Why this matters vs. existing testbeds:** Container-native testbeds like NetSecBed can automate execution and capture, but without controlled bottleneck regimes, the resulting data reflects only the container runtime's uncontrolled network behavior — not the real-world conditions researchers need to study. The CTP algebra and static/dynamic decomposition are what make the thin waist a *network measurement* platform rather than merely a *script execution* framework. The bottleneck regime is the object of study; without it, you have automation but not science.

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

## Section 6: The Hard Problems (~0.75 pages)

The MVP runs on Docker and AWS — substrates that impose few constraints on what we can do. The interesting research begins when we try to port the same experiment specification onto real edge infrastructure where bandwidth is committed to hosts, kernel-level operations are forbidden, and operators cannot afford to reserve resources per Docker container. Three problems become first-class.

### 6.1 The Constraint Mapping Problem

Every infrastructure imposes its own constraints: ARK enforces residential bandwidth commitments and integrates measurements only as Scamper-callable code, FABRIC enforces slice quotas, cloud nodes have no edge fidelity but no policy ceiling, residential Raspberry Pis can run Docker but not at full host bandwidth. Today, "porting" an experiment to a new substrate is a manual rewrite. The thin waist promises to eliminate that rewrite. To deliver on the promise, we need:

1. **A formal specification of infrastructure constraints** — what services each node type can host, what policies (rate limits, time windows, kernel access) apply, what communication patterns are permitted.
2. **A many-to-many service-to-node mapping graph** — for each microservice in an experiment, which node types can host it, and what does each placement cost?
3. **Intent satisfiability checking** — given a user intent and an infrastructure's constraint set, can this experiment run? If not, what is the minimal relaxation that makes it feasible?
4. **Constructive feedback to the user** — when the requested experiment cannot run on the chosen substrate, the orchestrator should explain why and propose alternatives, not silently fail.

This is the central unsolved problem. Naïvely "shipping a Docker container to ARK" violates host commitments; naïvely "rewriting in Scamper" defeats the point of a thin waist. The research is in designing the abstractions that bridge these worlds.

### 6.2 The Edge Fidelity Imperative

Cloud is convenient and easy to dispatch to. But for many measurement questions, *where the experiment runs* is part of *what the experiment measures*. Running a residential broadband study from AWS loses the very thing the study was about. The thin waist must work on edge nodes — with their constraints — or it becomes irrelevant for the research it claims to enable. We frame this as a non-negotiable design requirement: every architectural decision must preserve the option to deploy on constrained edge infrastructure, even if doing so requires more work than a cloud-only path.

### 6.3 Provenance for Agent-Driven Experiments

When agents run hundreds of experiments and claim a result, the provenance chain must be auditable: intent → hypothesis → experiment spec → substrate placement → execution → telemetry → insight → next hypothesis. PROV-AGENT and Flowcept provide starting points for the schema. Open question: what is the minimal provenance representation for an *agent-driven* experiment loop, and how does it integrate with the orchestrator's reasoning trace?

### 6.4 Safety for Infrastructure-Touching Actions

Most agentic systems assume their substrate is safe to operate on freely. Confucius has dry-run validators and human approval gates. Osprey has a four-layer pre-execution safety architecture for accelerator hardware. The thin waist's experiments are lower-stakes — emulated networks, not physical instruments — but as the substrate diversifies into real edge nodes, the safety problem returns. What is the minimal safety wrapper that makes an LLM-orchestrated experiment safe to run on a home router?

### 6.5 Towards a Universal Experiment Specification

Is there a single "SQL for experiments," or must each domain (networking, accelerators, chemistry, biology) define its own DSL with shared structural patterns? The cross-domain convergence in §3.4 suggests the structural patterns are universal even if the domain vocabularies differ. Whether this convergence becomes a standard or remains parallel evolution is an open community question.

---

## Figures (planned)

1. **The verification wall table** (Section 2.1) — systems × substrate × who built it
2. **The vertical trap table** (Section 2.1b) — Pantheon, Puffer, NetSecBed and what each can't do
3. **Specification-vs-substrate diagram** (Section 3.2) — intents above, substrates below, the thin waist as the spec layer in between (this is the headline figure)
4. **Three-layer stack diagram** (Section 3.3) — agent harness / empirical backend / domain instruments
5. **Cross-domain convergence table** (Section 3.4) — independent emergence of the same pattern
6. **Thin waist architecture diagram** (Section 4.1) — six services, three planes
7. **Constraint mapping diagram** (Section 6.1) — service-to-node many-to-many graph with policy constraints, illustrating intent satisfiability checking
8. **Replication pipeline** (Section 5.1) — knowledge graph → intent → execution → comparison

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

### Should-cite (verticals that prove the need)
- Pantheon (Yan et al., ATC 2018) — CC benchmarking vertical
- Puffer (Yan et al., NSDI 2020) — ABR streaming vertical
- NetSecBed (Bitzki, Kreutz et al., 2026) — cybersecurity dataset generation vertical; shares container-native + declarative specs motivation but no bottleneck control, no agentic loop, no cross-domain composability

---

*Outline produced from: full_synthesis.md, design_principles.md, vision.md, deepening_notes.md, and 3 targeted NLM queries (2026-04-06). Updated 2026-04-10 with sharper specification-layer framing, single-bottleneck scoping, and the constraint mapping problem — all surfaced in the KC Claffy collaboration meeting on the same date.*
