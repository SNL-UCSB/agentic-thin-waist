# Examples for the Agentic Thin Waist

This document specifies a set of self-contained, reproducible examples that serve as both the demo and the onboarding path for new users. Each example is a standalone directory under `examples/` with its own README, scripts, expected outputs, and screenshots. Anyone should be able to `git clone`, follow the README, and reproduce the results.

The examples are structured as five progressive acts. Each builds on the previous and demonstrates a distinct capability of the platform.

---

## Repository Structure

```
examples/
├── 01-intent-to-data/           # Hello world: one intent, one result
├── 02-youtube-under-pressure/   # Real browser app under controlled bottleneck
├── 03-application-comparison/   # Same bottleneck, three different applications
├── 04-capacity-sweep/           # Same app, varying network conditions
├── 05-fidelity-validation/      # Reproducibility proof via repeated runs
└── 06-cross-substrate/          # (stretch) Same spec, different substrate
```

Each directory contains:
```
├── README.md              # Self-contained walkthrough (the demo script)
├── run.sh                 # One-command execution
├── intent.json            # The input intent
├── expected_output/       # Reference results for validation
├── screenshots/           # Annotated screenshots at each step
└── validate.py            # Compares actual vs. expected, reports pass/fail
```

---

## Example 01: Intent to Data

**Intent:** `"Run iperf3 to measure throughput at 10 Mbps with 50ms latency"`

**What it demonstrates:** The core pipeline works end-to-end. A researcher types a sentence; the platform parses it, provisions infrastructure, configures the network, selects cross-traffic, captures packets, and stores structured results. Zero manual setup.

**Workflow type:** Shell (iperf3)

**Why iperf3 here:** This is the "hello world" — iperf3 is deterministic, has no external dependencies (no browser, no video server), and produces ground-truth throughput numbers we can validate precisely. It proves the plumbing.

**What to validate:**
- Pipeline completes: `status == "complete"`
- Shaping applied: `configured_capacity == 10.0`, `configured_latency == 50.0`
- CTP selected: a cross-traffic profile from the corpus was applied
- Measured throughput < configured capacity (because cross-traffic is sharing the link)
- PCAP artifact exists in telemetry
- Reasoning trace shows Claude's parsing and workflow selection

---

## Example 02: NDT Speed Test Under Controlled Conditions

**Intent:** `"Run an NDT speed test at 10 Mbps with 50ms latency"`

**What it demonstrates:** The platform runs a real-world speed test tool — not just raw iperf3 — through a controlled bottleneck with known ground truth. NDT is a different measurement methodology from iperf3 (different server, different algorithm, different protocol stack), yet it runs through the exact same bottleneck spec. This is the first step beyond "hello world" — a tool that researchers actually use in the wild, now with ground truth.

**Workflow type:** Shell (NDT via ndt-client)

**Why NDT here (not YouTube yet):** NDT is a shell workflow like iperf3, so it doesn't add the Browserless dependency. But it uses a completely different measurement methodology — NDT has its own throughput estimation algorithm, its own server infrastructure (M-Lab), and its own protocol behavior. Running NDT and iperf3 through the same bottleneck immediately surfaces the question: do they agree on capacity? If not, why? This is exactly the diagnostic question that motivates KC and Ricky's RABBIT work, and it requires no browser to demonstrate.

**What to validate:**
- Pipeline completes with a different workflow than Example 01 (NDT, not iperf3)
- Same bottleneck config as Example 01 (10 Mbps, 50ms) — proving the spec language works across tools
- NDT-reported throughput may differ from iperf3-reported throughput under identical conditions — this difference IS the interesting finding
- PCAP captures NDT traffic (TCP to M-Lab servers) interleaved with CTP cross-traffic
- Telemetry stores both Example 01 and Example 02 results, queryable side by side

**What to observe:** Compare the iperf3 result from Example 01 and the NDT result from Example 02 — same bottleneck, different tool, potentially different answer. The platform provides the controlled conditions that make this comparison meaningful.

---

## Example 03: Same Bottleneck, Many Applications

**This is the flagship example.** This is what no existing tool does.

**Intent:** `"Compare iperf3, NDT, YouTube, and a web page load at 10 Mbps with 50ms latency"`

**What it demonstrates:** One bottleneck regime, four applications, all generating traffic through the exact same controlled network conditions. The platform dispatches shell workflows (iperf3, NDT) and browser workflows (YouTube, web page) through the same pipeline. The bottleneck is identical across all four — same capacity, same latency, same cross-traffic profile, same AQM. The only variable is the application.

**Workflow types:** Shell (iperf3, NDT) + Browser (YouTube, page load)

**Why this is the key capability:** Today, if you want to compare how YouTube, Zoom, NDT, and iperf3 behave under the same network conditions, you have to build four separate test setups and hope the conditions are equivalent. They never are. The thin waist makes this trivial: specify the bottleneck once, vary the application. The network conditions are not just "similar" — they are identical. Same tc shaping, same netem latency, same CTP replay file, same capture interface. The only thing that changes is what application generates the traffic.

This is the data that enables:
- Fair comparison of speed test tools under known ground truth (KC/Ricky's RABBIT use case)
- Understanding how different applications respond to the same congestion (ABR adaptation vs. rate control vs. greedy TCP)
- Generating multi-application datasets under controlled conditions (something that does not exist in any public dataset)

**What to validate:**
- Four experiments generated from one intent
- Two shell workflows (iperf3, NDT) + two browser workflows (YouTube, page load) dispatched
- Identical bottleneck config across all four (10 Mbps, 50ms, same CTP cluster, same AQM)
- Results in telemetry are queryable by application: `GET /results?capacity_min=9&capacity_max=11`
- Throughput differs across applications — iperf3 saturates the link, NDT uses a different measurement methodology, YouTube adapts bitrate, page load has bursty short flows — but all operate through the same bottleneck with the same ground truth
- PCAPs for each run contain the application traffic interleaved with the same CTP cross-traffic

**The punchline:** "Four applications, one bottleneck, identical conditions, reproducible data. Vary the application, not the network. This is the composability that the thin waist provides."

**Screenshot opportunity:** Side-by-side throughput time series from all four PCAPs, with the CTP cross-traffic visible in each. Same background noise pattern, different foreground application behavior. This one image tells the whole story.

---

## Example 04: Capacity Sweep

**Intent:** `"Measure YouTube streaming quality at 2, 5, 10, and 25 Mbps with 50ms latency"`

**What it demonstrates:** One intent generates a parameter sweep across capacities. YouTube's adaptive bitrate algorithm responds differently at each capacity level. The platform handles the combinatorics; the researcher thinks about the question.

**Workflow type:** Browser (YouTube)

**Why YouTube for the sweep (not iperf3):** iperf3 at different capacities is boring — it just reports the cap. YouTube is interesting because its ABR algorithm makes different decisions at different capacities: lower resolutions at 2 Mbps, 720p at 5 Mbps, 1080p at 10 Mbps, etc. This shows the platform generating data about real application adaptation to network conditions — the core scientific use case.

**What to validate:**
- Four experiments generated (2, 5, 10, 25 Mbps)
- Each gets a CTP matched to its capacity band
- YouTube throughput in PCAP scales with capacity (but not linearly — ABR is step-wise)
- Telemetry results show a progression: as capacity increases, measured throughput and video quality metrics improve
- The static/dynamic decomposition is visible: capacity varies (static), CTP intensity matches (dynamic), latency is constant

---

## Example 05: Fidelity Validation

**Intent:** `"Run YouTube at 10 Mbps with 50ms latency, 5 trials"`

**What it demonstrates:** Same experiment, same conditions, five times. Results are consistent. This is what makes the platform a scientific instrument.

**Workflow type:** Browser (YouTube)

**Why YouTube for fidelity (not iperf3):** Proving reproducibility with iperf3 is trivial — it's a deterministic tool. Proving reproducibility with YouTube is meaningful — it's a real application making adaptive decisions based on network feedback. If five YouTube runs under identical bottleneck conditions produce similar throughput time series, that demonstrates the platform provides controlled, reproducible conditions even for complex, non-deterministic applications.

**What to validate:**
- Five trials complete independently
- Throughput time series extracted from each PCAP (100ms bins)
- Wasserstein distance between all pairs of trials < established threshold
- Visual: overlay of 5 time series shows tight spread with bounded stochastic variation
- "Same intent, same spec, same bottleneck — consistent results even for adaptive applications"

---

## Example 06: Cross-Substrate Portability (stretch)

**Intent:** Same as Example 02 (YouTube at 10 Mbps)

**What it demonstrates:** The same experiment specification produces consistent results on local Docker and AWS. The spec is the thin waist; the substrate is interchangeable.

**Two runs:**
- `./run_local.sh` — `CONNECTIVITY_BACKEND=local_docker`
- `./run_aws.sh` — `CONNECTIVITY_BACKEND=aws` (requires AWS credentials + configured backend)

**What to validate:**
- Both runs complete
- Measured throughput and latency are consistent within fidelity bounds from Example 05
- The experiment spec JSON is identical between the two runs — only the backend config changes

---

## The Progression (Why This Order)

| Example | What It Proves | Application | Key Capability |
|---------|---------------|-------------|----------------|
| 01 | Plumbing works | iperf3 (shell) | Intent → data pipeline |
| 02 | Different tool, same bottleneck | NDT (shell) | Same spec, different measurement methodology — do they agree? |
| **03** | **The headline** | **iperf3 + NDT + YouTube + page load** | **Same bottleneck, many apps — the composability that matters** |
| 04 | Sweeps work | YouTube × 4 capacities | Parameter variation, ABR adaptation visible |
| 05 | Reproducibility works | YouTube × 5 trials | Fidelity proof for non-deterministic apps |
| 06 | Portability works | YouTube on local + AWS | Thin waist = portable spec |

Examples 01 and 02 are setup. **Example 03 is the money shot** — it demonstrates the capability that no existing tool provides: diverse applications generating traffic through the exact same replicable bottleneck link. If you only have time to show one example to a stakeholder, show 03. Everything else is either building blocks (01, 02) or extensions (04, 05, 06).

---

## Instructions for the Team

**Quality bar:** If a reviewer can't reproduce the example by following the README alone — no Slack questions, no "ask Jaber" — the example is not done.

**For each example, produce:**

- [ ] `README.md` — complete walkthrough with copy-pasteable commands, explanation of what to observe, and why it matters
- [ ] `intent.json` — the input
- [ ] `run.sh` — single-command execution (submit intent + poll + retrieve results)
- [ ] `expected_output/` — reference JSON files with key fields annotated
- [ ] `screenshots/` — annotated screenshots at each step (terminal output, JSON responses, PCAP timeseries where relevant)
- [ ] `validate.py` — compares actual vs. expected, reports pass/fail with field-level checks

**Critical for Examples 02-05:** The browser workflow (YouTube) must be tested end-to-end before documenting. If Browserless or the YouTube workflow doesn't work reliably, the example degrades to "here's what it should look like" — which is not acceptable. Examples must be reproducible, not aspirational.

**The live demo IS these examples.** The presenter opens the README and runs the commands on screen. There is no separate demo script. The README is the script.

---

## Relationship to Vision Narrative

The examples demonstrate the *current* capabilities. The broader vision (constraint mapping, edge infrastructure, closed-loop agentic experimentation) is documented in:
- `docs/thin_waist_one_pager.md` — platform summary for external audiences
- `docs/lit-survey/paper_outline.md` — HotNets paper argument

These examples are evidence items E2 (paper replication) and E3 (portability) from the HotNets evidence plan. They should be referenced in the paper as "see examples/ in the repository for reproducible demonstrations."
