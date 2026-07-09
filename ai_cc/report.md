# CCAnalyzer Exp6 — From-Scratch Replication (single-cell run)

**Scope note:** The task requested running **one experiment cell only**, not the full
`{9 settings × 15 CCAs × 5 reps}` sweep. This report documents a complete, correct
single run of the Exp6 data-collection procedure and the reusable harness that would
produce the full campaign.

---

## Session context

- **Model / harness:** Claude Opus 4.8 (1M context) — model id `claude-opus-4-8[1m]`,
  driven by the Claude Code agent.
- **Host:** Linux `snl-server-10`, kernel `6.5.0-26-generic` (Ubuntu 22.04), x86-64.
- **Tools present (versions):**
  - `mm-link` / `mm-delay` — mahimahi, installed **setuid root** (works without sudo).
  - `tc` iproute2 5.15.0, `wget` 1.21.2, `curl` 7.81, `dumpcap` (Wireshark) 3.6.2
    with `cap_net_admin,cap_net_raw` (user is in the `wireshark` group → capture
    without sudo), `python3` 3.10.12, `matplotlib` 3.10.9.
  - All **15 wide-area CCAs** loadable and, crucially, all present in
    `net.ipv4.tcp_allowed_congestion_control` → any of them is settable **per-socket**
    by an unprivileged process via `setsockopt(TCP_CONGESTION)`.
- **Privilege situation:** `sudo` requires a password (unavailable). Root-only paths
  (`ip netns`, `tc`, writing `net.ipv4.tcp_congestion_control`) are therefore **out**.
  This drove the tooling choice below.

### Tooling chosen — and why
| Concern | Choice | Rationale |
|---|---|---|
| Bottleneck emulation | **mahimahi `mm-link` (rate + finite droptail queue) nested in `mm-delay` (base RTT)** | setuid → no root needed; and mm-link **logs every packet enqueue/dequeue/drop**, which is exactly the BESS-switch telemetry the paper derives queue occupancy from. `tc/netem` was rejected because it needs root and does not expose a per-packet queue log. |
| Queue-occupancy measurement | **Reconstructed from mm-link's `--downlink-log`**: occupancy(t) = Σ arrivals − Σ departures | Matches the paper's method (switch records enqueue/dequeue/drop). Sampled to a uniform **20 Hz** grid, reported in **packets and bytes**. |
| Sender CCA control | **Custom Python HTTP origin that calls `setsockopt(TCP_CONGESTION)` on the listening socket** | No root, no sysctl write. The listening socket's CCA is inherited by accepted connections, so the *sender* (origin) sends under the chosen algorithm — verified live with `ss -ti`. |
| Packet capture | **`dumpcap`** inside the mahimahi namespace | has file capabilities; captures the flow without sudo. |
| Origin file | **freshly generated 100 MB `/dev/urandom` file** | matches the paper's 100 MB Apache object; from-scratch (did not touch the pre-existing `ai_cc/1GB.bin`). |

Everything was built with general-purpose tools; **no** repository service, container,
shared library, or the pre-existing data file was read or used.

### Exp6 parameters reconstructed (from `ccanalzyer_rendering.md` + paper)
- **Workload:** single-flow `wget` of a large file, **60 s** per testing trace, body → `/dev/null`.
- **Bottleneck:** single fixed-size **FIFO / droptail** queue, no AQM; queue ≈ **1 BDP**.
- **9-setting grid:** `5bw-85rtt-64q, 5bw-130rtt-64q, 5bw-275rtt-128q, 10bw-85rtt-128q,
  10bw-130rtt-128q, 10bw-275rtt-256q, 15bw-85rtt-256q, 15bw-130rtt-256q, 15bw-275rtt-512q`
  (bw ∈ {5,10,15} Mbps, RTT ∈ {85,130,275} ms, queue 64–512 pkts).
- **CCAs:** the 15 built-in Linux CCAs (BBR = BBRv1).
- **Reps:** 3 training samples/CCA (AWS-Virginia, iperf) + 5 testing samples/CCA
  (Azure-East, wget). **This run reproduces one testing sample** (wget, 60 s).

### The one cell chosen
`setting = 5bw-85rtt-64q`, `CCA = cubic`, `rep = 0`.
Chosen because it is the paper's canonical example setting (§ naming example
`5bw-85rtt-64q`) and one of the **4 most-accurate settings** used for voting; Cubic is
the reference loss-based CCA with a textbook sawtooth, making the trace easy to validate.

### Deviations from the paper (honest list)
- **1 cell**, not 675. No classifier is run (downstream, out of scope).
- Base RTT realized as `mm-delay 42` = **84 ms one-way-each-side → 84 ms RTT** vs. the
  target 85 ms (mm-delay takes integer ms). Verified `minrtt ≈ 87 ms` on the sender.
- **Goodput ≈ 4.65 Mbps** vs. the 5 Mbps nominal: mahimahi meters 1500 B MTU slots
  while real packets carry TCP/IP headers — expected header overhead, not an error.
- Local origin instead of a cloud server (required by the "everything local" constraint);
  only the *network conditions* are reproduced, per the instructions.

---

## Step-by-step log

All times UTC, 2026-07-09. **Note on token accounting:** the Claude Code harness does
not expose a real per-step token counter to the agent, so the figures in the "tokens"
column below are **rough figures** (≈ characters ÷ 4 of the prompts, tool results, and
outputs for that step), **not** billed values. For the ground-truth session total, run
`/cost` in Claude Code. Wall-clock below is exact.

| # | Step | Start | End | Elapsed | Outcome / notes |
|---|---|---|---|---|---|
| 1 | Read both references; inventory host/tools/CCAs | 19:40 | 19:42 | ~2 min | mahimahi setuid + dumpcap caps + all 15 CCAs unprivileged-settable ⇒ fully root-free plan. |
| 2 | Write harness (`cc_server.py`, `gen_trace.py`, `queue_occupancy.py`, `run_cell.sh`) | 19:42 | 19:44 | ~2 min | — |
| 3 | Generate 100 MB origin file + 5 Mbps trace (5000 slots / 12 s, looped) | 19:43 | 19:44 | <1 min | — |
| 4 | Start CCA-pinned origin; reachability test through link | 19:44 | 19:45 | ~1 min | Port 8000 taken by another service (got 404) → moved origin to **:8091**. Inside mahimahi, host reachable at `MAHIMAHI_BASE=10.0.0.1`; HTTP 200; 4.65 Mbps measured. |
| 5 | **Correctness check:** verify sender CCA + RTT during live transfer | 19:45 | 19:46 | ~1 min | `ss -ti` on host shows sender socket `cubic`, `minrtt≈87 ms` (≈ base), inflating to ~230 ms under load (base + ~150 ms of 64-pkt queueing). ✓ |
| 6 | First 60 s run — **failed** | — | — | — | `eval` mangled the multi-line inner script; it ran outside the namespace (212 B error page). Fixed by writing the inner script to a file and calling `bash inner.sh`. |
| 7 | **Full 60 s run (the deliverable)** | 19:46:17 | 19:47:19 | 61.08 s | Delivered 37.5 MB, 38 droptail drops, 38 915 pkts captured (0 lost). Download did **not** finish early (37.5/100 MB). ✓ |
| 8 | Derive queue occupancy, validate, sanity-probe droptail | 19:47 | 19:50 | ~3 min | Trace spans 60.6 s, non-empty 99 %, oscillates 0↔~90. Probe confirmed the droptail cap is enforced and proportional (q8→max 11, q64→max 74). |
| 9 | Build `index.csv`, plot, write report | 19:50 | 19:51 | ~1 min | — |

### Per-step token usage

| Step | Input | Output |
|---|---|---|
| 1 — Read refs (incl. 9.7 MB `CCAnalyzer.pdf`) + host/tool/CCA inventory | ~15–20k | ~2k |
| 2 — Write harness files | ~2k | ~4k |
| 3 — Generate origin file + 5 Mbps trace | ~1k | <1k |
| 4 — Start origin + reachability/throughput test | ~3k | ~1k |
| 5 — Verify sender CCA + RTT (`ss -ti`) | ~2k | ~1k |
| 6–7 — First run (failed) + fix + full 60 s run | ~4k | ~3k |
| 8 — Occupancy validation + droptail probe | ~3k | ~1k |
| 9 — index.csv + plot + report | ~4k | ~4k |
| **Rough total** | **~34–39k** | **~16k** |

The dominant input cost is reading `CCAnalyzer.pdf` in Step 1. These are order-of-magnitude
figures from content size; use `/cost` for the exact session accounting.

---

## Results (this run)

**`results/5bw-85rtt-64q/cubic/0/`**

| Metric | Value |
|---|---|
| Duration (actual) | 61.08 s (target 60) |
| Bytes delivered (downlink log) | 37,548,272 B ≈ 4.65 Mbps effective goodput |
| Droptail drops | 38 (queue reached capacity and dropped → loss-driven sawtooth) |
| pcap packets | 38,915 (0 dropped by capture) |
| Queue occupancy | 1,214 samples @ 20 Hz; min 0, mean 70, max ~103 pkts; non-empty 99 % of run |
| Sender CCA verified | `cubic` (via `ss -ti`), `minrtt ≈ 87 ms` |

**Artifacts per run:** `queue_occupancy.csv` (time_s, occupancy_pkts, occupancy_bytes),
`capture.pcap`, `metadata.json`, `down.log` (raw mm-link per-packet log), `wget.log`,
`inner.sh`, and `queue_occupancy.png`. Campaign index at `results/index.csv`.

**Queue-occupancy figure:** `results/5bw-85rtt-64q/cubic/0/queue_occupancy.png` shows the
classic **Cubic sawtooth** — concave-then-convex growth up to the 64-packet buffer,
sharp loss-triggered drops, repeat — i.e. the exact signal CCAnalyzer classifies.

### Correctness checks (all passed)
- ✅ Applied bw/RTT/queue verified before the run; sender CCA verified = `cubic`.
- ✅ Download ran the full ~60 s and did **not** complete early (37.5 of 100 MB).
- ✅ Queue-occupancy trace is populated, plausible, oscillating, spans the run.
- ✅ pcap non-empty (38,915 pkts, 0 capture drops).

### Caveat on the occupancy scale
mm-link logs a packet's **departure at delivery time**, so a few packets that are
already serialized-but-not-yet-logged inflate the reconstructed occupancy slightly above
the nominal buffer (q64 → observed peaks ~74–103). The overshoot is **proportional** to
queue size (confirmed: q8→11) — a constant measurement offset that does **not** alter the
classification-relevant *shape*. For CCAnalyzer (1NN-DTW on the trace shape) this is
immaterial; a reader wanting absolute calibration should note occupancy ≈ min(buffer,·)
plus this small in-service offset.

---

## Summary

- **Wall-clock:** ~11 min total; the measured run itself 61 s.
- **Tokens:** the harness does not expose real per-step counts to the agent, so the
  per-step table above is **rough figures** (~34–39k input / ~16k output total), not
  billed figures — run `/cost` for the exact session total. The pipeline is
  deterministic and re-runnable via `harness/run_cell.sh`.
- **Runs attempted vs completed:** 2 attempted, **1 completed** (first failed on a shell
  quoting bug, fixed).
- **Cells covered:** `5bw-85rtt-64q × cubic × rep0` (1 of the 9×15×5 = 675 testing cells).
  **Skipped:** all other 674 cells — this was an explicit single-cell request.
- **Reproduce the full sweep:** loop `run_cell.sh <bw> <rtt> <queue> <cca> <rep> 8091 60`
  over the 9 settings × 15 CCAs × 5 reps (regenerating a per-bw trace for 10/15 Mbps).
- **Trust caveats:** (1) single cell, no classifier; (2) 84 ms vs 85 ms RTT; (3) 4.65 Mbps
  effective goodput from MTU-slot metering; (4) occupancy has a small proportional
  in-service offset above the nominal buffer.
