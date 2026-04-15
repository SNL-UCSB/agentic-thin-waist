import os
import subprocess
import time
import uuid
from datetime import datetime
from typing import Annotated, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from starlette.responses import FileResponse

# =========================
# Global variables
# =========================

app = FastAPI()

CURRENT_BOTTLENECK_STATE = None  # will hold a BottleneckState
CURRENT_INTERFACES = None  # {"downstream_iface": ..., "upstream_iface": ...}
ACTIVE_REPLAYS: dict = {}  # replay_id → session dict
ACTIVE_CAPTURES: dict = {}  # capture_id → session dict

CAPTURE_DIR = os.environ.get("CAPTURE_DIR", "/home/netreplica/config/captures")
CTP_DIR = os.environ.get("CTP_DIR", "/home/netreplica/config/ctp")

HEALTH_CACHE: dict = {}


@app.on_event("startup")
def startup_check():
    global HEALTH_CACHE
    root = _check_root()
    tc = _cmd_available("tc")
    tshark = _cmd_available("tshark")
    tcpreplay = _cmd_available("tcpreplay")
    qdisc = _check_qdisc_support() if tc else False
    interfaces = _get_interfaces()
    ctp_dir = (CTP_DIR or "").strip()
    capture_dir = (CAPTURE_DIR or "").strip()
    path_config_valid = bool(ctp_dir and capture_dir)
    healthy = all([root, tc, tshark, tcpreplay, qdisc, path_config_valid])

    HEALTH_CACHE = {
        "status": "ok" if healthy else "degraded",
        "root_privileges": root,
        "tc_available": tc,
        "tshark_available": tshark,
        "tcpreplay_available": tcpreplay,
        "qdisc_support": qdisc,
        "ctp_dir": ctp_dir or "(unset)",
        "capture_dir": capture_dir or "(unset)",
        "path_config_valid": path_config_valid,
        "interfaces": interfaces,
    }


# =========================
# Data models (classes)
# =========================


class ShapeRequest(BaseModel):
    upstream_iface: str = Field(
        ..., description="Upload/egress interface (e.g., veth4)"
    )
    downstream_iface: str = Field(
        ..., description="Download/ingress interface (e.g., veth2)"
    )
    download_mbps: float = Field(..., gt=0, description="Download capacity in Mbps")
    upload_mbps: float = Field(..., gt=0, description="Upload capacity in Mbps")

    latency_ms: float = Field(0, ge=0, description="One-way delay in ms (default: 0)")

    latency_location: Optional[Literal["upstream", "downstream", "both"]] = Field(
        None,
        description=(
            "Where to inject base latency: 'upstream' (veth3 in ns2), "
            "'downstream' (veth1 in ns1), 'both', or omit/null for none"
        ),
    )

    qdisc: str = Field("pfifo", description="Queue discipline (default: pfifo)")

    buffer_packets: int = Field(
        1000, ge=1, description="Queue depth / limit in packets (default: 1000)"
    )

    qdisc_params: Optional[Dict[str, str]] = Field(
        None,
        description=(
            "Extra qdisc-specific parameters passed verbatim to tc "
            "(e.g. {'target': '5ms', 'interval': '100ms'} for codel/fq_codel). "
            "For qdiscs in the limit-based family (pfifo, bfifo, sfq) the "
            "buffer_packets field already sets 'limit'; use this for everything else."
        ),
    )


class BottleneckState(BaseModel):
    download_mbps: float
    upload_mbps: float
    latency_ms: float
    latency_location: Optional[str] = None
    qdisc: str
    verified: bool = False
    buffer_packets: int = 1000
    qdisc_params: Optional[Dict[str, str]] = None
    loss_rate_percent: float = 0.0
    verification_log: List[str] = []


class ShapeResponse(BaseModel):
    status: str
    bottleneck_state: BottleneckState
    applied_commands: List[str]


class CaptureRequest(BaseModel):
    interface: str = Field(..., description="Interface to capture on (e.g., veth2)")
    capture_filter: str = Field(
        "", description="tcpdump-style filter (e.g., 'tcp port 443')"
    )
    filename: str = Field(
        ..., description="Output pcap filename (e.g., 'youtube_10mbps')"
    )
    duration_seconds: Optional[int] = Field(
        None, description="Stop capture after N seconds"
    )


class CaptureResponse(BaseModel):
    capture_id: str
    status: str
    pcap_path: str
    interface: str
    capture_filter: str


class CaptureStatusResponse(BaseModel):
    capture_id: str
    status: str  # "running", "finished"
    pcap_path: str
    interface: str
    capture_filter: str
    start_time: str
    exit_code: Optional[int] = None


class HealthResponse(BaseModel):
    status: str
    root_privileges: bool
    tc_available: bool
    tshark_available: bool
    tcpreplay_available: bool
    qdisc_support: bool
    ctp_dir: str
    capture_dir: str
    path_config_valid: bool
    interfaces: List[str]
    timestamp: str


class ReplayRequest(BaseModel):
    ctp_file: str = Field(
        ...,
        description=(
            "CTP base name without direction prefix or .pcap extension "
            "(e.g., 'cluster26_tree10_profile424'). "
            "Download PCAP is read from CTP_DIR/download/<ctp_file>.pcap; "
            "upload from CTP_DIR/upload/<ctp_file>.pcap."
        ),
    )
    duration_seconds: Optional[int] = Field(None, description="Stop after N seconds")
    pnat: str = Field(
        ...,
        description="PNAT rewrite rules mapping internal subnets to the target IP "
        "e.g. '169.231.0.0/16:172.16.1.1,128.111.0.0/16:172.16.1.1'",
    )


class ReplayResponse(BaseModel):
    replay_id: str
    status: str
    ctp_file: str
    pnat: str


class ReplayStatusResponse(BaseModel):
    replay_id: str
    status: (
        str  # "running" if either direction is still active, "finished" when both done
    )
    ctp_file: str
    pnat: str
    start_time: str


class CongestionRequest(BaseModel):
    algorithm: str = Field(
        ...,
        description="TCP congestion control algorithm name (e.g., 'bbr', 'cubic', 'reno')",
    )
    namespace: Optional[str] = Field(
        None,
        description=(
            "Network namespace to configure: 'ns1', 'ns2', or 'root' for the "
            "container root namespace. Omit or set null to apply in all namespaces."
        ),
    )


class CongestionResponse(BaseModel):
    current_algorithm: str
    available_algorithms: List[str]
    status: str


class CtpFetchRequest(BaseModel):
    ctp_pointer: str = Field(
        ...,
        description=(
            "URL, absolute path, or plain base name identifying the CTP to fetch. "
            "URL: fetches ?direction=download and ?direction=upload from the base URL. "
            "Absolute path: path to the download PCAP; upload derived by replacing /download/ with /upload/. "
            "Plain name: verifies files are already present in CTP_DIR."
        ),
    )
    ctp_root: Optional[str] = Field(
        None,
        description="Override the CTP root directory (defaults to CTP_DIR env var).",
    )


class CtpFetchResponse(BaseModel):
    status: str
    name: str
    download_path: str
    upload_path: str
    fetched: bool
    applied_commands: List[str] = []


class RunExperimentRequest(BaseModel):
    # --- Shaping ---
    upstream_iface: str = Field("veth4", description="Upload interface")
    downstream_iface: str = Field("veth2", description="Download interface")
    # None = shaping already applied via POST /shape — skip re-shaping in /run.
    # Provide explicit values (>0) to apply shaping as part of this call.
    download_mbps: Optional[float] = Field(
        None, gt=0, description="Download capacity in Mbps (omit to skip shaping)"
    )
    upload_mbps: Optional[float] = Field(
        None, gt=0, description="Upload capacity in Mbps (omit to skip shaping)"
    )
    latency_ms: float = Field(0, ge=0, description="One-way delay in ms")
    latency_location: Optional[Literal["upstream", "downstream", "both"]] = None
    qdisc: str = Field("pfifo", description="Queue discipline")
    buffer_packets: int = Field(1000, ge=1, description="Queue depth in packets")
    qdisc_params: Optional[Dict[str, str]] = None
    # --- Congestion (optional — skip when already applied via POST /congestion) ---
    cca: str = Field("cubic", description="TCP congestion control algorithm")
    cca_namespace: Optional[str] = Field(
        None, description="Namespace for CCA (ns1, ns2, or null for all)"
    )
    # --- Workflow ---
    workflow: Dict = Field(..., description="Workflow definition (state machine JSON)")
    runtime: Literal["shell", "browser"] = Field(
        "shell", description="Workflow runtime"
    )
    parameters: Optional[Dict[str, str]] = Field(
        None, description="Workflow parameter substitutions (key=value)"
    )


class RunExperimentResponse(BaseModel):
    status: str
    runtime: str
    result: List


# =========================
# Helper functions
# =========================


def run_cmd(cmd: str) -> None:
    subprocess.run(cmd, shell=True, check=True)


# Qdiscs that use `limit` as their primary queue-depth knob.
# AQMs like codel/fq_codel are intentionally excluded: they manage congestion
# proactively via target/interval and do not rely on tail-drop via limit.
_LIMIT_QDISCS = {"pfifo", "bfifo", "pfifo_fast", "sfq"}

# Parameters that are meaningless (or actively misleading) for AQM qdiscs.
_AQM_QDISCS = {"codel", "fq_codel"}


def _validate_qdisc_request(
    qdisc: str,
    buffer_packets: int,
    qdisc_params: Optional[Dict[str, str]],
) -> None:
    """Raise HTTPException for invalid or contradictory qdisc parameter combinations."""
    if qdisc_params:
        # Disallow keys that would silently override positional fields.
        if "limit" in qdisc_params and qdisc in _LIMIT_QDISCS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Do not set 'limit' in qdisc_params for '{qdisc}'; "
                    "use buffer_packets instead."
                ),
            )
        # Warn callers away from passing limit to AQM qdiscs via qdisc_params
        # — it is legal but almost always unintentional.
        # (We allow it so advanced users can still do it explicitly.)

    # buffer_packets has no effect on AQM qdiscs unless the caller also
    # passes limit via qdisc_params — flag the mismatch.
    if qdisc in _AQM_QDISCS and buffer_packets != 1000:
        # Non-default value was explicitly set; warn rather than silently ignore.
        raise HTTPException(
            status_code=422,
            detail=(
                f"buffer_packets has no effect on '{qdisc}'. "
                "Use qdisc_params to pass 'limit' explicitly if needed, "
                "or rely on the qdisc's default."
            ),
        )


def _build_qdisc_args(
    qdisc: str,
    buffer_packets: int,
    qdisc_params: Optional[Dict[str, str]] = None,
) -> str:
    parts = [qdisc]
    if qdisc in _LIMIT_QDISCS:
        parts.append(f"limit {buffer_packets}")
    if qdisc_params:
        for key, value in qdisc_params.items():
            parts.append(f"{key} {value}")
    return " ".join(parts)


def apply_shaping(
    downstream_iface: str,
    upstream_iface: str,
    download_mbps: float,
    upload_mbps: float,
    latency_ms: float,
    qdisc: str,
    buffer_packets: int,
    qdisc_params: Optional[Dict[str, str]] = None,
    latency_location: Optional[str] = None,
) -> List[str]:
    applied: List[str] = []
    qdisc_args = _build_qdisc_args(qdisc, buffer_packets, qdisc_params)

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
    _verify_bottleneck_state()
    # -------------------------
    # Latency shaping (netem)
    # -------------------------
    # Always clean up existing netem on both latency-injection interfaces,
    # then add netem only where requested and latency_ms > 0.
    for ns, iface, direction in [
        ("ns1", "veth1", "downstream"),
        ("ns2", "veth3", "upstream"),
    ]:
        apply = (
            latency_ms > 0
            and latency_location is not None
            and (latency_location == direction or latency_location == "both")
        )
        del_cmd = (
            f"ip netns exec {ns} tc qdisc del dev {iface} root 2>/dev/null || true"
        )
        run_cmd(del_cmd)
        applied.append(del_cmd)
        if apply:
            add_cmd = (
                f"ip netns exec {ns} tc qdisc add dev {iface} "
                f"root netem delay {latency_ms}ms"
            )
            run_cmd(add_cmd)
            applied.append(add_cmd)

    _verify_latency()
    return applied


def _run_in_ns(ns: str, cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        f"ip netns exec {ns} {cmd}",
        shell=True,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _kill_iperf3_servers() -> None:
    subprocess.run(
        "ip netns exec ns2 pkill -f 'iperf3 -s' 2>/dev/null || true", shell=True
    )
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
        import json as _json
        import time

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
            upload_mbps = (
                _json.loads(up.stdout)["end"]["sum_sent"]["bits_per_second"] / 1e6
            )
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
            download_mbps = (
                _json.loads(down.stdout)["end"]["sum_received"]["bits_per_second"] / 1e6
            )
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


def _verify_latency() -> None:
    global CURRENT_BOTTLENECK_STATE

    if CURRENT_BOTTLENECK_STATE is None:
        return

    import re

    TARGET_IP = "172.16.3.1"
    TOLERANCE_MS = 10.0
    log: List[str] = []
    latency_verified = True

    expected_ms = CURRENT_BOTTLENECK_STATE.latency_ms
    location = CURRENT_BOTTLENECK_STATE.latency_location

    # Calculate expected RTT contribution from netem:
    # - "both"            → outgoing + return leg both delayed  → +2*latency_ms
    # - "upstream" or
    #   "downstream"      → only one leg delayed                → +1*latency_ms
    # - None / 0          → no added delay; verify baseline is low
    if expected_ms > 0 and location is not None:
        if location == "both":
            expected_rtt_ms = expected_ms * 2
        else:
            expected_rtt_ms = expected_ms
    else:
        expected_rtt_ms = 0.0

    try:
        result = _run_in_ns(
            "ns1",
            f"ping -c 5 -W 2 -q {TARGET_IP}",
            timeout=20,
        )
        if result.returncode == 0:
            match = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", result.stdout)
            if match:
                measured_rtt_ms = float(match.group(1))
                diff_ms = abs(measured_rtt_ms - expected_rtt_ms)
                log.append(
                    f"latency: measured_rtt={measured_rtt_ms:.2f}ms "
                    f"expected_rtt={expected_rtt_ms:.2f}ms diff={diff_ms:.2f}ms"
                )
                if diff_ms > TOLERANCE_MS:
                    log.append(f"FAIL: latency out of ±{TOLERANCE_MS}ms range")
                    latency_verified = False
                else:
                    log.append("PASS: latency")
            else:
                log.append(
                    f"FAIL: could not parse ping output: {result.stdout.strip()}"
                )
                latency_verified = False
        else:
            log.append(f"FAIL: ping error: {result.stderr.strip()}")
            latency_verified = False
    except Exception as e:
        log.append(f"FAIL: latency verification exception: {e}")
        latency_verified = False

    CURRENT_BOTTLENECK_STATE.verification_log.extend(log)
    CURRENT_BOTTLENECK_STATE.verified = (
        CURRENT_BOTTLENECK_STATE.verified and latency_verified
    )


def _cmd_available(cmd: str) -> bool:
    result = subprocess.run(f"which {cmd}", shell=True, capture_output=True)
    return result.returncode == 0


def _check_root() -> bool:
    return os.geteuid() == 0


def _check_qdisc_support() -> bool:
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

    _validate_qdisc_request(cfg.qdisc, cfg.buffer_packets, cfg.qdisc_params)

    # Set state before apply_shaping so that the verification functions
    # called inside it (_verify_bottleneck_state, _verify_latency) can
    # read the expected values.
    state = BottleneckState(
        download_mbps=cfg.download_mbps,
        upload_mbps=cfg.upload_mbps,
        latency_ms=cfg.latency_ms,
        latency_location=cfg.latency_location,
        qdisc=cfg.qdisc,
        verified=False,
        buffer_packets=cfg.buffer_packets,
        qdisc_params=cfg.qdisc_params,
    )
    CURRENT_BOTTLENECK_STATE = state
    CURRENT_INTERFACES = {
        "downstream_iface": cfg.downstream_iface,
        "upstream_iface": cfg.upstream_iface,
    }

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
                qdisc_params=cfg.qdisc_params,
                latency_location=cfg.latency_location,
            )
        )
    except subprocess.CalledProcessError as exc:
        CURRENT_BOTTLENECK_STATE = None
        CURRENT_INTERFACES = None
        raise HTTPException(status_code=500, detail=f"tc command failed: {exc}")
    except Exception as exc:
        CURRENT_BOTTLENECK_STATE = None
        CURRENT_INTERFACES = None
        raise HTTPException(status_code=500, detail=str(exc))

    return ShapeResponse(
        status="shaped",
        bottleneck_state=state,
        applied_commands=applied_commands,
    )


# =========================
# Capture endpoints
# =========================


@app.post("/capture", response_model=CaptureResponse)
def start_capture(cfg: CaptureRequest) -> CaptureResponse:
    if not (CAPTURE_DIR or "").strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "CAPTURE_DIR is empty. Set CAPTURE_DIR (or SUBSTRATE_CAPTURE_DIR in compose) "
                "to a writable directory path."
            ),
        )
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    safe_name = os.path.basename(cfg.filename).strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="filename must be non-empty")

    interfaces = _get_interfaces()
    if cfg.interface not in interfaces:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown interface '{cfg.interface}'. Available: {interfaces}",
        )

    pcap_path = os.path.join(CAPTURE_DIR, f"{safe_name}.pcap")

    cmd_parts: List[str] = [
        "tshark",
        "-i",
        cfg.interface,
        "-w",
        pcap_path,
    ]

    if cfg.capture_filter:
        cmd_parts.extend(["-f", cfg.capture_filter])

    if cfg.duration_seconds:
        cmd_parts.extend(["-a", f"duration:{cfg.duration_seconds}"])

    try:
        proc = subprocess.Popen(
            cmd_parts,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start tshark: {exc}")

    # If tshark fails immediately (permissions / bad iface), surface stderr right away.
    time.sleep(0.2)
    if proc.poll() is not None and proc.returncode not in (0, None):
        try:
            _out, _err = proc.communicate(timeout=1)
        except Exception:
            _out, _err = "", ""
        raise HTTPException(
            status_code=500,
            detail={
                "message": "tshark exited immediately",
                "exit_code": proc.returncode,
                "stdout": (_out or "").strip(),
                "stderr": (_err or "").strip(),
                "pcap_path": pcap_path,
                "root_privileges": _check_root(),
            },
        )

    capture_id = str(uuid.uuid4())
    ACTIVE_CAPTURES[capture_id] = {
        "capture_id": capture_id,
        "pcap_path": pcap_path,
        "interface": cfg.interface,
        "capture_filter": cfg.capture_filter,
        "process": proc,
        "start_time": datetime.utcnow().isoformat(),
    }

    return CaptureResponse(
        capture_id=capture_id,
        status="started",
        pcap_path=pcap_path,
        interface=cfg.interface,
        capture_filter=cfg.capture_filter,
    )


@app.get("/capture/{capture_id}", response_model=CaptureStatusResponse)
def get_capture(capture_id: str) -> CaptureStatusResponse:
    session = ACTIVE_CAPTURES.get(capture_id)

    if session is None:
        raise HTTPException(
            status_code=404, detail=f"Capture session not found: {capture_id}"
        )

    proc: subprocess.Popen = session["process"]
    status = "running" if proc.poll() is None else "finished"

    return CaptureStatusResponse(
        capture_id=capture_id,
        status=status,
        pcap_path=session["pcap_path"],
        interface=session["interface"],
        capture_filter=session["capture_filter"],
        start_time=session["start_time"],
        exit_code=proc.returncode,
    )


def _require_capture_download_token(
    x_capture_download_token: Optional[str],
) -> None:
    expected = (os.environ.get("CAPTURE_DOWNLOAD_TOKEN") or "").strip()
    if not expected:
        return
    if not x_capture_download_token or x_capture_download_token.strip() != expected:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-Capture-Download-Token header",
        )


@app.get("/capture/{capture_id}/pcap")
def download_capture_pcap(
    capture_id: str,
    x_capture_download_token: Annotated[
        Optional[str], Header(alias="X-Capture-Download-Token")
    ] = None,
):
    """Download the PCAP for a finished capture (for orchestrator pull to telemetry)."""
    _require_capture_download_token(x_capture_download_token)
    session = ACTIVE_CAPTURES.get(capture_id)
    if session is None:
        raise HTTPException(
            status_code=404, detail=f"Capture session not found: {capture_id}"
        )
    proc: subprocess.Popen = session["process"]
    if proc.poll() is None:
        raise HTTPException(
            status_code=409,
            detail="Capture still running; PCAP not finalized",
        )
    pcap_path = session["pcap_path"]
    if not os.path.isfile(pcap_path):
        raise HTTPException(
            status_code=404,
            detail=f"PCAP file not found at {pcap_path}",
        )
    return FileResponse(
        pcap_path,
        media_type="application/vnd.tcpdump.pcap",
        filename=os.path.basename(pcap_path),
    )


@app.delete("/capture/{capture_id}")
def delete_capture(capture_id: str):
    session = ACTIVE_CAPTURES.get(capture_id)

    if session is None:
        raise HTTPException(
            status_code=404, detail=f"Capture session not found: {capture_id}"
        )

    proc: subprocess.Popen = session["process"]

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    del ACTIVE_CAPTURES[capture_id]

    return {"capture_id": capture_id, "status": "stopped"}


@app.get("/state")
def get_state():
    if CURRENT_BOTTLENECK_STATE is None:
        return {"status": "no_state", "bottleneck_state": None}

    return {
        "status": "ok",
        "bottleneck_state": CURRENT_BOTTLENECK_STATE,
    }


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        **HEALTH_CACHE,
        timestamp=datetime.utcnow().isoformat(),
    )


@app.post("/replay", response_model=ReplayResponse)
def start_replay(cfg: ReplayRequest) -> ReplayResponse:
    if not (CTP_DIR or "").strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "CTP_DIR is empty. Set CTP_DIR (or SUBSTRATE_CTP_DIR in compose) "
                "to a directory containing download/upload CTP files."
            ),
        )
    download_path = f"{CTP_DIR}/download/{cfg.ctp_file}.pcap"
    upload_path = f"{CTP_DIR}/upload/{cfg.ctp_file}.pcap"

    missing = [p for p in (download_path, upload_path) if not os.path.exists(p)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"CTP file(s) not found under CTP_DIR={CTP_DIR}: {', '.join(missing)}"
            ),
        )

    def _build_cmd(ns: str, iface: str, pcap_path: str) -> str:
        parts = [
            f"ip netns exec {ns} tcpreplay-edit",
            f"-i {iface}",
            f"--pnat={cfg.pnat}",
        ]
        if cfg.duration_seconds:
            parts.append(f"--duration={cfg.duration_seconds}")
        parts.append(pcap_path)
        return " ".join(parts)

    # Download: injected from ns2 (server side) on veth3 → simulates incoming traffic
    # Upload:   injected from ns1 (client side) on veth1 → simulates outgoing traffic
    dl_cmd = _build_cmd("ns2", "veth3", download_path)
    ul_cmd = _build_cmd("ns1", "veth1", upload_path)

    try:
        dl_proc = subprocess.Popen(
            dl_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        ul_proc = subprocess.Popen(
            ul_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start tcpreplay: {exc}")

    replay_id = str(uuid.uuid4())
    ACTIVE_REPLAYS[replay_id] = {
        "replay_id": replay_id,
        "ctp_file": cfg.ctp_file,
        "pnat": cfg.pnat,
        "download_proc": dl_proc,
        "upload_proc": ul_proc,
        "start_time": datetime.utcnow().isoformat(),
    }

    return ReplayResponse(
        replay_id=replay_id,
        status="started",
        ctp_file=cfg.ctp_file,
        pnat=cfg.pnat,
    )


@app.get("/replay/{replay_id}", response_model=ReplayStatusResponse)
def get_replay(replay_id: str) -> ReplayStatusResponse:
    session = ACTIVE_REPLAYS.get(replay_id)

    if session is None:
        raise HTTPException(
            status_code=404, detail=f"Replay session not found: {replay_id}"
        )

    dl_proc: subprocess.Popen = session["download_proc"]
    ul_proc: subprocess.Popen = session["upload_proc"]
    status = (
        "running" if (dl_proc.poll() is None or ul_proc.poll() is None) else "finished"
    )

    return ReplayStatusResponse(
        replay_id=replay_id,
        status=status,
        ctp_file=session["ctp_file"],
        pnat=session["pnat"],
        start_time=session["start_time"],
    )


@app.delete("/replay/{replay_id}")
def delete_replay(replay_id: str):
    session = ACTIVE_REPLAYS.get(replay_id)

    if session is None:
        raise HTTPException(
            status_code=404, detail=f"Replay session not found: {replay_id}"
        )

    for proc in (session["download_proc"], session["upload_proc"]):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    del ACTIVE_REPLAYS[replay_id]

    return {"replay_id": replay_id, "status": "stopped"}


def _sysctl_get_cca(ns: Optional[str]) -> str:
    key = "net.ipv4.tcp_congestion_control"
    if ns and ns != "root":
        result = subprocess.run(
            f"ip netns exec {ns} sysctl -n {key}",
            shell=True,
            capture_output=True,
            text=True,
        )
    else:
        result = subprocess.run(
            f"sysctl -n {key}", shell=True, capture_output=True, text=True
        )
    return result.stdout.strip()


def _sysctl_get_available() -> List[str]:
    result = subprocess.run(
        "sysctl -n net.ipv4.tcp_available_congestion_control",
        shell=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().split()


def _apply_cca_in_ns(ns: Optional[str], algorithm: str) -> str:
    key = "net.ipv4.tcp_congestion_control"
    if ns and ns != "root":
        cmd = f"ip netns exec {ns} sysctl -w {key}={algorithm}"
    else:
        cmd = f"sysctl -w {key}={algorithm}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0 or "Operation not permitted" in (
        result.stderr + result.stdout
    ):
        raise RuntimeError((result.stderr or result.stdout).strip())
    return cmd


@app.post("/congestion", response_model=CongestionResponse)
def set_congestion(cfg: CongestionRequest) -> CongestionResponse:
    algorithm = cfg.algorithm.strip().lower()
    applied: List[str] = []

    available = _sysctl_get_available()

    if algorithm not in available:
        raise HTTPException(
            status_code=400,
            detail=f"Algorithm '{algorithm}' not available. Available: {available}",
        )
    # Determine which namespaces to configure
    if cfg.namespace is None:
        namespaces = ["root", "ns1", "ns2"]
    elif cfg.namespace == "root":
        namespaces = ["root"]
    elif cfg.namespace in ("ns1", "ns2"):
        namespaces = [cfg.namespace]
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid namespace '{cfg.namespace}'. Use 'ns1', 'ns2', 'root', or null.",
        )

    for ns in namespaces:
        try:
            cmd = _apply_cca_in_ns(ns, algorithm)
            applied.append(cmd)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=500,
                detail=(f"Cannot set '{algorithm}' in namespace '{ns}': {exc}. "),
            )

    return CongestionResponse(
        current_algorithm=algorithm,
        available_algorithms=available,
        status="ok",
        applied_commands=applied,
    )


@app.get("/congestion", response_model=CongestionResponse)
def get_congestion(namespace: Optional[str] = None) -> CongestionResponse:
    ns = namespace if namespace else "root"
    current = _sysctl_get_cca(ns)
    available = _sysctl_get_available()

    return CongestionResponse(
        current_algorithm=current,
        available_algorithms=available,
        status="ok",
        applied_commands=[],
    )


@app.post("/ctp/fetch", response_model=CtpFetchResponse)
def fetch_ctp_endpoint(req: CtpFetchRequest) -> CtpFetchResponse:
    """Fetch download + upload PCAPs for a CTP pointer into the local CTP directory.

    The worker resolves *ctp_pointer*: HTTP(S) URL (including ``…/ctps/{id}/export``
    ZIP archives), absolute filesystem path, or plain base name.  It downloads or
    copies both PCAP files into::

        <ctp_root>/download/<name>.pcap
        <ctp_root>/upload/<name>.pcap

    On success the endpoint returns the resolved paths so the caller can confirm
    placement before issuing a ``POST /replay``.
    """
    from substrate.ctp_fetcher import fetch_ctp

    try:
        result = fetch_ctp(req.ctp_pointer, req.ctp_root)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Failed writing CTP files under CTP_DIR={CTP_DIR}: {exc}. "
                "Ensure the CTP directory is writable by substrate-worker."
            ),
        )

    return CtpFetchResponse(status="ok", **result)


@app.post("/run", response_model=RunExperimentResponse)
def run_experiment(req: RunExperimentRequest) -> RunExperimentResponse:
    """Apply shaping + congestion, then execute a workflow in a single call.

    Equivalent to calling ``POST /shape``, ``POST /congestion``, and running
    the netgent workflow runner in sequence.  When ``download_mbps`` or
    ``upload_mbps`` are not provided they default to 100 Mbps.
    """
    global CURRENT_BOTTLENECK_STATE, CURRENT_INTERFACES

    # 1. Apply shaping (skipped when download_mbps/upload_mbps are None,
    #    meaning the caller already shaped via POST /shape)
    if req.download_mbps is not None or req.upload_mbps is not None:
        dl = req.download_mbps or 100.0
        ul = req.upload_mbps or 100.0
        _validate_qdisc_request(req.qdisc, req.buffer_packets, req.qdisc_params)
        state = BottleneckState(
            download_mbps=dl,
            upload_mbps=ul,
            latency_ms=req.latency_ms,
            latency_location=req.latency_location,
            qdisc=req.qdisc,
            verified=False,
            buffer_packets=req.buffer_packets,
            qdisc_params=req.qdisc_params,
        )
        CURRENT_BOTTLENECK_STATE = state
        CURRENT_INTERFACES = {
            "downstream_iface": req.downstream_iface,
            "upstream_iface": req.upstream_iface,
        }
        try:
            apply_shaping(
                downstream_iface=req.downstream_iface,
                upstream_iface=req.upstream_iface,
                download_mbps=dl,
                upload_mbps=ul,
                latency_ms=req.latency_ms,
                qdisc=req.qdisc,
                buffer_packets=req.buffer_packets,
                qdisc_params=req.qdisc_params,
                latency_location=req.latency_location,
            )
        except subprocess.CalledProcessError as exc:
            CURRENT_BOTTLENECK_STATE = None
            CURRENT_INTERFACES = None
            raise HTTPException(status_code=500, detail=f"tc command failed: {exc}")
        except Exception as exc:
            CURRENT_BOTTLENECK_STATE = None
            CURRENT_INTERFACES = None
            raise HTTPException(status_code=500, detail=str(exc))

    # 2. Apply congestion control
    set_congestion(CongestionRequest(algorithm=req.cca, namespace=req.cca_namespace))

    # 3. Run workflow
    from clients.netgent.src.main import NetGent

    try:
        client = NetGent()
        result = client.run_workflow(
            req.workflow,
            type=req.runtime,
            parameters=req.parameters or {},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Workflow failed: {exc}")

    run_result = result.get("result", result) if isinstance(result, dict) else result
    return RunExperimentResponse(
        status="ok",
        runtime=req.runtime,
        result=run_result if isinstance(run_result, list) else [run_result],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("substrate.main:app", host="0.0.0.0", port=8002)
