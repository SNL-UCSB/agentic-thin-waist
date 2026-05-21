# Substrate Worker

**Port**: 8002 · **Plane**: Execution

The Substrate Worker is the sole owner of all kernel-level network operations: tc/netem traffic shaping, tshark capture, and tcpreplay-based CTP replay. It receives replay-ready PCAPs from the CTP Service and applies them to the network; CTP Service never touches the kernel.

## Network topology

`setup.sh` configures two namespaces and a bridge at startup:

```
 [ns1: client]          [host bridge]          [ns2: server]
   veth1 ─────── veth2 ── netrepBr ── veth4 ─────── veth3
172.16.1.1/30  172.16.1.2/30       172.16.2.2/30  172.16.2.1/30

                 veth6 (172.16.3.2/30) ── ns2: veth5 (172.16.3.1/30)
```

- **ns1** (client side): app traffic source, tcpreplay upload injection, downstream latency on `veth1`.
- **ns2** (server side): iperf3 server (`172.16.3.1`), tcpreplay download injection, upstream latency on `veth3`.
- **host**: HTB bandwidth shaping on `veth2` (downstream) and `veth4` (upstream).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Privileges, tool availability, qdisc support. |
| `POST` | `/shape` | Apply bottleneck regime (tc HTB + child qdisc + netem). |
| `GET` | `/state` | Cached bottleneck state. |
| `POST` | `/capture` | Start an async tshark capture. |
| `GET` | `/capture/{capture_id}` | Poll capture status. |
| `DELETE` | `/capture/{capture_id}` | Stop capture (PCAP retained). |
| `POST` | `/replay` | Start bidirectional `tcpreplay-edit` replay of a CTP. |
| `GET` | `/replay/{replay_id}` | Poll replay status. |
| `DELETE` | `/replay/{replay_id}` | Stop replay. |
| `POST` | `/qtrace` | Start a background qdisc-stats sampler (queue occupancy / drops). |
| `GET` | `/qtrace/{qtrace_id}` | Poll qtrace status (samples_written, running/finished). |
| `GET` | `/qtrace/{qtrace_id}/trace` | Download the JSONL trace once finished. |
| `DELETE` | `/qtrace/{qtrace_id}` | Stop the sampler (trace retained). |
| `POST` | `/ctp/fetch` | Fetch CTP download/upload PCAPs into `CTP_DIR`. |

### `POST /shape`

```json
{
  "upstream_iface": "veth4",
  "downstream_iface": "veth2",
  "download_mbps": 100.0,
  "upload_mbps": 100.0,
  "latency_ms": 50.0,
  "latency_location": "both",
  "qdisc": "fq_codel",
  "buffer_packets": 1000,
  "qdisc_params": {"target": "5ms", "interval": "100ms"}
}
```

- `latency_location`: `"upstream"` | `"downstream"` | `"both"` | `null` — which namespace interface gets netem delay.
- `qdisc`: `"pfifo"` (default) | `"fq_codel"` | `"codel"` | `"sfq"` | `"tbf"` | `"bfifo"` | `"pfifo_fast"`.
- `buffer_packets`: queue limit for `pfifo` / `bfifo` / `sfq`; ignored for AQM qdiscs.
- `qdisc_params`: per-qdisc tuning. **AQM qdiscs only** — for `pfifo`-family qdiscs `qdisc_params` must not include `"limit"` (use `buffer_packets`).

After applying tc rules, the worker runs **iperf3** (±20% bandwidth tolerance) and **ping** (±10 ms latency tolerance) and sets `verified`/`verification_log` accordingly.

Response (200):

```json
{
  "status": "shaped",
  "bottleneck_state": {
    "download_mbps": 100.0, "upload_mbps": 100.0,
    "latency_ms": 50.0, "latency_location": "both",
    "qdisc": "fq_codel", "buffer_packets": 1000,
    "qdisc_params": {"target": "5ms", "interval": "100ms"},
    "loss_rate_percent": 0.0,
    "verified": true,
    "verification_log": ["iperf3 download: 98.2 Mbps (target 100.0)", "..."]
  },
  "applied_commands": [
    "tc qdisc replace dev veth2 root handle 1: htb default 10",
    "tc class add dev veth2 parent 1: classid 1:10 htb rate 100mbit ceil 100mbit",
    "tc qdisc add dev veth2 parent 1:10 handle 10: fq_codel limit 1000 target 5ms interval 100ms",
    "..."
  ]
}
```

### `POST /capture`

```json
{
  "interface": "veth2",
  "capture_filter": "tcp port 443",
  "filename": "test1",
  "duration_seconds": 30
}
```

`capture_filter` is tcpdump syntax (optional). `duration_seconds` auto-stops tshark. Response includes `capture_id` and the resolved `pcap_path` under `CAPTURE_DIR`. Status transitions from `"started"` → `"running"` → `"finished"`.

### `POST /replay`

Launches two `tcpreplay-edit` processes simultaneously:

- Download (ingress): `CTP_DIR/download/<ctp_file>.pcap` injected from `ns2` on `veth3`.
- Upload (egress): `CTP_DIR/upload/<ctp_file>.pcap` injected from `ns1` on `veth1`.

```json
{
  "ctp_file": "cluster26_tree10_profile424",
  "duration_seconds": 60,
  "pnat": "169.231.0.0/16:172.16.1.20,128.111.0.0/16:172.16.1.20"
}
```

- `ctp_file`: base name (no direction prefix, no `.pcap`). Both `download/<name>.pcap` and `upload/<name>.pcap` must exist under `CTP_DIR`.
- `pnat`: **required** rewrite rule passed to `tcpreplay-edit --pnat`. Use an IP **distinct from the application's interface IP** (e.g. `172.16.1.20` while the app runs on `172.16.1.1`) so captured PCAPs can be split between app traffic and replayed cross-traffic by destination IP.
- `duration_seconds`: optional auto-stop.

Status is `"running"` while either direction is active, `"finished"` when both end.

### `POST /qtrace`

Start a background sampler that polls leaf-qdisc statistics on one or more interfaces and writes one JSON line per sample to `CAPTURE_DIR/<filename>.jsonl`. This is the lightweight tc-polling implementation of CCAnalyzer-style queue-occupancy traces — use it to study TCP's sawtooth / Cubic curve / BBR probes from the *real* bottleneck queue without instrumenting the kernel.

```json
{
  "interfaces": ["veth2", "veth4"],
  "filename": "iperf3_10mbps_qtrace",
  "interval_ms": 5,
  "duration_seconds": 30
}
```

| Field | Purpose |
|---|---|
| `interfaces` | Interfaces to sample. Default `["veth2", "veth4"]` — the two HTB-shaped bottleneck interfaces. |
| `filename` | Basename of the JSONL output file (no extension). |
| `interval_ms` | Sampling cadence in ms (1–1000). `5` ≈ 200 samples/s/iface; lower values capture faster transients but cost more CPU. |
| `duration_seconds` | Optional auto-stop. Omit and use `DELETE /qtrace/{id}` to stop manually. |

Each JSONL record has the schema:
```json
{"t": 1716000000.123, "iface": "veth2",
 "backlog_bytes": 12345, "backlog_pkts": 12,
 "bytes_sent": 78901234, "pkts_sent": 56789,
 "drops": 0, "overlimits": 0}
```

The sampler parses `tc -s -d qdisc show dev <iface>` and picks the leaf qdisc under HTB class `1:10` (the bottleneck). Counters are cumulative kernel counters — diff them to get rates. Drop the trace into `services/analysis/queue_trace.py:load_queue_trace` or open `services/analysis/analyze_queue.ipynb` to plot it.

Response (200):
```json
{
  "qtrace_id": "0c4a1b3e-...",
  "status": "started",
  "trace_path": "/home/netreplica/config/captures/iperf3_10mbps_qtrace.jsonl",
  "interfaces": ["veth2", "veth4"],
  "interval_ms": 5
}
```

`GET /qtrace/{id}` returns `{ status: "running"|"finished", samples_written, ... }`. `GET /qtrace/{id}/trace` returns the JSONL once stopped (returns `409` while still running — call `DELETE /qtrace/{id}` first).

### `POST /ctp/fetch`

```json
{ "ctp_pointer": "http://ctp-service:8001/ctps/abc123", "ctp_root": null }
```

`ctp_pointer` accepts three formats:

| Format | Example | Behavior |
|---|---|---|
| URL | `http://ctp-service:8001/ctps/abc123` | Streams `?direction=download` and `?direction=upload`. |
| Absolute path | `/mnt/md0/ctp/download/cluster0_tree1.pcap` | Copies both files; upload path derived by swapping `/download/` → `/upload/`. |
| Plain name | `cluster0_tree1_profile1` | Verifies both files are already present in `CTP_DIR`. |

`ctp_root` optionally overrides `CTP_DIR` for this request. Errors: `404` if a local source is missing, `502` if an HTTP fetch fails.

Response:

```json
{
  "status": "ok",
  "name": "abc123",
  "download_path": "/.../download/abc123.pcap",
  "upload_path":   "/.../upload/abc123.pcap",
  "fetched": true
}
```

`fetched: false` indicates idempotent re-fetch (same-size files already present).

Implementation: `app/ctp_fetcher.py` → `fetch_ctp(ctp_pointer, ctp_root)`.

### `GET /health`

```json
{
  "status": "ok",
  "root_privileges": true,
  "tc_available": true,
  "tshark_available": true,
  "tcpreplay_available": true,
  "qdisc_support": true,
  "interfaces": ["veth0", "veth2", "veth4", "veth6"],
  "timestamp": "2026-03-25T10:00:00"
}
```

`status` is `"degraded"` if any check fails.

## Data models

```python
class ShapeRequest:
    upstream_iface: str
    downstream_iface: str
    download_mbps: float          # > 0
    upload_mbps: float            # > 0
    latency_ms: float = 0         # ≥ 0
    latency_location: Literal["upstream","downstream","both"] | None
    qdisc: str = "pfifo"
    buffer_packets: int = 1000    # ≥ 1
    qdisc_params: dict[str, str] | None

class BottleneckState:
    download_mbps: float
    upload_mbps: float
    latency_ms: float
    latency_location: str | None
    qdisc: str
    buffer_packets: int = 1000
    qdisc_params: dict[str, str] | None
    loss_rate_percent: float = 0.0
    verified: bool                # iperf3 + ping passed within tolerance
    verification_log: list[str]

class CaptureRequest:
    interface: str
    capture_filter: str = ""
    filename: str                 # basename-sanitized
    duration_seconds: int | None

class ReplayRequest:
    ctp_file: str
    pnat: str                     # required
    duration_seconds: int | None

class CtpFetchRequest:
    ctp_pointer: str              # URL | abs path | plain name
    ctp_root: str | None
```

## tc topology applied by `/shape`

```bash
# HTB root + bandwidth class
tc qdisc replace dev veth2 root handle 1: htb default 10
tc class  add     dev veth2 parent 1: classid 1:10 htb rate 100mbit ceil 100mbit

# AQM as HTB leaf
tc qdisc  add     dev veth2 parent 1:10 handle 10: fq_codel limit 1000 target 5ms interval 100ms

# Latency in the client namespace
ip netns exec ns1 tc qdisc add dev veth1 root netem delay 50ms
```

## Host requirements (important for CC algorithm support)

The substrate worker uses the **host kernel** for everything below the application layer — there is no per-container kernel. To run experiments against the full set of CCAnalyzer congestion-control algorithms (bbr, bic, cdg, cubic, highspeed, htcp, hybla, illinois, nv, reno, scalable, vegas, veno, westwood, yeah), the host must satisfy three things:

1. **Real Linux host with a stock-style kernel.** Ubuntu, Debian, Fedora, RHEL, Amazon Linux 2, etc. all work out of the box. Docker Desktop on macOS / Windows runs a minimal **LinuxKit kernel** that is built with `CONFIG_TCP_CONG_ADVANCED=N` and ships *only `cubic` and `reno`* — the other 13 CCAs are physically not available in that kernel and cannot be added without rebuilding it. If you need all 15 CCAs on a Mac/Windows workstation, run this stack on an EC2 instance, a Linux VM (Lima, Multipass, etc.), or a Linux dev box rather than Docker Desktop.
2. **`linux-modules-extra-$(uname -r)` (or equivalent) installed on the host.** Ubuntu/Debian ship the 14 loadable `tcp_*` modules in a separate package — without it the worker can still set `cubic`/`reno` but will reject everything else with a clear `modprobe ... Module tcp_<algo> not found` 400.
3. **`/lib/modules` bind-mounted into the container** (already wired up in `docker-compose.yml` and in the orchestrator's ephemeral-worker provisioner). This gives the privileged worker visibility into the host's kernel modules so it can `modprobe tcp_<algo>` on demand.

On startup the setup script attempts `modprobe tcp_<algo>` for each of the 14 loadable CCAs and logs which loaded vs were skipped, so the worker's first few log lines are the canonical source of truth for what your host supports. The runtime `/run` endpoint also returns a `congestion_observed` field per request that aggregates `ss -tin` samples from inside ns1 — use it to confirm the configured CCA was *actually* used by the application (rather than silently downgraded to cubic).

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `CAPTURE_DIR` | `/home/netreplica/config/captures` | tshark output directory. |
| `CTP_DIR` | `/home/netreplica/config/ctp` | Root for CTP PCAPs; expects `download/` and `upload/` subdirs (created by `/ctp/fetch`). |

Runs as a **privileged** container with `CAP_NET_ADMIN` and `CAP_SYS_ADMIN`. For non-privileged deployments, allow `tc`, `tshark`, `tcpreplay`, `tcpreplay-edit` via sudoers.

## Build & run

Build from the **repository root** (the Dockerfile references repo-root paths):

```bash
sudo docker build -t substrate-worker \
  -f services/substrate-worker/Dockerfile .

sudo docker run -d \
  --name substrate-worker \
  --privileged --cap-add=NET_ADMIN --cap-add=SYS_ADMIN \
  --sysctl net.ipv4.ip_forward=1 \
  -p 8002:8002 \
  -v /home/netreplica/config/captures:/home/netreplica/config/captures \
  -v /home/netreplica/config/ctp:/home/netreplica/config/ctp \
  -e CAPTURE_DIR=/home/netreplica/config/captures \
  -e CTP_DIR=/home/netreplica/config/ctp \
  substrate-worker
```

Or via Compose (see top-level `docker-compose.yml` for the full service block).

Local Python workflow uses `uv` with `pyproject.toml`:

```bash
uv run python -m substrate.main
```

## Example flow

```bash
# 1. Shape
curl -X POST http://localhost:8002/shape -H 'Content-Type: application/json' \
  -d '{"upstream_iface":"veth4","downstream_iface":"veth2",
       "download_mbps":100,"upload_mbps":100,"latency_ms":50,
       "latency_location":"both","qdisc":"fq_codel"}'

# 2. Start capture
curl -X POST http://localhost:8002/capture -H 'Content-Type: application/json' \
  -d '{"interface":"veth2","capture_filter":"tcp port 443","filename":"run1"}'

# 3. Start CTP replay
curl -X POST http://localhost:8002/replay -H 'Content-Type: application/json' \
  -d '{"ctp_file":"cluster26_tree10_profile424",
       "pnat":"169.231.0.0/16:172.16.1.20,128.111.0.0/16:172.16.1.20",
       "duration_seconds":60}'

# 4. Inspect state
curl http://localhost:8002/state
```

## Tests

```bash
pytest services/substrate-worker/tests/ -v
```

Unit coverage: qdisc argument building, Pydantic validation, health caching, capture/replay lifecycle, netem placement, `qdisc_params` conflict detection. Integration coverage: live tc execution, tshark PCAP generation, tcpreplay injection, bandwidth/latency verification within tolerance, concurrent replays.

## Source layout

```
services/substrate-worker/
├── src/
│   ├── substrate/   # service entry + API + setup helpers
│   ├── netgent/     # NetGent integration glue
│   └── browser/     # browser integration glue
├── pyproject.toml
└── tests/
```

## References

- Linux tc: https://man7.org/linux/man-pages/man8/tc.8.html
- HTB: https://tldp.org/HOWTO/Traffic-Control-HOWTO/classful-qdiscs.html
- tshark: https://www.wireshark.org/docs/man-pages/tshark.html
- tcpreplay: https://tcpreplay.appneta.com/
