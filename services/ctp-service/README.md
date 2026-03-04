# CTP Service

**Port**: 8001
**Deliverable**: D1 (Network Virtualization Substrate - Representation Plane)
**Priority**: CRITICAL
**Status**: To be implemented

## Purpose

The CTP (Capacity-Throughput Profile) Service is the network representation layer that translates high-level network conditions (capacity, latency, loss rate, AQM policy) into Linux kernel `tc` (traffic control) commands. It serves as a bridge between abstract research intents and concrete network configurations.

A CTP is a tuple: `(capacity_mbps, latency_ms, loss_rate, aqm_policy)` that completely specifies a network condition. The CTP Service:

1. **Validates CTPs** — Ensure parameters are physically feasible
2. **Compiles CTPs** — Translate to `tc qdisc` commands
3. **Manages presets** — Store and retrieve common network profiles
4. **Verifies state** — Confirm network matches configured CTP
5. **Supports algebra** — Compose, scale, and normalize CTPs

This service is infrastructure-agnostic but assumes Linux `tc` is available on the data plane.

## Architecture

```
┌──────────────────────────────┐
│   Experiment API (8000)      │
│   or External Client         │
└────────────┬─────────────────┘
             │ POST /ctps/validate
             │ POST /ctps/compile
             ▼
┌──────────────────────────────┐
│   CTP SERVICE (8001)         │
│  ┌────────────────────────┐  │
│  │ CTP Algebra Engine     │  │
│  │ - Validation           │  │
│  │ - Compilation          │  │
│  │ - Verification         │  │
│  └────────────────────────┘  │
└──────────────┬────────────────┘
               │ tc commands
               │ iperf3, ping for verification
               ▼
        ┌──────────────────┐
        │ Linux Kernel     │
        │ tc/qdisc         │
        │ network stack    │
        └──────────────────┘
```

## API Specification

### 1. Validate CTP

**Endpoint**: `POST /ctps/validate`

**Request**:
```json
{
  "capacity_mbps": 10.0,
  "latency_ms": 50,
  "loss_rate": 0.0,
  "aqm_policy": "fifo"
}
```

**Response** (200 OK):
```json
{
  "valid": true,
  "ctp_id": "ctp-001",
  "warnings": [],
  "compiled_commands": [
    "tc qdisc replace dev eth0 root handle 1: tbf rate 10mbit burst 15k latency 50ms",
    "tc qdisc add dev eth0 parent 1: handle 10: fifo limit 1000"
  ]
}
```

**Validation Rules**:
- `0 < capacity_mbps <= 10000` (Mbps)
- `0 <= latency_ms <= 10000` (ms)
- `0 <= loss_rate <= 1.0`
- `aqm_policy` in ["fifo", "codel", "pie", "fq_codel", "sfq"]

**Error Codes**:
- 200 OK + valid: false — warnings but no hard errors
- 400 Bad Request — invalid parameters

---

### 2. Compile CTP to tc Commands

**Endpoint**: `POST /ctps/compile`

**Request**:
```json
{
  "capacity_mbps": 25.0,
  "latency_ms": 30,
  "loss_rate": 0.001,
  "aqm_policy": "codel",
  "interface": "eth0"
}
```

**Response** (200 OK):
```json
{
  "interface": "eth0",
  "tc_commands": [
    "tc qdisc replace dev eth0 root handle 1: tbf rate 25mbit burst 31250b latency 30ms",
    "tc qdisc add dev eth0 parent 1: handle 10: codel target 5ms interval 100ms",
    "tc filter add dev eth0 parent 1: protocol ip prio 1 u32 match ip src 0.0.0.0/0 action netem loss 0.1%"
  ],
  "cleanup_commands": [
    "tc qdisc del dev eth0 root"
  ],
  "estimated_buffer_packets": 1024,
  "notes": "CoDel AQM requires kernel 3.5+. Verify with 'tc qdisc show dev eth0'"
}
```

**AQM Implementations**:

| AQM | tc qdisc | Description | Kernel Version |
|-----|----------|-------------|-----------------|
| fifo | fifo | FIFO queue, no active queue management | All |
| codel | codel | Controlled Delay, targets low latency | 3.5+ |
| pie | pie | Proportional Integral controller Enhanced | 4.0+ |
| fq_codel | fq_codel | Fair Queue + CoDel, per-flow queue | 3.11+ |
| sfq | sfq | Stochastic Fairness Queueing | 2.2+ |

---

### 3. Get CTP Presets

**Endpoint**: `GET /ctps/presets`

**Response** (200 OK):
```json
{
  "presets": [
    {
      "name": "broadband-50mbps",
      "capacity_mbps": 50,
      "latency_ms": 20,
      "loss_rate": 0.0,
      "aqm_policy": "codel",
      "description": "Typical home broadband (cable/fiber)"
    },
    {
      "name": "mobile-lte",
      "capacity_mbps": 15,
      "latency_ms": 100,
      "loss_rate": 0.001,
      "aqm_policy": "pie",
      "description": "LTE mobile network"
    },
    {
      "name": "mobile-5g",
      "capacity_mbps": 100,
      "latency_ms": 30,
      "loss_rate": 0.0,
      "aqm_policy": "codel",
      "description": "5G network"
    },
    {
      "name": "satellite",
      "capacity_mbps": 20,
      "latency_ms": 600,
      "loss_rate": 0.01,
      "aqm_policy": "fifo",
      "description": "Satellite internet (GEO)"
    },
    {
      "name": "dial-up",
      "capacity_mbps": 0.056,
      "latency_ms": 150,
      "loss_rate": 0.05,
      "aqm_policy": "fifo",
      "description": "Dial-up modem (for historical testing)"
    }
  ],
  "total": 5
}
```

---

### 4. Create CTP Preset

**Endpoint**: `POST /ctps/presets`

**Request**:
```json
{
  "name": "custom-profile",
  "capacity_mbps": 30,
  "latency_ms": 40,
  "loss_rate": 0.002,
  "aqm_policy": "codel",
  "description": "Custom research profile"
}
```

**Response** (201 Created):
```json
{
  "preset_id": "ctp-custom-001",
  "created_at": "2026-03-04T10:00:00Z"
}
```

---

### 5. Verify Network State

**Endpoint**: `POST /ctps/verify`

**Request**:
```json
{
  "interface": "eth0",
  "expected_capacity_mbps": 10.0,
  "expected_latency_ms": 50,
  "measurement_duration_seconds": 5,
  "tolerance_percent": 5
}
```

**Response** (200 OK):
```json
{
  "verification_passed": true,
  "measurements": {
    "throughput_mbps": 9.8,
    "throughput_error_percent": 2.0,
    "rtt_ms": 51.2,
    "rtt_error_percent": 2.4,
    "packet_loss_percent": 0.0,
    "jitter_ms": 1.5
  },
  "details": {
    "measured_via": "iperf3 + ping",
    "sample_count": 60,
    "measurement_start": "2026-03-04T10:00:00Z",
    "measurement_end": "2026-03-04T10:00:05Z"
  }
}
```

**Error Cases**:
- 400 Bad Request — interface doesn't exist
- 408 Request Timeout — measurement taking too long
- 422 Unprocessable Entity — network state doesn't match tolerance
- 503 Service Unavailable — iperf3 or ping unavailable

---

### 6. CTP Algebra Operations

**Endpoint**: `POST /ctps/algebra`

**Request** (scale operation):
```json
{
  "operation": "scale",
  "ctp": {
    "capacity_mbps": 10,
    "latency_ms": 50,
    "loss_rate": 0.0,
    "aqm_policy": "fifo"
  },
  "scale_factor": 2.5
}
```

**Response** (200 OK):
```json
{
  "result": {
    "capacity_mbps": 25.0,
    "latency_ms": 50,
    "loss_rate": 0.0,
    "aqm_policy": "fifo"
  },
  "operation": "scale",
  "note": "Only capacity scaled; latency and loss unchanged"
}
```

**Supported Operations**:
- `scale` — multiply capacity by factor (e.g., 2x slower = 0.5x capacity)
- `compose` — combine two CTPs (takes minimum capacity, maximum latency)
- `normalize` — ensure parameters are within bounds

---

### 7. Health Check

**Endpoint**: `GET /health`

**Response** (200 OK):
```json
{
  "status": "healthy",
  "kernel_version": "6.8.0-94-generic",
  "tc_available": true,
  "iperf3_available": true,
  "ping_available": true
}
```

## Dataclass Contracts

```python
from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum

class AQMPolicy(str, Enum):
    FIFO = "fifo"
    CODEL = "codel"
    PIE = "pie"
    FQ_CODEL = "fq_codel"
    SFQ = "sfq"

@dataclass
class NetReplicaConfig:
    """Network emulation configuration."""
    capacity_mbps: float
    latency_ms: float
    loss_rate: float = 0.0
    aqm_policy: AQMPolicy = AQMPolicy.FIFO
    buffer_size: Optional[int] = None  # bytes
    jitter_ms: float = 0.0

@dataclass
class BottleneckState:
    """Measured network state for verification."""
    configured_capacity: float
    configured_latency: float
    measured_throughput: float
    measured_rtt: float
    packet_loss_percent: float = 0.0
    jitter_ms: float = 0.0
    verification_passed: bool = True

@dataclass
class TCCommand:
    """Compiled tc qdisc command."""
    command: str
    description: str
    requires_root: bool = True

@dataclass
class CTPPreset:
    """Pre-defined network profile."""
    name: str
    capacity_mbps: float
    latency_ms: float
    loss_rate: float
    aqm_policy: AQMPolicy
    description: str
    created_at: Optional[str] = None
```

## Service Dependencies

None - this service is independent and doesn't call other services.

## Testing Criteria

### Unit Tests
- Validation passes/fails correctly for boundary values
- tc command generation produces correct qdisc syntax
- Preset loading and creation work
- Algebra operations (scale, compose) are correct
- AQM policy translation works for all policies

### Integration Tests
- Compiled tc commands successfully apply to test interface (requires root)
- Network verification detects applied configuration
- Throughput and RTT measurements match configured CTP (±5%)
- Verification fails gracefully when network not configured

### Performance Tests
- CTP validation < 10ms
- tc command compilation < 50ms
- Preset list retrieval < 100ms
- Network verification takes ~5s (measurement time)

## Implementation Guide

### Step 1: Project Structure
```bash
services/ctp-service/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py              # Flask app
│   ├── api/
│   │   ├── __init__.py
│   │   └── ctps.py          # Route handlers
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── validator.py     # CTP validation logic
│   │   ├── compiler.py      # tc command generation
│   │   ├── verifier.py      # Network state measurement
│   │   └── algebra.py       # CTP algebra operations
│   ├── models/
│   │   ├── __init__.py
│   │   └── ctp.py           # Dataclass definitions
│   └── utils/
│       ├── __init__.py
│       ├── subprocess.py    # Safe subprocess execution
│       └── logging.py
└── tests/
    ├── __init__.py
    ├── test_api.py
    ├── test_validator.py
    ├── test_compiler.py
    └── test_verifier.py
```

### Step 2: Validation Engine
```python
# app/engine/validator.py
class CTCValidator:
    CAPACITY_RANGE = (0, 10000)  # Mbps
    LATENCY_RANGE = (0, 10000)   # ms
    LOSS_RANGE = (0, 1.0)

    def validate_ctp(self, ctp: NetReplicaConfig) -> Tuple[bool, List[str]]:
        """Returns (valid, warnings)"""
        warnings = []

        # Check bounds
        if not self.CAPACITY_RANGE[0] < ctp.capacity_mbps <= self.CAPACITY_RANGE[1]:
            return False, ["Capacity out of range"]

        if ctp.latency_ms < self.LATENCY_RANGE[0]:
            return False, ["Latency must be non-negative"]

        # Warning for extreme values
        if ctp.capacity_mbps < 0.1:
            warnings.append("Very low capacity may be difficult to emulate")

        return True, warnings
```

### Step 3: tc Command Compiler
```python
# app/engine/compiler.py
class TCCompiler:
    def compile(self, ctp: NetReplicaConfig, interface: str) -> List[str]:
        """Compile CTP to tc commands."""
        commands = []

        # TBF (Token Bucket Filter) for capacity limiting
        commands.append(self._compile_capacity(ctp, interface))

        # AQM qdisc for active queue management
        commands.append(self._compile_aqm(ctp, interface))

        # Packet loss via netem if needed
        if ctp.loss_rate > 0:
            commands.append(self._compile_loss(ctp, interface))

        return commands

    def _compile_capacity(self, ctp, interface):
        # Calculate burst size: ~100ms worth of tokens
        burst = int(ctp.capacity_mbps * 1e6 / 8 * 0.1 / 1500)
        return (
            f"tc qdisc replace dev {interface} root handle 1: "
            f"tbf rate {int(ctp.capacity_mbps)}mbit burst {burst}b "
            f"latency {int(ctp.latency_ms)}ms"
        )
```

### Step 4: Network Verifier
```python
# app/engine/verifier.py
import subprocess
import time

class NetworkVerifier:
    def verify(self, interface: str, expected_ctp: NetReplicaConfig) -> BottleneckState:
        """Measure actual network state."""

        # Run iperf3 server on interface
        # Start iperf3 client, measure throughput
        throughput = self._measure_throughput(interface)

        # Use ping to measure RTT
        rtt = self._measure_rtt(interface)

        # Compare to expected
        state = BottleneckState(
            configured_capacity=expected_ctp.capacity_mbps,
            configured_latency=expected_ctp.latency_ms,
            measured_throughput=throughput,
            measured_rtt=rtt,
            verification_passed=(
                abs(throughput - expected_ctp.capacity_mbps) /
                expected_ctp.capacity_mbps < 0.05
            )
        )
        return state
```

### Step 5: Tests
```python
# tests/test_compiler.py
def test_compile_capacity():
    compiler = TCCompiler()
    ctp = NetReplicaConfig(capacity_mbps=10, latency_ms=50)
    cmds = compiler.compile(ctp, "eth0")
    assert any("tbf" in cmd for cmd in cmds)
    assert any("10mbit" in cmd for cmd in cmds)
```

## References

- Linux tc qdisc documentation: https://man7.org/linux/man-pages/man8/tc.8.html
- NetReplica controller.py: https://github.com/SNL-UCSB/netReplica/blob/main/controller.py
- Linux AQM algorithms: https://tools.ietf.org/html/rfc7567
- iperf3 documentation: https://software.es.net/iperf/
- netem (network emulation) man page: https://man7.org/linux/man-pages/man8/tc-netem.8.html

---

**Last Updated**: 2026-03-04
**Status**: Specification Ready
**Next Milestone**: Implementation (Week 1)
