import json
import os
import re
import subprocess
import threading
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

# Workflows dispatched via POST /run MUST traverse the shaped veth path inside
# ns1; otherwise the captured pcap on veth2 never sees the application traffic.
# Force the NetGent shell adapter to always wrap commands with
# `nsenter -- ip netns exec ns1 <cmd>` regardless of how the container env was
# set. We pin both the new (NETGENT_*) and legacy (USE_LOCAL / LINUX_NAMESPACE)
# env names before NetGent's execution module gets loaded, and then patch
# whatever execution-module instances already live in sys.modules so the
# override sticks even if something has already imported it.
os.environ["NETGENT_USE_LOCAL"] = "false"
os.environ["NETGENT_NAMESPACE"] = "ns1"
os.environ["USE_LOCAL"] = "false"
os.environ["LINUX_NAMESPACE"] = "ns1"

import sys as _sys

for _mod_name, _mod in list(_sys.modules.items()):
    if _mod is None:
        continue
    if _mod_name == "utils.execution" or _mod_name.endswith(".utils.execution"):
        if hasattr(_mod, "USE_LOCAL"):
            _mod.USE_LOCAL = False
        if hasattr(_mod, "LINUX_NAMESPACE"):
            _mod.LINUX_NAMESPACE = "ns1"

# ---------------------------------------------------------------------------
# Per-experiment shell-command deadline
# ---------------------------------------------------------------------------
# See main_local.py for the full rationale. We monkey-patch the NetGent
# shell-execution `run_subprocess` to honor a contextvars-scoped wallclock
# deadline. On timeout the process is SIGTERMed (2s grace) then SIGKILLed
# and a (124, partial_stdout, partial_stderr + "[terminated at deadline]")
# tuple is returned so downstream still gets a usable ProcessOutcome.
import contextvars as _contextvars
import importlib as _importlib

_netgent_exec = _importlib.import_module("utils.execution")

_SHELL_DEADLINE_SECONDS: "_contextvars.ContextVar[Optional[float]]" = (
    _contextvars.ContextVar("substrate_shell_deadline_seconds", default=None)
)
# Triggered flag uses a mutable list so the patched runner can signal back
# across asyncio.run() boundaries — NetGent runs the workflow in a fresh
# Context, and `.set(True)` inside that Context doesn't propagate up to the
# sync /run handler. Mutating a shared list does.
_SHELL_DEADLINE_TRIGGERED: "_contextvars.ContextVar[list]" = _contextvars.ContextVar(
    "substrate_shell_deadline_triggered", default=[False]
)

_orig_run_subprocess = _netgent_exec.run_subprocess


async def _run_subprocess_with_deadline(command):
    import asyncio

    deadline = _SHELL_DEADLINE_SECONDS.get()
    if deadline is None or deadline <= 0:
        return await _orig_run_subprocess(command)

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Keep dedicated reader tasks alive across the entire run so partial
    # stdout/stderr buffered in the pipe is still readable after we kill the
    # child. `communicate()` with wait_for() cancels its own internal readers
    # on timeout, which loses the buffered data — that's why we don't use it.
    stdout_task = asyncio.create_task(proc.stdout.read())
    stderr_task = asyncio.create_task(proc.stderr.read())

    async def _drain_and_return(returncode, deadline_hit):
        stdout_b = await stdout_task
        stderr_b = await stderr_task
        stderr_text = stderr_b.decode(errors="replace")
        if deadline_hit:
            stderr_text += "\n[terminated at experiment-duration deadline]\n"
        return returncode, stdout_b.decode(errors="replace"), stderr_text

    try:
        await asyncio.wait_for(proc.wait(), timeout=deadline)
        rc = proc.returncode if proc.returncode is not None else -1
        return await _drain_and_return(rc, deadline_hit=False)
    except asyncio.TimeoutError:
        # Mutate the shared list in place so the /run handler in the parent
        # context sees the flag set even though we're in a child asyncio Context.
        _SHELL_DEADLINE_TRIGGERED.get()[0] = True
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), 2.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        return await _drain_and_return(124, deadline_hit=True)


_netgent_exec.run_subprocess = _run_subprocess_with_deadline

app = FastAPI()

CURRENT_BOTTLENECK_STATE = None  # will hold a BottleneckState
CURRENT_INTERFACES = None  # {"downstream_iface": ..., "upstream_iface": ...}
ACTIVE_REPLAYS: dict = {}  # replay_id → session dict
ACTIVE_CAPTURES: dict = {}  # capture_id → session dict
ACTIVE_QTRACES: dict = {}  # qtrace_id → session dict

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

    verify: bool = Field(
        True,
        description=(
            "Run iperf3 + ping probes after applying tc rules to confirm the "
            "bottleneck landed. Default True because /shape's whole job is "
            "configure + validate. Pass false when calling /shape during a "
            "concurrent pcap capture (e.g. from the orchestrator's /intent "
            "pipeline) so the probes don't pollute the trace."
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


class QTraceRequest(BaseModel):
    """Start a background sampler that polls qdisc statistics into a JSONL file.

    Each sample produces one JSON line per interface with epoch timestamp,
    backlog (bytes + packets), cumulative bytes sent, drops, and overlimits.
    Sampling cadence is approximate — kernel `tc -s` parsing has ~sub-ms
    overhead and the loop sleeps for ``interval_ms``.
    """

    interfaces: List[str] = Field(
        default_factory=lambda: ["veth2", "veth4"],
        description="Interfaces to sample (bottleneck egress points).",
    )
    filename: str = Field(
        ..., description="Output JSONL basename (e.g., 'iperf3_10mbps_qtrace')"
    )
    interval_ms: int = Field(
        5,
        ge=1,
        le=1000,
        description="Sampling cadence in milliseconds (≥1; 5 ms is a good default).",
    )
    duration_seconds: Optional[int] = Field(
        None, description="Auto-stop after this many seconds (None = run until DELETE)."
    )


class QTraceResponse(BaseModel):
    qtrace_id: str
    status: str
    trace_path: str
    interfaces: List[str]
    interval_ms: int


class QTraceStatusResponse(BaseModel):
    qtrace_id: str
    status: str  # "running", "finished"
    trace_path: str
    interfaces: List[str]
    interval_ms: int
    start_time: str
    samples_written: int


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
    experiment_max_seconds: Optional[float] = Field(
        None,
        gt=0,
        description=(
            "Wallclock deadline (seconds, from the start of this /run call) for "
            "any shell command spawned by the workflow. On timeout the process "
            "is SIGTERMed (2s grace) then SIGKILLed; partial stdout/stderr are "
            "captured and the run still returns a result with "
            "terminated_at_deadline=True. Omit to let workflows run to natural "
            "completion (legacy behavior)."
        ),
    )
    verify_shaping: bool = Field(
        False,
        description=(
            "Run iperf3 + ping probes after applying shaping to verify the "
            "bottleneck state. Default False because the probes add ~10s of "
            "non-workflow traffic to any concurrent pcap capture. Use POST "
            "/shape (which always verifies) when you need verification."
        ),
    )


class RunExperimentResponse(BaseModel):
    status: str
    runtime: str
    result: List
    terminated_at_deadline: bool = Field(
        False,
        description=(
            "True iff any shell command in the workflow was force-terminated "
            "because it exceeded experiment_max_seconds."
        ),
    )


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


def _detect_wan_iface() -> Optional[str]:
    """Best-effort detection of the active IPv4 egress interface."""
    candidates = [
        "ip -4 route get 1.1.1.1 2>/dev/null | awk '/dev/ {for (i=1;i<=NF;i++) if ($i==\"dev\") {print $(i+1); exit}}'",
        "ip -4 route show default 2>/dev/null | awk '{print $5; exit}'",
    ]
    for cmd in candidates:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        iface = (res.stdout or "").strip()
        if iface:
            exists = (
                subprocess.run(f"test -d /sys/class/net/{iface}", shell=True).returncode
                == 0
            )
            if exists:
                return iface
    return None


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
    verify: bool = False,
) -> List[str]:
    applied: List[str] = []
    qdisc_args = _build_qdisc_args(qdisc, buffer_packets, qdisc_params)

    # -------------------------
    # Bandwidth shaping (HTB)
    # -------------------------
    iface_rates = [(downstream_iface, download_mbps), (upstream_iface, upload_mbps)]
    wan_iface = _detect_wan_iface()
    # With the bridged setup, internet egress can bypass veth4; enforce upload
    # shaping on WAN as well so ns1->internet upload is capped correctly.
    if wan_iface:
        iface_rates.append((wan_iface, upload_mbps))

    seen_ifaces = set()
    for iface, rate in iface_rates:
        if iface in seen_ifaces:
            continue
        seen_ifaces.add(iface)
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
    if verify:
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

    if verify:
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
                verify=cfg.verify,
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


# =========================
# Queue-occupancy trace (qtrace) — Option B: tc -s polling
# =========================

_QDISC_BACKLOG_RE = re.compile(r"backlog\s+(\d+)b\s+(\d+)p", re.IGNORECASE)
_QDISC_SENT_RE = re.compile(
    r"Sent\s+(\d+)\s+bytes\s+(\d+)\s+pkt\s+\(dropped\s+(\d+),\s+overlimits\s+(\d+)\s+requeues\s+(\d+)\)",
    re.IGNORECASE,
)


def _sample_qdisc(iface: str) -> Dict[str, Optional[int]]:
    """Snapshot the leaf qdisc stats for one interface.

    Parses ``tc -s -d qdisc show dev <iface>``. The leaf qdisc under the HTB
    class (e.g., ``fq_codel`` at handle ``10:`` under parent ``1:10``) is the
    one carrying the bottleneck queue — its `backlog` is what CCAnalyzer-style
    plots want.
    """
    try:
        out = subprocess.run(
            ["tc", "-s", "-d", "qdisc", "show", "dev", iface],
            capture_output=True,
            text=True,
            timeout=1,
        ).stdout
    except Exception:
        return {
            "backlog_bytes": None,
            "backlog_pkts": None,
            "bytes_sent": None,
            "pkts_sent": None,
            "drops": None,
            "overlimits": None,
        }

    # The output has one "qdisc ..." stanza per qdisc on the interface. We
    # prefer the leaf qdisc that lives under HTB class 1:10 — its line starts
    # with ``qdisc <name> 10:``. Fall back to the last stanza otherwise.
    stanzas: List[str] = []
    current: List[str] = []
    for line in out.splitlines():
        if line.startswith("qdisc "):
            if current:
                stanzas.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        stanzas.append("\n".join(current))

    chosen = None
    for s in stanzas:
        first = s.splitlines()[0] if s else ""
        if re.search(r"qdisc \S+ 10:", first):
            chosen = s
            break
    if chosen is None and stanzas:
        chosen = stanzas[-1]
    if chosen is None:
        return {
            "backlog_bytes": None,
            "backlog_pkts": None,
            "bytes_sent": None,
            "pkts_sent": None,
            "drops": None,
            "overlimits": None,
        }

    backlog_b = backlog_p = bytes_sent = pkts_sent = drops = overlimits = None
    m = _QDISC_BACKLOG_RE.search(chosen)
    if m:
        backlog_b, backlog_p = int(m.group(1)), int(m.group(2))
    m = _QDISC_SENT_RE.search(chosen)
    if m:
        bytes_sent = int(m.group(1))
        pkts_sent = int(m.group(2))
        drops = int(m.group(3))
        overlimits = int(m.group(4))
    return {
        "backlog_bytes": backlog_b,
        "backlog_pkts": backlog_p,
        "bytes_sent": bytes_sent,
        "pkts_sent": pkts_sent,
        "drops": drops,
        "overlimits": overlimits,
    }


def _qtrace_loop(
    qtrace_id: str,
    interfaces: List[str],
    interval_ms: int,
    trace_path: str,
    duration_seconds: Optional[int],
    stop_event: threading.Event,
) -> None:
    """Background sampler — runs until duration elapses or stop_event is set."""
    session = ACTIVE_QTRACES.get(qtrace_id)
    started = time.time()
    period = max(interval_ms, 1) / 1000.0
    samples = 0
    try:
        with open(trace_path, "a", buffering=1) as f:  # line-buffered
            while not stop_event.is_set():
                t = time.time()
                for iface in interfaces:
                    snap = _sample_qdisc(iface)
                    record = {"t": t, "iface": iface, **snap}
                    f.write(json.dumps(record) + "\n")
                samples += len(interfaces)
                if session is not None:
                    session["samples_written"] = samples
                if duration_seconds and (time.time() - started) >= duration_seconds:
                    break
                # Sleep without oversleeping past the next tick.
                next_tick = started + (samples // len(interfaces)) * period
                drift = max(0.0, next_tick - time.time())
                if drift > 0:
                    stop_event.wait(drift)
    finally:
        if session is not None:
            session["finished_at"] = datetime.utcnow().isoformat()


@app.post("/qtrace", response_model=QTraceResponse)
def start_qtrace(cfg: QTraceRequest) -> QTraceResponse:
    """Start a background qdisc-stats sampler.

    Captures backlog (bytes + packets) and cumulative drops/overlimits/sent on
    every requested interface every ``interval_ms`` milliseconds. The trace is
    streamed to ``CAPTURE_DIR/<filename>.jsonl`` as one JSON object per line.
    """
    if not (CAPTURE_DIR or "").strip():
        raise HTTPException(
            status_code=422,
            detail=("CAPTURE_DIR is empty. Set CAPTURE_DIR to a writable directory."),
        )
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    safe_name = os.path.basename(cfg.filename).strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="filename must be non-empty")

    available = _get_interfaces()
    for iface in cfg.interfaces:
        if iface not in available:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown interface '{iface}'. Available: {available}",
            )

    trace_path = os.path.join(CAPTURE_DIR, f"{safe_name}.jsonl")
    qtrace_id = str(uuid.uuid4())
    stop_event = threading.Event()

    session = {
        "qtrace_id": qtrace_id,
        "trace_path": trace_path,
        "interfaces": list(cfg.interfaces),
        "interval_ms": cfg.interval_ms,
        "start_time": datetime.utcnow().isoformat(),
        "stop_event": stop_event,
        "samples_written": 0,
        "duration_seconds": cfg.duration_seconds,
    }
    ACTIVE_QTRACES[qtrace_id] = session

    thread = threading.Thread(
        target=_qtrace_loop,
        kwargs=dict(
            qtrace_id=qtrace_id,
            interfaces=list(cfg.interfaces),
            interval_ms=cfg.interval_ms,
            trace_path=trace_path,
            duration_seconds=cfg.duration_seconds,
            stop_event=stop_event,
        ),
        daemon=True,
        name=f"qtrace-{qtrace_id[:8]}",
    )
    session["thread"] = thread
    thread.start()

    return QTraceResponse(
        qtrace_id=qtrace_id,
        status="started",
        trace_path=trace_path,
        interfaces=list(cfg.interfaces),
        interval_ms=cfg.interval_ms,
    )


@app.get("/qtrace/{qtrace_id}", response_model=QTraceStatusResponse)
def get_qtrace(qtrace_id: str) -> QTraceStatusResponse:
    session = ACTIVE_QTRACES.get(qtrace_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"QTrace not found: {qtrace_id}")
    thread: threading.Thread = session["thread"]
    status = "running" if thread.is_alive() else "finished"
    return QTraceStatusResponse(
        qtrace_id=qtrace_id,
        status=status,
        trace_path=session["trace_path"],
        interfaces=session["interfaces"],
        interval_ms=session["interval_ms"],
        start_time=session["start_time"],
        samples_written=session.get("samples_written", 0),
    )


@app.get("/qtrace/{qtrace_id}/trace")
def download_qtrace(
    qtrace_id: str,
    x_capture_download_token: Annotated[
        Optional[str], Header(alias="X-Capture-Download-Token")
    ] = None,
):
    """Download the JSONL trace for a finished qtrace session."""
    _require_capture_download_token(x_capture_download_token)
    session = ACTIVE_QTRACES.get(qtrace_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"QTrace not found: {qtrace_id}")
    thread: threading.Thread = session["thread"]
    if thread.is_alive():
        raise HTTPException(
            status_code=409,
            detail="QTrace still running; stop it (DELETE) before downloading.",
        )
    trace_path = session["trace_path"]
    if not os.path.isfile(trace_path):
        raise HTTPException(
            status_code=404, detail=f"Trace file not found at {trace_path}"
        )
    return FileResponse(
        trace_path,
        media_type="application/x-ndjson",
        filename=os.path.basename(trace_path),
    )


@app.delete("/qtrace/{qtrace_id}")
def stop_qtrace(qtrace_id: str):
    session = ACTIVE_QTRACES.get(qtrace_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"QTrace not found: {qtrace_id}")
    stop_event: threading.Event = session["stop_event"]
    thread: threading.Thread = session["thread"]
    stop_event.set()
    thread.join(timeout=5)
    samples = session.get("samples_written", 0)
    # Keep session metadata around so /qtrace/{id}/trace is still downloadable.
    return {
        "qtrace_id": qtrace_id,
        "status": "stopped",
        "samples_written": samples,
        "trace_path": session["trace_path"],
    }


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
                verify=req.verify_shaping,
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
    from main import NetGent

    # Use a fresh mutable list so a stale flag from a prior request can't
    # leak into this one (FastAPI runs sync endpoints in a threadpool —
    # each thread is reused; ContextVars persist across requests on the
    # same thread otherwise).
    triggered_box: list[bool] = [False]
    triggered_token = _SHELL_DEADLINE_TRIGGERED.set(triggered_box)
    deadline_token = None
    if req.experiment_max_seconds:
        deadline_token = _SHELL_DEADLINE_SECONDS.set(float(req.experiment_max_seconds))

    try:
        client = NetGent(
            cdp_url=os.environ.get("BROWSERLESS_WS_ENDPOINT", "").strip() or None,
            headless=True,
        )
        result = client.run_workflow(
            req.workflow,
            type=req.runtime,
            parameters=req.parameters or {},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Workflow failed: {exc}")
    finally:
        terminated_at_deadline = bool(triggered_box[0])
        _SHELL_DEADLINE_TRIGGERED.reset(triggered_token)
        if deadline_token is not None:
            _SHELL_DEADLINE_SECONDS.reset(deadline_token)

    run_result = result.get("result", result) if isinstance(result, dict) else result
    return RunExperimentResponse(
        status="ok",
        runtime=req.runtime,
        result=run_result if isinstance(run_result, list) else [run_result],
        terminated_at_deadline=terminated_at_deadline,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("substrate.main:app", host="0.0.0.0", port=8002)
