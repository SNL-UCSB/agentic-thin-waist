# CCAnalyzer Experiment 6 — From-Scratch Replication Prompt

You are a general-purpose AI agent. Your task is to **replicate Experiment 6 of
CCAnalyzer**, as described **together** in `ccanalzyer_rendering.md` and
`CCAnalyzer.pdf` (Ware et al., *"CCAnalyzer: An Efficient and Nearly-Passive
Congestion Control Classifier,"* ACM SIGCOMM '24), **entirely from scratch** on this
Linux host.

"From scratch" is a hard rule. Read the constraints in §0 before anything else.

- **Your references for the experiment (read both, together):**
  - `ccanalzyer_rendering.md` — maps every figure/table to its experiment and spells
    out the **Exp6** setup: the network-setting grid, the CCAs, durations, and
    repetition counts. **Start here to find exactly what Exp6 is.**
  - `CCAnalyzer.pdf` — the authoritative paper behind it; use it to cross-check and
    fill in any detail the rendering doc summarizes.

  Both live in this folder. Use them together to reconstruct the network conditions
  and measurement procedure.
- **All output goes to:** `/home/jaber/agentic-thin-waist/ai_cc/results/`
- **Your running log / write-up goes to:** `/home/jaber/agentic-thin-waist/ai_cc/report.md`

---

## 0. Hard constraints — read first

1. **Pure from-scratch execution.** Do **not** read, import, reuse, or rely on any
   other file, directory, service, container, or framework on this machine. In
   particular, ignore anything belonging to the surrounding repository (its
   services, shared libraries, Docker/Compose stack, orchestration, and telemetry).
   The **only** files you read are the two references in this folder —
   `CCAnalyzer.pdf` and `ccanalzyer_rendering.md`. Every artifact you produce — the
   emulated network, the traffic, the queue-occupancy trace, the pcap, the
   metadata — must be built by you with standard, general-purpose tools.

2. **You choose the tooling.** Set up the emulated bottleneck however you judge
   best: **`mahimahi` (mm-link / mm-delay)**, **`tc`/`netem`/`tbf`/`htb`**, a
   software switch, or anything else available. Justify your choice briefly in
   `report.md`. If a tool is missing, install it if you can, otherwise pick another
   and record the decision.

3. **Everything is local.** There are **no** cloud servers (no AWS, Azure, or
   remote hosts). Run a local origin (e.g. a simple HTTP server) that serves a
   large file, shape the path locally, and run the client locally. The paper's
   remote-server geography is irrelevant — you only need to reproduce the *network
   conditions* and *measurement*, not its physical testbed.

4. **Log everything to `report.md` as you go** (see §6). Every step, every problem,
   every decision — with timing, token usage, and the model in use.

---

## 1. What Experiment 6 requires you to collect

Read `ccanalzyer_rendering.md` (the **Exp6** section) alongside the paper for the
authoritative description. In essence, Exp6 is a
**data-collection campaign** that, for each congestion-control algorithm and each
network setting, downloads a large file over a single shaped bottleneck and records
the **bottleneck queue-occupancy time series** (plus supporting telemetry). The
classifier itself is downstream; your job here is to **collect the traces and
metadata** the way the paper does.

For **each run** you must produce:

- **A bottleneck queue-occupancy trace over time** (the core signal — occupancy of
  the bottleneck queue sampled/derived across the run).
- **A packet capture (pcap)** of the flow.
- **A metadata record** for the run: bandwidth, base latency/RTT, queue size, queue
  management, congestion-control algorithm, download tool, file size, duration,
  bytes transferred, timestamps, and the exact emulation command used.

### Workload
- Download a **large file** with a client such as `wget` (or `curl`), discarding the
  body (e.g. write to `/dev/null`) — nothing needs to be persisted on the client.
- **Each run lasts ~60 s** (the paper's testing-trace length). Your capture and
  queue-occupancy window must cover the full run.
- **The served file must be large enough that the download never finishes early**
  at your highest bandwidth over 60 s (otherwise the queue trace flatlines). If the
  available file is too small, generate a bigger one first.

### Congestion-control algorithms (15)
Use the 15 built-in wide-area Linux CCAs (BBR = BBRv1). Kernel module name → paper
name:

| kernel | paper | | kernel | paper |
|---|---|---|---|---|
| `reno`      | NewReno   | | `illinois` | Illinois       |
| `cubic`     | Cubic     | | `nv`       | New Vegas (NV) |
| `bbr`       | BBR (v1)  | | `scalable` | Scalable       |
| `bic`       | BIC       | | `vegas`    | Vegas          |
| `cdg`       | CDG       | | `veno`     | Veno           |
| `highspeed` | Highspeed | | `westwood` | Westwood       |
| `htcp`      | HTCP      | | `yeah`     | Yeah           |
| `hybla`     | Hybla     | | | |

Exclude datacenter-only algorithms (e.g. `dctcp`). Before the campaign, confirm all
15 are loadable (`sysctl net.ipv4.tcp_available_congestion_control`; `modprobe
tcp_<name>` as needed). Any CCA that will not load → **record it in `report.md` and
skip it** (do not silently drop it; state which CCAs were actually collected).

> **The congestion control that shapes the queue is the *sender's* CC.** In a
> download the origin server is the sender, so the queue-occupancy shape is governed
> by the kernel CC of whatever process is sending the data. Make sure the target CCA
> is applied to the **sender** for each run (e.g. via
> `net.ipv4.tcp_congestion_control` on the sending host/namespace), and **verify it
> took effect** before starting the run. Label each run's metadata with the CCA you
> set.

### Network settings
The paper sweeps a small grid of **{bandwidth × base-RTT × queue-size}** settings,
with the queue sized to roughly one bandwidth-delay product (BDP). Extract the exact
grid Exp6 uses from `ccanalzyer_rendering.md` (cross-check the paper) and reproduce
it. Record the setting for every run using a clear naming scheme (e.g.
`<bw>bw-<rtt>rtt-<queue>q`).

For each `(setting × CCA)` pair, collect the number of repetitions specified in the
references (note the training vs. testing sample counts and state which
you reproduce). If full coverage is too expensive, **collect a well-defined subset
and say exactly what you covered and what you skipped** — never imply full coverage
you did not achieve.

---

## 2. Suggested procedure (adapt as you see fit)

You own the design; this is a sane default, not a mandate.

1. **Environment preflight.** Check which emulation tools, capture tools, and CCA
   modules are available. Install what you need. Record versions.
2. **Origin.** Serve a large file locally over HTTP. Verify reachability and that
   the file is big enough for a 60 s download at max bandwidth.
3. **Bottleneck.** Build the single shaped bottleneck (bandwidth limit + base delay
   + finite queue ≈ 1 BDP). Decide and record the queue-management discipline; the
   paper uses a plain fixed-size FIFO — match that unless you justify otherwise.
4. **Per run**, for each `(setting, CCA)`:
   a. Apply the setting to the bottleneck and the CCA to the **sender**; verify both.
   b. Start the pcap capture and the queue-occupancy sampler covering ≥60 s.
   c. Run the 60 s `wget`/`curl` download to `/dev/null`.
   d. Stop capture/sampler; save the pcap, the queue-occupancy trace, and the
      metadata record under a per-run directory in `results/`.
   e. Sanity-check the trace (non-trivial, non-flatlined, spans ~60 s); if bad,
      diagnose, fix, and note it in `report.md`.
5. **Measuring queue occupancy** is the crux. Whatever emulator you pick, derive the
   bottleneck queue length/occupancy over time (e.g. sampling the bottleneck qdisc
   backlog, parsing the emulator's per-packet uplink/queue log, or an equivalent
   method). Document exactly how you obtained it and its units/sampling rate.

---

## 3. Output layout

Write all artifacts under `/home/jaber/agentic-thin-waist/ai_cc/results/`, organized
per run, e.g.:

```
results/
  <setting>/<cca>/<rep>/
     queue_occupancy.csv     # time, occupancy  (state units + sampling rate)
     capture.pcap
     metadata.json           # bw, rtt, queue, qmgmt, cca, tool, file size,
                             # duration, bytes transferred, timestamps, commands
  index.csv                  # one row per run, summarizing all metadata
```

Keep an `index.csv` (or similar) with one row per completed run so the full campaign
is queryable at a glance.

---

## 4. Correctness checks

- Verify the applied bandwidth/RTT/queue and the sender CCA **before** each run;
  a run whose settings did not take effect is invalid — fix or discard it.
- Confirm the download ran the full ~60 s and did **not** complete early.
- Confirm the queue-occupancy trace is populated and plausible for that CCA/setting.
- Any failure (module load, unreachable origin, CC not applied, early completion,
  empty capture, sampler gap) → log it in `report.md` and either fix or skip with an
  explicit note.

---

## 5. Deliverable

A `results/` tree with, for every completed run, a queue-occupancy trace + pcap +
metadata; an `index.csv` summarizing the campaign; and a complete `report.md`.
Where feasible, add a short summary/plot of representative queue-occupancy traces
(e.g. a couple of CCAs at one setting) to show the collection worked.

---

## 6. `report.md` — mandatory step-by-step write-up

Maintain `/home/jaber/agentic-thin-waist/ai_cc/report.md` **continuously** (append as
you work, do not reconstruct at the end). It is both an execution log and the final
report.

**At the top**, record the session context:
- Model(s) used (name/version) and the agent/harness.
- Host facts you rely on (OS/kernel, available emulation & capture tools + versions,
  CCA modules present).
- The tooling you chose for emulation, capture, and queue measurement — and **why**.
- The exact Exp6 parameters you reconstructed from the paper (the setting grid, CCA
  list, durations, repetition counts) and any deviation you had to make.

**For every step**, append an entry with:
- **What was done** — the action, the exact commands, and the outcome.
- **Wall-clock time** — start time, end time, and elapsed duration for that step.
- **Token usage** — input/output tokens consumed for that step (and a running
  total).
- **Model** — which model performed the step (note any change mid-run).
- **Issues & decisions** — anything that failed, what you changed, what you skipped
  and why.

**At the end**, add a summary: total wall-clock time, total tokens, number of runs
attempted vs. completed, which `(setting × CCA)` cells were collected vs. skipped,
and any caveats a reader needs to trust the dataset.
