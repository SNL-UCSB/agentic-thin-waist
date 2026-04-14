# The Agentic Thin Waist — Platform One-Pager

**UCSB SNL · 2026-04-10**

## Motivation

Network and systems researchers want to ask "what happens to application X under network condition Y?" and get reproducible empirical answers in minutes, not weeks. The pain points blocking this today are operational, not conceptual:

- **Bespoke setup per study.** Reproducing a single IMC paper typically requires weeks of manual infrastructure work — configuring topologies, calibrating cross-traffic, deploying applications, wiring telemetry. Each new question demands a fresh pipeline.
- **No portability across substrates.** A study built on a campus testbed cannot be re-run on AWS, on a Raspberry Pi at a contributor's home, or on a federated facility like FABRIC without a full rewrite.
- **Static datasets are not enough.** Public traces are frozen in time, lack ground truth about the network conditions that produced them, and cannot answer counterfactual questions ("what if the link had been 5 Mbps instead of 10?").
- **Agentic research has nowhere to land.** AI agents can now generate hypotheses, design experiments, and write analysis code — but every existing system assumes the evaluation substrate already exists. For networking, it does not.

## Architecture

The thin waist is a **specification layer**, not an infrastructure layer. Above it sit diverse research intents ("compare YouTube and Zoom across capacity sweeps"). Below it sit heterogeneous substrates (Docker on a laptop, AWS, FABRIC, residential edge nodes). The waist is the minimal experiment specification language plus the orchestrator that maps an intent onto whichever substrate can satisfy it.

**Key abstractions:**

1. **Single-bottleneck scoping.** Each experiment targets one bottleneck link. The bottleneck dictates application performance; modeling it precisely is sufficient for the vast majority of application-layer questions and keeps the spec language tractable.
2. **Static + dynamic decomposition.** Static attributes (capacity, base latency, buffer, AQM, congestion control) describe the link. Dynamic pressure (cross-traffic intensity and burstiness) describes the workload sharing it. The two are specified independently and composed at execution time.
3. **Cross-Traffic Profiles (CTPs).** Real packet traces transformed into reusable, composable pressure signals indexed by intensity, burstiness, and direction. An agent can say "apply CTP cluster 7 to a 10 Mbps link" instead of writing tcpreplay scripts.
4. **Connectivity abstraction.** The same experiment specification dispatches to local Docker, AWS, or any substrate that provides the connectivity backend — only the configuration changes, not the spec.

**Six microservices, one source of intelligence:**

- **Orchestrator** — parses NL intent, selects parameters, dispatches services. The only LLM in the system.
- **CTP Service** — corpus of cross-traffic profiles with select/transform/export operations.
- **Substrate Worker** — applies tc/netem shaping, runs tcpreplay, captures traffic via tshark.
- **NetGent Service** — deterministic application workflows (iperf3, ping, browser-based YouTube/Zoom via Playwright).
- **Telemetry Service** — structured result storage with rich query API and artifact management.
- **Experiment API** — experiment lifecycle and registration.

The orchestrator sends messages, never data. Substrate workers communicate directly with CTP and Telemetry. Every service is a deterministic executor — only the orchestrator reasons.

## Demo Plan

**What the MVP delivers (and what we will show on April 10):**

1. **Intent → result, end-to-end.** A user submits a natural-language intent. The orchestrator parses it, queries the global CTP corpus for matching cross-traffic profiles, configures the bottleneck via the substrate worker, captures traffic, runs the application, persists results to telemetry, and returns structured output.
2. **Static + dynamic configuration verified.** The demo shows that the requested capacity, base latency, and cross-traffic profile are reflected in the captured pcap. Wasserstein distance over throughput time series confirms run-to-run fidelity (already validated).
3. **Two application paths.** iperf3 (the deterministic ground-truth path) and one Playwright-based dynamic workflow (the real-application path) both run through the same orchestration pipeline.
4. **Two deployment paths.** The same experiment specification runs (a) entirely locally — orchestrator, telemetry, substrate worker on one machine — and (b) with the substrate worker on AWS and the rest local. This is the concrete proof that the spec is portable.
5. **Parallel execution.** Ten concurrent experiment runs validate that the orchestrator–substrate communication is stable under load.

**What is intentionally out of scope for the demo:** live CTP extraction and transformation (we use a pre-transformed corpus), automated analysis services (no plot generation), and porting to constrained edge infrastructure (the next milestone after the demo).

The demo is the smallest credible proof that the specification layer works: one intent, two substrates, two applications, structured results out the other end.
