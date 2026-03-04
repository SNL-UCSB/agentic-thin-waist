# Substrate Worker Service

**Port**: 8002
**Deliverable**: D1 (Network Virtualization Substrate - Execution Plane)
**Priority**: CRITICAL
**Status**: To be implemented

## Purpose

The Substrate Worker is the execution layer that applies network conditions to the data plane using Linux kernel capabilities. It operates with elevated privileges (CAP_NET_ADMIN, privileged mode) to use `tc` for traffic control and `tshark`/`tcpdump` for packet capture. The Substrate Worker:

1. **Applies network configurations** — Execute tc qdisc commands from CTP Service
2. **Captures network traffic** — Collect pcap files via tshark
3. **Measures bottleneck state** — Verify applied network conditions match configuration
4. **Manages interface state** — Reset and clean up after experiments
5. **Provides real-time telemetry** — Report throughput, RTT, packet loss metrics

This service runs in the data plane (could be the same machine or remote infrastructure) and has privileged access to network interfaces.

## Architecture

```
┌──────────────────────────────┐
│  Experiment API (8000)       │
│  or CTP Service (8001)       │
└────────────┬─────────────────┘
             │ POST /workers/configure
             │ POST /workers/capture/start
             ▼
┌──────────────────────────────┐
│  SUBSTRATE WORKER (8002)     │
│  Privileged Process (root)   │
│  ┌────────────────────────┐  │
│  │ tc Executor            │  │
│  │ tshark/tcpdump         │  │
│  │ iperf3 / ping client   │  │
│  │ telemetry collector    │  │
│  └────────────────────────┘  │
└──────────────┬────────────────┘
               │ tc commands
               │ pcap files
               ▼
        ┌──────────────────┐
        │ Linux Kernel     │
        │ eth0/eth1/...    │
        │ tc qdisc         │
        └──────────────────┘
```

## API Specification

### 1. Configure Network Interface

**Endpoint**: `POST /workers/configure`

**Request**:
```json
{
  "interface": "eth0",
  "tc_commands": [
    "tc qdisc replace dev eth0 root handle 1: tbf rate 10mbit burst 15k latency 50ms",
    "tc qdisc add dev eth0 parent 1: handle 10: fifo limit 1000"
  ]
}
```

**Response** (200 OK):
```json
{
  "interface": "eth0",
  "configuration_applied": true,
  "verification": {
    "configured_capacity": 10.0,
    "configured_latency": 50,
    "measured_throughput": 9.8,
    "measured_rtt": 52,
    "verification_passed": true
  },
  "timestamp": "2026-03-04T10:00:00Z"
}
```

**Error Codes**:
- 400 Bad Request — invalid interface or malformed commands
- 500 Internal Server Error — tc execution failed
- 503 Service Unavailable — required tools unavailable

---

### 2. Get Network Status

**Endpoint**: `GET /workers/status`

**Query Parameters**:
- `interface` — specific interface (default: eth0)

**Response** (200 OK):
```json
{
  "interface": "eth0",
  "configured": true,
  "current_config": {
    "capacity_mbps": 10.0,
    "latency_ms": 50,
    "aqm_policy": "fifo"
  },
  "current_metrics": {
    "throughput_mbps": 9.8,
    "rtt_ms": 52,
    "packet_loss_percent": 0.0,
    "jitter_ms": 1.2,
    "tx_packets": 10245,
    "rx_packets": 10198,
    "tx_errors": 0,
    "rx_errors": 0
  },
  "interfaces_available": ["eth0", "eth1", "docker0"]
}
```

---

### 3. Start Packet Capture

**Endpoint**: `POST /workers/capture/start`

**Request**:
```json
{
  "interface": "eth0",
  "capture_filter": "",
  "output_format": "pcap",
  "max_packet_bytes": 0
}
```

**Response** (200 OK):
```json
{
  "capture_id": "capture-abc123",
  "interface": "eth0",
  "status": "capturing",
  "start_time": "2026-03-04T10:00:00Z",
  "pcap_path": "/tmp/captures/capture-abc123.pcap"
}
```

**Supported Filters**:
- Empty string "" → capture all packets
- "tcp" → TCP packets only
- "port 80 or port 443" → HTTP/HTTPS
- "ip src 192.168.1.100" → traffic from specific IP

---

### 4. Stop Packet Capture

**Endpoint**: `POST /workers/capture/stop`

**Request**:
```json
{
  "capture_id": "capture-abc123",
  "move_to": "/data/pcaps/experiment-001.pcap"
}
```

**Response** (200 OK):
```json
{
  "capture_id": "capture-abc123",
  "status": "stopped",
  "stop_time": "2026-03-04T10:00:30Z",
  "duration_seconds": 30,
  "packets_captured": 5240,
  "bytes_captured": 3567890,
  "pcap_path": "/data/pcaps/experiment-001.pcap",
  "file_size_mb": 3.4
}
```

---

### 5. Get Real-time Metrics

**Endpoint**: `GET /workers/metrics`

**Query Parameters**:
- `interface` — network interface (default: eth0)
- `duration_seconds` — measurement duration (default: 10)

**Response** (200 OK):
```json
{
  "interface": "eth0",
  "measurement_duration": 10,
  "metrics": {
    "throughput_mbps": 9.8,
    "throughput_stddev_mbps": 0.3,
    "rtt_ms": 51.5,
    "rtt_stddev_ms": 1.2,
    "packet_loss_percent": 0.0,
    "jitter_ms": 1.5,
    "tx_packets": 10245,
    "rx_packets": 10198,
    "tx_errors": 0,
    "rx_errors": 0,
    "tx_dropped": 0,
    "rx_dropped": 0
  },
  "measurement_start": "2026-03-04T10:00:00Z",
  "measurement_end": "2026-03-04T10:00:10Z"
}
```

---

### 6. Reset Network Configuration

**Endpoint**: `POST /workers/reset`

**Request**:
```json
{
  "interface": "eth0",
  "force": false
}
```

**Response** (200 OK):
```json
{
  "interface": "eth0",
  "reset_status": "success",
  "timestamp": "2026-03-04T10:00:35Z"
}
```

---

### 7. Health Check

**Endpoint**: `GET /health`

**Response** (200 OK):
```json
{
  "status": "healthy",
  "checks": {
    "root_privileges": true,
    "tc_available": true,
    "tshark_available": true,
    "iperf3_available": true,
    "ping_available": true,
    "docker_socket": true,
    "kernel_version": "6.8.0-94-generic"
  }
}
```

## Dataclass Contracts

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

@dataclass
class BottleneckState:
    """Measured network configuration state."""
    configured_capacity: float
    configured_latency: float
    measured_throughput: float
    measured_rtt: float
    packet_loss_percent: float = 0.0
    jitter_ms: float = 0.0
    verification_passed: bool = True

@dataclass
class TelemetrySnapshot:
    """Point-in-time network metrics."""
    timestamp: str
    interface: str
    throughput_mbps: float
    rtt_ms: float
    packet_loss_percent: float
    jitter_ms: float
    tx_packets: int
    rx_packets: int
    tx_bytes: int
    rx_bytes: int
    tx_errors: int
    rx_errors: int

@dataclass
class CaptureSession:
    """Packet capture metadata."""
    capture_id: str
    interface: str
    pcap_path: str
    start_time: str
    stop_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    packets_captured: int = 0
    bytes_captured: int = 0
    status: str = "capturing"  # capturing, stopped, archived

@dataclass
class NetworkConfiguration:
    """Applied network configuration."""
    interface: str
    capacity_mbps: float
    latency_ms: float
    loss_rate: float
    aqm_policy: str
    applied_at: str
    tc_commands: List[str] = field(default_factory=list)
```

## Service Dependencies

| Service | Endpoint | Purpose |
|---------|----------|---------|
| Storage Service | POST /artifacts | Store pcap files |

## Testing Criteria

### Unit Tests
- Command parsing and validation
- Interface name validation
- CTP parameter range checks

### Integration Tests (requires root and Linux)
- tc commands successfully apply to test interface
- Throughput measurements match configured capacity (±5%)
- RTT measurements match configured latency (±5%)
- Packet capture starts and stops correctly
- Captured pcap file is valid (can be opened with Wireshark)
- Reset clears all qdisc configurations
- Multiple captures can run sequentially

### Performance Tests
- Configure interface < 500ms
- Start capture < 100ms
- Stop capture and write pcap < 1s
- Get metrics < 2s (includes 10s measurement)

## Implementation Guide

### Step 1: Docker Setup
The container must run with:
```dockerfile
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    iproute2 \
    iputils-ping \
    iperf3 \
    tshark \
    tcpdump \
    python3-flask \
    python3-requests

WORKDIR /app
COPY . .
CMD ["python3", "-m", "flask", "run", "--host=0.0.0.0"]
```

Docker Compose should use:
```yaml
substrate-worker:
  privileged: true
  cap_add:
    - NET_ADMIN
    - SYS_ADMIN
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
```

### Step 2: Project Structure
```bash
services/substrate-worker/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── workers.py
│   ├── executor/
│   │   ├── __init__.py
│   │   ├── tc_executor.py      # Run tc commands
│   │   ├── capture.py          # tshark wrapper
│   │   ├── metrics.py          # iperf3/ping runner
│   │   └── subprocess_safe.py  # Safe subprocess execution
│   ├── models/
│   │   └── __init__.py
│   └── utils/
│       ├── __init__.py
│       └── logging.py
└── tests/
    ├── __init__.py
    └── test_*.py
```

### Step 3: tc Executor
```python
# app/executor/tc_executor.py
import subprocess
import logging

class TCExecutor:
    def execute(self, commands: List[str]) -> Tuple[bool, str]:
        """Execute tc commands."""
        try:
            for cmd in commands:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True,
                    timeout=10, check=True
                )
            return True, "OK"
        except subprocess.CalledProcessError as e:
            logging.error(f"tc command failed: {e}")
            return False, str(e)
```

### Step 4: Packet Capture
```python
# app/executor/capture.py
class PacketCapture:
    def start(self, interface: str, output_file: str) -> str:
        """Start tshark capture."""
        cmd = (
            f"tshark -i {interface} -w {output_file} "
            f"-b filesize:100000 -b files:10"
        )
        # Start in background, return capture_id
        proc = subprocess.Popen(
            cmd, shell=True, stdout=subprocess.PIPE
        )
        return capture_id

    def stop(self, capture_id: str) -> dict:
        """Stop tshark capture."""
        # Send SIGTERM to process
        # Wait for graceful shutdown
        # Return statistics
```

### Step 5: Metrics Collection
```python
# app/executor/metrics.py
class MetricsCollector:
    def measure_throughput(self, interface: str, duration: int) -> float:
        """Measure throughput with iperf3."""
        # Assumes iperf3 server is running elsewhere
        cmd = f"iperf3 -c {gateway} -i 1 -t {duration} -R"
        # Parse output, return throughput in Mbps

    def measure_rtt(self, interface: str, duration: int) -> float:
        """Measure RTT with ping."""
        cmd = f"ping -c {duration*10} 8.8.8.8"
        # Parse output, extract RTT statistics
```

### Step 6: API Endpoints
```python
# app/api/workers.py
from flask import Blueprint, request, jsonify
from app.executor.tc_executor import TCExecutor

workers_bp = Blueprint('workers', __name__)

@workers_bp.route('/workers/configure', methods=['POST'])
def configure():
    data = request.get_json()
    executor = TCExecutor()
    success, msg = executor.execute(data['tc_commands'])
    if success:
        return jsonify({"configuration_applied": True}), 200
    else:
        return jsonify({"error": msg}), 500
```

## References

- Linux tc qdisc: https://man7.org/linux/man-pages/man8/tc.8.html
- tshark: https://www.wireshark.org/docs/man-pages/tshark.html
- iperf3: https://software.es.net/iperf/
- Docker privileged mode: https://docs.docker.com/engine/reference/run/#runtime-privilege-and-linux-capabilities
- NetReplica tc integration: https://github.com/SNL-UCSB/netReplica

---

**Last Updated**: 2026-03-04
**Status**: Specification Ready
**Next Milestone**: Implementation (Week 1-2)
