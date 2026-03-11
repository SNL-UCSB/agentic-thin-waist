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
- BottleneckState specifications: download/upload capacity (Mbps), latency (ms), queue discipline, buffer depth
- Network interface assignments: upstream/downstream interfaces, delay interface
- CTP replay sessions: replay-ready PCAP files (from CTP Service), replay rates, hybrid mode configuration
- Packet capture filters: interface, tcpdump filter syntax, output directory
- Configuration: network namespace, capture directory path

## Output

Substrate Worker produces:
- BottleneckState verification results: verified boolean, measured capacity, measured RTT
- tc qdisc command outputs confirming kernel module load
- PCAP files from packet capture at specified interface
- tcpreplay session metrics: packets replayed, actual rate achieved
- Status reports: interface configuration, qdisc state, available tc modules

## Interfaces

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/shape` | POST | Configure bottleneck regime (tc qdisc rules) |
| `/capture` | POST | Start packet capture with tshark |
| `/replay` | POST | Start CTP traffic replay via tcpreplay |
| `/state` | GET | Get current bottleneck configuration and verification |
| `/health` | GET | Health check: privileges, tc availability, qdisc support |

## YouTube MVP Example

For YouTube at 10/25/50 Mbps with 50ms latency under CUBIC:
- /shape: Apply tc rules to eth0 for each capacity (tbf rate + fq_codel, netem delay 50ms)
- /capture: Start tshark on eth0, capture filter "tcp port 443"
- /replay: Start tcpreplay with scaled CTP at each bottleneck rate
- /state: Verify bottleneck_state.verified=True, measured_throughput within ±5% of target
- Success criteria: all 3 capacity regimes verify, tc modules load, measured throughput matches config within tolerance

## Core Concepts

**Bottleneck Regime**: A complete network condition specification with two components:

1. **Static Attributes** (configured via tc):
   - Capacity (bandwidth shaping)
   - Base latency (propagation delay)
   - Buffering (queue depth)
   - Queue management policy (AQM: FIFO, fq_codel, prio, etc.)

2. **Dynamic Pressure** (replayed via tcpreplay):
   - CTP (Common Traffic Pattern) background traffic
   - Hybrid replay model: background traffic open-loop, target application fully reactive
   - Captures contention and packet interaction effects

The worker must verify that configured shaping matches the intended specification via `BottleneckState.verified`.

## Deployment Modes

**Standalone**: Single host using Linux namespaces, bridges, and traffic control.

**Distributed** (three-server topology):
- **Server A**: Client applications and traffic sources
- **Server B**: Bottleneck with tc/LibreQoS enforcement (packet shaping layer)
- **Server C**: Application endpoints and NAT

NetForge provides `NAT()` and `Tunnel()` abstractions for connectivity beyond the testbed.

## Architecture

```
┌──────────────────────────────────┐
│  Experiment API                  │
│  (Intent Plane Orchestration)    │
└────────────┬──────────────────────┘
             │
             │ POST /shape (BottleneckState)
             │ POST /capture
             │ POST /replay
             │ GET /state, /health
             ▼
┌──────────────────────────────────┐
│  SUBSTRATE WORKER (8002)         │
│  EXECUTION PLANE                 │
│  ┌──────────────────────────┐    │
│  │ TC Executor              │    │
│  │ (qdisc, filter, class)   │    │
│  ├──────────────────────────┤    │
│  │ Packet Capture (tshark)  │    │
│  ├──────────────────────────┤    │
│  │ CTP Replay (tcpreplay)   │    │
│  ├──────────────────────────┤    │
│  │ State Verification       │    │
│  │ (verified bool)          │    │
│  └──────────────────────────┘    │
└────────────┬─────────────────────┘
             │
             │ tc commands
             │ tshark capture
             │ tcpreplay stream
             ▼
        ┌─────────────────┐
        │ Linux Kernel    │
        │ tc qdisc stack  │
        │ LibreQoS/XDP    │
        └─────────────────┘
```

### Dependencies

- **CTP Service** (Port 8001): Provides replay-ready PCAP data via `GET /ctps/{id}/replay-data`. The Substrate Worker does not perform CTP algebra — it receives pre-processed PCAP and replays it via tcpreplay.
- **Experiment API** (Port 8000): Dispatches configuration, replay, and capture commands. The Experiment API orchestrates the sequencing of Substrate Worker operations.

## Configuration Requirements

The worker requires a `NetReplicaConfig` object with the following fields:

- `capture_dir`: Directory for pcap files (replaces hardcoded `/home/jaber/captures/`)
- `upstream_iface`: Ingress interface (e.g., `eth0`)
- `downstream_iface`: Egress interface (e.g., `eth1`)
- `delay_iface`: Interface for delay application (optional)
- `namespace`: Network namespace name (for isolated testbeds)
- `ctp_dir`: Directory containing CTP traffic patterns for tcpreplay

**Critical Security Notes**:
- Remove hardcoded passwords and paths from the codebase
- Use sudoers configuration for tc/tshark privilege elevation
- Run as a privileged Docker container with `CAP_NET_ADMIN` capability
- Never commit credentials to version control

## API Specification

### 1. Shape Network (POST /shape)

Configure bottleneck regime on target interfaces.

**Request**:
```json
{
  "upstream_iface": "eth0",
  "downstream_iface": "eth1",
  "download_mbps": 10.0,
  "upload_mbps": 5.0,
  "latency_ms": 50,
  "qdisc": "fq_codel",
  "buffer_packets": 1000
}
```

**Response** (200 OK):
```json
{
  "status": "shaped",
  "bottleneck_state": {
    "download_mbps": 10.0,
    "upload_mbps": 5.0,
    "latency_ms": 50,
    "qdisc": "fq_codel",
    "verified": true
  },
  "applied_commands": [
    "tc qdisc replace dev eth0 root handle 1: tbf rate 10mbit burst 15k latency 50ms",
    "tc qdisc add dev eth0 parent 1: handle 10: fq_codel limit 1000"
  ]
}
```

---

### 2. Packet Capture (POST /capture)
Start tshark: `{interface, capture_filter, filename}` → `{capture_id, status, pcap_path}`

### 3. Replay CTP (POST /replay)
Replay traffic: `{ctp_file, interface, rate, loop, duration_seconds}` → `{replay_id, status, packets_replayed}`

### 4. Get State (GET /state)
Retrieve bottleneck config: `{download_mbps, upload_mbps, latency_ms, qdisc, verified}`

### 5. Health Check (GET /health)
Worker status: `{status, root_privileges, tc_available, tshark_available, tcpreplay_available, interfaces}`

**Error Codes**: 400 Bad Request, 403 Forbidden, 500 Internal Server Error, 503 Service Unavailable

## Dataclass Contracts

```python
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class BottleneckState:
    """Static and dynamic network configuration with verification."""
    download_mbps: float          # Downstream capacity (bits/s)
    upload_mbps: float            # Upstream capacity (bits/s)
    latency_ms: float             # Base propagation latency
    qdisc: str                    # Queue discipline (tbf, fq_codel, prio, etc.)
    verified: bool = False        # Verification passed: config matches measurement
    buffer_packets: int = 1000    # Queue depth for AQM
    loss_rate_percent: float = 0.0  # Packet loss injection (optional)

@dataclass
class SubstrateStatus:
    """Worker health and operational status."""
    status: str                   # "healthy" or "degraded"
    root_privileges: bool         # Can execute tc/tshark
    tc_available: bool            # tc command available
    tshark_available: bool        # tshark command available
    tcpreplay_available: bool     # tcpreplay command available
    qdisc_support: bool           # Kernel supports requested qdisc
    interfaces: List[str]         # Available network interfaces
    timestamp: str                # ISO 8601 timestamp

@dataclass
class NetReplicaConfig:
    """Configuration for substrate worker (replaces hardcoded paths)."""
    capture_dir: str              # Directory for pcap files
    upstream_iface: str           # Ingress interface (e.g., eth0)
    downstream_iface: str         # Egress interface (e.g., eth1)
    delay_iface: Optional[str]    # Interface for delay application
    namespace: Optional[str]      # Network namespace (isolated testbed)
    ctp_dir: str                  # Directory with CTP traffic patterns

@dataclass
class CTPReplaySession:
    """Traffic replay metadata."""
    replay_id: str                # Unique replay identifier
    ctp_file: str                 # CTP pcap filename
    interface: str                # Target interface
    rate: str                     # Replay rate (e.g., "10M", "50K")
    loop: bool = False            # Repeat indefinitely
    start_time: str = ""          # ISO 8601 timestamp
    packets_replayed: int = 0     # Count during active replay
```

## Implementation Notes

### Linux Traffic Control (tc)

The worker translates bottleneck specifications into tc commands:

```bash
# Basic traffic shaping (TBF: Token Bucket Filter)
tc qdisc replace dev eth0 root handle 1: tbf \
  rate 10mbit burst 15k latency 50ms

# Queue management (fq_codel: Fair Queuing + CoDel AQM)
tc qdisc add dev eth0 parent 1: handle 10: fq_codel \
  limit 1000 target 5ms interval 100ms

# Latency (netem: Network Emulation)
tc qdisc add dev eth0 root netem delay 50ms
```

### Packet Capture and CTP Replay

- **tshark**: Captures packets with optional filtering for analysis
- **tcpreplay**: Replays CTPs (background traffic) from pcap files
- **Hybrid Model**: Background traffic open-loop (replay-based), target application fully reactive (measures real contention effects)

### Privilege Elevation

Configure sudoers to allow the worker process tc and tshark execution:

```
# /etc/sudoers.d/substrate-worker
substrate-worker ALL=(ALL) NOPASSWD: /sbin/tc
substrate-worker ALL=(ALL) NOPASSWD: /usr/bin/tshark
substrate-worker ALL=(ALL) NOPASSWD: /usr/bin/tcpreplay
```

Never hardcode passwords in configuration files.

## Testing and Validation

> **Unit tests for this service live in `services/substrate-worker/tests/`.** Run them with `pytest services/substrate-worker/tests/ -v`.

**Unit Tests**: BottleneckState/SubstrateStatus dataclass parsing, parameter range checks, interface validation, CTP path resolution.

**Integration Tests**: tc command execution (±5% capacity/latency tolerance), tshark pcap generation, tcpreplay injection at specified rate, BottleneckState.verified state accuracy.

**Performance Targets**: POST /shape < 500ms, POST /capture < 100ms, POST /replay < 200ms, GET /state < 50ms, GET /health < 100ms.

## Docker Configuration
The Dockerfile executes `setup.sh` and runs the service on port 8002.

### Build and Run

Navigate to the service directory and build the image:

```bash
cd agentic-thin-waist/services/substrate-worker
sudo docker build -t substrate-worker .
```

Run the container with the required privileges and volume mounts:

```bash
sudo docker run -it \
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
 
**Dockerfile**:
```dockerfile
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 python3-pip python-is-python3 \
    tshark iputils-ping iproute2 \
    net-tools iperf3 \
    curl wget iptables byobu nano \
    speedtest-cli tcpreplay \
    python3-flask python3-requests \
    sudo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY . .


EXPOSE 8002

CMD ["bash", "-lc", "cd app && chmod +x setup.sh && ./setup.sh && uvicorn main:app --host 0.0.0.0 --port 8002"]
```

**Docker Compose**:
```yaml
substrate-worker:
  build: ./services/substrate-worker
  container_name: substrate-worker
  privileged: true
  cap_add:
    - NET_ADMIN
    - SYS_ADMIN
  ports:
    - "8002:8002"
  volumes:
    - /home/config/captures:/home/config/captures
    - /home/config/ctp:/home/config/ctp
  environment:
    - CAPTURE_DIR=/home/config/captures
    - CTP_DIR=/home/config/ctp
    - UPSTREAM_IFACE=eth0
    - DOWNSTREAM_IFACE=eth1
```

## Key Responsibilities

- **Translate specifications into tc commands**: Convert BottleneckState into operational qdisc configurations
- **Enforce bottleneck regimes**: Apply both static attributes and dynamic pressure (CTP replay)
- **Verify configuration state**: Ensure BottleneckState.verified reflects actual network behavior
- **Capture and replay traffic**: Provide hooks for experiment analysis and load injection
- **Report health and status**: Enable orchestration layer visibility into execution plane state

## References

- Linux tc (traffic control): https://man7.org/linux/man-pages/man8/tc.8.html
- tshark (Wireshark CLI): https://www.wireshark.org/docs/man-pages/tshark.html
- tcpreplay: https://tcpreplay.appneta.com/
- Linux queue disciplines: https://tldp.org/HOWTO/Traffic-Control-HOWTO/
- Docker privileged containers: https://docs.docker.com/engine/reference/run/#runtime-privilege-and-linux-capabilities

---

**Project**: Agentic Thin Waist (NetForge Service)
**PI**: Prof. Arpit Gupta
**Lead**: Jaber
**Last Updated**: 2026-03-05
**Status**: Specification Complete — Ready for Implementation
