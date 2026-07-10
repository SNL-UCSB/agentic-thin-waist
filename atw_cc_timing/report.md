# Agentic Thin Waist — 20-Experiment Phase-Resolved Timing & Token Benchmark

**Goal.** Run 20 CCAnalyzer-Exp6 data-collection experiments through the Agentic Thin
Waist (ATW) stack and measure, **per experiment**, exactly where the wall-clock goes —
splitting the old single "overhead" bucket into **compile → spin-up → transfer →
drain+upload** — plus the **token cost of converting each intent into a networking
configuration**. Everything is stored under `atw_cc_timing/`.

All 20 runs completed successfully (**20/20**), covering **all 15 CCAs** across the 9
network settings + the queue-size sweep, host CC set and verified per run.

---

## 1. Session context

- **Driving agent:** Claude Code, Claude Opus 4.8 (1M) — operates the stack (submits
  intents, polls phases, collects telemetry). Not the model ATW uses internally.
- **ATW's internal LLM (intent→config):** provider `gemini`, model
  **`gemini-3.1-flash-lite`** (`ORCHESTRATOR_LLM_PROVIDER=gemini`; the `/intent`
  response's `claude_model` label is stale — the real call is Gemini, confirmed by
  direct measurement).
- **Host:** Linux `snl-server-10`, kernel 6.5.0-26. Host IP `128.111.5.237`; origin is
  `python3 -m http.server :8888` serving `1GB.bin` (172 MB — enough that 15 Mbps×60 s
  ≈ 112 MB never finishes early).
- **CC control:** passwordless `sudo sysctl -w net.ipv4.tcp_congestion_control=<cc>`
  (a scoped sudoers drop-in the user enabled). All 15 CCAs verified host-settable; each
  run sets + verifies the sender CC before submitting. The queue-occupancy gallery
  (§5) shows 15 **distinct** CC signatures — direct proof the sender CC took effect.
- **Execution backend:** default `local_docker` — ATW spins up an **ephemeral
  `substrate-worker-{id}` Docker container per experiment**, shapes `ns1` (veth pair),
  runs `wget` in the namespace, captures pcap + a 200 Hz tc-qdisc queue trace, uploads
  to telemetry, tears the container down.

### Method for phase timing (why it's trustworthy)
ATW does **not** persist per-stage timestamps in its final record (the in-memory
lifecycle stages come back empty), so I captured phase boundaries **live**: each run
(`harness/run_one.sh`) records epoch marks by fine-grained polling of the orchestration
status (`pending→parsing→generating→executing→complete`), and aligns the transfer
window post-hoc to the **absolute epoch timestamps in the qtrace** (the shaped link's
own clock). Phases:

| phase | definition | what it is | part of |
|---|---|---|---|
| `healthcheck` | pre-submit probe of all 6 services | liveness | (before `wall`) |
| `submit_rtt` | `POST /intent` round-trip | API submit | `wall` |
| `compile` | status `parsing`→`executing` | **intent→spec** (parse_intent LLM + spec/param prep) | **`orchestration_overhead`** |
|  ↳ `parse` | `parsing`→`generating` | the intent→config LLM call | (⊂ compile) |
|  ↳ `generate` | `generating`→`executing` | experiment-spec + workflow binding | (⊂ compile) |
| `spinup_prepare` | `executing`→transfer start | **Docker container spin-up + shaping + dispatch** | **`orchestration_overhead`** |
| `transfer` | qtrace first→last sample | the 60 s data-gen (download) — **the only non-overhead phase** | `wall` |
| `drain_upload` | transfer end→`complete` | capture drain + pcap/qtrace upload to telemetry | **`orchestration_overhead`** |
| `orchestration_overhead` | `wall − transfer` | **roll-up = `compile` + `spinup_prepare` + `drain_upload`** (+ ~0.2 s submit/poll slack); **not a separate segment** | (= its children) |
| `wall` | submit→`complete` | full experiment = `orchestration_overhead` + `transfer` | — |

> **`orchestration_overhead` is a container, not a sibling.** It is defined as
> `wall − transfer`, which is exactly the sum of the three real work phases that are
> *not* the measurement: **`compile` + `spinup_prepare` + `drain_upload`** (plus a
> ≤0.8 s residual for the submit round-trip and inter-phase polling slack). Verified
> per-run in `timing.csv`: for every run, `compile + spinup_prepare + drain_upload`
> equals `orchestration_overhead` to within ~0.2 s. **Do not add
> `orchestration_overhead` on top of those three — that double-counts.** The stacked
> figure (`fig_phase_stacked.png`) deliberately stacks only
> `compile / spinup_prepare / transfer / drain_upload` so the bars sum to `wall`.

Because the container is ephemeral, its shaping is not observable on the compose
worker `:8002` (`t_shaping_applied` stayed empty every run), so spin-up and
fetch/prepare are reported as one `spinup_prepare` bucket.

### Deviations / decisions (logged)
- **Pinned `workflow_id=test_wget_workflow`** (with `workflow_source=library`) for a
  deterministic path. The `auto`/`generate` route hits a flaky LangGraph bug
  (`"No synchronous function provided to 'decide'"`) ~half the time — non-representative
  noise, not real timing. Pinning is the tool's documented override and matches the
  intent of a reproducible sweep.
- **Data-integrity guard:** telemetry is collected only when the run reached
  `complete` with a real `experiment_id`, so a failure can never pull a stale prior
  result (a bug I hit and fixed during harness bring-up).

---

## 2. Headline results

**20/20 completed.** Median wall-clock **177.1 s** per experiment, of which only
**60 s (34%) is the actual measurement** and **117.1 s (66%) is orchestration
overhead**.

### Phase-resolved timing (median + p10/p90 over 20 runs, seconds)

Indentation shows containment: **`wall` = `orchestration_overhead` + `transfer`**, and
**`orchestration_overhead` = `compile` + `spinup_prepare` + `drain_upload`**. The
indented rows are the *parts of* the bold roll-up above them — they are already counted
in it, not additional to it.

| phase | median | p10 | p90 | min | max |
|---|--:|--:|--:|--:|--:|
| healthcheck *(pre-`wall`)* | 0.18 | 0.16 | 0.20 | 0.14 | 15.1* |
| **`wall` (submit→complete)** | **177.14** | 170.06 | 184.73 | 151.22 | 186.55 |
| &nbsp;&nbsp;├─ **`orchestration_overhead`** *(= the 3 rows below)* | **117.15** | 110.06 | 124.73 | 91.22 | 126.56 |
| &nbsp;&nbsp;│&nbsp;&nbsp;&nbsp;├─ compile (intent→spec) | 2.66 | 1.77 | 2.97 | 1.72 | 4.15 |
| &nbsp;&nbsp;│&nbsp;&nbsp;&nbsp;│&nbsp;&nbsp;&nbsp;├─ parse (intent→config LLM) | 1.21 | 0.60 | 1.78 | 0.57 | 2.97 |
| &nbsp;&nbsp;│&nbsp;&nbsp;&nbsp;│&nbsp;&nbsp;&nbsp;└─ generate (spec + bind) | 1.18 | 1.09 | 1.75 | 0.59 | 1.77 |
| &nbsp;&nbsp;│&nbsp;&nbsp;&nbsp;├─ spin-up + prepare (Docker) | 44.28 | 40.29 | 47.94 | 13.99 | 54.36 |
| &nbsp;&nbsp;│&nbsp;&nbsp;&nbsp;└─ drain + upload (telemetry) | 71.05 | 67.65 | 73.17 | 61.02 | 74.04 |
| &nbsp;&nbsp;└─ **`transfer`** (data-gen, the measurement) | **60.00** | 60.00 | 60.00 | 59.99 | 60.00 |

(`submit_rtt` ≈ 0.05 s and ~0.2 s inter-phase polling slack are the small remainder
inside `orchestration_overhead` beyond the three components.)

\* one healthcheck spiked to 15.1 s (a service momentarily slow to answer `/health`);
median 0.18 s. It does not affect wall-clock (healthcheck precedes submit).

**So instead of "≈117 s of overhead," the sentence is now:**
> compile **2.7 s**, container spin-up **44.3 s**, experiment (transfer) **60 s**,
> telemetry drain+upload **71 s** — median wall **177 s**.

The two dominant costs are **not** the LLM: they are **Docker container spin-up +
shaping (44 s)** and **telemetry drain + artifact upload (71 s)**. The intent→config
LLM call is ~1.2 s — <1% of wall-clock.

### What the phases are (concurrent vs. additive)
The phases run **one after another** end-to-end (they are additive), with **one
exception inside the transfer**:
- **spin-up (44 s)** happens *before* the download (container + tc shaping must exist first).
- **transfer (60 s)** — the worker fires the pcap capture, the qtrace sampler, and the
  `wget` **as simultaneous threads** aligned to a whole-minute boundary. So the **60 s
  is `wget`'s runtime**, and the capture/qtrace run *concurrently on top of it* — they
  add **no** extra time. `wget` is `timeout 60 wget …`, killed at the 60 s deadline
  (`returncode=124`, `terminated_at_deadline=true`), so it never finishes early; the
  60 s is a fixed measurement window, not a throughput bottleneck.
- **drain+upload (71 s)** happens *after* the transfer (sequential): stop capture, pull
  the pcap + qtrace off the worker into telemetry, then destroy the ephemeral container.

### Why drain+upload is ~71 s — it scales with **duration**, not data size
A controlled probe pins this down. Holding everything else fixed and varying only the
experiment duration:

| transfer window | drain+upload | pcap size |
|---|--:|--:|
| 60 s (the campaign) | ~71 s | 38–76 MB (varies with bandwidth) |
| 20 s (probe) | **26 s** | ~13 MB |

Two facts fall out: (1) across the 20 campaign runs, drain is **flat ~71 s whether the
pcap is 38 MB (5 Mbps) or 76 MB (10 Mbps)** — so it is **not** bound by pcap byte
volume; (2) cutting the duration 60 s→20 s cuts drain 71 s→26 s — so **drain ≈
transfer_duration + ~7 s**. The only per-run quantity that scales with *duration but not
bandwidth* is the **qtrace**: a fixed **200 Hz** sampler on 2 interfaces produces
**24,000 samples for 60 s vs 8,000 for 20 s**. So the drain is dominated by the
**qtrace stop → read → stream-to-telemetry path (∝ sample count)**, not by the pcap
upload. (Exact per-substep split would need orchestrator-container logs, which aren't
accessible here without Docker; the *scaling law* is the actionable result.)

**Lever:** dropping `duration_seconds` to 20 s (the paper says ~20 s suffices for
classification) would cut **both** transfer (60→20 s) **and** drain (71→26 s) — roughly
**halving** wall-clock to ~90 s. Lowering `ORCH_QTRACE_INTERVAL_MS` (fewer samples/s)
would cut drain further.

### Figures (in `atw_cc_timing/`)
- `fig_phase_stacked.png` — per-run stacked decomposition (compile/spin-up/transfer/drain); strikingly uniform across all 20.
- `fig_phase_stats.png` — median ± p10/p90 per phase (the table above).
- `fig_overhead_cdf.png` — CDF of orchestration overhead (p50 ≈ 117 s, p90 ≈ 125 s).
- `fig_tokens.png` — per-intent parse-token cost.
- `fig_queue_gallery.png` — bottleneck queue occupancy for all 20 runs (15 distinct CC signatures).

---

## 3. Intent → networking-configuration token cost

Measured **exactly** per experiment by reconstructing the deterministic `parse_intent`
prompt (system.md + 5 knowledge files + few-shot `examples.md` + instruction + the
intent) and querying Gemini's `countTokens`; output counted from the logged
`ParsedIntent`.

| | median | min | max |
|---|--:|--:|--:|
| **input tokens** (intent→config prompt) | **9,789** | 9,787 | 9,791 |
| **output tokens** (ParsedIntent JSON) | 162 | 159 | 343 |
| **total / conversion** | **≈ 9,951** | — | — |

- The intent string itself is only ~60 tokens; **~98% of input is the fixed
  system-prompt + few-shot scaffolding**, so the per-intent cost is essentially
  constant regardless of the bw/rtt/queue/cc values (input varies by just ±2 tokens).
- **Second orchestrator LLM call:** the workflow **param-mapper**
  (`shell_map_workflow_params`) runs even with a pinned workflow — measured **~390 in /
  ~60 out ≈ 450 tokens**. So the **full orchestrator cost per intent→execution ≈
  10,400 tokens** (parse_intent 96%, mapper 4%).
- **Campaign total:** ~199,600 parse tokens across 20 runs (+~9k mapper) ≈ **209k
  tokens** for the whole 20-experiment sweep — i.e. **~$0.02–0.05** at flash-lite
  rates. LLM cost is negligible next to the wall-clock.
- ATW itself records **no** token telemetry; these numbers are measured out-of-band and
  reproducible via `harness/parse_tokens.py`.

---

## 4. What the per-experiment story is now

For a single ATW experiment (median):

```
submit ─▶ compile 2.7s ─▶ spin-up+shape 44.3s ─▶ transfer 60s ─▶ drain+upload 71s ─▶ complete
         (parse_intent    (ephemeral Docker      (the actual     (pcap+qtrace →
          LLM ~1.2s +       container +            measurement)    telemetry)
          bind ~1.2s)       tc shaping)
         └──────────────── orchestration overhead 117s (66%) ─────────────┘  wall 177s
```

- **compile / intent→config** is cheap and fast: ~2.7 s and ~9,950 tokens.
- **spin-up (44 s)** is the price of the per-experiment ephemeral Docker worker + tc
  shaping. A persistent/reused worker (the `remote`/reuse backend) would largely
  remove this.
- **drain+upload (71 s)** is the price of shipping the raw artifacts (a ~38 MB pcap
  each) into the telemetry service — the single largest phase.
- The measurement itself is a fixed 60 s and rock-steady (p10=p90=60.0).

---

## 5. Data integrity & CC validation

- **20/20 `complete`**, every `cc_verified == cc` (host CC took effect each run).
- Queue backlog peaks span **24 → 1024 pkts** (BBR/Vegas/CDG stay near-empty; loss-based
  CCAs fill their buffer; veno fills the 1024-pkt queue) — the 15 CC signatures in
  `fig_queue_gallery.png` are visibly distinct, confirming the **sender** CC governed
  each trace.
- Per-run wall-clocks are tight: 151–187 s (the 151 s min is run 00, whose spin-up was
  14 s — the first container after an idle stack warms fastest; later runs sit ~44 s).

---

## 6. Comparison to the pure-AI run (`ai_cc`) and the earlier single ATW run

| Dimension | Pure-AI (`ai_cc`) | ATW (this campaign) |
|---|---|---|
| Wall-clock / experiment | ~61 s | **177 s median** (p10 170, p90 185) |
| Overhead beyond the 60 s transfer | ~1 s | **117 s median (66%)** |
| — compile (intent→config) | n/a (agent wrote code) | 2.7 s |
| — container spin-up + shaping | n/a (mahimahi setuid, instant) | 44 s |
| — telemetry drain + upload | n/a (local files) | 71 s |
| Intent→config tokens | n/a | **9,951 / intent** (Gemini flash-lite) |
| Queue-cap fidelity | overshoots (~103 vs 64) | exact (capped at buffer) |
| Provenance | local files | telemetry-indexed, 4-layer context tree |

ATW is **~2.9× slower per experiment**, and the overhead is now **attributed**: it is
dominated by per-experiment Docker spin-up and artifact upload, **not** by the LLM
(compile is <2% of wall). The earlier single ATW run reported "~133 s overhead" as one
bucket; this campaign resolves that into **compile 3 s + spin-up 44 s + drain 71 s**
(the earlier run's 60 s "pre-capture" included a one-off cold container; steady-state
spin-up is ~44 s).

---

## 7. Deliverables in `atw_cc_timing/`

- `timing.csv` — one row/run with every phase (seconds) + a `# phase,median,p10,p90,min,max` stats block.
- `tokens.csv` — per-intent parse input/output/total tokens.
- `runs/<NN_setting_cc>/` — per experiment: `phases.env` (raw epoch marks), `result.json`, `parsed_intent.json`, `intent.txt`, `pcap__*.pcap`, `queue_trace__*.jsonl`, `artifacts.json`, `intent_response.json`.
- `campaign.log` — full run log with the aggregate stats.
- `fig_*.png` — the five figures above.
- `harness/` — `run_one.sh`, `run_campaign.sh`, `cells.txt`, `aggregate.py`, `analyze.py`, `parse_tokens.py` (fully reproducible).

## 8. Caveats
- **Pinned workflow** avoids the flaky generate path; the `auto` route would add one
  more LLM call (workflow picker/generator) to `compile` — a few seconds and a few k
  tokens — but is unreliable here, so its timing isn't representative.
- **Ephemeral container** ⇒ spin-up and fetch/prepare couldn't be split (not observable
  on `:8002`); reported as one `spinup_prepare` bucket.
- **Token counts** are measured out-of-band (ATW stores none); parse_intent is exact
  per-run, the mapper is a single representative measurement (~450 tok).
- Timing reflects **this host under light load**; spin-up/drain depend on Docker and
  telemetry-DB load and would shift on a busier or remote-backend deployment.
