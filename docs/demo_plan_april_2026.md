# Agentic Thin Waist — Getting Started Examples

## What This Platform Does

The Agentic Thin Waist is a platform for generating network measurement data under controlled, reproducible conditions. A researcher describes what they want in plain English — which application to run, what network conditions to create — and the platform handles everything else: configuring the network, running the application, capturing traffic, and storing structured results.

The platform solves three problems that make network measurement research slow and unreliable today:

1. **Every study requires bespoke infrastructure.** Reproducing a published measurement paper typically takes weeks of manual setup — configuring emulated topologies, calibrating background traffic, deploying applications, wiring up packet capture. The platform eliminates this: you describe the experiment, and the infrastructure configures itself.

2. **Network conditions are uncontrolled or unreproducible.** Most measurement studies either run on the live Internet (where conditions change between runs) or use static datasets (which can't answer "what if?" questions). The platform creates controlled network conditions with two independently tunable dimensions:
   - **Static attributes** — the fixed properties of a bottleneck link: its capacity (e.g., 10 Mbps), base latency (e.g., 50ms), queue management policy, and buffer size.
   - **Dynamic congestion pressure** — realistic background traffic that shares the bottleneck link. This background traffic is derived from real network traces, stored as reusable profiles in a corpus, and replayed during the experiment to create realistic congestion. The researcher can let the platform choose an appropriate profile automatically, or specify the type of congestion they want (e.g., "heavy and bursty").

3. **Different measurement tools can't be fairly compared.** When two speed tests report different numbers, is it the tool or the network? You can't tell unless both tools ran through the exact same network conditions. The platform makes this trivial: specify the network conditions once, run any number of applications through them, and compare the results knowing the conditions were identical.

## What These Examples Demonstrate

The seven examples below are structured as a progressive tutorial. Each one adds a new capability on top of the previous. Together, they validate every core promise of the platform.

| # | Example | What It Proves |
|---|---------|---------------|
| 01 | Controlled network conditions | The platform creates a bottleneck link with precise capacity and latency, and the measured results match |
| 02 | Realistic congestion | Adding background traffic from real network traces reduces throughput — the platform models realistic network pressure, not just static pipe limits |
| 03 | Researcher controls the congestion | The researcher can specify what kind of background traffic they want, and the platform selects matching traffic profiles from its corpus |
| **04** | **Multiple applications, identical conditions** | **The headline capability: different applications (speed tests, video streaming, raw throughput tools) all run through the exact same network conditions, enabling fair comparison** |
| 05 | Protocol algorithm comparison | The researcher can vary low-level network parameters (like the congestion control algorithm) while holding everything else constant |
| 06 | Reproducibility | Repeated runs under identical conditions produce consistent results — proving the platform is a scientific instrument, not a random number generator |
| 07 | Infrastructure decoupling | The same experiment specification produces equivalent results whether it runs on a local laptop or on cloud infrastructure — the specification is portable |

---

## How to Run These Examples

**Prerequisites:**
- Docker and Docker Compose installed
- An Anthropic API key (for natural language intent parsing): set `ANTHROPIC_API_KEY` in your environment
- Platform services running: `docker compose up -d` from the repository root

Each example is a self-contained directory under `examples/`. Every directory has:
- `README.md` — step-by-step walkthrough with copy-pasteable commands
- `intent.json` — the input to the platform
- `run.sh` — runs the full example in one command
- `expected_output/` — reference results so you can verify your run matches
- `screenshots/` — what each step should look like on your screen
- `validate.py` — automated check that compares your results against the reference

**Quality standard:** If you can't reproduce an example by following the README alone — no external help needed — the example has a bug. Please file an issue.

---

## Example 01: Controlled Network Conditions

**Goal:** Verify that the platform creates a bottleneck link with the network conditions you specified, and that a measurement tool running through it reports results consistent with those conditions.

**What you'll do:** Ask the platform to run an iperf3 throughput test through a bottleneck link with 10 Mbps capacity and 50 milliseconds of base latency. No background traffic — just the raw link.

**Intent:**
```
"Run iperf3 at 10 Mbps with 50ms latency, no cross-traffic"
```

**What to expect:**
- Measured throughput ≈ 10 Mbps (nothing else competing for the link)
- Measured round-trip time ≈ 50ms
- A packet capture (PCAP) file stored in the telemetry service, available for download

**Why iperf3 with no background traffic:** This is the simplest possible test. iperf3 is a deterministic tool — it sends TCP traffic as fast as the link allows. With no background traffic competing, measured throughput should match configured capacity closely. If it doesn't, the link shaping is broken. This must work before we add complexity.

**What to check:**
- The platform parsed your English sentence into a structured experiment specification
- An ephemeral execution container was created, ran the experiment, and was destroyed
- The telemetry service has a structured result with the configured and measured values
- The packet capture file exists and contains iperf3 traffic

---

## Example 02: Realistic Congestion

**Goal:** Show that adding background traffic from real network traces creates realistic congestion that reduces available throughput — modeling what actually happens on shared Internet links.

**What you'll do:** Ask the platform to run an NDT speed test through the same 10 Mbps / 50ms bottleneck as Example 01. This time, the platform will automatically select a background traffic profile from its corpus — a replay of real network traffic captured from production networks — and inject it alongside the NDT test.

**Intent:**
```
"Run NDT speed test at 10 Mbps with 50ms latency"
```

**What to expect:**
- NDT-reported throughput < 10 Mbps (background traffic is consuming part of the link capacity)
- The packet capture contains two types of traffic: the NDT speed test and the replayed background traffic
- The platform shows which background traffic profile it selected and why (its intensity, burstiness, and direction)

**The comparison that matters:** Example 01 measured ≈ 10 Mbps. Example 02 measures less. The network link is identical. The difference is the background traffic. This is how the platform separates *link capacity* (a static property you configure) from *available throughput* (which depends on who else is using the link).

**Why NDT instead of iperf3:** NDT is a real speed test that researchers use to measure Internet performance. It has its own measurement algorithm that differs from iperf3. Running it through a controlled bottleneck gives us ground truth — we *know* the link is 10 Mbps, so we can evaluate how accurately NDT reports it under congestion.

---

## Example 03: Researcher Controls the Congestion

**Goal:** Show that the researcher can specify what type of background traffic they want, giving independent control over both the link properties (static) and the congestion characteristics (dynamic).

**What you'll do:** Run the same NDT speed test through the same 10 Mbps / 50ms link, but this time explicitly request heavy, bursty background traffic.

**Intent:**
```
"Run NDT speed test at 10 Mbps with 50ms latency with heavy bursty cross-traffic"
```

**What to expect:**
- The platform selects a different, more aggressive background traffic profile than Example 02
- Throughput is lower than Example 02 (heavier congestion)
- Comparing all three examples reveals the decomposition:

| Example | Link Capacity | Background Traffic | Measured Throughput |
|---------|--------------|-------------------|-------------------|
| 01 | 10 Mbps | None | ≈ 10 Mbps |
| 02 | 10 Mbps | Moderate (auto-selected) | 5–8 Mbps |
| 03 | 10 Mbps | Heavy bursty (researcher-specified) | 2–5 Mbps |

**The point:** The link didn't change. Only the background traffic changed. The researcher controls both dimensions independently — set the link properties, then independently dial the congestion from none to heavy. This is what makes the platform a scientific instrument: you can isolate the effect of congestion from the effect of link capacity.

---

## Example 04: Multiple Applications, Identical Conditions

**This is the flagship example.** This demonstrates the capability that no existing tool provides.

**Goal:** Run multiple applications — a speed test, a raw throughput tool, and a video streaming service — through the exact same network conditions, and compare how each one behaves.

**What you'll do:** Ask the platform to compare NDT, iperf3, and YouTube, all through a 10 Mbps / 50ms bottleneck with moderate background traffic. The platform dispatches each application (command-line tools and browser-based applications alike) through the same pipeline, with identical network conditions.

**Intent:**
```
"Compare NDT, iperf3, and YouTube at 10 Mbps with 50ms latency with moderate cross-traffic"
```

**What to expect:**
- Three experiments generated from one sentence
- All three share the exact same network conditions: same link capacity, same latency, same background traffic profile, same queue management
- Each application behaves differently:
  - **iperf3** saturates the available capacity (it's a greedy TCP sender)
  - **NDT** reports a throughput number using its own estimation algorithm (it may differ from iperf3)
  - **YouTube** adapts its video bitrate to the available bandwidth (you'll see step-wise quality changes)
- The packet captures for each run show the same background traffic pattern with different foreground application traffic

**Why this matters:** Today, if you want to compare how YouTube and NDT behave on the same network, you have to build two separate test setups and hope the conditions are equivalent. They never are — the network changes between runs, different paths have different bottlenecks. This platform makes the comparison trivial: one sentence, identical conditions, all results queryable side by side. The conditions are not just "similar" — they are identical. Same link shaping, same background traffic file, same capture interface. The only variable is the application.

---

## Example 05: Protocol Algorithm Comparison

**Goal:** Show that the researcher can vary low-level network parameters — specifically, the TCP congestion control algorithm — while holding everything else constant, and observe how different algorithms respond to the same congestion.

**What you'll do:** Run iperf3 twice through the same bottleneck, once with CUBIC (the Linux default) and once with BBR (Google's alternative). Same link, same background traffic, same application — only the congestion control algorithm changes.

**Intent:**
```
"Compare iperf3 with CUBIC vs BBR at 10 Mbps with 50ms latency with moderate cross-traffic"
```

**What to expect:**
- Two experiments generated, identical except for the congestion control algorithm
- The throughput time series look different: CUBIC backs off when it detects packet loss; BBR probes for bandwidth using a different strategy
- Both results are stored in the telemetry service, queryable by congestion control algorithm

**Why iperf3:** We want to isolate the congestion control effect. iperf3 generates pure TCP traffic with no application-layer adaptation. Any difference in throughput between the two runs is directly attributable to how CUBIC and BBR respond to the same network congestion.

**Further exploration (modify the intent to try):**
- Change the queue management policy (e.g., replace the default `fq_codel` with `pfifo`) to see how queue management interacts with congestion control
- Add a buffer size constraint (e.g., "with 50-packet buffers") to test shallow-buffer behavior
- Sweep across capacities (e.g., "at 5, 10, and 25 Mbps") to generate a congestion control × capacity comparison matrix

---

## Example 06: Reproducibility

**Goal:** Prove that repeated runs under identical conditions produce consistent results. This is what separates a scientific instrument from a one-off script.

**What you'll do:** Run the same experiment 5 times with two different applications (iperf3 and NDT), same network conditions each time.

**Intent:**
```
"Run iperf3 and NDT at 10 Mbps with 50ms latency with moderate cross-traffic, 5 trials each"
```

**What to expect:**
- 10 experiments total (5 × iperf3 + 5 × NDT)
- For iperf3: throughput time series across the 5 trials are tightly clustered
- For NDT: throughput time series are also clustered, but with slightly more spread

**Why both iperf3 and NDT:** This separates *platform variance* from *application variance*.
- iperf3 is deterministic — if 5 iperf3 runs diverge, the platform has a reproducibility problem (the application wouldn't cause it)
- NDT has its own measurement algorithm with inherent variability — if NDT runs diverge more than iperf3 runs, the additional spread is attributable to NDT's methodology, not the platform

**How we measure fidelity:** Extract the throughput time series from each packet capture (100ms bins over the experiment duration). Compute the Wasserstein distance (a statistical measure of how different two distributions are) between every pair of trials. Lower distance = higher fidelity = more reproducible.

**What to check:**
- Wasserstein distances within iperf3 trials are small (tight reproducibility)
- Wasserstein distances within NDT trials are small but larger than iperf3 (NDT adds its own variance)
- Visual overlay of all 5 time series for each application shows bounded spread

---

## Example 07: Execution and Infrastructure Decoupling

**Goal:** Prove that the experiment specification — not the infrastructure it runs on — determines the results. The same specification should produce equivalent data whether it runs on your laptop or on cloud infrastructure.

**What you'll do:** Run the same experiment from Example 06 (iperf3 + NDT, 5 trials each, same network conditions) on two different substrates: local Docker and AWS. Compare the fidelity of locally generated data against cloud-generated data.

**Intent:** Same as Example 06.

**Two runs:**
```bash
./run_local.sh    # Runs on local Docker (your laptop)
./run_aws.sh      # Runs on AWS (cloud infrastructure)
```

**What to expect:**
- The experiment specification is identical between the two runs — only the infrastructure backend changes
- For each application, compare three Wasserstein distances:
  - **Within-local:** variance across the 5 local trials (from Example 06)
  - **Within-AWS:** variance across the 5 AWS trials
  - **Across-substrate:** local trials vs. AWS trials

**What "success" looks like:**
- If across-substrate Wasserstein ≈ within-substrate Wasserstein, the specification layer is doing its job — the data is equivalent regardless of where it was generated. The infrastructure is interchangeable.
- If across-substrate Wasserstein >> within-substrate Wasserstein, the two substrates are introducing systematic differences (different kernel versions, different NIC drivers, different timing behavior) that the specification layer does not fully abstract away. This is a finding, not a failure — it tells us where the abstraction has limits.

**The punchline:** The experiment specification is the "thin waist" of the platform — the narrow interface between what you want to measure and where you measure it. If the Wasserstein distances are comparable across substrates, that interface is holding. The same specification, the same data, regardless of the machine underneath.

---

## Progression Summary

| # | Example | What's New | Platform Promise Validated |
|---|---------|-----------|--------------------------|
| 01 | Controlled conditions | Baseline | The platform creates precise, measurable network conditions |
| 02 | Realistic congestion | Background traffic added | The platform models realistic congestion from real traffic traces |
| 03 | Researcher controls congestion | Researcher specifies congestion type | Static and dynamic dimensions are independently controllable |
| **04** | **Multi-app comparison** | **Multiple applications** | **Identical conditions across diverse applications — fair comparison** |
| 05 | Protocol comparison | Congestion control algorithm varied | Low-level network parameters are configurable |
| 06 | Reproducibility | Repeated trials | Results are consistent; platform variance is separable from app variance |
| 07 | Infrastructure decoupling | Two substrates | The specification is portable; infrastructure is interchangeable |

---

## Feature Coverage

| Platform Promise | Where Validated | How You Can See It |
|-----------------|----------------|-------------------|
| Natural language → structured experiment | All examples | Every example starts with a plain English sentence |
| Controlled static network conditions | 01+ | Configured capacity/latency vs. measured values in results |
| Realistic dynamic congestion from real traces | 02+ | Background traffic profile shown in results; throughput drops |
| Independent control of static and dynamic dimensions | 01 vs 02 vs 03 | Same link, different congestion, different throughput |
| Diverse applications through identical conditions | 04 | NDT + iperf3 + YouTube, same network, same telemetry query |
| Configurable protocol parameters | 05 | CUBIC vs BBR, same conditions, different throughput curves |
| Run-to-run reproducibility | 06 | Wasserstein distance across repeated trials |
| Platform vs. application variance separation | 06 | iperf3 variance < NDT variance |
| Portable specification across infrastructure | 07 | Local vs AWS Wasserstein comparison |
| Automated infrastructure lifecycle | All READMEs | Execution container created, ran experiment, destroyed |
| Synchronized capture of all traffic | 02+ READMEs | Packet capture timestamps align across application and background traffic |
| Structured, queryable results | All READMEs | Telemetry API queries filtering by application, capacity, algorithm |
| Packet capture artifacts | All READMEs | Download PCAP from telemetry, inspect in Wireshark |

---

## Instructions for Contributors

**Quality bar:** If someone who has never seen the platform can't reproduce an example by following its README alone — no Slack messages, no verbal explanations — the example is not done.

**Each example directory must contain:**

- [ ] `README.md` — complete walkthrough: what you'll do, why, copy-pasteable commands, what to observe, what success looks like
- [ ] `intent.json` — the input
- [ ] `run.sh` — runs the full example in one command
- [ ] `expected_output/` — reference JSON with key fields annotated
- [ ] `screenshots/` — annotated screenshots at each step
- [ ] `validate.py` — compares your results against the reference, reports pass/fail

**The live demo IS these examples.** The presenter opens the README and runs the commands on screen. There is no separate demo script.
