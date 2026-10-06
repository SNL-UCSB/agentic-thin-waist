# Gordon (vendored) — baseline CWND-based CC classifier

Vendored from **[github.com/NUS-SNL/Gordon](https://github.com/NUS-SNL/Gordon)** —
Mishra, Sun, Jain, Pande, Joshi, Leong, *"The Great Internet TCP Congestion Control
Census"*, SIGMETRICS 2019. Used here as the **Gordon baseline** in CCAnalyzer's Exp8
comparison (Fig 13–15). License: see `LICENSE` (upstream).

## Why it's here
CCAnalyzer compares its 1NN-DTW queue-occupancy classifier against Gordon (an *active*
CWND-estimating prober). Reproducing Fig 13 (Gordon's per-CCA votes) requires running
Gordon. Gordon's prober uses **NFQUEUE** (`libnetfilter_queue`) to intercept a flow's
inbound packets and manipulate the receive window to reveal the server's congestion
window — which needs `CAP_NET_ADMIN`. The substrate worker already runs **privileged
with NET_ADMIN/SYS_ADMIN**, so it is the correct home for it.

## What's vendored (and how it differs from upstream)
| File | Origin | Change |
|---|---|---|
| `probe.c` | upstream `probe.c` | **patched two stack-buffer overflows** (`get[]` 17→1024 B; `cmd[]`/`number`/`window`/`in` enlarged; output path via `GORDON_WINDOWS_CSV`). Compiles clean. |
| `Scripts/tcpClassify.py` | upstream | fixed the broken module tail (`classify(folder+str(i)+.csv)` was a syntax error) → importable + a safe CLI. `classify()` logic unchanged. |
| `gordon_run.sh` | new (adapts upstream `Scripts/launch.sh`) | runs inside ATW's `ns1` using tc-applied RTT/bw/queue instead of `mm-delay`; NFQUEUE matches the ns1 client IP `172.16.1.1`; parameterized target/trials. |
| `gordon_classify.py` | new | thin wrapper: windows.csv → CCA label JSON (the Fig-13 vote). |

The prober binary is compiled at image build time to `/usr/local/bin/gordon-prober`
(see the substrate-worker `Dockerfile`).

## Run it
Through the worker's shell workflow (`test_gordon_workflow.json`), or directly:
```bash
# inside the substrate worker container, after ATW has shaped ns1:
ip netns exec ns1 /app/src/gordon/gordon_run.sh http://<origin>/<file> 40
# -> writes Data/windows.csv (CWND-vs-RTT) and prints {"tool":"gordon","cca":"..."}
```
For the full Fig-13 vote the paper runs multiple trials per CCA and takes the majority.

## Status
- ✅ `probe.c` compiles (verified against libnetfilter-queue-dev 1.0.5); patched overflows gone.
- ✅ `tcpClassify.py` / `gordon_classify.py` run — verified on Gordon's own published
  census traces.
- ⏳ End-to-end prober run requires an **image rebuild** (`make build`) so
  `gordon-prober` and the netfilter libs are present, then a shaped `ns1`. Not runnable
  on a bare no-root host (NFQUEUE needs CAP_NET_ADMIN).
