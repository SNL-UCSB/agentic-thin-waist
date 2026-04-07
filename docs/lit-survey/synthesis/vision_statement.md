# Vision Statement: The Composable Empirical Backend

**Source:** NLM final synthesis across 30+ sources (2026-04-05)

## The First-Principles Argument

> **Autonomous discovery currently hits a "verification wall" where agentic reasoning remains ungrounded because researchers must custom-build monolithic simulators for every new problem. A composable empirical backend is the critical missing infrastructure because it provides a standardized "spanning layer" that allows agents to ground hallucination-prone reasoning in reproducible, physical ground truth across any systems domain. By decoupling scientific intent from heterogeneous substrates, we shift the bottleneck of research from infrastructure engineering back to creative problem formulation.**

## The Thin Waist of the Agentic Research Stack

Following Beck's hourglass model ("a spanning layer as weak as possible"), the thin waist is NOT MCP, NOT a heavyweight harness — it is a **Minimal Experiment Specification (MES)**: a target-agnostic task graph that specifies experimental parameters and success criteria without assuming the specifics of the underlying substrate.

Evidence: netUnicorn disaggregates intents into reusable tasks. Confucius uses DSLs as a spanning layer. SED-ML encodes the five components of any experiment (model, change, simulation, data processing, output). The MES is the domain-agnostic generalization of all of these.

## Four-Plane Architecture

| Plane | Function | Realized By |
|-------|----------|-------------|
| **Intent Plane** | Define research objectives, decoupled from substrate | netUnicorn's intent disaggregation |
| **Instruction Plane** | Domain-extensible recipes (skills) that map intent to primitives | OpenClaw's markdown skills |
| **Mechanism Plane** | Progressive disaggregation of structure from pressure | NetForge's static-dynamic decomposition |
| **Provenance Plane** | Agent-centric metadata: prompts, reasoning, decisions, lineage | PROV-AGENT's W3C PROV extension |

## The Verification Wall

Every agentic system in the corpus hits the same wall:
- Glia needs Vidur (a simulator someone else built)
- AI Scientist needs Python + GPU (trivially available for ML, not for systems)
- AlphaEvolve needs Google's internal evaluation harnesses
- Confucius needs Meta's production network tools (decades of engineering)

**The composable empirical backend removes this wall** by providing a standardized execution substrate that any agentic system can plug into — whether for networking (tc/netem), databases (pgbench), OS (stress-ng/eBPF), cloud (Terraform), or physical science (EPICS).

## Connection to the Tooling Framing

As you said: "It's all about tooling."
- The thin-waist IS tooling for controlled experiments
- Osprey IS tooling for accelerator facility instruments
- OpenClaw IS a tooling harness for general agent capabilities
- The empirical backend IS the tooling layer between agentic intelligence and physical/virtual infrastructure

The key design insight from OpenClaw: **Skills (text recipes) are the extensibility mechanism.** Adding a new domain doesn't require new architecture — just a new skill file that teaches the agent how to compose the existing primitives.
