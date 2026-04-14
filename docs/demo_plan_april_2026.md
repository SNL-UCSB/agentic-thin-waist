# Examples for the Agentic Thin Waist

This document specifies a set of self-contained, reproducible examples that serve as both the demo and the onboarding path for new users. Each example is a standalone directory under `examples/` with its own README, scripts, expected outputs, and screenshots. Anyone should be able to `git clone`, follow the README, and reproduce the results.

The examples are structured as three progressive acts. Each act builds on the previous one and demonstrates a distinct capability of the platform.

---

## Repository Structure

```
examples/
├── 01-intent-to-data/
│   ├── README.md              # Self-contained walkthrough
│   ├── run.sh                 # One-command execution script
│   ├── intent.json            # The input intent
│   ├── expected_output/       # Reference results for validation
│   │   ├── orchestration_status.json
│   │   ├── experiment_result.json
│   │   └── reasoning_trace.json
│   └── screenshots/           # Annotated screenshots of each step
│       ├── 01_submit_intent.png
│       ├── 02_orchestration_progress.png
│       ├── 03_telemetry_result.png
│       └── 04_reasoning_trace.png
│
├── 02-capacity-sweep/
│   ├── README.md
│   ├── run.sh
│   ├── intent.json
│   ├── expected_output/
│   │   ├── sweep_results.json
│   │   └── configured_vs_measured.csv
│   └── screenshots/
│       ├── 01_submit_sweep.png
│       ├── 02_three_experiments_progress.png
│       ├── 03_telemetry_comparison.png
│       └── 04_configured_vs_measured_plot.png
│
├── 03-fidelity-validation/
│   ├── README.md
│   ├── run.sh
│   ├── intent.json
│   ├── expected_output/
│   │   ├── trial_results.json
│   │   └── wasserstein_distances.csv
│   └── screenshots/
│       ├── 01_repeated_runs.png
│       ├── 02_throughput_timeseries_overlay.png
│       └── 03_wasserstein_summary.png
│
└── 04-cross-substrate/         # (stretch — requires AWS)
    ├── README.md
    ├── run_local.sh
    ├── run_aws.sh
    ├── intent.json
    ├── expected_output/
    │   ├── local_result.json
    │   └── aws_result.json
    └── screenshots/
        ├── 01_local_run.png
        ├── 02_aws_run.png
        └── 03_comparison.png
```

---

## Example 01: Intent to Data

**What it demonstrates:** A researcher submits one sentence. The platform parses it, provisions infrastructure, configures the network, runs the experiment, captures traffic, and stores structured results — automatically.

**Why it matters:** This is the core value proposition. Zero-to-data with no manual infrastructure setup.

### README Contents (outline)

#### Prerequisites
- Docker and Docker Compose installed
- `ANTHROPIC_API_KEY` set (for intent parsing)
- Platform services running: `docker compose up -d` from repo root
- Global CTP service reachable (or set `CTP_SERVICE_GLOBAL` to a local instance)

#### Step 1: Review the Intent

```json
// examples/01-intent-to-data/intent.json
{
  "intent": "Run iperf3 to measure throughput at 10 Mbps with 50ms latency"
}
```

This intent specifies:
- **Application:** iperf3 (ground-truth throughput measurement)
- **Static bottleneck:** 10 Mbps capacity, 50ms base latency
- **Dynamic pressure:** CTP automatically selected from the corpus (matching ~10 Mbps intensity)
- **Defaults applied:** cubic congestion control, fq_codel AQM, 60s duration

#### Step 2: Submit the Intent

```bash
curl -X POST http://localhost:8005/intent \
  -H "Content-Type: application/json" \
  -d @intent.json
```

**Expected response:**
```json
{"orchestration_id": "orch-a1b2c3d4", "status": "pending"}
```

*Screenshot: `01_submit_intent.png` — terminal showing the curl command and response*

#### Step 3: Watch the Pipeline Execute

```bash
# Poll orchestration status
watch -n 2 'curl -s http://localhost:8005/orchestration/orch-a1b2c3d4 | python -m json.tool'
```

The status progresses through these stages:
1. `parsing` — Claude extracts structured parameters from the NL intent
2. `generating` — Cartesian product produces experiment specs
3. `selecting_workflow` — NetGent workflow fetched from GitHub registry
4. `provisioning_worker` — ephemeral Docker container created
5. `selecting_ctp` — global CTP service queried for matching cross-traffic
6. `executing` — synchronized capture + replay + workflow fire at next minute boundary
7. `streaming_pcap` — PCAP uploaded to telemetry service
8. `complete` — worker destroyed, results persisted

*Screenshot: `02_orchestration_progress.png` — JSON showing stage flags and iteration details*

#### Step 4: Inspect the Results

```bash
# Experiment results
curl -s http://localhost:8005/orchestration/orch-a1b2c3d4/results | python -m json.tool

# Claude's reasoning trace
curl -s http://localhost:8005/orchestration/orch-a1b2c3d4/reasoning | python -m json.tool

# Telemetry query
curl -s 'http://localhost:8004/results?experiment_id=shell-10mbps-50ms-cubic-001' | python -m json.tool
```

*Screenshot: `03_telemetry_result.png` — JSON showing configured_capacity=10, measured_throughput=~9.2 (reduced by cross-traffic), configured_latency=50, measured_rtt=~52*

*Screenshot: `04_reasoning_trace.png` — Claude's intent parsing and workflow selection reasoning*

#### Step 5: Validate Against Expected Output

```bash
# Compare key fields against reference
python validate.py --actual <(curl -s http://localhost:8005/orchestration/orch-a1b2c3d4/results) \
                    --expected expected_output/experiment_result.json
```

Validation checks:
- `status == "complete"`
- `configured_capacity == 10.0`
- `configured_latency == 50.0`
- `measured_throughput` within [5.0, 10.0] (cross-traffic reduces available capacity)
- `measured_rtt` within [45, 60] (base latency ± jitter)
- PCAP artifact exists in telemetry

**What to look for:** The measured throughput should be *less* than the configured capacity because cross-traffic (from the CTP) is sharing the bottleneck. The gap between configured and measured IS the effect of realistic congestion. This is the ground truth that static datasets cannot provide.

---

## Example 02: Capacity Sweep

**What it demonstrates:** One intent generates multiple experiments across a parameter sweep. The platform handles the combinatorics, runs each experiment independently, and stores results that can be compared side by side.

**Why it matters:** Research questions are almost never "run one experiment." They're "how does X change as Y varies?" The platform handles the sweep; the researcher thinks about the question.

### README Contents (outline)

#### The Intent

```json
{
  "intent": "Compare iperf3 throughput at 5, 10, and 25 Mbps with 50ms latency"
}
```

This generates three experiments:
- `shell-5mbps-50ms-cubic-001`
- `shell-10mbps-50ms-cubic-002`
- `shell-25mbps-50ms-cubic-003`

All three share the same latency, congestion control, and AQM. Only capacity varies.

#### What to Observe

After all three experiments complete, query telemetry:

```bash
curl -s 'http://localhost:8004/results?latency_min=49&latency_max=51&sort_by=configured_capacity' \
  | python -m json.tool
```

**Validation table (included in README as reference):**

| Configured Capacity | Expected Measured Throughput | CTP Intensity |
|--------------------|-----------------------------|---------------|
| 5 Mbps | 2–5 Mbps (CTP consumes significant share) | ~5 Mbps band |
| 10 Mbps | 5–9 Mbps | ~10 Mbps band |
| 25 Mbps | 15–23 Mbps | ~25 Mbps band |

*Screenshot: `04_configured_vs_measured_plot.png` — bar chart or scatter plot showing the three data points*

**The point:** Static attributes (capacity) and dynamic pressure (CTP) are independently controlled. The researcher specified the capacity sweep; the platform selected matching cross-traffic for each capacity independently. This is the static/dynamic decomposition in action.

---

## Example 03: Fidelity Validation

**What it demonstrates:** Running the same experiment multiple times under identical conditions produces consistent results. This is what makes the platform a scientific instrument.

**Why it matters:** If results aren't reproducible, the platform is a random number generator, not a measurement tool.

### README Contents (outline)

#### The Intent

```json
{
  "intent": "Run iperf3 at 10 Mbps with 50ms latency, 5 trials"
}
```

This generates one experiment spec but requests 5 independent runs.

#### What to Observe

For each trial, extract the throughput time series from the PCAP (100ms bins, 300 bins per 30s window). Overlay all 5 time series on one plot.

**Validation:**
- Wasserstein distance between each pair of trials should be < threshold (Jaber has established this)
- Visual inspection: time series should track each other closely, with small stochastic variation from CTP replay

*Screenshot: `02_throughput_timeseries_overlay.png` — 5 overlaid time series, tight spread*
*Screenshot: `03_wasserstein_summary.png` — table of pairwise Wasserstein distances*

**The point:** Same intent → same spec → same bottleneck → consistent results. The CTP replay introduces realistic variation (it's a real traffic trace, not synthetic), but the variation is bounded and quantifiable.

---

## Example 04: Cross-Substrate Portability (stretch)

**What it demonstrates:** The same experiment specification produces consistent results on different substrates (local Docker vs. AWS).

**Why it matters:** This is the thin waist in action — the specification layer decouples intent from infrastructure.

### README Contents (outline)

#### Run Locally

```bash
./run_local.sh   # CONNECTIVITY_BACKEND=local_docker
```

#### Run on AWS

```bash
./run_aws.sh     # CONNECTIVITY_BACKEND=aws (requires AWS credentials + configured ECS)
```

#### Compare

Show that configured capacity, measured throughput, and measured latency are consistent across the two substrates. Differences should be within the fidelity bounds established in Example 03.

**The point:** "The experiment specification is the thin waist. The substrate is interchangeable."

---

## Instructions for the Team

Each example directory must be self-contained. A user who has never seen the platform should be able to:

1. Read the README from top to bottom
2. Run the commands exactly as written
3. See output that matches the expected output and screenshots
4. Understand what the platform did, why it matters, and how to adapt it

**For each example, the team needs to produce:**

- [ ] `README.md` — complete walkthrough with copy-pasteable commands
- [ ] `intent.json` — the input
- [ ] `run.sh` — single-command execution (submit intent + poll + retrieve results)
- [ ] `expected_output/` — reference JSON files for validation
- [ ] `screenshots/` — annotated screenshots at each step (terminal + JSON output)
- [ ] `validate.py` or `validate.sh` — script that compares actual vs. expected and reports pass/fail

**Quality bar:** If a reviewer can't reproduce the example by following the README alone (no Slack questions, no "ask Jaber"), the example is not done.

---

## Relationship to Live Demo

The live demo IS these examples run in real-time. The presenter:
1. Opens `examples/01-intent-to-data/README.md` on screen
2. Runs the commands from the README
3. Shows that the output matches the expected output and screenshots
4. Narrates the "why it matters" from the README

There is no separate demo script. The examples ARE the demo. The README IS the script. This ensures that everything shown in a demo is reproducible by anyone who clones the repo.

For the vision narrative (what's next: real applications, real infrastructure, closing the loop), use the platform one-pager (`docs/thin_waist_one_pager.md`) as the talking-point guide. That content doesn't belong in the examples — it belongs in the docs.
