# CCAnalyzer Exp6 Replication — Data-Collection Playbook

Reproduce the **main 1NN-DTW classification collection (Exp6)** from *CCAnalyzer*
(Ware et al., SIGCOMM '24) on the local Agentic Thin Waist stack, plus the
queue-size sweep (paper Fig. 5/6). We drive a `wget` download of a large file
over a shaped bottleneck, capture the **bottleneck queue-occupancy trace** and
**pcap** for every run, and record end-to-end timing for benchmarking.

- **Reference paper:** `CCAnalyzer.pdf`
- **Experiment→figure mapping / setup:** `ccanalzyer_rendering.md` (see **Exp6**, **Exp4/Exp5**)
- **Canonical download target:** `http://128.111.5.237:8888/1GB.bin`
- **All telemetry lands in:** `/home/jaber/agentic-thin-waist/cc_results/`
- **All execution issues get logged in:** `/home/jaber/agentic-thin-waist/cc_report.md`

---

## 0. Ground rules (read first)

1. **Everything is local.** The download server (`http.server`) runs on **this Linux
   host**; the shaped path and the `wget` client run inside the Agentic Thin Waist
   containers. There is **no** AWS-Virginia / Azure-East / cloud component — ignore
   the paper's remote-server details. We are only sweeping the shaping parameters
   and congestion-control algorithm and collecting the resulting traces.
2. **The CC that matters is the *sender's* CC.** In a download the **server** (the
   host's `http.server`) is the sender, so the queue-occupancy shape is governed by
   **the host kernel's** `net.ipv4.tcp_congestion_control` — **not** the client-side
   CC inside the containers. Therefore, before each run **set the CC on the host**
   with `sysctl` (§3). Also pass the same `cc` in the intent `context` so the
   `experiment_id` and telemetry are labeled correctly.
3. **No file storage.** `wget` writes to `/dev/null` (`-O /dev/null`); nothing is
   persisted on the client.
4. **60 s per run.** Each experiment runs for 60 seconds (paper testing-trace
   length). The capture/qtrace window must cover the full 60 s (§5).
5. **Log every problem** — module load failures, unreachable server, CC not
   applied, missing artifacts, timeouts — to `cc_report.md` as you go.

> **File-size caveat:** `1GB.bin` on this host is ~172 MB, not 1 GB. At our max
> setting (15 Mbps × 60 s ≈ 112 MB) that is enough. **If you ever raise bandwidth
> or duration** so a run could pull >172 MB, `wget` finishes early and the queue
> trace flatlines — regenerate a true ≥1 GB file first (see §2, fallback).

---

## 1. The 15 congestion-control algorithms

The paper's 15 built-in wide-area Linux CCAs (BBR = BBRv1). Kernel name on the
left, paper name on the right:

| kernel name | paper name | | kernel name | paper name |
|---|---|---|---|---|
| `reno`      | NewReno    | | `illinois`  | Illinois   |
| `cubic`     | Cubic      | | `nv`        | New Vegas (NV) |
| `bbr`       | BBR (v1)   | | `scalable`  | Scalable   |
| `bic`       | BIC        | | `vegas`     | Vegas      |
| `cdg`       | CDG        | | `veno`      | Veno       |
| `highspeed` | Highspeed  | | `westwood`  | Westwood   |
| `htcp`      | HTCP       | | `yeah`      | Yeah       |
| `hybla`     | Hybla      | |             |            |

Do **not** include `dctcp` or datacenter-only algorithms (paper excludes them).

**Preflight — confirm all 15 are usable on the host** (verified present on this
host as of writing; re-check before a campaign):

```bash
# List what the kernel currently exposes:
sysctl net.ipv4.tcp_available_congestion_control

# If any of the 15 are missing, load the module (needs root):
for m in bbr bic cdg highspeed htcp hybla illinois nv scalable vegas veno westwood yeah; do
  sudo modprobe "tcp_$m" 2>>/home/jaber/agentic-thin-waist/cc_report.md || \
    echo "MODPROBE FAILED: tcp_$m" >> /home/jaber/agentic-thin-waist/cc_report.md
done
# reno + cubic are built in. Re-list to confirm all 15 now appear:
sysctl net.ipv4.tcp_available_congestion_control
```

Anything that still won't load → note it in `cc_report.md` and **skip that CC**
(do not silently drop it from the results — record which CCs were collected).

---

## 2. Preflight — download server

The server must be serving a large file at `http://128.111.5.237:8888/1GB.bin`.

```bash
# Reachability + size check:
curl -sI --max-time 5 http://128.111.5.237:8888/1GB.bin | head -3
```

**Fallback if unreachable / server down.** Re-serve the existing file from the
repo (where `1GB.bin` already lives) or the home directory, on port **8000**:

```bash
cd /home/jaber/agentic-thin-waist        # 1GB.bin is here
python3 -m http.server 8000              # then use http://<host-ip>:8000/1GB.bin
```

If you switch host/port, update the URL in the intent template (§4) and note the
change in `cc_report.md`. To create a genuine 1 GB file when needed:
`head -c 1073741824 /dev/urandom > 1GB.bin`.

---

## 3. Setting the host CC before each run

`net.ipv4.tcp_congestion_control` sets the default CC for **new** TCP connections.
`http.server` opens a fresh socket per request, so setting it *before* the run's
`wget` is enough — no server restart needed.

```bash
# show available algorithms
sysctl net.ipv4.tcp_available_congestion_control

# temporarily change it (until reboot) — do this on the HOST, not in containers
sudo sysctl -w net.ipv4.tcp_congestion_control=bbr

# verify it stuck
sysctl net.ipv4.tcp_congestion_control
```

**Reminder:** this is set on the **host** that runs the `http.server` and serves
the file — **not** inside the Agentic Thin Waist containers. Verify the value
actually changed before submitting the intent; if `sysctl -w` fails or reports a
different value, log it to `cc_report.md` and skip the CC.

---

## 4. The intent template

One parameterized `POST /intent`. `context` keys **override** the LLM-extracted
values (deterministic sweep). `${...}` are the per-run parameters from §5.

```bash
# Per-run parameters (example: BBR at the 10bw-130rtt-128q setting):
CC=bbr; BW=10; RTT=130; Q=128; DUR=60

# 3a) set the host CC first (see §3)
sudo sysctl -w net.ipv4.tcp_congestion_control="$CC"

# 3b) submit the intent, capture submit timestamp + orchestration_id
T_SUBMIT=$(date +%s.%N)
ORCH_ID=$(curl -s -X POST http://localhost:8005/intent \
  -H "Content-Type: application/json" \
  -d "{
    \"intent\": \"Run a wget download from http://128.111.5.237:8888/1GB.bin over a ${BW} Mbps bottleneck with ${RTT} ms added latency, pfifo queue of ${Q} packets and ${CC} congestion control. Do not store the downloaded file (write it to /dev/null). Stop the wget process after ${DUR} seconds. One trial.\",
    \"workflow_source\": \"library\",
    \"context\": {
      \"capacities\":       [${BW}],
      \"latencies\":        [${RTT}],
      \"cc_algorithms\":    [\"${CC}\"],
      \"aqm_policy\":        \"pfifo\",
      \"buffer_packets\":    ${Q},
      \"qdisc_params\":      {},
      \"duration_seconds\":  ${DUR},
      \"num_trials\":        1
    }
  }" | python3 -c "import json,sys;print(json.load(sys.stdin)['orchestration_id'])")
echo "orch=$ORCH_ID  cc=$CC bw=$BW rtt=$RTT q=$Q"
```

Notes:
- `aqm_policy: pfifo` → a plain FIFO queue of `buffer_packets` (the paper uses a
  fixed FIFO ≈ 1 BDP; no AQM). Queue size goes in `buffer_packets`, **not**
  `qdisc_params` (that's only for AQM qdiscs like `fq_codel`).
- `workflow_source: library` pins the wget workflow from the NetGent library.
- **Latency semantics caveat:** the orchestrator treats `latencies` as *one-way*
  ms. The paper's numbers are **RTT**. Set `latencies` to the paper RTT value and
  **verify** the realized RTT once (§6, `/state` + a ping through the shaped path);
  if the worker applies delay per-direction (RTT ≈ 2×latency), halve the value and
  record the correction in `cc_report.md`. Keep whichever convention you pick
  **consistent across the whole campaign.**

---

## 5. The experiment matrix

### 5a. Main collection — 9 coupled settings × 15 CCs (Exp6 → Fig. 7)

Queue is ≈ 1 BDP per setting. Naming: `<bw>bw-<rtt>rtt-<queue>q`.

| setting | bw (Mbps) | rtt (ms) | queue (pkts) |
|---|---|---|---|
| `5bw-85rtt-64q`    | 5  | 85  | 64  |
| `5bw-130rtt-64q`   | 5  | 130 | 64  |
| `5bw-275rtt-128q`  | 5  | 275 | 128 |
| `10bw-85rtt-128q`  | 10 | 85  | 128 |
| `10bw-130rtt-128q` | 10 | 130 | 128 |
| `10bw-275rtt-256q` | 10 | 275 | 256 |
| `15bw-85rtt-256q`  | 15 | 85  | 256 |
| `15bw-130rtt-256q` | 15 | 130 | 256 |
| `15bw-275rtt-512q` | 15 | 275 | 512 |

→ 9 settings × 15 CCs × **1 trial** = **135 runs**.
(The 4 "most accurate" settings used for voting in the paper are
`10bw-130rtt-128q`, `10bw-85rtt-128q`, `5bw-130rtt-64q`, `5bw-85rtt-64q`.)

### 5b. Queue-size sweep — fixed 5 Mbps / 275 ms (Exp4/Exp5 → Fig. 5/6)

| bw (Mbps) | rtt (ms) | queue sizes (pkts) |
|---|---|---|
| 5 | 275 | 32, 128, 512, 1024 |

→ 4 queue sizes × 15 CCs × **1 trial** = **60 runs**.
(Paper Fig. 5 = Cubic, Fig. 6 = BBR; we collect all 15 for a fuller dataset.)

**Total this pass: 195 runs at 1 trial each.** Treat this as the full dry run;
scale `num_trials` up later (e.g. 5 → the paper's 675-sample Fig. 7) once one
clean end-to-end pass is confirmed.

**Iteration order:** outer loop over settings, inner loop over the 15 CCs. Set the
host CC (§3), submit (§4), poll to completion (§6), collect artifacts (§7), append
timing (§7), then move on. Log failures and continue — never abort the whole
campaign on one bad run.

---

## 6. Poll a run to completion + verify shaping

```bash
# Poll orchestration until complete/failed:
while STATUS=$(curl -s http://localhost:8005/orchestration/$ORCH_ID | jq -r .status); \
      [ "$STATUS" != complete ] && [ "$STATUS" != failed ]; do sleep 5; done
T_FINISH=$(date +%s.%N)
echo "final=$STATUS"

# Sanity-check the kernel actually applied the shaping (once per new setting):
curl -s http://localhost:8002/state \
  | jq '.bottleneck_state | {qdisc, buffer_packets, download_mbps, latency_ms, verified}'
```

If `status=failed`, or `buffer_packets` / `download_mbps` don't match the request,
log it to `cc_report.md` (with the `orch_id`) and mark the run for a retry.

---

## 7. Collect telemetry into `cc_results/`

For every run, pull the **pcap** and the **queue-occupancy trace** and store them
under a self-describing name, plus one row of timing. Artifacts flow:
`orchestration → experiment_id → telemetry result_id → artifacts`.

```bash
RESULTS=/home/jaber/agentic-thin-waist/cc_results
mkdir -p "$RESULTS"
TAG="${BW}bw-${RTT}rtt-${Q}q_${CC}"           # e.g. 10bw-130rtt-128q_bbr

# experiment_id from orchestration:
EXP=$(curl -s http://localhost:8005/orchestration/$ORCH_ID/results \
        | jq -r '.results[0].experiment_id // empty')

# telemetry result row for that experiment:
RID=$(curl -s "http://localhost:8004/results?experiment_id=$EXP&limit=1" \
        | jq -r '.results[0].result_id // empty')

# download each artifact (pcap + queue_trace) by type:
curl -s "http://localhost:8004/results/$RID/artifacts" \
  | jq -c '.artifacts[] | {artifact_id, artifact_type, filename}' \
  | while read -r a; do
      AID=$(echo "$a" | jq -r .artifact_id)
      ATYPE=$(echo "$a" | jq -r .artifact_type)
      FN=$(echo "$a" | jq -r .filename)
      curl -s "http://localhost:8004/artifacts/$AID" -o "$RESULTS/${TAG}__${ATYPE}__${FN}"
    done

# save the full result JSON (qoe metrics, tags, context tree) for provenance:
curl -s "http://localhost:8004/results/$RID" > "$RESULTS/${TAG}__result.json"

# append one benchmarking row (timing) — see §8:
WALL=$(echo "$T_FINISH - $T_SUBMIT" | bc)
echo "${EXP},${CC},${BW},${RTT},${Q},${DUR},${T_SUBMIT},${T_FINISH},${WALL},${STATUS}" \
  >> "$RESULTS/timing.csv"
```

**What `cc_results/` should contain per run:**
- `…__pcap__*.pcap` — packet capture of the shaped download.
- `…__queue_trace__*.jsonl` — bottleneck queue-occupancy samples (the input to
  CCAnalyzer's 1NN-DTW; sampled from `tc … qdisc show` on `veth2`/`veth4`).
- `…__result.json` — telemetry result (metrics + four-layer context tree).
- one appended line in `timing.csv`.

> **Ensure the trace spans the full 60 s.** The qtrace/pcap window follows
> `ORCH_CAPTURE_DURATION_SECONDS` (default ≤60). If traces come back short, set
> `ORCH_CAPTURE_DURATION_SECONDS=65` (and keep `ORCH_QTRACE_ENABLED=true`,
> `ORCH_QTRACE_INTERVAL_MS=5`) in the orchestration service env and re-run.

---

## 8. Benchmarking — timing every experiment

**Goal:** for each experiment record (a) wall-clock time from **intent submission**
to **finish**, and (b) the **declared** per-experiment duration from the intent
(60 s). We use these for later benchmarking of orchestration overhead.

`cc_results/timing.csv` header (write once, before the campaign):

```
experiment_id,cc,bw_mbps,rtt_ms,queue_pkts,declared_duration_s,t_submit_epoch,t_finish_epoch,wall_s,status
```

- `t_submit_epoch` — captured right when `POST /intent` returns (§4, `T_SUBMIT`).
- `t_finish_epoch` — captured when the orchestration status flips to
  `complete`/`failed` (§6, `T_FINISH`).
- `wall_s = t_finish - t_submit` (includes worker spin-up, CTP fetch, capture
  drain, telemetry upload — i.e. the full orchestration overhead, not just the
  60 s transfer).
- `declared_duration_s` — the `duration_seconds` from the intent (60).

---

## 9. Naming & bookkeeping conventions

- **Per-run tag:** `<bw>bw-<rtt>rtt-<queue>q_<cc>` (e.g. `5bw-85rtt-64q_cubic`).
  Matches the paper's `<bw>bw-<rtt>rtt-<queue>q` plus the CC.
- **Artifact files:** `<tag>__<artifact_type>__<original_filename>`.
- **Trial suffix (when `num_trials`>1 later):** append `_tN` to the tag.
- Keep the `experiment_id` (from orchestration, format
  `{app}_{dl}_{ul}_{lat}_{aqm}_{cc}_{uuid8}`) in `timing.csv` and `result.json`
  so every file is traceable back to its run.

---

## 10. Issue log — `cc_report.md`

Create `cc_report.md` at the start and append a dated entry for **every**
execution problem, including but not limited to:

- CC module that would not `modprobe` / does not appear in
  `tcp_available_congestion_control` (which CC, exact error).
- Host `sysctl -w tcp_congestion_control` that didn't take effect.
- Download server unreachable / restarted / moved to a new port.
- Orchestration run that returned `failed`, or `/state` shaping that didn't match
  the request (`orch_id`, expected vs actual).
- Missing/short/empty pcap or queue_trace artifact for a run.
- Latency-semantics correction (one-way vs RTT) applied in §4.
- Any CC ultimately **skipped** (so results are not silently incomplete).

Suggested entry format:

```
## <ISO date> — <setting> / <cc>
- symptom: ...
- orch_id / exp_id: ...
- action taken: ...
- resolved: yes/no
```

---

## 11. End-to-end checklist per run

1. [ ] Host CC set + verified (`sysctl -w`, §3).
2. [ ] Intent submitted; `T_SUBMIT` + `orch_id` captured (§4).
3. [ ] (New setting) shaping verified via `/state` (§6).
4. [ ] Polled to `complete`; `T_FINISH` captured (§6).
5. [ ] pcap + queue_trace + result.json saved to `cc_results/` (§7).
6. [ ] `timing.csv` row appended (§8).
7. [ ] Any issue logged in `cc_report.md` (§10).
