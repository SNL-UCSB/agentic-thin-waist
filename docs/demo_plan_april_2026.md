# Examples for the Agentic Thin Waist

Self-contained, reproducible examples that serve as the demo, onboarding path, and feature validation suite. Each is a standalone directory under `examples/` with its own README, scripts, expected outputs, and screenshots. Anyone can `git clone`, follow the README, and reproduce.

---

## Repository Structure

```
examples/
├── 01-static-only/
├── 02-add-dynamic-pressure/
├── 03-control-dynamics/
├── 04-multi-app-same-bottleneck/
├── 05-cc-comparison/
├── 06-fidelity/
└── 07-local-vs-aws/
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

## Example 01: Static Only

**Intent:** `"Run iperf3 at 10 Mbps with 50ms latency, no cross-traffic"`

**What it demonstrates:** The core pipeline end-to-end. Intent parsing, experiment spec generation, ephemeral worker provisioning, bottleneck shaping (tc/netem), workflow execution, PCAP capture, telemetry persistence. No CTP — isolates the static bottleneck.

**App:** iperf3 (shell) · **CTP:** none · **CC:** cubic (default)

**What to validate:**
- Pipeline completes: `status == "complete"`
- Shaping applied: configured_capacity=10, configured_latency=50
- Measured throughput ≈ 10 Mbps (no cross-traffic competing)
- Measured RTT ≈ 50ms
- PCAP artifact stored in telemetry
- Ephemeral worker created and destroyed (show container lifecycle in README)

**Why iperf3, why no CTP:** This is the baseline. iperf3 is deterministic, and no CTP means measured throughput should match configured capacity closely. If it doesn't, the shaping is broken. This must work before anything else.

---

## Example 02: Add Dynamic Pressure

**Intent:** `"Run NDT speed test at 10 Mbps with 50ms latency"`

**What it demonstrates:** Same static config as Example 01, but now the orchestrator auto-selects a CTP from the corpus (matching ~10 Mbps intensity band). Cross-traffic shares the bottleneck. Throughput drops.

**App:** NDT (shell) · **CTP:** implicit (auto-selected) · **CC:** cubic

**What to validate:**
- Same static config as Example 01 (10 Mbps, 50ms)
- CTP was selected: show the CTP ID, its intensity, burstiness, direction from the orchestration results
- NDT-reported throughput < 10 Mbps (cross-traffic is consuming part of the capacity)
- PCAP contains both NDT traffic AND CTP replay traffic (two distinct flow patterns visible)

**The comparison that matters:** Example 01 throughput ≈ 10 Mbps. Example 02 throughput < 10 Mbps. Same static bottleneck. The difference IS the dynamic pressure from the CTP. This makes the CTP visible — it's no longer "something the platform does behind the scenes."

**README must include:** Explicit step to inspect CTP selection: `curl /orchestration/{id}/results | jq '.iterations[0].ctp_resolution'` — show cluster ID, intensity_mbps, burstiness metrics, download/upload PCAP paths.

---

## Example 03: Researcher Controls the Dynamics

**Intent:** `"Run NDT speed test at 10 Mbps with 50ms latency with heavy bursty cross-traffic"`

**What it demonstrates:** The researcher explicitly specifies the type of cross-traffic. The orchestrator selects a CTP matching the description (high intensity, high burstiness). Compare with Example 02 where the orchestrator chose automatically — different CTP, different throughput, same static config.

**App:** NDT (shell) · **CTP:** explicit ("heavy bursty") · **CC:** cubic

**What to validate:**
- Same static config as Examples 01 and 02
- CTP selected has higher intensity and burstiness than Example 02's auto-selected CTP
- Throughput lower than Example 02 (heavier cross-traffic)
- The three-example progression is now visible in telemetry:

| Example | CTP | Throughput |
|---------|-----|-----------|
| 01 (static only) | none | ≈ 10 Mbps |
| 02 (auto CTP) | moderate | 5–8 Mbps |
| 03 (heavy bursty CTP) | heavy | 2–5 Mbps |

**The point:** Static attributes held constant. Dynamic pressure varied from none → moderate → heavy. Throughput responds accordingly. This IS the static/dynamic decomposition — the researcher controls both dimensions independently.

**README must include:** Telemetry query showing all three examples side by side: `curl '/results?capacity_min=9&capacity_max=11&sort_by=created_at'`

---

## Example 04: Same Bottleneck, Many Applications

**This is the flagship example.**

**Intent:** `"Compare NDT, iperf3, and YouTube at 10 Mbps with 50ms latency with moderate cross-traffic"`

**What it demonstrates:** One bottleneck regime, three applications, identical network conditions. The platform dispatches shell workflows (NDT, iperf3) and a browser workflow (YouTube) through the same pipeline. Same capacity, same latency, same CTP, same AQM. Only the application varies.

**App:** NDT + iperf3 (shell) + YouTube (browser) · **CTP:** explicit · **CC:** cubic

**What to validate:**
- Three experiments generated from one intent
- Two shell workflows (NDT, iperf3) + one browser workflow (YouTube)
- Identical bottleneck config across all three (verify in telemetry contextual tree: c_bottleneck is identical)
- Identical CTP across all three (verify: same CTP ID in all results)
- Throughput differs across applications:
  - iperf3 saturates available capacity (greedy TCP)
  - NDT reports differently (its own measurement algorithm)
  - YouTube adapts bitrate (ABR algorithm makes step-wise decisions)
- PCAPs for each run show the same CTP background pattern with different foreground application traffic

**Screenshot opportunity:** Side-by-side throughput time series from all three PCAPs. Same background cross-traffic pattern, different foreground application behavior. This one image tells the whole story.

**README must include:**
- Telemetry query filtered by capacity range showing all three results
- Contextual tree comparison: `c_app` differs, `c_bottleneck` and `c_ctp` are identical
- "This is the data that enables fair comparison of measurement tools under known ground truth"

---

## Example 05: CC Algorithm Comparison

**Intent:** `"Compare iperf3 with CUBIC vs BBR at 10 Mbps with 50ms latency with moderate cross-traffic"`

**What it demonstrates:** Same bottleneck, same application, different congestion control algorithms. The platform configures the CC algorithm per experiment via sysctl. The throughput patterns differ because CUBIC and BBR respond differently to the same congestion.

**App:** iperf3 (shell) · **CTP:** explicit · **CC:** cubic vs bbr

**Why iperf3:** We want to isolate the CC effect. iperf3 is a pure TCP throughput test — no application-layer adaptation. Differences in throughput time series are directly attributable to the CC algorithm's response to congestion.

**What to validate:**
- Two experiments generated, identical except for CC algorithm
- Same bottleneck, same CTP, same iperf3 workflow
- Throughput time series differ: BBR's probing behavior vs CUBIC's loss-based approach
- Both are stored in telemetry, queryable by `congestion_control` field

**README hints for further exploration:**
- "Change `fq_codel` to `pfifo` in the intent to test how AQM interacts with CC"
- "Add `buffer_packets: 50` to test shallow buffer behavior"
- "Change `10 Mbps` to `5, 10, 25 Mbps` to generate a CC × capacity sweep"

---

## Example 06: Fidelity

**Intent:** `"Run iperf3 and NDT at 10 Mbps with 50ms latency with moderate cross-traffic, 5 trials each"`

**What it demonstrates:** Same experiment, same conditions, repeated 5 times, with two different applications. Results are consistent. This is what makes the platform a scientific instrument.

**App:** iperf3 + NDT (shell) · **CTP:** explicit · **CC:** cubic

**Why both iperf3 and NDT:**
- iperf3 (deterministic): if 5 iperf3 runs diverge, the *platform* has a reproducibility problem — the app wouldn't cause it
- NDT (real tool): if 5 NDT runs diverge more than iperf3 runs, the additional variance is attributable to NDT's measurement methodology, not the platform

Separating platform variance from application variance is the point.

**What to validate:**
- 10 experiments total (5 iperf3 + 5 NDT)
- For iperf3: extract throughput time series from each PCAP (100ms bins), compute pairwise Wasserstein distance — should be tight
- For NDT: same extraction, Wasserstein distance — may be wider than iperf3 (NDT adds its own variance)
- Visual: overlay of 5 iperf3 time series (tight), overlay of 5 NDT time series (slightly wider)
- Wasserstein within iperf3 < Wasserstein within NDT — confirms the additional variance comes from the application, not the platform

**README must include:** Table of pairwise Wasserstein distances for both apps.

---

## Example 07: Execution/Infrastructure Decoupling

**Intent:** Same as Example 06 (iperf3 + NDT, 10 Mbps, 50ms, moderate CTP, 5 trials each)

**What it demonstrates:** The same experiment specification produces equivalent data on local Docker and AWS. The thin waist holds across substrates.

**App:** iperf3 + NDT (shell) · **CTP:** explicit · **CC:** cubic

**Two runs:**
```bash
./run_local.sh    # CONNECTIVITY_BACKEND=local_docker, 5 trials × 2 apps
./run_aws.sh      # CONNECTIVITY_BACKEND=aws, 5 trials × 2 apps
```

**What to validate:**
- Experiment spec JSON is identical between local and AWS — only backend config changes
- For each app, compute:
  - **Within-local Wasserstein** (from Example 06): platform variance on local Docker
  - **Within-AWS Wasserstein**: platform variance on AWS
  - **Across-substrate Wasserstein**: local trials vs. AWS trials
- If across-substrate ≈ within-substrate, the thin waist holds — the spec is truly portable
- If across-substrate >> within-substrate, the substrates are introducing systematic differences that need investigation

**The punchline:** "Same specification, different substrate. If the Wasserstein distances are comparable, the specification layer is doing its job — the data is equivalent regardless of where it was generated."

**README must include:**
- Side-by-side Wasserstein summary table (within-local, within-AWS, across)
- Note on what systematic differences might mean (different kernel versions, different NIC drivers, different CTP replay timing behavior)

---

## Progression Summary

| # | Example | App | What's New | Key Feature Tested |
|---|---------|-----|-----------|-------------------|
| 01 | Static only | iperf3 | — | Plumbing, shaping, telemetry |
| 02 | Add dynamic pressure | NDT | CTP auto-selected | CTP visibility, dynamic pressure effect |
| 03 | Control dynamics | NDT | CTP researcher-specified | Static/dynamic decomposition |
| **04** | **Multi-app** | **NDT + iperf3 + YouTube** | **Multiple apps, shell + browser** | **Composability headline** |
| 05 | CC comparison | iperf3 | CUBIC vs BBR | CC/AQM configurability |
| 06 | Fidelity | iperf3 + NDT | 5 trials × 2 apps | Reproducibility, platform vs. app variance |
| 07 | Execution/infra decoupling | iperf3 + NDT | Same spec, two substrates | Portability, cross-substrate fidelity |

Examples 01-03 teach the bottleneck model (static → dynamic → decomposition). Example 04 is the headline. Example 05 adds configurability. Examples 06-07 prove the data is trustworthy — first on one substrate, then across substrates.

---

## Feature Coverage Audit

| Promised Feature | Where Tested | How It's Visible |
|-----------------|-------------|-----------------|
| NL intent → structured spec | All | Every example starts with a curl |
| Static bottleneck (capacity, latency) | 01+ | Configured vs. measured in results |
| No-CTP baseline | 01 | Throughput ≈ capacity |
| CTP auto-selection | 02 | CTP ID, intensity shown in results; throughput drops |
| CTP researcher-specified | 03-07 | Intent includes cross-traffic description; different CTP selected |
| Static/dynamic decomposition | 01 vs 02 vs 03 | Three-row telemetry comparison table |
| Multi-app composability (shell + browser) | 04 | NDT + iperf3 + YouTube, same bottleneck |
| CC configurability | 05 | CUBIC vs BBR throughput comparison |
| Reproducibility | 06 | Wasserstein across 5 trials |
| Platform vs. app variance | 06 | iperf3 Wasserstein < NDT Wasserstein |
| Execution/infrastructure decoupling | 07 | Same spec, local vs AWS, Wasserstein comparison |
| Ephemeral worker lifecycle | 01+ README | "Observe container created/destroyed" step |
| Synchronized execution | 02+ README | "Verify PCAP timestamp alignment" step |
| Telemetry structured query | 03+ README | Filter by app, capacity, CC; show contextual tree |
| PCAP artifact retrieval | All README | "Download PCAP from telemetry" step |
| CTP corpus inspection | 02-03 README | "Inspect CTP: intensity, burstiness, direction" step |
| Contextual tree (c_app, c_bottleneck, c_ctp) | 04 README | Side-by-side contextual trees across apps |
| AQM configurability | 05 README hint | "Change fq_codel to pfifo" |
| Buffer size | 05 README hint | "Add buffer_packets: 50" |
| Capacity sweep | 04 README hint | "Change 10 Mbps to 5, 10, 25 Mbps" |

---

## Instructions for the Team

**Quality bar:** If someone who has never seen the platform can't reproduce the example by following the README alone — no Slack questions, no "ask Jaber" — the example is not done.

**For each example, produce:**

- [ ] `README.md` — complete walkthrough with copy-pasteable commands, what to observe, why it matters
- [ ] `intent.json` — the input
- [ ] `run.sh` — single-command execution (submit + poll + retrieve)
- [ ] `expected_output/` — reference JSON files with key fields annotated
- [ ] `screenshots/` — annotated screenshots at each step
- [ ] `validate.py` — compares actual vs. expected, reports pass/fail with field-level checks

**The live demo IS these examples.** The presenter opens the README and runs the commands. There is no separate demo script.
