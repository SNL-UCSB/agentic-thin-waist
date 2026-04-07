# Gap Analysis: The Evaluation Substrate Problem

**Source:** NLM cross-corpus query, grounded in 25-source notebook (2026-04-04)

## Core Finding

Every agentic system in the corpus is fundamentally tethered to its **evaluation substrate** — the testbed, simulator, or execution environment where the agent runs experiments. Without the substrate, the system hits a **"verification wall"**: it can generate ideas but cannot determine if they work.

## Evaluation Substrate Inventory (NLM-grounded)

| System | Evaluation Substrate | Who Built It? | Domain-Locked? |
|--------|---------------------|---------------|----------------|
| **Glia** | Vidur (LLM inference simulator) + GPU cluster | Researchers/collaborators | Yes — LLM serving only |
| **AI Scientist** | Python + PyTorch/Jax + GPUs | Open-source community | Yes — ML training only |
| **Confucius** | Meta production infrastructure (NAPT, ODS, Robotron) | Meta (decades of internal tooling) | Yes — Meta networks only |
| **PolicySmith** | Kernel sandbox (CC) + trace-driven simulator (caching) | Domain experts | Yes — per-domain |
| **AlphaEvolve** | Google computational stacks (Borg, hardware sims) | Google (internal) | Yes — Google infra only |
| **POPPER** | Domain-specific observation sources | Varies per domain | Flexible but manual |
| **netUnicorn** | Composable thin-waist across diverse networks | **Builds the substrate itself** | No — domain-general |
| **NetForge** | Programmable bottleneck-centric data generation | **Builds the substrate itself** | No — any bottleneck regime |

## The Verification Wall

NLM analysis confirms: **none of these systems can function without their substrate.**

- Glia without Vidur = "no performance feedback loop"
- AI Scientist without Python+GPU = "a hallucination engine that can only write about hypothetical results"
- PolicySmith without kernel sandbox = "cannot guarantee safety or performance"
- AlphaEvolve without evaluation harness = "evolutionary search has no direction"

## What netUnicorn/NetForge Uniquely Provide

From NLM (grounded in papers):
> "What netUnicorn and NetForge provide is the **infrastructure layer itself**, which none of the other agentic systems build."

Specifically:
1. **netUnicorn**: "thin waist" that decouples intents from deployment mechanisms; enables endogenous data collection across diverse, realistic environments
2. **NetForge**: programmable substrate for bottleneck-centric data generation via Cross-Traffic Profiles; disaggregates observed demand from original context

## The Composable Empirical Backend Thesis

NLM synthesis (grounded across Barbarians at the Gate, Engram, netUnicorn, NetForge, POPPER):

> "There is strong evidence in this corpus that a **Composable Empirical Backend** is the critical missing layer for agentic research."

Three supporting arguments from the literature:

1. **The ADRS Assumption** (Barbarians at the Gate): The AI-Driven Research for Systems paradigm "explicitly assumes the existence of a **reliable verifier**." Current work is limited because each agent must be custom-fitted to a specific, often proprietary simulator.

2. **The Coherence Ceiling** (Engram): Even systems solving the coherence problem via persistent knowledge still "rely on independent runs against a fixed evaluator" — they don't solve the substrate problem.

3. **Scalability via Composability** (netUnicorn/NetForge): By making the empirical backend composable and programmable, you can "scale agentic discovery across underrepresented regimes and diverse environments."

## NLM's Skeptic Conclusion

> "A skeptical systems researcher would conclude that until we have a **standardized, composable backend** that allows an agent to 'plug in' to any arbitrary network or system environment and begin falsifying hypotheses, agentic research will remain **siloed in specific, high-resource domains** like LLM inference or hyper-scale data centers."

## Implication for the Thin-Waist

The agentic thin-waist is the **only system in the corpus that builds the evaluation substrate as a composable, agent-callable service**. Every other system either:
- (a) Assumes a proprietary simulator exists (Glia, AlphaEvolve)
- (b) Uses trivially-available compute (AI Scientist)
- (c) Wraps existing production infrastructure (Confucius)

The thin-waist fills the gap by providing:
- **Intent Plane** → research intent decomposition (what Glia's front-end does, but for networking)
- **Representation Plane** → composable cross-traffic profiles + contextual telemetry (no equivalent in any other system)
- **Execution Plane** → privileged infrastructure operations via tc/tshark/tcpreplay/browser automation (the missing "Vidur for networking")

## Convergent Evidence from Other Domains

The same pattern appears independently in:
- **Osprey** (DOE accelerator facilities): NL → auditable plan → EPICS execution
- **Confucius** (Meta production networks): NL → DAG → DSL tool execution
- **Bluesky** (BNL synchrotron beamlines): experiment intents → EPICS control

The intent → composable plan → safe infrastructure execution pattern is **fundamental, not domain-specific**.
