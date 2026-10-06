# Figure 5 replication: the packet-merging (offloading) issue

**Setting:** CCAnalyzer Figure 5 — Cubic, 5 Mbps, 275 ms added RTT, pfifo queue of
32 / 128 / 512 / 1024 packets, 60 s local wget of `http://128.111.5.237:8888/1GB.bin`.

## TL;DR

Our July runs did not queue real 1500-byte packets. The Linux sender handed the
bottleneck queue **2-segment "super-packets" (~2900 B)**, and `pfifo limit N` counts
those buffers, not wire packets. So every "N-packet" queue really held about **2N**
packets' worth of bytes, which made all four panels behave like a larger buffer than
the paper's. The paper's switch (BESS) counts real packets.

Turning off the merging on the sender and along the path fixed it: the queue now holds
**1514 B per packet**, and the traces look like normal Cubic.

## What "offloading" / packet merging is

To save CPU, Linux processes TCP data in large buffers and splits them into MTU-sized
packets as late as possible:

- **TSO / GSO** (segmentation offload) — the sender's TCP stack builds one big buffer
  covering several MSS-sized segments; the NIC (TSO) or the kernel just before
  transmission (GSO) splits it into wire packets.
- **GRO** (receive offload) — the receiver merges consecutive incoming packets back into
  one big buffer.

On real hardware this is harmless. In an emulated bottleneck it matters, because the
**qdisc enqueues the buffer before it is split**. A pfifo with `limit 32` therefore
admits 32 buffers, however many packets each one contains.

## Why the July runs had ~2900 B "packets"

The sender is this host (`python3 -m http.server 8888`). Linux sizes each TSO buffer
from the pacing rate (`tcp_tso_autosize`), but never below `net.ipv4.tcp_min_tso_segs`,
which defaults to **2**. At 5 Mbps the rate-based size is ~1 segment, so the floor wins
and almost every buffer is exactly **2 × 1448 = 2896 B** of payload.

These buffers stayed whole all the way into the pfifo on `veth2` (the bottleneck),
since nothing on the path disabled GSO.

## Evidence

| Check | July runs | After fix |
|---|---|---|
| Most common data segment in pcap | 2896 B (~90%) | 1448 B (100%) |
| Bytes per queued packet on `veth2` (32q / 128q / 512q / 1024q) | 2843 / 2778 / 2852 / 2954 | 1514 / 1514 / 1514 / 1514 |
| Effective buffer of "1024q" | ~3.0 MB (~2000 MTU packets) | ~1.55 MB (1024 packets) |
| 128q Cubic cycle period | ~15 s | ~6–7 s (paper: ~6–8 s) |

## How it distorted Figure 5

1. **Every queue acted ~2× bigger.** Longer Cubic cycles (32q ≈ 10 s vs the paper's
   ≈ 3–4 s), and 512q / 1024q filled completely where the paper's top out at ~0.6–0.8.
2. **1024q became receive-window limited.** The client's receive window maxes out at
   **3.15 MB** (default `tcp_rmem` max 6 MB, halved). Filling a ~3 MB queue plus the
   0.17 MB in flight needs ~3.14 MB, so the window became the limit, not Cubic. The raw
   trace showed a sawtooth from 20–60 s where the queue drained repeatedly **with no
   drops** — not a Cubic loss response.

## The fix (`run_cc_fig5_nooffload.sh`)

Applied only for the duration of the run; all settings are restored on exit.

| Where | Change |
|---|---|
| Sender (this host) | `net.ipv4.tcp_min_tso_segs=1` (this alone produced 1514 B packets) |
| Sender (this host) | `net.ipv4.tcp_wmem` max → 32 MB |
| substrate-worker container, `ns1`, `ns2` | `ethtool -K <iface> tso off gso off gro off` on every interface |
| Client (`ns1`) | `net.ipv4.tcp_rmem` max → 32 MB |

```bash
sudo bash /home/jaber/agentic-thin-waist/run_cc_fig5_nooffload.sh
```

Outputs in `cc_results/` are tagged `cubic_5bw-275rtt-<Q>q-nooffload__*`
(`result.json`, `pcap`, `queue_trace`); the July files are untouched. The exact offload
and sysctl state used is logged in `cc_results/fig5_nooffload_settings.txt`.

## Verification of the new runs

- 1514 B per queued packet and 1448 B data segments in all four runs.
- Result files record 5 Mbps, 275 ms, pfifo, Cubic and the right queue size; the
  TCP handshake in each pcap takes exactly 275 ms.
- Full 60 s traces (~12,000 samples at 5 ms), throughput ≈ 4.81 Mbps, peak backlog
  equals the queue limit.
- Every queue drop now lines up with packet losses; the drop-free sawtooth in 1024q is gone.

## Caveats

- **Receive window still capped at 3.1 MB.** The 32 MB `tcp_rmem` setting in `ns1`
  apparently did not take effect. It no longer matters: with real 1514 B packets the
  largest window needed (1024q) is ~1.7 MB.
- **Host-side docker bridge/veth offloads were not changed.** The script's lookup of
  those interfaces failed, so they are missing from the settings log. This did not
  affect the result, since `tcp_min_tso_segs=1` already yields MTU-sized packets.
- **Remaining difference from the paper:** our 512q / 1024q still fill to 1.0, while the
  paper's peak around 0.6–0.8. The paper downloaded from a real Azure-East server
  (~24 ms real RTT, Internet path, kernel 5.15) through a BESS switch; we use a local
  server with emulated delay through HTB + pfifo. This is a path/testbed difference that
  host settings can't remove.
- One run per queue size, as in the July data and the paper's "example" traces.

## Takeaway for other ATW experiments

Any experiment that uses a **packet-count** queue (`pfifo`, `limit N`) on this testbed is
affected the same way at low rates: the queue counts merged buffers, not wire packets.
For packet-accurate queues, set `tcp_min_tso_segs=1` on the sender and disable
TSO/GSO/GRO along the path, or use `bfifo` with a byte limit of N × 1514.

## Figures

- `fig5.pdf`, `cc_results/fig5_nooffload.pdf` — paper-style Figure 5 from the new runs
  (styled like the WD/CDF plot: 3.5 in wide, 16 pt).
- `cc_results/fig_paper05_cubic_old_vs_nooffload.png` — raw traces, July vs new, with
  cumulative drops.
- Generated by the last cells of `cc_fig5_paperstyle.ipynb`.
