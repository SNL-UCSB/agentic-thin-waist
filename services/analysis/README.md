# Analysis — pcap + queue trace plotting

Helpers for turning a finished experiment's **pcap** and **queue_trace** artifacts into plots you can drop into a report. Used by the Quick Start notebook and adaptable to any custom analysis you want to run.

## When to use this

After a `POST /intent` run finishes (`status: complete`), telemetry will have two artifacts per result:

- `<experiment_id>.pcap` — raw packet capture on the bottleneck interface (`veth2`)
- `<experiment_id>_qtrace.jsonl` — per-sample queue occupancy + drop counts on `veth2` and `veth4`

This package downloads them by `experiment_id` and produces throughput / queue / drop plots. The default entrypoint is the notebook; the modules are also importable directly.

## Quick start — the notebook

[analyze_queue.ipynb](analyze_queue.ipynb) is the canonical walkthrough. It fetches both artifacts from telemetry and produces the standard 3-panel + zoom-in plot used in the project's writeups.

```bash
# from the repo root, with the stack already up via `make up`:
jupyter notebook services/analysis/analyze_queue.ipynb
```

Then in **cell 2**, set `EXPERIMENT_ID` to the value the orchestrator printed (you can also set it via env var: `EXPERIMENT_ID=… jupyter notebook …`):

```python
EXPERIMENT_ID = os.environ.get('EXPERIMENT_ID', 'PASTE-YOUR-ID-HERE')
```

Then **Run All**. The notebook will:

1. Hit `http://localhost:8004` (telemetry) and download the pcap + queue_trace into `_pcap_cache/`.
2. Print the experiment's **contextual tree** (bottleneck capacity, latency, qdisc, buffer, CC) so you can confirm the run matched what you asked for.
3. Plot four panels (sections 4 and 5 of the notebook):

| panel | shows | derived from |
|---|---|---|
| Download throughput (mbps over time) | how close the actual throughput got to the configured cap; cold-start ramp; any TCP stalls | pcap, 100 ms bins |
| Upload throughput (mbps over time) | TCP ACK rate, plus any upload-direction traffic | pcap, 100 ms bins |
| Bottleneck queue occupancy (packets) | how full the bottleneck queue got over time, per interface (veth2 = downstream, veth4 = upstream) | qtrace, raw samples |
| Drop rate (per sec) | when the bottleneck started shedding packets — usually right when the queue hits `buffer_packets` | qtrace, derived from running drop counter |

Section 5 of the notebook also renders a **CCAnalyzer-style queue-evolution zoom** in *bytes* — handy for spotting the congestion-control fingerprint (Reno's sawtooth, Cubic's $x^3$ curve, BBR's periodic probes).

### What a healthy run looks like

For the default Quick Start command (10 Mbps, pfifo, 200-packet buffer, cubic, 30 s wget):

- Download panel: ramps up in the first ~2 s, then sits near 10 Mbps for the rest of the run.
- Upload panel: low and flat (~0.1 Mbps of ACKs).
- Queue panel: `veth2` (blue) ramps up, plateaus near the 200-packet limit, holds there until wget finishes.
- Drop panel: zero until the queue hits 200 packets, then a sustained non-zero rate.

If the download panel goes idle in the middle of the run, or the queue stays at 0, your pcap was either captured on the wrong interface or your workflow didn't actually run — check `GET /orchestration/{id}` for an error.

## Headless — running on a remote VM and viewing on your laptop

When the stack runs on a remote VM (typical SNL setup), there's no browser to open the notebook in. The flow is: execute the notebook on the VM into a self-contained HTML file, then `scp` that file back to your laptop and open it locally.

### 1. (On the VM) install Jupyter + analysis deps in a venv

Ubuntu 24.04 blocks plain `pip install` to system Python (PEP 668), so use a venv. The `jupyter-core` apt package only ships the dispatcher, not subcommands like `nbconvert` — uninstall it if it's in the way:

```bash
sudo apt remove -y jupyter-core    # optional; system pkg is in the way and ships old versions
sudo apt install -y python3-venv

cd ~/agentic-thin-waist
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install jupyter nbconvert ipykernel matplotlib pandas scapy requests
```

When you come back later, just `source ~/agentic-thin-waist/.venv/bin/activate` first — no need to reinstall.

### 2. (On the VM) render the notebook to HTML

Run from the **repo root** (the notebook adds `services/analysis` to `sys.path` by walking up from `cwd`, so launching elsewhere breaks imports). Substitute your real experiment ID:

```bash
EXPERIMENT_ID=wget_10_10_20_pfifo_cubic_83423825 \
TELEMETRY_BASE=http://localhost:8004 \
jupyter nbconvert --to html --execute \
  services/analysis/analyze_queue.ipynb \
  --output analyze_queue.html
```

This produces `services/analysis/analyze_queue.html` — a self-contained HTML file with every cell's output and plot embedded. Confirm it exists and has non-zero size:

```bash
ls -la services/analysis/analyze_queue.html
```

Other output formats: `--to notebook --execute --output executed_analyze_queue.ipynb` (saves results back into an `.ipynb`), or `--to script` then `python` (no plots — useful only for quick numerical checks).

### 3. (On your laptop) pull the HTML over `scp`

`scp` runs **on your laptop**, not from inside the SSH session — open a new terminal on the laptop. Format is `scp -P <port> <user>@<host>:<remote-path> <local-path>`:

```bash
scp -P 2201 student@<vm-host>:~/agentic-thin-waist/services/analysis/analyze_queue.html ~/Downloads/
```

Then open it:

```bash
open  ~/Downloads/analyze_queue.html      # macOS
xdg-open ~/Downloads/analyze_queue.html   # Linux
start ~\Downloads\analyze_queue.html      # Windows (PowerShell)
```

Use **capital `-P`** for the port — lowercase `-p` means something else for `scp`. The password is the same one used for `ssh`.

**Alternative — VS Code Remote-SSH:** If you're connected via VS Code Remote-SSH, skip the `scp` step. Right-click `analyze_queue.html` in the file explorer and pick **Download…**, or use the "Live Preview" extension to view it in the editor.

### Common failures

- **`Jupyter command 'jupyter-nbconvert' not found`** — you have `jupyter-core` from apt but not the `nbconvert` package. Activate the venv and `pip install nbconvert`.
- **`NoSuchKernel: python3`** — `ipykernel` isn't installed in the venv. `pip install ipykernel`.
- **`ImportError: services.analysis`** — you ran `nbconvert` from somewhere other than the repo root. `cd ~/agentic-thin-waist` and try again.
- **`no telemetry rows for <id>`** — that `EXPERIMENT_ID` isn't in your telemetry DB. Did the orchestration actually finish (`status: complete`)? Pull a real ID with the snippet in [the root README §4](../../README.md#4-pull-the-experiment--result-ids).

## Using the modules directly

If you want to script your own analysis or work on a pcap that isn't in telemetry:

```python
from services.analysis import (
    load_pcap, filter_downlink, filter_uplink, summarize_pcap, plot_throughput,
    load_queue_trace, summarize_queue_trace, plot_queue_occupancy, plot_drop_rate,
)

pkts = load_pcap("/path/to/my.pcap")
print(summarize_pcap(pkts))                 # packets, total bytes, mean Mbps, tcp_flows
plot_throughput(filter_downlink(pkts), bin_seconds=0.1, unit="mbps")

df = load_queue_trace("/path/to/my_qtrace.jsonl")
print(summarize_queue_trace(df))            # per-iface: p50/p95/max backlog, drops, mean Mbps
plot_queue_occupancy(df, unit="packets")
```

`pcap_analysis.py` is the pcap-side API (load / filter / summarize / plot throughput + packet-size scatter). `queue_trace.py` is the qtrace-side API (load JSONL into a DataFrame, summarize per-interface stats, plot occupancy + drop rate). `qoe.py` extracts iperf3 / ndt / ping numbers from the `qoe_metrics` block of a telemetry result.

## Other notebooks in this directory

- [analyze_queue.ipynb](analyze_queue.ipynb) — **start here.** Telemetry-mode walkthrough (downloads artifacts from `:8004`).
- [analyze_experiment.ipynb](analyze_experiment.ipynb) — older variant focused on QoE metrics; useful when you only have an experiment_id and want a summary without redrawing plots.
- [local_analyze_queue.ipynb](local_analyze_queue.ipynb) — same as `analyze_queue.ipynb` but skips the telemetry pull and reads a local `.pcap` + `.jsonl` pair directly. Use this when the worker captured to a path you already have on disk and you don't want to round-trip through MinIO.

## Troubleshooting

- **`404` / `500` downloading the pcap artifact** — usually means MinIO was wiped (`make clean`) but the telemetry Postgres row still references the old blob. The notebook caches downloads under `_pcap_cache/<experiment_id>.pcap`, so a previously-successful run will keep working from the cache.
- **`(no queue_trace artifact)`** — the experiment predates the `/qtrace` change. Re-run the experiment; new runs always produce one.
- **Throughput plot empty / very low** — the pcap was captured on the wrong interface or the bottleneck didn't shape correctly. Check the `applied_commands` block under `result["run"]["shaping"]` for the actual `tc` rules that were installed.
