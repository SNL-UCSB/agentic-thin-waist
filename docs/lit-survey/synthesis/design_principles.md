# Eight Design Principles for a Generalizable Empirical Backend

**Source:** Cross-domain literature synthesis (48 papers across testbeds, SDLs, experiment platforms, digital twins, provenance)

## The Principles

### 1. Intent/Mechanism Disaggregation
**Separate *what* to do from *how* to do it.**

The experiment API expresses intent; the backend translates to substrate-specific mechanisms. This is netUnicorn's core principle, but it appears independently across domains: Confucius (NL → DSLs), ChemOS 2.0 (recipe → instrument drivers), SED-ML (model specification → simulator execution).

*Sources: netUnicorn (CCS '23), Confucius (SIGCOMM '25), ChemOS 2.0 (Matter '24), Abolhasani (Accounts of Chem Res '22)*

### 2. Minimal Spanning Layer / Thin Waist
**The shared abstraction should be as weak as possible while supporting the necessary diversity.**

Beck's formal result: a spanning layer "sufficient for necessary applications but as weak as possible" maximizes deployment scalability. Richness kills adoption. The experiment API should expose the minimal set of primitives that enable diverse intents above and diverse substrates below.

*Sources: Beck "On the Hourglass Model" (CACM '19), POSIX Abstractions (EuroSys '16), Lakehouse (CIDR '21), CWL (CACM '22)*

### 3. Federation over Standardization
**Don't require all substrates to be identical. Federate diverse resources through a common slice/experiment abstraction.**

GENI, FABRIC, Chameleon, CloudLab all federate heterogeneous resources without homogenizing them. The key: a shared *allocation and lifecycle API*, not shared infrastructure. Each substrate keeps its own capabilities; the federation layer provides discovery, slicing, and coordination.

*Sources: GENI (Computer Networks '14), FABRIC (IEEE IC '19), Chameleon (ATC '20), CloudLab (ATC '19), ExoGENI (TridentCom '12)*

### 4. Declarative Experiment Specification
**Experiments should be described declaratively (desired state), not imperatively (step-by-step).**

SED-ML encodes *which models, which modifications, which simulations, how to post-process, how to visualize* — five components that map directly to the experiment lifecycle. CWL specifies inputs/outputs/tool invocations and lets the engine handle scheduling. The Popper convention treats experiments as CI/CD pipelines.

*Sources: SED-ML (BMC Sys Bio '11, v5 '24), CWL (CACM '22), Popper Convention (IPDPS '17), SweetPea (BRM '22)*

### 5. Embedded Provenance
**Lineage tracking must be built into the execution layer, not bolted on.**

Flowcept captures provenance non-intrusively via pub-sub adapters. PROV-AGENT extends W3C PROV with agent-specific constructs — capturing not just data lineage but *decision lineage* (why the agent chose each action). ProvDB uses git as a provenance backbone.

*Sources: Flowcept (eScience '24), PROV-AGENT (arXiv '25), ProvDB (HILDA '17), Workflow Provenance in SciML (arXiv '20)*

### 6. Fidelity-Aware Substrates
**The backend must expose what approximations it makes.**

Users and agents need to know whether the substrate faithfully represents the target system. Hifinet monitors emulated packet delays in real-time to assess fidelity. Mininet runs unmodified code to ensure functional fidelity. The sim-to-emulation architecture bridges fidelity levels.

*Sources: Mininet (HotNets '10), Hifinet (Computer Networks '24), Sim-to-Emulation (WNS3 '25), Network Simulation Fidelity (ACM TOMACS)*

### 7. Composable Microservice Architecture
**Domain specificity lives in leaf services; orchestration is domain-agnostic.**

ChemOS 2.0 has six modules (learning, robotics, characterization, databases, interfaces, analysis) behind a fog-computing kernel. INTERSECT uses message-bus integration (instruments publish, AI subscribes). The thin-waist uses Flask microservices with a shared models layer. ModelingToolkit composes through shared interface types.

*Sources: ChemOS 2.0 (Matter '24), INTERSECT (ORNL '24), ModelingToolkit (arXiv '21), Agentic Thin Waist*

### 8. CI/CD for Experiments
**Every experiment should be a reproducible pipeline — version-controlled, containerized, with automated validation.**

The Popper convention combines git + Docker + CI for systems experiments. MLflow's three abstractions (Tracking, Projects, Models) map to configure/execute/measure. CloudLab profiles capture entire experiment environments. The replication crisis in CS (70%+ failure to reproduce) motivates this as a first-class concern.

*Sources: Popper (IPDPS '17, P-RECS '19), MLflow (IEEE DE '18), CloudLab Profiles (ATC '19), Replication Crisis (CACM '20)*

---

## Cross-Domain Analogues: The Empirical Backend Pattern

| Domain | System | Backend Architecture | Thin Waist |
|--------|--------|---------------------|------------|
| **Networking** | netUnicorn / Agentic Thin Waist | Intent → CTP/Substrate Worker → Telemetry | Experiment API |
| **Chemistry** | ChemOS 2.0 | Recipe → Instrument drivers → Analysis | Fog computing kernel |
| **Accelerators** | Osprey | NL → Execution plan → EPICS | Plan-first orchestrator |
| **Materials** | INTERSECT | AI intent → Message bus → Instruments | Pub-sub message layer |
| **ML** | MLflow | Config → Training → Tracking | Tracking API |
| **Biology** | SED-ML | Model spec → Simulator → Post-processing | XML schema |
| **Production networks** | Confucius | NL → DAG → DSL tools | Three foundational DSLs |

**The pattern is universal:** intent → composable representation → domain-specific execution, with provenance threading through all layers.

## The Three-Layer Stack (from OpenClaw synthesis)

```
Layer 1: AGENT HARNESS (OpenClaw, Claude Code, Glia, SkyDiscover)
         ↕ skills, tools, MCP
Layer 2: EMPIRICAL BACKEND (thin-waist, ChemOS, Osprey, INTERSECT)
         ↕ instrument APIs, DSLs
Layer 3: DOMAIN INSTRUMENTS (tc, pgbench, EPICS, mass spec, GPU cluster)
```

The empirical backend IS the middle layer. It provides composition, safety, and reproducibility that the agent harness lacks and raw instruments can't provide alone.

## Key New Papers for the Corpus

### Must-add to NLM (Pass 2-3):
- Beck "On the Hourglass Model" (CACM '19) — formal theory
- ChemOS 2.0 (Matter '24) — the SDL analog
- SED-ML — the "DSL for experiments"
- CWL (CACM '22) — thin-waist for workflows
- Popper Convention (IPDPS '17) — CI/CD for experiments
- PROV-AGENT (arXiv '25) — provenance for agentic workflows
- CloudLab (ATC '19) — composable testbed design
- FABRIC (IEEE IC '19) — federated programmable infrastructure
- Google Overlapping Experiments (KDD '10) — experiment platform design
- SDL Review (Chemical Reviews '24) — comprehensive self-driving lab survey
