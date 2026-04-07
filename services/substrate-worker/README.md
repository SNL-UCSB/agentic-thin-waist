# Substrate Worker Service

**Port**: 8002
**Deliverable**: D1 (Network Virtualization Substrate - Execution Plane)
**Lead**: Jaber | **Supporting**: Satyam, Snithik
**PI**: Prof. Arpit Gupta
**Priority**: CRITICAL
**Status**: Active Development

## Purpose

The Substrate Worker is the **Execution Plane** of the NetForge Service. It instantiates bottleneck-regime specifications on concrete infrastructure, translating high-level network constraints into operational Linux traffic control (tc) configurations, packet capture (tshark), and traffic replay (tcpreplay) operations. It applies both static attributes (capacity, latency, AQM) and dynamic pressure (CTP background traffic) to the network interface.

**The Substrate Worker is the sole owner of all network execution**: tc qdisc management, tcpreplay for CTP traffic, and tshark for packet capture. It receives replay-ready PCAP data from the CTP Service (which handles CTP algebra and export) and executes the actual replay on the network interface. This separation keeps CTP Service as a pure representation/database layer while Substrate Worker handles all privileged kernel operations.

## Input

Substrate Worker accepts:
- BottleneckState specifications: download/upload capacity (Mbps), latency (ms), latency location, queue discipline, buffer depth, qdisc parameters
- Network interface assignments: upstream/downstream interfaces
- CTP replay sessions: replay-ready PCAP files (from CTP Service), replay rates, PNAT rewrite, loop/duration options
- Packet capture requests: interface, tcpdump filter syntax, filename, optional duration
- Configuration: capture directory path, CTP directory path (via environment variables)

## Output

Substrate Worker produces:
- BottleneckState verification results: verified boolean, applied tc commands, verification log
- tc qdisc command outputs confirming kernel module load
- PCAP files from packet capture at specified interface
- tcpreplay session metrics: replay ID, status, rate achieved
- Status reports: interface configuration, qdisc state, available tc modules

## Source Layout

- `src/substrate`: the worker service entrypoint, API module, and setup helpers
- `src/netgent`: reserved package space for NetGent-specific integrations
- `src/browser`: reserved package space for browser-specific integrations

For local Python workflows, the service now uses `uv` with [`pyproject.toml`](/Users/eugenevuong/Documents/UCSB/agentic-thin-waist/services/substrate-worker/pyproject.toml). Run it with `uv run python -m substrate.main`.

## Interfaces

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/shape` | POST | Configure bottleneck regime (tc qdisc rules + netem latency) |
| `/capture` | POST | Start asynchronous packet capture with tshark |
| `/capture/{capture_id}` | GET | Poll capture session status |
| `/capture/{capture_id}` | DELETE | Stop active capture session |
| `/replay` | POST | Start CTP traffic replay via tcpreplay |
| `/replay/{replay_id}` | GET | Poll replay session status |
| `/replay/{replay_id}` | DELETE | Stop active replay session |
| `/ctp/fetch` | POST | Fetch download + upload PCAPs from a URL or local path into `CTP_DIR` |
| `/state` | GET | Get current bottleneck configuration and verification |
| `/health` | GET | Health check: privileges, tc availability, qdisc support |

## Core Concepts

**Bottleneck Regime**: A complete network condition specification with two components:

1. **Static Attributes** (configured via tc):
   - Capacity (bandwidth shaping via HTB root qdisc)
   - Base latency (propagation delay via netem)
   - Buffering (queue depth)
   - Queue management policy (AQM: pfifo, fq_codel, codel, sfq, etc.)

2. **Dynamic Pressure** (replayed via tcpreplay):
   - CTP (Common Traffic Pattern) background traffic
   - Hybrid replay model: background traffic open-loop, target application fully reactive
   - Captures contention and packet interaction effects

The worker verifies configured shaping via iperf3 (±20% bandwidth tolerance) and ping (±10ms latency tolerance), recorded in `BottleneckState.verified`.

## Deployment Modes

**Standalone**: Single host using Linux namespaces, bridges, and traffic control.

**Distributed** (three-server topology):
- **Server A**: Client applications and traffic sources
- **Server B**: Bottleneck with tc/LibreQoS enforcement (packet shaping layer)
- **Server C**: Application endpoints and NAT

NetForge provides `NAT()` and `Tunnel()` abstractions for connectivity beyond the testbed.

## Network Topology (setup.sh)

The service configures a two-namespace topology at startup:

```
 [ns1: client]          [host bridge]          [ns2: server]
   veth1 ─────── veth2 ── netrepBr ── veth4 ─────── veth3
172.16.1.1/30  172.16.1.2/30       172.16.2.2/30  172.16.2.1/30

                 veth6 (172.16.3.2/30) ── ns2: veth5 (172.16.3.1/30)
```

- **ns1** (downstream/client): iperf3 client, tcpreplay injection point, downstream latency via `veth1`
- **ns2** (upstream/server): iperf3 server (target 172.16.3.1), upstream latency via `veth3`
- **host**: HTB bandwidth shaping on `veth2` (downstream) and `veth4` (upstream)

## Architecture

```
┌──────────────────────────────────┐
│  Experiment API                  │
│  (Intent Plane Orchestration)    │
└────────────┬─────────────────────┘
             │
             │ POST /shape, /capture, /replay
             │ GET /state, /health
             ▼
┌──────────────────────────────────┐
│  SUBSTRATE WORKER (8002)         │
│  EXECUTION PLANE (FastAPI)       │
│  ┌──────────────────────────┐    │
│  │ TC Executor              │    │
│  │ (HTB root + child qdisc) │    │
│  ├──────────────────────────┤    │
│  │ netem Latency Injection  │    │
│  │ (upstream/downstream/    │    │
│  │  both)                   │    │
│  ├──────────────────────────┤    │
│  │ Packet Capture (tshark)  │    │
│  ├──────────────────────────┤    │
│  │ CTP Replay (tcpreplay)   │    │
│  ├──────────────────────────┤    │
│  │ State Verification       │    │
│  │ (iperf3 + ping)          │    │
│  └──────────────────────────┘    │
└────────────┬─────────────────────┘
             │
             │ tc commands (HTB, netem, qdisc)
             │ tshark capture
             │ tcpreplay / tcpreplay-edit (PNAT)
             │ iperf3, ping (verification)
             ▼
        ┌─────────────────┐
        │ Linux Kernel    │
        │ Network NS      │
        │ tc qdisc stack  │
        │ Virtual Bridges │
        | LibreQoS/ XDP   │
        └─────────────────┘
```

### Dependencies

- **CTP Service** (Port 8001): Provides replay-ready PCAP data. The Substrate Worker does not perform CTP algebra — it receives pre-processed PCAP and replays it via tcpreplay.
- **Experiment API** (Port 8000): Dispatches configuration, replay, and capture commands.

## Configuration

**Environment Variables**:

| Variable | Default | Purpose |
|----------|---------|---------|
| `CAPTURE_DIR` | `/home/netreplica/config/captures` | Output directory for PCAP files |
| `CTP_DIR` | `/home/netreplica/config/ctp` | Root CTP directory; `download/` and `upload/` subdirs are expected (or created by `/ctp/fetch`) |

**Security Notes**:
- Run as a privileged Docker container with `CAP_NET_ADMIN` and `CAP_SYS_ADMIN`
- Never commit credentials to version control

## API Specification

### 1. Shape Network (POST /shape)

Configure bottleneck regime on target interfaces.

**Request**:
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
  "qdisc_params": {
    "target": "5ms",
    "interval": "100ms"
  }
}
```

- `latency_location`: `"upstream"` | `"downstream"` | `"both"` | `null` — controls which namespace interface receives netem delay
- `qdisc`: `"pfifo"` (default) | `"fq_codel"` | `"codel"` | `"sfq"` | `"tbf"` | `"bfifo"` | `"pfifo_fast"`
- `qdisc_params`: optional per-qdisc tuning (e.g., `target`, `interval` for fq_codel/codel)
- `buffer_packets`: queue limit for pfifo/bfifo/sfq; ignored for AQM qdiscs (fq_codel, codel)

**Response** (200 OK):
```json
{
  "status": "shaped",
  "bottleneck_state": {
    "download_mbps": 100.0,
    "upload_mbps": 100.0,
    "latency_ms": 50.0,
    "latency_location": "both",
    "qdisc": "fq_codel",
    "buffer_packets": 1000,
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

**Verification**: After applying tc rules, the worker runs iperf3 (±20% bandwidth tolerance) and ping (±10ms latency tolerance) and sets `verified` accordingly.

---

### 2. Get State (GET /state)

Retrieve cached bottleneck state without re-running verification.

**Response** (200 OK):
```json
{
  "status": "ok",
  "bottleneck_state": { ... }
}
```

Returns `"status": "no_state"` with `"bottleneck_state": null` if no shaping has been applied.

---

### 3. Health Check (GET /health)

**Response** (200 OK):
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

`status` is `"ok"` when all checks pass; `"degraded"` if any check fails.

---

### 4. Packet Capture (POST /capture)

Start an asynchronous tshark capture session.

**Request**:
```json
{
  "interface": "veth2",
  "capture_filter": "tcp port 443",
  "filename": "test1",
  "duration_seconds": 30
}
```

- `capture_filter`: tcpdump-style filter (optional, default captures all traffic)
- `duration_seconds`: optional auto-stop timeout

**Response** (200 OK):
```json
{
  "capture_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "started",
  "pcap_path": "/home/netreplica/config/captures/test1.pcap",
  "interface": "veth2",
  "capture_filter": "tcp port 443"
}
```

Use the returned `capture_id` to poll or stop the session.

---

### 5. Check Capture Status (GET /capture/{capture_id})

**Response** (200 OK):
```json
{
  "capture_id": "...",
  "status": "running",
  "pcap_path": "/home/netreplica/config/captures/test1.pcap",
  "interface": "veth2",
  "capture_filter": "tcp port 443",
  "start_time": "2026-03-25T10:00:00",
  "exit_code": null
}
```

`status` transitions to `"finished"` when tshark exits (duration elapsed or stopped).

---

### 6. Stop Capture (DELETE /capture/{capture_id})

Gracefully terminates tshark; PCAP file is retained on disk.

**Response** (200 OK):
```json
{
  "capture_id": "...",
  "status": "stopped"
}
```

---

### 7. Replay CTP Traffic (POST /replay)

Start bidirectional CTP background traffic replay. Two `tcpreplay-edit` processes are launched simultaneously:
- **Download** (incoming): `CTP_DIR/download/<ctp_file>.pcap` injected from `ns2` on `veth3`
- **Upload** (outgoing): `CTP_DIR/upload/<ctp_file>.pcap` injected from `ns1` on `veth1`

**Request**:
```json
{
  "ctp_file": "cluster26_tree10_profile424",
  "duration_seconds": 60,
  "pnat": "169.231.0.0/16:172.16.1.1,128.111.0.0/16:172.16.1.1"
}
```

- `ctp_file`: base filename (without direction prefix or `.pcap`). Both `CTP_DIR/download/<ctp_file>.pcap` and `CTP_DIR/upload/<ctp_file>.pcap` must exist.
- `pnat`: required IP rewrite rule mapping internal subnets to the target client IP — passed to `tcpreplay-edit --pnat`
- `duration_seconds`: auto-stop both directions after N seconds (optional)

**Response** (200 OK):
```json
{
  "replay_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "started",
  "ctp_file": "cluster26_tree10_profile424",
  "pnat": "169.231.0.0/16:172.16.1.1,128.111.0.0/16:172.16.1.1"
}
```

---

### 8. Check Replay Status (GET /replay/{replay_id})

**Response** (200 OK):
```json
{
  "replay_id": "...",
  "status": "running",
  "ctp_file": "cluster26_tree10_profile424",
  "pnat": "169.231.0.0/16:172.16.1.1,128.111.0.0/16:172.16.1.1",
  "start_time": "2026-03-25T10:00:00"
}
```

`status` is `"running"` if either direction is still active; `"finished"` when both are done.

---

### 9. Stop Replay (DELETE /replay/{replay_id})

**Response** (200 OK):
```json
{
  "replay_id": "...",
  "status": "stopped"
}
```

**Error Codes**: 400 Bad Request, 404 Not Found, 422 Validation Error, 500 Internal Server Error

---

### 10. Fetch CTP PCAPs (POST /ctp/fetch)

Fetch the download and upload PCAP files for a CTP pointer and place them in the expected directory structure under `CTP_DIR`:

```
CTP_DIR/
  download/<name>.pcap
  upload/<name>.pcap
```

Both directories are created if they do not exist. After a successful fetch, the resolved `ctp_file` base name can be passed directly to `POST /replay`.

**Request**:
```json
{
  "ctp_pointer": "http://ctp-service:8001/ctps/abc123",
  "ctp_root": null
}
```

`ctp_pointer` formats:

| Format | Example | Behavior |
|--------|---------|----------|
| URL | `http://ctp-service:8001/ctps/abc123` | Fetches `?direction=download` and `?direction=upload` via HTTP streaming |
| Absolute path | `/mnt/md0/ctp/download/cluster0_tree1.pcap` | Copies both files; upload path derived by replacing `/download/` with `/upload/` |
| Plain name | `cluster0_tree1_profile1` | Verifies both files are already present in `CTP_DIR` (no fetch) |

`ctp_root`: override the worker's `CTP_DIR` for this request (optional, defaults to `CTP_DIR` env var).

**Response** (200 OK):
```json
{
  "status": "ok",
  "name": "abc123",
  "download_path": "/mnt/md0/ctp_test/download/abc123.pcap",
  "upload_path": "/mnt/md0/ctp_test/upload/abc123.pcap",
  "fetched": true
}
```

`fetched` is `false` when files were already present (plain-name pointer or idempotent re-fetch of same-size files).

**Error Codes**: 404 when a local source file is missing; 502 when an HTTP fetch fails.

**Implementation**: `app/ctp_fetcher.py` — `fetch_ctp(ctp_pointer, ctp_root)`.

---

## Data Models

### ShapeRequest
```python
upstream_iface: str
downstream_iface: str
download_mbps: float          # Must be > 0
upload_mbps: float            # Must be > 0
latency_ms: float             # Must be >= 0, default 0
latency_location: Optional[Literal["upstream", "downstream", "both"]]
qdisc: str                    # Default "pfifo"
buffer_packets: int           # >= 1, default 1000
qdisc_params: Optional[Dict[str, str]]
```

### BottleneckState
```python
download_mbps: float
upload_mbps: float
latency_ms: float
latency_location: Optional[str]
qdisc: str
verified: bool                # True if iperf3+ping verification passed
buffer_packets: int           # Default 1000
qdisc_params: Optional[Dict[str, str]]
loss_rate_percent: float      # Default 0.0
verification_log: List[str]   # Detailed verification output
```

### CaptureRequest
```python
interface: str
capture_filter: str           # Default ""
filename: str                 # Non-empty; basename-sanitized
duration_seconds: Optional[int]
```

### ReplayRequest
```python
ctp_file: str                 # Base name; resolves to CTP_DIR/download/<name>.pcap and CTP_DIR/upload/<name>.pcap
pnat: str                     # Required: "src_net:dst_ip[,...]" passed to tcpreplay-edit --pnat
duration_seconds: Optional[int]
```

### CtpFetchRequest
```python
ctp_pointer: str              # URL, absolute path, or plain base name identifying the CTP
ctp_root: Optional[str]       # Override CTP_DIR for this request; defaults to CTP_DIR env var
```

### CtpFetchResponse
```python
status: str                   # "ok"
name: str                     # Resolved base name (no .pcap suffix)
download_path: str            # Absolute path: <ctp_root>/download/<name>.pcap
upload_path: str              # Absolute path: <ctp_root>/upload/<name>.pcap
fetched: bool                 # True if files were downloaded/copied; False if already present
```

## Implementation Notes

### Linux Traffic Control (tc)

The worker builds an HTB hierarchy with a child qdisc:

```bash
# HTB root + bandwidth class
tc qdisc replace dev veth2 root handle 1: htb default 10
tc class add dev veth2 parent 1: classid 1:10 htb rate 100mbit ceil 100mbit

# Queue management (applied as HTB leaf)
tc qdisc add dev veth2 parent 1:10 handle 10: fq_codel limit 1000 target 5ms interval 100ms

# Latency via netem (in namespace)
ip netns exec ns1 tc qdisc add dev veth1 root netem delay 50ms
```

### Qdisc Parameter Rules

| Qdisc family | buffer_packets behavior | qdisc_params |
|---|---|---|
| `pfifo`, `bfifo`, `pfifo_fast`, `sfq` | Sets `limit` | Cannot include `"limit"` key |
| `fq_codel`, `codel` | Ignored | Can include `"limit"`, `"target"`, `"interval"`, etc. |

### Verification

After applying shaping rules, the worker runs:
- **iperf3** upload and download tests (3 second duration, ±20% tolerance)
- **ping** RTT measurement (±10ms tolerance)

Results are logged in `verification_log` and summarized in `verified`.

### Privilege Elevation

The container runs privileged. For non-privileged deployments, configure sudoers:

```
# /etc/sudoers.d/substrate-worker
substrate-worker ALL=(ALL) NOPASSWD: /sbin/tc
substrate-worker ALL=(ALL) NOPASSWD: /usr/bin/tshark
substrate-worker ALL=(ALL) NOPASSWD: /usr/bin/tcpreplay
substrate-worker ALL=(ALL) NOPASSWD: /usr/bin/tcpreplay-edit
```

## Docker Configuration

The Dockerfile copies paths relative to the repo root, so **build from the repository root**.

### Build

```bash
cd agentic-thin-waist/
sudo docker build -t substrate-worker -f services/substrate-worker/Dockerfile .
```

### Run (detached)

```bash
sudo docker run -d \
  --name substrate-worker \
  --privileged \
  --cap-add=NET_ADMIN \
  --cap-add=SYS_ADMIN \
  --sysctl net.ipv4.ip_forward=1 \
  -p 8002:8002 \
  -v /home/netreplica/config/captures:/home/netreplica/config/captures \
  -v /home/netreplica/config/ctp:/home/netreplica/config/ctp \
  -e CAPTURE_DIR=/home/netreplica/config/captures \
  -e CTP_DIR=/home/netreplica/config/ctp \
  substrate-worker
```

### Docker Compose

```yaml
substrate-worker:
  build:
    context: .
    dockerfile: services/substrate-worker/Dockerfile
  container_name: substrate-worker
  privileged: true
  cap_add:
    - NET_ADMIN
    - SYS_ADMIN
  sysctls:
    - net.ipv4.ip_forward=1
  ports:
    - "8002:8002"
  volumes:
    - /home/netreplica/config/captures:/home/netreplica/config/captures
    - /home/netreplica/config/ctp:/home/netreplica/config/ctp
  environment:
    - CAPTURE_DIR=/home/netreplica/config/captures
    - CTP_DIR=/home/netreplica/config/ctp
```

## Usage Examples

### Shape the network

```bash
curl -X POST http://localhost:8002/shape \
  -H "Content-Type: application/json" \
  -d '{
    "upstream_iface": "veth4",
    "downstream_iface": "veth2",
    "download_mbps": 100.0,
    "upload_mbps": 100.0,
    "latency_ms": 50.0,
    "latency_location": "both",
    "qdisc": "fq_codel",
    "buffer_packets": 1000,
    "qdisc_params": {
      "target": "5ms",
      "interval": "100ms"
    }
  }'
```

### Check current bottleneck state

```bash
curl http://localhost:8002/state
```

### Health check

```bash
curl http://localhost:8002/health
```

### Capture packets

```bash
curl -X POST http://localhost:8002/capture \
  -H "Content-Type: application/json" \
  -d '{
    "duration": 10,
    "prefix": "test1",
    "upstream_iface": "veth4",
    "downstream_iface": "veth2"
  }'
```

Poll capture status:
```bash
curl http://localhost:8002/capture/{capture_id}
```

Stop capture:
```bash
curl -X DELETE http://localhost:8002/capture/{capture_id}
```

### Replay CTP background traffic

Launches download (ns2→veth3) and upload (ns1→veth1) simultaneously:

```bash
curl -X POST http://localhost:8002/replay -H "Content-Type: application/json" -d '{"ctp_file":"cluster26_tree10_profile424","pnat":"169.231.0.0/16:172.16.1.1,128.111.0.0/16:172.16.1.1","duration_seconds":60}'
```

Poll replay status:
```bash
curl http://localhost:8002/replay/{replay_id}
```

Stop replay:
```bash
curl -X DELETE http://localhost:8002/replay/{replay_id}
```

### YouTube MVP Example

For YouTube at 100 Mbps with 50ms latency under fq_codel:

```bash
# 1. Shape the bottleneck
curl -X POST http://localhost:8002/shape \
  -H "Content-Type: application/json" \
  -d '{"upstream_iface":"veth4","downstream_iface":"veth2","download_mbps":100.0,"upload_mbps":100.0,"latency_ms":50.0,"latency_location":"both","qdisc":"fq_codel"}'

# 2. Start packet capture
curl -X POST http://localhost:8002/capture \
  -H "Content-Type: application/json" \
  -d '{"interface":"veth2","capture_filter":"tcp port 443","filename":"youtube_100mbps"}'

# 3. Inject background traffic
curl -X POST http://localhost:8002/replay \
  -H "Content-Type: application/json" \
  -d '{"ctp_file":"youtube_background","interface":"veth1","rate":"100","duration_seconds":60}'

# 4. Verify bottleneck state
curl http://localhost:8002/state
```

Success criteria: `bottleneck_state.verified == true`, measured throughput within ±20% of target, measured RTT within ±10ms of configured latency.

## Testing

> Unit tests live in `services/substrate-worker/tests/`. Run from repo root:

```bash
pytest services/substrate-worker/tests/ -v
```

**Unit tests** cover: qdisc argument building, Pydantic model validation, health caching, state endpoint behavior, netem latency placement, capture/replay lifecycle, qdisc_params conflict detection.

**Integration tests** cover: live tc execution, tshark pcap generation, tcpreplay injection, bandwidth and latency verification within tolerance, concurrent replay sessions, error paths.

**Performance targets**: POST /shape < 500ms (excluding iperf3 verification), POST /capture < 100ms, POST /replay < 200ms, GET /state < 50ms, GET /health < 100ms.

## Key Responsibilities

- **Translate specifications into tc commands**: Convert BottleneckState into HTB + child qdisc configurations
- **Enforce bottleneck regimes**: Apply both static attributes (tc) and dynamic pressure (tcpreplay)
- **Verify configuration state**: Run iperf3 and ping after shaping; set `BottleneckState.verified`
- **Capture and replay traffic**: Lifecycle management for tshark and tcpreplay sessions
- **Report health and status**: Expose dependency checks and cached bottleneck state

## References

- Linux tc (traffic control): https://man7.org/linux/man-pages/man8/tc.8.html
- HTB qdisc: https://tldp.org/HOWTO/Traffic-Control-HOWTO/classful-qdiscs.html
- tshark (Wireshark CLI): https://www.wireshark.org/docs/man-pages/tshark.html
- tcpreplay: https://tcpreplay.appneta.com/
- Linux queue disciplines: https://tldp.org/HOWTO/Traffic-Control-HOWTO/
- Docker privileged containers: https://docs.docker.com/engine/reference/run/#runtime-privilege-and-linux-capabilities

---

**Project**: Agentic Thin Waist (NetForge Service)
**PI**: Prof. Arpit Gupta
**Lead**: Jaber
**Last Updated**: 2026-03-25
**Status**: Active Development
