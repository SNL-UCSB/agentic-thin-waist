# CCAnalyzer Exp6 — One-Cell Run via the **Agentic Thin Waist** stack

**Scope note:** This runs **one** Exp6 data-collection cell (`5bw-85rtt-64q`, `cubic`,
1 trial) end-to-end through the Agentic Thin Waist (ATW) orchestration API, following
`cc.md`. It is the ATW counterpart of the pure-from-scratch run in
`ai_cc/report.md` (same cell), so the two can be compared directly on **time** and
**tokens** — see §Comparison at the end.

---

## Session context

- **Driving agent / harness:** Claude Code, model Claude Opus 4.8 (1M context)
  (`claude-opus-4-8[1m]`). This is the agent *operating* the stack (submitting the
  intent, polling, collecting telemetry). It is **not** the model the stack uses
  internally.
- **ATW's own LLM (the one that converts intent → config):** the orchestration
  service is configured with `ORCHESTRATOR_LLM_PROVIDER=gemini`, model
  **`gemini-3.1-flash-lite`** (via `GOOGLE_API_KEY`; `ANTHROPIC_API_KEY` is empty).
  Note the `/intent` response advertises `claude_model: claude-sonnet-4-6`, but that
  is a stale label in the response schema — the code path in `agent/utils.py:get_model()`
  resolves to Gemini given the env. Confirmed by measuring the real call (below).
- **Host:** Linux `snl-server-10`, kernel `6.5.0-26-generic`, x86-64. Host is
  `128.111.5.237`; the download origin is a plain `python3 -m http.server` on
  **:8888** serving `1GB.bin` (**179,893,728 B ≈ 172 MB** — at 5 Mbps × 60 s ≈ 37 MB,
  no early finish).
- **Stack:** all six services healthy (`:8000` experiment-api, `:8001` CTP,
  `:8002` substrate-worker `root_privileges:true, tc/tshark available`, `:8003`
  netgent, `:8004` telemetry, `:8005` orchestration). I do **not** have Docker socket
  permission, so I drove everything through the HTTP APIs (no container introspection).
- **Host CC:** `net.ipv4.tcp_congestion_control` was already `cubic`. Per `cc.md §2/§3`
  the sender is the host `http.server`, so the queue shape is governed by the **host**
  kernel CC. Because the chosen cell is `cubic` and the host default is already `cubic`,
  **no `sudo sysctl` was needed** (it would have been — `sudo` requires a password on
  this host — for any non-cubic CCA; see Caveats).

### What "intent → networking configuration" means here
The ATW pipeline is `parse_intent → generate_experiments → execute_experiments →
respond` (LangGraph `OrchestratorAgent`). The **intent → config** conversion the user
asked about is the **`parse_intent`** node: one LLM call that turns the natural-language
`intent` string into a structured `ParsedIntent` (applications, capacities, latencies,
cc_algorithms, aqm_policy, buffer_packets, duration, …). The deterministic `context`
block in the POST body then **overrides** the LLM's fields for a reproducible sweep.

---

## The one cell chosen
`setting = 5bw-85rtt-64q`, `CCA = cubic`, `1 trial` — identical to the `ai_cc` cell,
for a like-for-like comparison. Submitted via `POST http://localhost:8005/intent` with
the `cc.md §4` template.

---

## Step-by-step log

All times UTC, 2026-07-09. **Token accounting:** unlike the pure-AI run, here I could
measure the ATW LLM cost **exactly** — the intent→config prompt is deterministic (it's
in the repo), so I reconstructed it and queried Gemini's `countTokens` + timed a real
`generateContent`. (The ATW app itself records **no** token telemetry — verified: no
`usage`/`input_tokens` capture anywhere in `services/orchestration/app`.)

| # | Step | Start | End | Elapsed | Outcome / notes |
|---|---|---|---|---|---|
| 1 | Read `cc.md`; probe stack health, host CC, download target, capture defaults | 21:27 | 21:28 | ~1 min | All 6 services healthy; target 200 OK, 172 MB; host CC already `cubic`; capture default = `min(dur,60)=60 s`, qtrace 5 ms. `jq` missing → used `python3`. |
| 2 | Inspect orchestrator to locate the intent→config LLM step + model | 21:28 | 21:30 | ~2 min | `parse_intent` = single LLM call; provider resolves to **Gemini** `gemini-3.1-flash-lite`; app stores no token usage. |
| 3 | **Submit #1** (`workflow_source=library`, per cc.md) — **FAILED** | 21:30:15 | 21:30:24 | ~9 s | Intent parsed & spec generated correctly (`5/85/pfifo/64/cubic`), but the **library workflow-picker LLM refused the match** ("pre-built workflows don't support the network-emulation parameters") — a misjudgment (shaping is applied by the substrate worker, not the workflow). `orch-0f0a401f`. |
| 4 | **Submit #2** (`workflow_source=auto`) — the deliverable | 21:31:00 | 21:34:13 | **193.4 s** | `auto` falls through library→**generate**; ran to `complete`. `orch-4752f3f3` → `experiment_id=wget_5_5_85_pfifo_cubic_16bfa2cc`. |
| 5 | Poll to completion; capture `T_SUBMIT`/`T_FINISH` | — | — | — | wall = 193.44 s. |
| 6 | Collect telemetry: result_id, pcap, qtrace, result.json; append `timing.csv` | 21:34 | 21:35 | ~1 min | pcap 38.3 MB (25,576 pkts, 37.40 MB payload), qtrace 3.77 MB (24,002 lines, 2 ifaces). |
| 7 | Analyze qtrace, extract occupancy CSV, plot, validate | 21:35 | 21:36 | ~1 min | Bottleneck = **veth2**: backlog 0→**64** (capped exactly), mean 39.6, non-empty 98 %, spans 60.0 s, 65 drops. Clean Cubic sawtooth. |
| 8 | **Measure intent→config token+latency cost** (Gemini `countTokens` + 3× timed `generateContent`) | 21:36 | 21:38 | ~2 min | **9,787 input tok**, ~335 output tok, **~1.7 s** per call. |
| 9 | Build comparison plot + write report | 21:38 | 21:40 | ~2 min | — |

### Intent → networking-config conversion cost (the headline the user asked for)
Measured directly against `gemini-3.1-flash-lite` with the **exact** `parse_intent`
prompt (system.md + 5 knowledge files + few-shot `examples.md` + instruction + intent):

| Quantity | Value |
|---|---|
| Input tokens (prompt) | **9,787** (`countTokens`, exact) |
| — of which system prompt (system.md + knowledge) | ~5.0k tok (19,293 chars) |
| — of which few-shot examples block | ~4.4k tok (17,655 chars) |
| — of which instruction + the intent itself | ~0.4k tok |
| Output tokens (ParsedIntent JSON) | ~316–354 (mean ~335) |
| **Total tokens / conversion** | **≈ 10,120** |
| Latency / conversion | **~1.7 s** (3 trials: 1.77 / 1.72 / 1.68 s) |

So the intent string (~60 tokens) is expanded to a **~9,800-token prompt** — 98 % of the
input cost is the fixed system-prompt + few-shot scaffolding, not the user's words. The
conversion is one cheap, fast Gemini call (~10k tokens, ~1.7 s). It is a **small** part
of the 193 s wall-clock (see breakdown).

> **Observation on parse vs. overrides:** in the actual run the logged `parse_intent`
> output was *partial* — it extracted `applications/capacities/latencies/num_trials`
> but left `cc_algorithms/aqm_policy/buffer_packets/duration_seconds = null`. The
> deterministic `context` overrides supplied those. (My standalone reproduction of the
> same prompt extracted them all — LLM nondeterminism.) Either way correctness comes
> from the `context` overrides, not from trusting the parse — which is exactly what
> `cc.md §4` intends.

### Wall-clock breakdown of the 193.4 s run
Derived from `T_SUBMIT`, the qtrace first/last sample timestamps, and `T_FINISH`:

| Phase | Seconds | % |
|---|---|---|
| Pre-capture setup (parse ~1.7 s + workflow-**generate** LLM call + CTP validation + worker dispatch + tc shaping) | **59.9** | 31 % |
| Capture / transfer window (the actual 60 s measurement) | **60.0** | 31 % |
| Post-capture (capture drain + 38 MB pcap & 3.8 MB qtrace upload to telemetry + status flip) | **73.6** | 38 % |
| **Total (intent submit → complete)** | **193.4** | 100 % |

**Only ~31 % of the wall-clock is the measurement; ~69 % (133 s) is orchestration
overhead.** The intent→config LLM step (~1.7 s) is a tiny slice; the large costs are
the second LLM call (workflow generation) + service hops before capture, and the
telemetry artifact upload after.

---

## Results (this run) — `atw_cc/results/`

| Metric | Value |
|---|---|
| Wall-clock (submit→complete) | **193.44 s** |
| Transfer/capture window | 60.0 s (wget `returncode=124`, `terminated_at_deadline=true` — did **not** finish early) |
| Bytes transferred (pcap payload) | 37,402,448 B ≈ **4.99 Mbps** effective |
| pcap packets | 25,576 |
| Queue backlog (veth2, tc qdisc @ 5 ms / 200 Hz) | min 0, mean 39.6, median 35, **max 64 (capped)**, non-empty 98 % |
| Queue drops | 65 |
| Config verified (result.json context tree) | qdisc=pfifo, buffer=64, capacity=5 Mbps, latency=85 ms, cc=cubic ✓ |
| Intent→config LLM | gemini-3.1-flash-lite, 9,787 in / ~335 out tok, ~1.7 s |

**Artifacts (per `cc.md §7` naming `<tag>__<type>__<file>`):**
- `5bw-85rtt-64q_cubic__pcap__*.pcap` — 38.3 MB packet capture.
- `5bw-85rtt-64q_cubic__queue_trace__*_qtrace.jsonl` — raw tc-qdisc backlog samples
  (both veths, 24,002 lines).
- `5bw-85rtt-64q_cubic__queue_occupancy.csv` — bottleneck (veth2) occupancy extracted
  to `time_s, backlog_pkts, backlog_bytes` (12,001 rows).
- `5bw-85rtt-64q_cubic__queue_occupancy.png` — the Cubic sawtooth (capped at 64).
- `5bw-85rtt-64q_cubic__result.json` — telemetry result + four-layer context tree.
- `5bw-85rtt-64q_cubic__metadata.json` — consolidated run metadata.
- `compare_occupancy_aicc_vs_atw.png` — side-by-side vs the pure-AI run.
- `timing.csv`, `timing_marks.txt`, `intent_response.json`, `orch_results.json`,
  `reasoning.json` — provenance & benchmarking.

### Correctness checks (all passed)
- ✅ Config applied & verified via the result context tree (pfifo/64/5 Mbps/85 ms/cubic).
- ✅ Transfer ran the full 60 s and did not complete early (`terminated_at_deadline`).
- ✅ Queue-occupancy trace populated, oscillating, capped exactly at 64, spans 60.0 s.
- ✅ pcap non-empty (25,576 pkts, 37.4 MB).
- ✅ Sender CC = cubic (host default; matches the intent/label).

---

## Comparison — Agentic Thin Waist vs. pure-AI (ai_cc)

Same cell (`5bw-85rtt-64q`, cubic, 1 run), same host, same 60 s workload.

| Dimension | **Pure-AI (`ai_cc`)** | **Agentic Thin Waist (`atw_cc`)** |
|---|---|---|
| How the config was produced | The agent (Opus 4.8) hand-built a mahimahi harness from the paper | NL intent string → ATW `parse_intent` LLM → structured spec (+ deterministic `context` overrides) |
| **Intent→config token cost** | n/a (no NL→config step; agent wrote code directly) | **9,787 in / ~335 out ≈ 10.1k tokens** (Gemini `gemini-3.1-flash-lite`) |
| **Intent→config latency** | n/a | **~1.7 s** |
| Additional LLM calls | — | ≥1 more (workflow picker/**generator**); not separately metered here |
| **Wall-clock for one run** | **61.1 s** (≈ the transfer itself) | **193.4 s** (60 s transfer + **133 s orchestration overhead**) |
| Overhead beyond the 60 s transfer | ~1 s | **~133 s** (60 s setup + 74 s telemetry drain/upload) |
| Emulator | mahimahi mm-link + mm-delay (setuid, no root) | tc/netem qdisc in `ns1` on veth pair (substrate worker, root) |
| Queue-occupancy source | reconstructed from mm-link per-packet log | tc qdisc `backlog` polled @ 5 ms (200 Hz) on veth2 |
| Queue cap fidelity | overshoots to ~90–103 (in-service serialization offset) | **capped exactly at 64** (cleaner) |
| Bytes delivered | 37.55 MB (~4.9 Mbps) | 37.40 MB (~5.0 Mbps) |
| Trace shape | Cubic sawtooth, ~11 s period | Cubic sawtooth, ~10.5 s period — **matches** |
| Artifacts auto-persisted & queryable | manual (local files) | yes — telemetry service (result_id → artifacts), context tree, orchestration record |
| Agent tokens to *operate* | high — agent authored ~4 harness scripts, debugged, plotted (~34–39k in / ~16k out, rough) | lower for config authoring (one curl), but agent still spent tokens polling/collecting/analyzing |

**Takeaways for the user's question**
1. **Time to run one experiment:** ATW **193 s** vs pure-AI **61 s**. The ATW pipeline
   adds **~133 s (2.2×) of orchestration overhead** per run — split ~60 s pre-capture
   (2nd LLM call for workflow-gen + service hops + shaping) and ~74 s post-capture
   (uploading the 38 MB pcap + qtrace into telemetry and flipping status). The measured
   60 s transfer is identical in both.
2. **Cost of converting intent → networking config:** **~10.1k tokens and ~1.7 s** per
   intent, on a cheap Gemini flash-lite model. 98 % of the input tokens are the fixed
   system-prompt + few-shot scaffolding; the user's NL intent is only ~60 tokens. This
   is cheap in isolation but recurs **per run** (parse re-runs each submission).
3. **What you buy for that overhead:** ATW turns a *sentence* into a shaped, captured,
   labeled, and telemetry-indexed experiment with a verified four-layer context tree and
   an exact-capped queue trace — no bespoke harness authoring. Pure-AI is ~3× faster
   per run and needs no services, but the agent had to *write and debug* the emulation
   harness itself (higher agent-token + human-trust cost up front) and produces looser
   queue-cap fidelity.
4. **Amortization:** ATW's ~133 s overhead is fixed per run, so across the full
   195-run campaign it dominates (~7 h of pure overhead), whereas the pure-AI harness,
   once written, runs each cell in ~61 s. ATW's advantage is *expressivity and
   provenance per intent*, not throughput.

---

## Issues & decisions (also logged inline above)
- **`workflow_source=library` failed** (picker LLM rejected the wget workflow as
  "not supporting" the shaping params). **Decision:** re-submit with `workflow_source=auto`
  (the tool's documented fallback: library→generate). This is the only deviation from
  `cc.md`, and it is within the tool's own supported modes. `orch-0f0a401f` (failed) →
  `orch-4752f3f3` (complete).
- **Model label mismatch:** `/intent` returns `claude_model: claude-sonnet-4-6`, but the
  configured provider is Gemini; the real call is `gemini-3.1-flash-lite` (measured).
- **No native token telemetry:** the ATW app discards LLM `usage`; I measured the
  intent→config cost out-of-band (deterministic prompt → `countTokens` + timed call).
  The 2nd LLM call (workflow generation) is acknowledged but not separately metered.
- **`sudo` unavailable** (password-gated): fine for this `cubic` cell (host default), but
  a full campaign would need host-side `sysctl -w tcp_congestion_control` per non-cubic
  CCA — a blocker to record for the other 14 CCAs.
- **Latency semantics:** submitted `latencies=[85]` (paper RTT convention per `cc.md §4`);
  realized queueing behavior is consistent with the ai_cc ~85 ms-RTT run (matching
  sawtooth period), so the convention held for this cell.

## Summary
- **Runs attempted / completed:** 2 / 1 (first failed on the library picker; fixed with
  `auto`).
- **Cell covered:** `5bw-85rtt-64q × cubic × 1 trial` (1 of the 195-run `cc.md` matrix).
  **Skipped:** the other 194 cells (explicit single-experiment request).
- **One-run wall-clock:** 193.4 s (60 s measurement + 133 s ATW overhead).
- **Intent→config conversion:** 9,787 in / ~335 out tokens, ~1.7 s, on
  `gemini-3.1-flash-lite`.
- **Headline vs pure-AI:** same trace, same bytes; ATW is **3.2× slower per run** due to
  orchestration overhead, but produces the config from a single NL sentence plus a
  fully-indexed, provenance-rich telemetry record.
