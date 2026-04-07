---
title: "Agentic AI for User Facilities — LBNL Workshop Book of Abstracts"
venue: Lawrence Berkeley National Lab, Jan 21-22, 2026
year: 2026
category: workshop
pass: 1
relevance: high
---

# [Pass 1] — Workshop Abstracts + Author Research

## Workshop Overview

"Agentic AI for User Facilities" — DOE national labs converging on agentic AI for scientific infrastructure. Key themes: plan-first orchestration, safety for physical facilities, provenance/reproducibility, federated agent deployment.

Organized by thellert@lbl.gov (Tobias Hellert, LBNL ATAP Division).

---

## Talk 1: Software Development Agents: The Blueprint for Scientific AI (Invited Talk #10)

**Key claim:** "Environment design matters more than model capability, and deterministic feedback loops are everything." Software dev agents (deployed across 30,000+ scientists/engineers) generalize to science: analyze data, draft papers, control hardware, process signals.

**Relevance to thin-waist:** Validates the principle that the *environment/substrate* is the bottleneck, not the LLM. The thin-waist IS the environment design for networking research.

---

## Talk 2: The Future of AI-empowered Physical Sciences (Invited Talk #11)

Autonomous experimentation (AE) via Bayesian optimization for x-ray scattering experiments in polymer science. Vision for agentic AI workflows in experimental sciences.

**Related work:** gpCAM (Marcus Noack, LBNL) — "Gaussian processes for autonomous data acquisition at large-scale synchrotron and neutron facilities." *Nature Reviews Physics, 2021*. GP-driven active learning deployed at ALS and SNS beamlines.

---

## Talk 3: For Provenance and with Provenance (Invited Talk #12)

**System: Flowcept** — ORNL multi-workflow provenance framework.

Two concepts:
- **"Provenance of Agents"** — captures agent decisions (LLM reasoning chains, tool calls, decision points) for root cause analysis and accountability
- **"Provenance with Agents"** — uses LLMs as interfaces to query/reason over complex runtime provenance data

Applications: computational chemistry, adaptive additive manufacturing at ORNL.

**Key concern:** Agent-driven workflows introduce "dataflow contamination" and non-determinism that threaten scientific reproducibility. Provenance is the critical enabler for trustworthy autonomous systems.

**Published work:**
- Souza, R. et al. — "Flowcept: A Lightweight Framework for Multi-Workflow Provenance." eScience 2024.
- GitHub: https://github.com/ORNL/flowcept
- Architecture: pub-sub (Redis/Kafka) for non-intrusive capture, MongoDB storage, W3C PROV-compatible

**Relevance to thin-waist:** Directly addresses a gap in the triage landscape — none of the core papers (Glia, AI Scientist, Confucius, SkyDiscover) address provenance or reproducibility of agent-driven experiments. The thin-waist's Telemetry Service could integrate Flowcept-style provenance to track how intents map to executions and results.

---

## Talk 4: Evaluating Agentic AI Systems (Invited Talk #13)

**Author:** runderwood@anl.gov — likely Ross Underwood, Argonne National Lab

Methodology for evaluating impact of agentic systems: importance of outcomes, breadth/robustness/efficiency of achievement. Lessons from adjacent domains.

**Relevance:** Evaluation methodology is a gap — how do you measure whether an agentic research system actually accelerates discovery?

---

## Talk 5: Frontier AI for Synchrotron Beamlines (Invited Talk #14)

AI for beamline operation: voice-controlled interactions, **beamline simulators for AI-driven evaluation**, robotic automation.

**Key insight:** They're building *beamline simulators* as evaluation environments for AI agents — exactly the Glia "Evaluation Playground" pattern, but for physical science infrastructure. This validates the thin-waist concept: you need a composable evaluation substrate before agents can operate.

---

## Talk 6: Osprey (Contributed Oral #15) — MOST RELEVANT

**Title:** "Osprey: A Production-Ready Framework for Deploying Agentic AI in Scientific User Facilities"
**Author:** Tobias Hellert (thellert@lbl.gov), LBNL ATAP Division
**Status:** Likely first publicly described at this workshop. No prior arXiv preprint or GitHub repo found as of research date.

### Abstract
Large-scale scientific user facilities: complex control systems with hundreds of thousands of channels, distributed expertise, strict safety requirements. Osprey transforms NL requests into transparent, auditable execution plans through:
1. **Plan-first orchestration** — intent → transparent plan → execution (not direct action)
2. **Multi-layer safety architecture** with human-in-the-loop approval
3. **Integration with EPICS** control systems (standard across DOE accelerators)

Being rolled out across DOE complex through Genesis mission and Multi-Office Accelerator Team.

### Architecture Mapping to Thin-Waist

| Osprey | Thin-Waist | Pattern |
|--------|-----------|---------|
| NL request → execution plan | Intent → experiment spec | Intent decomposition |
| Plan-first orchestration | Experiment API orchestration | Smart controller |
| Multi-layer safety + human approval | Validation (Confucius-style dry-run) | Safety as first-class |
| EPICS channel access | tc/tshark/tcpreplay | Domain-specific execution |
| DOE facility infrastructure | Network testbed infrastructure | Diverse substrates |

### Why Osprey Matters for This Survey

Osprey validates the thin-waist architectural pattern **in a completely different domain** (accelerator facilities vs. networking). The same decomposition — intent → auditable plan → safe execution on real infrastructure — appears independently in:
- Thin-waist (networking): intent → bottleneck regime spec → tc/tshark execution
- Osprey (accelerators): NL → execution plan → EPICS channel operations
- Confucius (production networks): NL → DAG → DSL tool execution

This convergence suggests the pattern is **fundamental**, not domain-specific.

### Genesis Mission & DOE Context

- DOE initiative for deploying AI across accelerator facility complex
- Multi-Office Accelerator Team coordinates across BES, NP, HEP offices
- Osprey is a key deliverable — production-grade, not research prototype
- EPICS is the universal control system substrate (like tc/netem is for networking)

**Monitor for publications:** IPAC 2026 proceedings, ICALEPCS, LBNL technical reports.

---

## Talk 7: Academy (Contributed Oral #16)

**Title:** "Building Scalable Agentic Systems for Science with Academy"

Modular, extensible middleware for deploying autonomous agents across federated research ecosystem: HPC systems, experimental facilities, data repositories. Case studies in materials science, micro-genomics, astronomy.

**No prior publications found.** Likely builds on or integrates with:
- **funcX / Globus Compute** — federated function-as-a-service for HPC (Chard et al., HPDC 2020)
- **Globus Flows** — workflow automation across distributed research infrastructure
- **Parsl** — parallel scripting across HPC resources (Babuji et al., HPDC 2019)
- **Colmena** (Ward et al., Argonne) — ML-steered simulation campaigns on HPC

**Relevance:** Academy = composable middleware between agents and federated infrastructure. Analogous to the thin-waist's Representation Plane.

---

## Related DOE Agentic AI Systems (from author research)

### INTERSECT (ORNL)
"INTelligent ExpERiments SeCurity and Trust" — open architecture for federated autonomous experiments connecting instruments, edge computing, and HPC with security/trust emphasis.

### Colmena (Argonne)
Ward, L. et al. "Colmena: Scalable Machine-Learning-Based Steering of Ensemble Simulations for Drug Design." IEEE/ACM MLHPC 2021. GitHub: https://github.com/exalearn/colmena
Agent-like decision making for computational experiments on HPC.

### gpCAM (LBNL)
Noack, M. et al. "Gaussian processes for autonomous data acquisition at large-scale synchrotron and neutron facilities." Nature Reviews Physics, 2021.
GP-driven active learning for autonomous beamline experiments.

### Bluesky (BNL)
NSLS-II data collection framework built on EPICS, with growing AI/ML integration for adaptive experiments.
