---
title: "A Case for Learned Cloud Emulators"
authors: Archit Bhatnagar, Yiming Qiu, Sarah McClure, Sylvia Ratnasamy, Ang Chen
venue: HotNets '25 (ACM)
year: 2025
category: systems-building
pass: 1
relevance: very-high
---

# [Pass 1]

**CATEGORY:** Systems-building (LLM-driven synthesis of evaluation substrates from documentation)

**PROBLEM:** Cloud emulators (LocalStack, Moto) mock cloud APIs so DevOps engineers can test infrastructure-as-code programs locally without provisioning real cloud resources. But building these emulators is Sisyphean: Moto (the most advanced, 800+ contributors, 10k+ commits over 10 years) covers only ~32% of APIs for a subset of AWS services. Network Firewall coverage is 11%. Critical resources like EKS have only 26% coverage. Manual emulator development cannot keep pace with cloud API proliferation (AWS alone has 240+ services, each with up to 200 APIs). Beyond coverage, manually-built emulators contain correctness bugs — e.g., Moto's DeleteVpc() succeeds even with an Internet Gateway attached, while real AWS returns DependencyViolation.

**CONTRIBUTION:** A neuro-symbolic approach to automatically generate high-fidelity emulation code from cloud documentation. The key insight: cloud resources can be modeled as a **hierarchy of state machines (SMs)**, where states are resource attributes and transitions are API calls. LLMs extract SM specs from documentation; a formal grammar constrains generation; symbolic execution aligns emulator behavior against real cloud.

**ARCHITECTURE — Four-Phase Pipeline:**

1. **Documentation Wrangling** — LLM + automated scraping to identify and curate authoritative cloud documentation. Symbolic parser extracts per-resource information (attributes, API signatures, error types). AWS: centralized PDFs (EC2 alone is 4000+ pages). Azure/GCP: scattered across web pages, requiring provider-specific adapters.

2. **SM Spec Generation (LLM)** — LLM generates state machine specifications per resource using a formal grammar:
   - `read(s,v)` — read state variable
   - `write(s,v)` — write state variable
   - `assert(pred)` — encode constraints (e.g., PublicIP and NIC must be in same zone)
   - `call(transition)` — trigger transition on another SM (cross-resource dependency)
   - Incremental extraction: resource-level dependency graph → generate individual SMs → splice via "specification linking" pass
   - Consistency checks: completeness (all resources captured) and soundness (no invalid transitions) via transitive closure

3. **Code Generation (Interpreter)** — SM specs translated to executable code (Python/C++). The interpreter is a one-time build; SM specs are the "executable specification" that drives it. Constrained decoding can enforce grammar compliance during generation.

4. **Automated Alignment** — Symbolic execution over SMs to find behavioral divergence between emulator and real cloud. Symbolic passes divide search space into equivalence classes. Discrepancies fed back to LLM for diagnosis: is the error in the SM spec or in the cloud documentation? Closes the loop for continuous improvement.

**KEY DESIGN CHOICES:**
- **State machines as the universal abstraction**: Every cloud resource (VM, VPC, NIC, PublicIP) is an SM with typed state variables and constrained transitions. This is a thin waist for cloud emulation — it sits between documentation above and executable code below.
- **Hierarchy for composition**: SMs are organized hierarchically (VM + Subnet contained by VPC). `call()` primitives enable cross-SM transitions. Containment scopes the impact of operations.
- **Grammar-constrained generation over free-form LLM output**: The formal grammar prevents hallucinated transitions and state corruption. Direct-to-code (D2C) baseline achieves similar API coverage but fails on 9/12 alignment traces due to state errors and transition errors.
- **Documentation as ground truth (with alignment as fallback)**: Unlike approaches that infer behavior from runtime traces, this approach reads documentation — which cloud providers have strong incentives to keep comprehensive and current.

**PRELIMINARY RESULTS:**
- Prototype covers all 45 Network Firewall APIs (vs. Moto's 5/45 = 11%) and all EC2 + DynamoDB APIs tested
- Generated specs: 28 SMs for EC2, 8 for Network Firewall, 7 for DynamoDB
- SM-based emulator: 100% accuracy on provisioning, 75% on edge cases, 100% on state updates
- D2C baseline: 50%, 25%, 0% respectively — fails catastrophically on state updates
- Multi-cloud: same workflow applied to Azure with comparable accuracy
- Code synthesis takes minutes, not months of manual engineering

**CRITICAL OBSERVATION FOR THIN-WAIST RELEVANCE:**

This paper is structurally isomorphic to the agentic thin waist in three ways:

1. **The SM formalism IS a thin waist for cloud emulation.** It provides a unified interface between diverse cloud documentation (above) and diverse executable emulators (below). The grammar constrains the interface to be "sufficient for necessary applications but as weak as possible" — Beck's thin-waist criterion.

2. **The verification wall in cloud DevOps.** The paper documents the same structural problem: teams need evaluation substrates (emulators) to test code, building them manually is unsustainable, and the gap between what's emulated and what's real (32% API coverage, correctness bugs) blocks progress. This is the cloud analog of the networking verification wall.

3. **"Cloud gym" = evaluation playground.** Section 4.4 explicitly proposes "building gym environments for cloud agents" — using learned emulators as training/evaluation substrates for AI agents managing cloud infrastructure. This is EXACTLY the evaluation playground concept from Glia, and validates the composable empirical backend thesis from a completely independent direction.

4. **LLM-as-spec-extractor pattern.** The thin waist uses LLMs to extract experiment specifications from research intents (natural language → structured experiment spec). This paper uses LLMs to extract emulator specifications from cloud documentation (natural language → formal SM spec). Same pattern, different domain — further evidence for cross-domain convergence.

**LIMITATIONS:**
- Preliminary prototype — limited to 3 AWS services + Azure proof-of-concept
- No completeness guarantees for alignment phase
- Documentation quality varies across providers (AWS well-structured, Azure/GCP scattered)
- No performance evaluation of generated emulators (latency, throughput)
- State machines assume sequential API calls — no concurrency model
- Constrained decoding not yet implemented (uses re-prompting instead)

**PAPERS WORTH CHASING FROM REFERENCES:**
- [49] Yang et al. "Cloud infrastructure management in the age of AI agents" arXiv:2506.12270, 2025 — AI agents for cloud management
- [41] Mazhar et al. "Fidelity of cloud emulators" ICSE 2025 — sim-to-real gap in cloud testing
- [50] SkyPilot (Yang et al., NSDI 2023) — intercloud broker, substrate heterogeneity
