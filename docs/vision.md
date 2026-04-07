# The Agentic Thin Waist: A Joint Platform for AI-Accelerated Network Measurement Research

**Shared Working Document — UCSB (Arpit Gupta, Jaber Daneshamooz) × UCI (Sangeetha Abdu Jyothi, Alagappan)**
**Last updated:** April 1, 2026
**Target venue:** HotNets 2026 (June deadline, 6-page vision paper)
**Downstream targets:** SIGCOMM/NSDI (full system paper), NSF CIRC proposal (~Aug/Sept 2026)

---

## 1. The Big Idea

Networking research is hitting an inflection point. AI agents can now design scheduling algorithms (Glia, MIT 2025), run hundreds of autonomous experiments overnight (Karpathy's autoresearch, March 2026), and parse thousands of papers to extract reusable methodology. But these successes share a hidden dependency: they work only because a fast evaluation substrate already exists. Glia relies on Vidur (a high-fidelity LLM inference simulator). Autoresearch relies on GPT-2 training fitting on a single GPU with a five-minute eval cycle. Remove the evaluation substrate, and agents produce hypotheses into the void.

For networking, this substrate rarely exists. Reproducing a single IMC paper typically requires weeks of manual infrastructure setup: configuring emulated topologies, calibrating cross-traffic, deploying applications, and collecting telemetry. Every new research question demands a bespoke pipeline. The result: innovation speed is bottlenecked not by the pace of ideas but by the overhead of setting up experiments. We call this the *ideation-to-result gap*.

Prior platforms that did provide fast evaluation — Puffer for ABR algorithms, Pantheon for congestion control — produced genuine acceleration within their domains. But each was a vertical: a multi-year engineering effort serving one application, one problem, one community. Extending the same capability to a different domain required starting from scratch.

**Our proposal:** an *agentic thin waist* — a platform architecture, inspired by IP's hourglass, that decouples diverse research intents (above) from diverse evaluation substrates (below) through a narrow, composable service layer. The key insight is that two complementary capabilities — Sangeetha's reasoning layer (deciding what experiments to run and why) and Arpit/Jaber's execution substrate (running them under controlled conditions and collecting data) — are two halves of the same system. Neither is complete without the other. Together, they form a full agentic measurement stack.

---

## 2. What Each Team Brings

### 2.1 UCSB: The Execution Substrate (Arpit + Jaber)

Over the past three years, we have built a series of progressively disaggregated systems, each separating a previously coupled concern in network measurement:

- **NetUnicorn (CCS '23):** Decoupled experiment logic from execution infrastructure. Same experiment definition runs on different testbeds.
- **NetReplica / NetForge:** Introduced the Cross-Traffic Profile (CTP) algebra — a formal representation of network conditions that separates static attributes (capacity, latency, loss) from dynamic attributes (cross-traffic patterns). CTP clusters, derived from Satyam's preprocessing of real network traces, provide a structured vocabulary for specifying "what kind of network environment do I want?"
- **NetGent (MLSys '25 Workshop):** NFA-compiled application workflows. Automates the execution of ~100 application workflows (YouTube, Zoom, Teams, speed tests, etc.) using Playwright-based browser automation. Converts high-level intent ("run YouTube at 1080p for 60 seconds") into deterministic, reproducible execution scripts.
- **IEF (NeurIPS '25):** Intrinsic Evaluation Framework for network representation quality. Provides domain-general metrics for assessing whether learned representations capture meaningful structure.
- **TurboTest (NSDI '26):** Speed test infrastructure demonstrating the measurement pipeline at scale.

**The agentic thin waist subsumes all of these into a unified platform** with six composable microservices:

| Service | Role | Plane |
|---------|------|-------|
| **Experiment API** | Accepts research intent (natural language or structured JSON) | Intent |
| **CTP Service** | Selects/generates network condition profiles from the CTP algebra | Representation |
| **NetGent Service** | Executes application workflows (pre-validated scripts from a GitHub repo) | Execution |
| **Substrate Worker** | Configures the actual network environment (tc, netem, tshark, tcpreplay) | Execution |
| **Telemetry Service** | Collects, stores, and serves all experimental data via a unified API | Data |
| **Orchestrator** | LLM-driven coordination — translates intent into precise service calls, manages lifecycle | Intelligence |

**Architecture decisions (locked in as of April 1, 2026):**

- **Local-first deployment.** The orchestrator, telemetry service, and database all run on the user's machine. `git clone` → `docker compose up` → generating data. No cloud accounts or API keys required for step one. Cloud (AWS, etc.) is used strictly for scaling data generation.
- **All intelligence in the orchestrator.** Every other service is a dumb executor. No LLM calls outside the orchestrator. NetGent in the thin waist is a deterministic executor of pre-validated workflows, not a generative system.
- **No data through the orchestrator.** Substrate workers communicate directly with the CTP service and telemetry. The orchestrator sends messages, never data.
- **Portability via configuration.** A connectivity manager abstraction (Docker SDK for local, AWS API for cloud) means the same experiment specification runs on a laptop, PINOT campus testbed (~60 nodes), ESnet, or Google WAN. Only a configuration flag changes.

**Current status:** Task force sprint (Jaber + Haarika + Manni + Eugene) is building the MVP. Target: functional intent → data pipeline by mid-April.

### 2.2 UCI: The Reasoning Layer and Knowledge Graph (Sangeetha + Alagappan)

Sangeetha's group has built the complementary reasoning and analysis layer:

- **ArachNet (HotNets '25):** Agentic workflow for Internet measurement research. Four specialized agents — QueryMind, WorkflowScout, SolutionWeaver, RegistryCurator — that formulate research questions, plan experiments, and interpret results. This is the reasoning layer that decides *what* to measure and *why*.
- **Airavat (SIGCOMM '26 submission):** Full system extending ArachNet to production-grade agentic measurement.

**The Knowledge Graph:** Alagappan has constructed a Neo4j knowledge graph of ~2,000 measurement papers from SIGCOMM, IMC, CoNEXT, and Sigmetrics. The construction pipeline works as follows:

1. **PDF parsing:** Text extraction via Grobid (text only; figures and tables are not currently parsed).
2. **Section tagging:** A smaller LLM (Llama-based, for cost efficiency at scale) tags each section of the paper with what it explains (problem statement, methodology, validation, etc.).
3. **Structured extraction:** For each paper, the system extracts algorithms used, parameter values, rationale for parameter choices, data sources (e.g., RIPE Atlas, CAIDA), and pipeline steps.
4. **Graph construction:** Extracted entities become nodes; relationships (e.g., "this pipeline step uses this dataset") become edges. Embeddings enable similarity-based retrieval.

**Current state of the knowledge graph:**

- Covers ~2,000 papers from top networking venues.
- Strong extraction for design and validation sections (detailed prompts already developed).
- Data sources are captured as nodes with metadata (timeline, collection method, rationale).
- Pipeline steps are stored as sequential JSON (parallel execution not yet handled).
- Extraction uses handwritten rules (20–30 variations) for structured output rather than free-form LLM generation, to minimize hallucination.

**What the knowledge graph does NOT yet capture (identified in March 30 meeting):**

- Precise experimental environment setups (bandwidth values, topology details, number of machines, specific configurations).
- Table and figure content from PDFs.
- Information from external dataset websites (e.g., CICIDS, NetDetection dataset pages).
- GitHub repositories or tool artifacts cited in papers.

---

## 3. The Combined System: How It Works

The combined agentic thin waist brings together reasoning (UCI) and execution (UCSB) into a closed loop:

```
[Knowledge Graph: 2K+ papers]
        ↓ query
[Reasoning Layer: ArachNet/Airavat agents]
        ↓ formulate intent
[Agentic Thin Waist: Experiment API]
        ↓ decompose
[CTP Service + NetGent + Substrate Worker]
        ↓ execute
[Telemetry Service: structured results]
        ↓ analyze
[Reasoning Layer: interpret, refine, iterate]
        ↓ next experiment
        ... (closed loop)
```

The interface between the two teams is the **intent specification**: Sangeetha's system formulates *what* experiment to run (expressed as structured JSON or natural language); Jaber's system *executes* that intent and returns structured results. The knowledge graph enables systematic selection of which papers to target and what experimental conditions to replicate.

---

## 4. Capabilities and Limitations

### 4.1 What the Platform Currently Supports

**Network conditions we can generate:**
- Wired emulation via tc/netem (configurable bandwidth, latency, loss, jitter)
- Static bottleneck attributes (capacity, base RTT, queue size)
- Dynamic cross-traffic patterns (via CTP clusters derived from real network traces, replayed via tcpreplay)
- Symmetric and asymmetric link configurations
- Multiple bottleneck regimes (Jaber's NetReplica capability)

**Application workflows we can execute (~100 workflows, growing):**
- Video streaming: YouTube (multiple resolutions), Netflix, Twitch
- Video conferencing: Zoom, Google Meet, Microsoft Teams (two-party and multi-party calls)
- Speed tests: NDT, Ookla, fast.com, Wehe
- Web browsing: Configurable page loads, HTTP archive replay
- General: iperf3, ping, traceroute, custom CLI tools

**Telemetry we can collect:**
- Full packet captures (PCAPs)
- Transport-layer metrics (throughput, RTT, retransmissions, congestion window)
- Application-layer metrics (video bitrate, resolution switches, rebuffering, MOS scores)
- Network utilization and queue occupancy

**Infrastructure backends supported:**
- Local Docker (default, zero-config)
- PINOT campus testbed (~60 nodes, UCSB)
- AWS EC2 (via connectivity manager, in development)
- ESnet and Google WAN (planned, same interface)

### 4.2 What the Platform Does NOT Currently Support

- **Cellular / wireless networks.** No wireless emulation or mobile network modeling. Entirely out of scope for the current version.
- **Real Internet paths.** Current mode is controlled emulation, not active probing over the live Internet.
- **Arbitrary external tools from GitHub.** If a paper requires running a custom tool from its GitHub repository (e.g., Docker compose for a specific system), the platform cannot automatically discover and deploy it. Papers requiring such tools are currently out of scope for automated replication.
- **Figure/table parsing from PDFs.** The knowledge graph extracts text only. Table content (often critical for understanding experimental setups) and figures are not parsed. Grobid may support table extraction — Alagappan will investigate.
- **External dataset website crawling.** If a paper references a dataset hosted on a website (e.g., CICIDS), the knowledge graph captures the citation but does not crawl the website for additional context (topology, collection methodology, etc.). This is deferred due to the unstructured nature of arbitrary websites.
- **Parallel pipeline execution.** The knowledge graph represents pipeline steps sequentially. Parallel execution paths are serialized.
- **LLM-driven generative workflows in the pipeline.** NetGent's generative mode (LLM-powered synthesis of new application workflows) is available as a separate development tool but is deliberately excluded from the thin waist's production pipeline for determinism and reliability.

---

## 5. The Replication Use Case: Our First "Killer App"

Replication is the most natural first application of the combined system, and the primary demonstration for the HotNets paper. The pipeline works as follows:

1. **Paper selection (Knowledge Graph).** Query the knowledge graph: "Which published measurement papers from top venues (2019–2025) involve controlled network experiments with application-level traffic that fall within the thin waist's current capabilities?" This yields a ranked list of candidate papers.

2. **Experiment extraction (Reasoning Layer).** For each selected paper, extract the experimental setup: What network conditions were used? What applications were tested? What metrics were reported? What were the success criteria? This is where the knowledge graph's experiment-section extraction (currently being developed) is critical.

3. **Intent specification (Interface).** Translate the extracted setup into a thin-waist intent specification (structured JSON): target bandwidth, latency, cross-traffic profile, application workflow, telemetry requirements.

4. **Execution (Thin Waist).** The platform configures the network environment, runs the application workflows, and collects telemetry — automatically, without manual setup.

5. **Evaluation (Analysis).** Compare reproduced results against published results. Assess reproduction fidelity. Identify discrepancies and potential causes.

6. **Iteration (Closed Loop).** If results diverge, the reasoning layer can propose refinements: adjust parameters, try different cross-traffic profiles, vary application versions. The thin waist executes the refined experiment. This loop continues until convergence or a diagnostic is produced.

**Candidate papers for initial reproduction (to be finalized jointly):**
- Video conferencing comparison under varied network conditions (e.g., the Meet/Teams/Zoom study with table of three applications across controlled bandwidth/latency)
- ABR algorithm benchmarking (controlled comparison of adaptive bitrate strategies)
- Congestion control fairness analysis (bandwidth utilization and fairness across CC algorithms)

Jaber has curated ~30 papers across these areas using DeepSearch and NotebookLM, seeded with the thin waist's capabilities and constraints. These will be shared with Alagappan as the starting corpus for the knowledge graph pilot.

---

## 6. Knowledge Graph Integration Plan

### 6.1 Immediate Steps (April 2026)

**Step 1: Pilot knowledge graph with ~30 papers.**
Rather than modifying the existing 2,000-paper graph, Alagappan will construct a new knowledge graph from Jaber's curated ~30 papers. This allows rapid iteration on extraction quality without risking the existing infrastructure.

**Step 2: Experiment-section extraction prompts.**
Alagappan will design new prompts (analogous to what was done for design sections) to extract experimental environment details: network conditions, topology, number of machines, application configurations, metric definitions. This will be tested on 10–15 papers first, with output shared with Jaber for validation and iterative refinement.

**Step 3: Structured environment context.**
The extraction should produce structured output mapping to the thin waist's input parameters:
- Bandwidth (upstream/downstream)
- Latency (RTT)
- Loss rate
- Cross-traffic type and intensity
- Application(s) under test
- Duration
- Metric(s) of interest
- Default vs. explicitly specified parameters

### 6.2 Design Decisions (from March 30 meeting)

- **Single knowledge graph.** Infrastructure-level and application-level papers will be merged into one graph, not separated. Hallucination risk is mitigated by embedding-based similarity matching (not free-form LLM generation) and explicit handwritten extraction rules.
- **Table parsing: investigate.** Alagappan will check whether Grobid supports table extraction. If not, alternative PDF parsers will be evaluated. Tables are high-priority because experimental parameters are frequently reported only in tables.
- **External website crawling: deferred.** Too complex for now (unstructured HTML, no standard format). The knowledge graph will link to dataset citations but will not crawl linked websites.
- **GitHub artifact discovery: deferred.** The knowledge graph can extract cited GitHub links, but exploring and integrating the tools found there is out of scope for the initial system.

### 6.3 Scaling Plan

Once the pilot with ~30 papers validates the extraction pipeline, extend to the full corpus. Cost optimization is important: the current pipeline uses smaller Llama models to keep costs manageable at 2,000-paper scale. Prompt design will need to be broken into phases (section tagging → environment extraction → parameter structuring) to work within smaller model context windows.

---

## 7. Evidence Plan for HotNets

The HotNets paper requires enough empirical grounding that reviewers believe (a) the platform exists and works, (b) the benefits are real, and (c) the vision has teeth. We do NOT need a full system evaluation — that is the SIGCOMM paper.

| # | Evidence Component | Necessity | Lead | Deadline |
|---|---|---|---|---|
| E1 | Knowledge graph statistics: How many papers are reproducible? How many match our capabilities? | CRITICAL | Alagappan | April 5 |
| E2 | End-to-end reproduction of 2–3 papers | CRITICAL | Jaber + Haarika | May 1 |
| E3 | Infrastructure portability: same spec runs on Docker, PINOT, (stretch: AWS) | HIGH | Jaber | May 7 |
| E4 | Time comparison: manual reproduction vs. thin waist (headline speedup number) | HIGH | Arpit | May 7 |
| E5 | LLM agent iteration demo (stretch goal) | NICE-TO-HAVE | Jaber + Eugene | May 15 |

**Minimum viable paper = E1 + E2 + E4.** Quantitative diagnosis + working demos + headline speedup.
**Strong paper = E1 + E2 + E3 + E4.** Adds portability proof.
**Home run = all five.** Adds the agentic vision demo.

---

## 8. Division of Labor

| Responsibility | Lead | Supporting |
|---|---|---|
| Knowledge graph construction (30-paper pilot) | Alagappan | Jaber (paper list, validation) |
| Experiment-section extraction prompts | Alagappan | Sangeetha (prompt design guidance) |
| Thin waist MVP (intent → data) | Jaber | Haarika, Manni, Eugene |
| Paper selection and curation (~30 papers) | Jaber | Alagappan (cross-check with existing graph) |
| Reproduction experiments (E2) | Jaber + Haarika | Alagappan (extraction output) |
| Portability demonstration (E3) | Jaber | — |
| Time comparison metrics (E4) | Arpit | Jaber |
| LLM agent integration (E5, stretch) | Jaber + Eugene | — |
| Paper writing | Arpit + Sangeetha | All |

**Bandwidth note:** Alagappan has limited bandwidth through April (IMC submissions due end of April). He can dedicate a few hours per week now, with full availability starting May. The pilot with ~30 papers is scoped to fit this constraint.

---

## 9. Timeline

| Date | Milestone | Owner |
|---|---|---|
| **Week of April 1** | Jaber sends curated paper list (~30 papers) with specifications to Alagappan | Jaber |
| **Week of April 1** | This shared document circulated for comments | Arpit |
| **April 5** | E1: Knowledge graph queries (reproducibility statistics) | Alagappan |
| **April 15** | Thin waist MVP functional end-to-end | Jaber |
| **April 20** | Paper selection finalized (2–3 for E2), validated jointly | Jaber + Sangeetha |
| **April 29** | Sangeetha's IMC deadline → more bandwidth | Sangeetha + Alagappan |
| **May 1** | E2: Reproductions complete on Docker | Jaber + Haarika |
| **May 7** | E3: Same experiments on PINOT | Jaber |
| **May 7** | E4: Time comparison documented | Arpit |
| **May 15** | E5: LLM agent iteration (stretch) | Jaber + Eugene |
| **May 15 – June** | Paper writing sprint | Arpit + Sangeetha |
| **~Mid-June** | HotNets submission (estimated, based on last year's July 1 deadline minus 2 weeks) | All |

---

## 10. Broader Vision (Beyond HotNets)

The HotNets paper stakes the claim. The longer arc:

**Replication at scale (SIGCOMM/NSDI).** Once the pilot demonstrates the pipeline works for 2–3 papers, extend to dozens. Evaluate reproduction fidelity systematically. This is the "killer app" that validates both the reasoning layer and the execution substrate.

**Counterfactual dataset generation.** The thin waist can systematically generate datasets pairing identical network conditions with diverse application behaviors — data that does not exist today. Manni's dissertation (the "broadband blind spot") centers on building the first such datasets.

**Iterative refinement.** Once a paper is replicated, LLM agents can stress-test, identify failure modes, generate hypotheses, and iterate — the Glia pattern applied to *any* networking problem, not just LLM inference scheduling.

**Community infrastructure (NSF CIRC, ~Aug/Sept 2026).** A three-PI proposal: UCSB (platform development), UCI (knowledge graph and reasoning), CAIDA/UCSD (KC Claffy — dataset integration, community credibility, adoption). Deep Medhi at NSF has indicated CIRC as the right vehicle.

**Production validation.** The same experiment specification that runs on Docker runs on ESnet (Inder Monga, LDRD FY27) and Google WAN (Ranjita Bhagwan). Progressive fidelity: iterate fast on controlled substrates, validate on real infrastructure.

---

## 11. Collaborator Note: Dongsu Han (KAIST)

Sangeetha has noted that Dongsu Han (KAIST), who helped shape the ArachNet idea during his UCI sabbatical, should be part of this collaboration. He is not interested in US grants but should be included on papers. This is agreed.

---

## 12. Open Questions

1. **Success metrics for replication.** What constitutes a "successful" reproduction? Exact numerical match? Within-confidence-interval? Qualitative agreement on trends? We need to define this before executing E2.

2. **Knowledge graph node/edge schema for experiments.** What structured fields should the experiment-section extraction produce? This needs to be jointly designed to match the thin waist's input parameters. Sangeetha suggested adding more nuanced node and edge types to explicitly capture the parameters Jaber needs.

3. **HotNets deadline.** Last year it was July 1 (moved to July 9). Assuming 1–2 weeks earlier this year, we estimate mid-June. Need to confirm when the call is published.

4. **Author list.** Working assumption: Arpit, Sangeetha, Jaber, Alagappan, [Dongsu Han?], [KC Claffy — depends on meeting outcome]. To be finalized.

---

*This document synthesizes context from: Arpit's Obsidian Vault project notes (Agentic Thin-Waist, HotNets Draft Introduction, Empirical Evidence Roadmap, Brain Dump on Glia/Autoresearch, KC Meeting Prep, Sangeetha Collaboration Synthesis), email exchanges with Sangeetha (March 3, 2026) and KC Claffy (March 23, 2026), the March 10 Sangeetha–Arpit collaboration call, and the March 30 joint team meeting (Jaber, Sangeetha, Alagappan).*
