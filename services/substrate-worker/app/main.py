from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import subprocess
import os
from typing import List, Optional
from datetime import datetime

# =========================
# Global variables
# =========================

app = FastAPI()

CURRENT_BOTTLENECK_STATE = None  # will hold a BottleneckState
CURRENT_INTERFACES = None        # {"downstream_iface": ..., "upstream_iface": ...}
ACTIVE_REPLAYS: dict = {}        # replay_id → session dict


# =========================
# Data models (classes)
# =========================

class ShapeRequest(BaseModel):
    upstream_iface: str = Field(..., description="Upload/egress interface (e.g., veth4)")
    downstream_iface: str = Field(..., description="Download/ingress interface (e.g., veth2)")
    download_mbps: float = Field(..., gt=0, description="Download capacity in Mbps")
    upload_mbps: float = Field(..., gt=0, description="Upload capacity in Mbps")
    latency_ms: float = Field(..., ge=0, description="One-way delay in ms")
    qdisc: str = Field(..., description="Queue discipline (e.g., fq_codel, pfifo)")
    buffer_packets: int = Field(1000, ge=1, description="Queue depth / limit in packets")


class BottleneckState(BaseModel):
    download_mbps: float
    upload_mbps: float
    latency_ms: float
    qdisc: str
    verified: bool = False
    buffer_packets: int = 1000
    loss_rate_percent: float = 0.0
    verification_log: List[str] = []


class ShapeResponse(BaseModel):
    status: str
    bottleneck_state: BottleneckState
    applied_commands: List[str]


class CaptureRequest(BaseModel):
    duration: int = Field(..., gt=0, description="Capture duration in seconds")
    prefix: str = Field("capture", description="Filename prefix for pcap files")
    upstream_iface: str = Field("veth4", description="Interface to capture upstream traffic")
    downstream_iface: str = Field("veth2", description="Interface to capture downstream traffic")


class CaptureResponse(BaseModel):
    status: str
    duration: int
    files: List[str]


class ReplayRequest(BaseModel):
    ctp_id: str = Field(..., description="CTP ID to fetch from CTP Service (port 8001)")
    interface: str = Field("veth4", description="Interface to replay traffic on")
    rate: str = Field("10M", description="Replay rate e.g. '10M', '5M', '50K'")
    loop: bool = Field(False, description="Loop replay indefinitely")
    duration_seconds: Optional[int] = Field(None, description="Stop replay after N seconds (ignored if loop=False)")
    ctp_service_url: str = Field("http://localhost:8001", description="Base URL of CTP Service")


class ReplayResponse(BaseModel):
    replay_id: str
    status: str
    ctp_id: str
    interface: str
    rate: str
    pcap_path: str
    start_time: str


class ReplayStatusResponse(BaseModel):
    replay_id: str
    status: str  # "running", "completed", "failed", "stopped", "starting"
    ctp_id: str
    interface: str
    rate: str
    start_time: str
    end_time: Optional[str] = None
    packets_replayed: int = 0
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    root_privileges: bool
    tc_available: bool
    tshark_available: bool
    tcpreplay_available: bool
    qdisc_support: bool
    interfaces: List[str]
    timestamp: str


# =========================
# Helper functions
# =========================

def run_cmd(cmd: str) -> None:
    subprocess.run(cmd, shell=True, check=True)


def _build_qdisc_args(qdisc: str, buffer_packets: int) -> str:
    """
    Build qdisc arguments, including buffer/limit for AQM-style qdiscs.
    """
    if qdisc in ("fq_codel", "codel"):
        return f"{qdisc} limit {buffer_packets}"
    return qdisc


def apply_shaping(
    downstream_iface: str,
    upstream_iface: str,
    download_mbps: float,
    upload_mbps: float,
    latency_ms: float,
    qdisc: str,
    buffer_packets: int,
) -> List[str]:
    applied: List[str] = []
    qdisc_args = _build_qdisc_args(qdisc, buffer_packets)

    # -------------------------
    # Bandwidth shaping (HTB)
    # -------------------------
    for iface, rate in [
        (downstream_iface, download_mbps),
        (upstream_iface, upload_mbps),
    ]:
        c0 = f"tc qdisc del dev {iface} root 2>/dev/null || true"
        run_cmd(c0)
        applied.append(c0)

        # HTB root
        c1 = f"tc qdisc add dev {iface} root handle 1: htb default 10 r2q 100"
        run_cmd(c1)
        applied.append(c1)

        # HTB class
        c2 = (
            f"tc class add dev {iface} parent 1: classid 1:10 "
            f"htb rate {rate}Mbit ceil {rate}Mbit"
        )
        run_cmd(c2)
        applied.append(c2)

        # AQM qdisc
        c3 = f"tc qdisc add dev {iface} parent 1:10 handle 10: {qdisc_args}"
        run_cmd(c3)
        applied.append(c3)

    # -------------------------
    # Latency shaping (netem)
    # -------------------------
    if latency_ms == 0:
        c4 = "tc qdisc del dev veth6 root 2>/dev/null || true"
        run_cmd(c4)
        applied.append(c4)
    else:
        c4 = (
            "tc qdisc del dev veth6 root 2>/dev/null || true && "
            f"tc qdisc add dev veth6 root netem delay {latency_ms}ms"
        )
        run_cmd(c4)
        applied.append(c4)

    return applied


def _run_in_ns(ns: str, cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a command inside a network namespace."""
    return subprocess.run(
        f"ip netns exec {ns} {cmd}",
        shell=True,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _kill_iperf3_servers() -> None:
    subprocess.run("ip netns exec ns2 pkill -f 'iperf3 -s' 2>/dev/null || true", shell=True)
    import time
    time.sleep(0.3)


def _verify_bottleneck_state() -> None:
    global CURRENT_BOTTLENECK_STATE, CURRENT_INTERFACES

    if CURRENT_BOTTLENECK_STATE is None or CURRENT_INTERFACES is None:
        return

    TARGET_IP = "172.16.3.1"
    IPERF_DURATION = 3
    TOLERANCE_PCT = 20
    verified = True
    log: List[str] = []

    try:
        import time
        import json as _json

        # Upload test: ns1 → ns2
        _kill_iperf3_servers()
        subprocess.Popen(
            "ip netns exec ns2 iperf3 -s -1 -D --logfile /tmp/iperf3_server_up.log",
            shell=True,
        )
        time.sleep(0.5)

        up = _run_in_ns(
            "ns1",
            f"iperf3 -c {TARGET_IP} -t {IPERF_DURATION} -J",
            timeout=IPERF_DURATION + 10,
        )
        if up.returncode == 0:
            upload_mbps = _json.loads(up.stdout)["end"]["sum_sent"]["bits_per_second"] / 1e6
            expected = CURRENT_BOTTLENECK_STATE.upload_mbps
            diff_pct = abs(upload_mbps - expected) / expected * 100
            log.append(
                f"upload: measured={upload_mbps:.2f}Mbps "
                f"expected={expected}Mbps diff={diff_pct:.1f}%"
            )
            if diff_pct > TOLERANCE_PCT:
                log.append(f"FAIL: upload out of ±{TOLERANCE_PCT}% range")
                verified = False
            else:
                log.append("PASS: upload")
        else:
            log.append(f"FAIL: iperf3 upload error: {up.stderr.strip()}")
            verified = False

        # Download test: ns2 → ns1
        _kill_iperf3_servers()
        subprocess.Popen(
            "ip netns exec ns2 iperf3 -s -1 -D --logfile /tmp/iperf3_server_down.log",
            shell=True,
        )
        time.sleep(0.5)

        down = _run_in_ns(
            "ns1",
            f"iperf3 -c {TARGET_IP} -t {IPERF_DURATION} -R -J",
            timeout=IPERF_DURATION + 10,
        )
        if down.returncode == 0:
            download_mbps = _json.loads(down.stdout)["end"]["sum_received"]["bits_per_second"] / 1e6
            expected = CURRENT_BOTTLENECK_STATE.download_mbps
            diff_pct = abs(download_mbps - expected) / expected * 100
            log.append(
                f"download: measured={download_mbps:.2f}Mbps "
                f"expected={expected}Mbps diff={diff_pct:.1f}%"
            )
            if diff_pct > TOLERANCE_PCT:
                log.append(f"FAIL: download out of ±{TOLERANCE_PCT}% range")
                verified = False
            else:
                log.append("PASS: download")
        else:
            log.append(f"FAIL: iperf3 download error: {down.stderr.strip()}")
            verified = False

    except Exception as e:
        log.append(f"FAIL: exception: {e}")
        verified = False

    CURRENT_BOTTLENECK_STATE.verified = verified
    CURRENT_BOTTLENECK_STATE.verification_log = log




def _cmd_available(cmd: str) -> bool:
    result = subprocess.run(f"which {cmd}", shell=True, capture_output=True)
    return result.returncode == 0


def _check_root() -> bool:
    return os.geteuid() == 0


def _check_qdisc_support() -> bool:
    """Check that fq_codel is available in the kernel."""
    result = subprocess.run(
        "tc qdisc add dev lo root fq_codel 2>&1",
        shell=True,
        capture_output=True,
        text=True,
    )
    # Clean up immediately
    subprocess.run(
        "tc qdisc del dev lo root 2>/dev/null || true",
        shell=True,
        capture_output=True,
    )
    # If error mentions "fq_codel" not found it's unsupported; any other error is fine
    return "No such file" not in result.stdout and "Unknown qdisc" not in result.stdout


def _get_interfaces() -> List[str]:
    result = subprocess.run(
        "ip -o link show | awk -F': ' '{print $2}' | cut -d'@' -f1",
        shell=True,
        capture_output=True,
        text=True,
    )
    ifaces = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [i for i in ifaces if i != "lo"]


# =========================
# API endpoints
# =========================

@app.post("/shape", response_model=ShapeResponse)
def shape(cfg: ShapeRequest) -> ShapeResponse:
    global CURRENT_BOTTLENECK_STATE, CURRENT_INTERFACES

    try:
        applied_commands: List[str] = []
        applied_commands.extend(
            apply_shaping(
                downstream_iface=cfg.downstream_iface,
                upstream_iface=cfg.upstream_iface,
                download_mbps=cfg.download_mbps,
                upload_mbps=cfg.upload_mbps,
                latency_ms=cfg.latency_ms,
                qdisc=cfg.qdisc,
                buffer_packets=cfg.buffer_packets,
            )
        )
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"tc command failed: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    state = BottleneckState(
        download_mbps=cfg.download_mbps,
        upload_mbps=cfg.upload_mbps,
        latency_ms=cfg.latency_ms,
        qdisc=cfg.qdisc,
        verified=False,  # will be set by verification logic
        buffer_packets=cfg.buffer_packets,
    )

    CURRENT_BOTTLENECK_STATE = state
    CURRENT_INTERFACES = {
        "downstream_iface": cfg.downstream_iface,
        "upstream_iface": cfg.upstream_iface,
    }

    # Run verification immediately after applying shaping
    _verify_bottleneck_state()

    return ShapeResponse(
        status="shaped",
        bottleneck_state=state,
        applied_commands=applied_commands,
    )


@app.post("/capture", response_model=CaptureResponse)
def start_capture(cfg: CaptureRequest) -> CaptureResponse:
    """
    Start packet capture on upstream and downstream interfaces using tshark.
    Writes pcaps into ./captures inside the container.
    """
    os.makedirs("captures", exist_ok=True)

    up_file = f"captures/up_{cfg.prefix}.pcap"
    down_file = f"captures/down_{cfg.prefix}.pcap"

    # Run tshark in the background; endpoint returns immediately
    subprocess.Popen(
        f"tshark -i {cfg.upstream_iface} -a duration:{cfg.duration} -w {up_file}",
        shell=True,
    )
    subprocess.Popen(
        f"tshark -i {cfg.downstream_iface} -a duration:{cfg.duration} -w {down_file}",
        shell=True,
    )

    return CaptureResponse(
        status="started",
        duration=cfg.duration,
        files=[up_file, down_file],
    )



@app.get("/state")
def get_state():
    """
    Retrieve bottleneck configuration and verification status.
    Returns the last applied BottleneckState and updates the
    'verified' flag based on current tc configuration.
    """
    if CURRENT_BOTTLENECK_STATE is None:
        return {"status": "no_state", "bottleneck_state": None}

    # Refresh verification status before returning
    _verify_bottleneck_state()

    return {
        "status": "ok",
        "bottleneck_state": CURRENT_BOTTLENECK_STATE,
    }


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    root = _check_root()
    tc = _cmd_available("tc")
    tshark = _cmd_available("tshark")
    tcpreplay = _cmd_available("tcpreplay")
    qdisc = _check_qdisc_support() if tc else False
    interfaces = _get_interfaces()

    healthy = all([root, tc, tshark, tcpreplay, qdisc])

    return HealthResponse(
        status="ok" if healthy else "degraded",
        root_privileges=root,
        tc_available=tc,
        tshark_available=tshark,
        tcpreplay_available=tcpreplay,
        qdisc_support=qdisc,
        interfaces=interfaces,
        timestamp=datetime.utcnow().isoformat(),
    )


# If you ever want to run this module directly:
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8002)