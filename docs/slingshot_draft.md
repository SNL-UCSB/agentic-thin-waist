# Laude Slingshot Application — Draft

**Project:** Pramana
**Applicant:** Arpit Gupta, Associate Professor, UC Santa Barbara
**Date:** April 15, 2026

---

## Pramana: The Composable Empirical Backend for AI-Powered Science

AI-powered empirical research faces an infrastructure gap: agents generate hypotheses faster than existing evaluation substrates can test them. Pramana is the empirical backend that closes this loop — turning intent into experiment, experiment into data, and data into the feedback that drives the next hypothesis.

The architecture follows IP's hourglass. Above the waist, any AI agent or human researcher expresses experimental intent. Below, any Docker-capable host executes it. Six composable microservices span the middle — intent specification, condition representation, application execution, substrate configuration, telemetry collection, and LLM-driven orchestration. One experiment specification runs unchanged from a laptop to a national-scale research backbone.

We instantiate Pramana in networking, where a series of systems built over three years each progressively disaggregated a different coupling that blocked agent autonomy. The platform subsumes all of them. The design principles — progressive disaggregation, composable service contracts, intent-execution decoupling — are domain-general. Any field where AI agents need to ground hypotheses in empirical data faces the same bottleneck.

---

## The Problem: Evaluation Substrates Gate AI-Powered Research

The pattern is consistent across domains. Glia (MIT, 2025) designed LLM inference scheduling algorithms — but only because Vidur, a high-fidelity simulator, already existed. Karpathy's autoresearch ran hundreds of autonomous experiments overnight — but only because GPT-2 training fits on a single GPU with a five-minute eval cycle. Remove the evaluation substrate, and agents produce hypotheses into the void.

For most empirical domains, that substrate does not exist. In networking, reproducing a single published study requires weeks of manual infrastructure: configuring emulated topologies, calibrating cross-traffic, deploying applications, wiring telemetry. Every new research question demands a bespoke pipeline. Prior platforms that did provide fast evaluation — Puffer for ABR algorithms, Pantheon for congestion control — produced genuine acceleration within their domains. But each was a vertical: a multi-year effort serving one application, one community. Extending the capability to a different domain required starting from scratch.

The same gap exists in materials science (synthesis conditions must be manually configured for each experiment), climate modeling (observation-model comparisons require bespoke data pipelines), and facility operations (validating AI decisions on production infrastructure requires controlled testbeds that don't exist).

Pramana is the horizontal platform that replaces vertical one-offs. It standardizes the contract between intent and execution so that building a new evaluation substrate for a new domain is a configuration problem, not a systems-engineering project.

---

## The Key Enabler: Progressive Disaggregation

**Progressive disaggregation** is a repeatable design methodology: each system separates one coupling that blocks agent autonomy, and the resulting service becomes a composable building block.

Over the past three years, we identified and separated five distinct couplings:

| System | Coupling Broken | Service Created |
|--------|----------------|-----------------|
| **NetUnicorn** (CCS '23) | Experiment logic tied to specific infrastructure | Portable experiment definitions |
| **NetForge / NetReplica** | Static network attributes entangled with dynamic cross-traffic | Cross-Traffic Profile algebra |
| **NetGent** (NeurIPS MLforSys '25) | Application specification coupled to browser automation | NFA-compiled deterministic workflows |
| **BQT+** | Raw measurement data locked away from policymakers | Queryable telemetry with natural-language interface |
| **IEF** (NeurIPS '25) | Model quality assessed only via downstream tasks | Intrinsic evaluation of learned representations |

Each separation was a research contribution — published at venues including ACM CCS, NeurIPS, and NSDI, with others under review. Pramana is the integration: all five compose into a single platform where an agent can express intent, control conditions, execute applications, collect telemetry, and iterate — through narrow, well-defined service contracts.

The methodology transfers. Identify a coupling that blocks agent autonomy in your domain, build a service that breaks it, expose it through a composable contract.

---

## Impact

### Automating the most tedious part of empirical research

The platform compresses the ideation-to-result gap from weeks to minutes. Our first demonstration: automated replication of published measurement studies. An AI agent reads a paper, extracts the experimental setup, expresses it as a Pramana intent, executes the experiment, and compares results — end-to-end, without manual infrastructure setup. We are targeting 2–3 full paper replications for a HotNets 2026 submission with collaborators at UC Irvine.

### Making AI trustworthy for mission-critical science infrastructure

The Department of Energy operates ESnet — the high-speed backbone connecting every national laboratory and supercomputing center in the United States. AI models are being developed for this network to classify traffic from particle physics experiments, forecast bandwidth demand, and detect anomalies across facilities including CERN and Jefferson Lab. Before any of these models touches production infrastructure, it needs to be validated under controlled conditions that mirror real operational scenarios.

Through active collaborations with Lawrence Berkeley National Laboratory and Fermilab, we use Pramana's controlled data generation to build a data flywheel: intrinsic evaluation diagnoses where a model's learned representations are weak, Pramana generates targeted experimental data to stress-test those regions, the model is retrained, and the cycle repeats. Models validated under controlled conditions before they touch production traffic.

This work feeds into the DOE's broader American Science Cloud initiative — a multi-lab partnership building intelligent infrastructure for physics, genomics, power grids, and light-source facilities. Once controlled data generation works for network bottlenecks, the same methodology applies to any facility where AI agents need empirical grounding before acting autonomously.

### A template for AI-for-science across domains

Our national laboratory collaborations expose the same bottleneck across domains: scientists have hypotheses, AI agents can reason, but no evaluation substrate exists to close the loop.

- In **high-energy physics**, ML models classify particle collision events but lack controlled data generation for edge-case validation.
- In **nuclear physics**, autonomous beam tuning needs a safe empirical sandbox before it can replace manual calibration.
- In **scientific computing**, AI-driven resource scheduling needs counterfactual evaluation — "what would have happened if the workload mix shifted?" — that does not exist today.

Progressive disaggregation, composable service contracts, and intent-execution decoupling are not networking-specific. They are a repeatable recipe for building the evaluation substrate that any AI-for-science effort needs. Networking is where we prove the recipe works. The DOE science complex is where we scale it.

### Already deployed: Public service

BQT+ — built on Pramana's telemetry and query abstractions — has supported broadband quality analyses for the California Public Utilities Commission and Pew Charitable Trusts, and established pre-disbursement baselines across 124,000+ addresses for the federal BEAD broadband program.

---

## What Slingshot Enables

Pramana works in our lab. Three gaps separate a working research prototype from community infrastructure:

**Hosted access.** Today, using Pramana requires `git clone`, `docker compose up`, and familiarity with the service architecture. The target: a researcher at any institution describes an experiment and gets results back. This requires hosted compute, a web interface, and managed orchestration.

**Domain adaptation.** The Cross-Traffic Profile algebra, NetGent workflows, and substrate configuration are networking-specific instantiations of domain-general abstractions. Building the toolkit that lets a particle physicist or materials scientist plug in their domain's equivalent — conditions, execution workflows, telemetry schemas — is an engineering effort beyond lab-scale resources. It is a product design problem as much as a research problem.

**Community.** Pramana's value scales with users. The platform needs documentation, tutorials, example notebooks, and integration with existing scientific workflows — Jupyter, HuggingFace, DOE computing environments.

---

## Applicant

Arpit Gupta is an Associate Professor of Computer Science at UC Santa Barbara, where he leads the Systems, Networking, and Measurement Lab. He holds an NSF CAREER Award, a Google Research Scholar Award, and is a Benton Fellow and UC Presidential UCDC Fellow. His group builds infrastructure that other researchers and policymakers adopt: portable experiment pipelines (ACM CCS '23), intrinsic evaluation of learned representations (NeurIPS '25), large-scale measurement systems (NSDI '26), and broadband quality tools that have supported policy analyses for the California Public Utilities Commission and Pew Charitable Trusts.

He is PI on a DOE-funded project deploying AI on the national science network (with Lawrence Berkeley National Laboratory and Fermilab) and Co-PI on a Berkeley Lab project building the safety substrate for agentic AI at national user facilities. He is a Faculty Scientist at Berkeley Lab's ESnet division and collaborates with Google on production network telemetry. Publications span SIGCOMM, IMC, NSDI, NeurIPS, and CCS.
