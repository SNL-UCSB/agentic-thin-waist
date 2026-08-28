#!/usr/bin/env python3
"""Run one Google Meet receiver through a shaped Thin Waist bottleneck."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from run_direct_youtube_vimeo_experiment import (
    IMAGE,
    REPO_ROOT,
    docker,
    request_json,
    run_video_collectors_concurrently,
    summarize_stats_jsonl,
    wait_for_worker,
    write_json,
)


# ---------------------------------------------------------------------------
# EDIT THESE VALUES TO CHANGE THE EXPERIMENT.
# ---------------------------------------------------------------------------
BOTTLENECK_CAPACITY_MBPS = 100
BOTTLENECK_LATENCY_MS = 100
BOTTLENECK_QUEUE = "pfifo"
BOTTLENECK_BUFFER_PACKETS = 50
EXPERIMENT_DURATION_SECONDS = 15

GOOGLE_MEET_URL = os.environ.get("GOOGLE_MEET_URL", "")
GOOGLE_MEET_GUEST_NAME = os.environ.get(
    "GOOGLE_MEET_GUEST_NAME", "NetGent QoE Collector"
)
GOOGLE_MEET_PROFILE_DIR = os.environ.get("GOOGLE_MEET_PROFILE_DIR", "")
GOOGLE_MEET_JOIN_TIMEOUT_SECONDS = 180


def resolve_profile() -> Path | None:
    if not GOOGLE_MEET_PROFILE_DIR.strip():
        return None
    profile = Path(GOOGLE_MEET_PROFILE_DIR).expanduser().resolve()
    if not profile.is_dir():
        raise RuntimeError(f"Chrome profile directory does not exist: {profile}")
    try:
        profile.relative_to(REPO_ROOT)
    except ValueError:
        return profile
    raise RuntimeError("The authenticated Chrome profile must be outside the repository")


def main() -> int:
    if not GOOGLE_MEET_URL.strip():
        raise RuntimeError("Set GOOGLE_MEET_URL to the room URL")

    profile = resolve_profile()
    experiment_id = (
        f"google-meet-{BOTTLENECK_CAPACITY_MBPS}mbps-"
        f"{BOTTLENECK_LATENCY_MS}ms-{BOTTLENECK_QUEUE}"
    )
    experiment: dict[str, Any] = {
        "experiment_id": experiment_id,
        "applications": ["google_meet"],
        "execution_mode": "single",
        "capacity_mbps": BOTTLENECK_CAPACITY_MBPS,
        "upload_mbps": BOTTLENECK_CAPACITY_MBPS,
        "latency_ms": BOTTLENECK_LATENCY_MS,
        "latency_location": "upstream",
        "aqm_policy": BOTTLENECK_QUEUE,
        "buffer_packets": BOTTLENECK_BUFFER_PACKETS,
        "cc_algorithm": "cubic",
        "duration_seconds": EXPERIMENT_DURATION_SECONDS,
        "google_meet_qoe_source": "webrtc_inbound_rtp",
    }
    result_dir = (
        REPO_ROOT
        / "experiments"
        / f"google_meet_{BOTTLENECK_LATENCY_MS}ms_{BOTTLENECK_QUEUE}"
        / "results"
        / f"{BOTTLENECK_CAPACITY_MBPS}mbps"
    )
    result_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "google_meet_stats.jsonl",
        f"{experiment_id}.pcap",
        "failure.log",
    ):
        (result_dir / name).unlink(missing_ok=True)
    write_json(result_dir / "experiment.json", experiment)

    container = f"google-meet-direct-{uuid.uuid4().hex[:8]}"
    ctp_temp = tempfile.TemporaryDirectory(prefix="google-meet-direct-ctp-")
    capture_id: str | None = None
    endpoint: str | None = None
    failed = False

    try:
        print("1/5 creating one ephemeral substrate worker")
        docker(
            "run",
            "--detach",
            "--rm",
            "--privileged",
            "--pid",
            "host",
            "--name",
            container,
            "--publish",
            "127.0.0.1::8002",
            "--env",
            "CONNECTIVITY_BACKEND=local_docker",
            "--env",
            "CAPTURE_DIR=/out",
            "--env",
            "CTP_DIR=/ctp",
            "--env",
            "NETGENT_USE_LOCAL=false",
            "--env",
            "NETGENT_NAMESPACE=ns1",
            "--env",
            "TIMEOUT=300000",
            "--volume",
            f"{result_dir}:/out",
            "--volume",
            f"{ctp_temp.name}:/ctp",
            "--volume",
            f"{REPO_ROOT / 'shared'}:/shared:ro",
            "--volume",
            (
                f"{REPO_ROOT / 'services/substrate-worker/src/substrate/main_local.py'}:"
                "/app/src/substrate/main_local.py:ro"
            ),
            IMAGE,
        )
        published = docker("port", container, "8002/tcp").splitlines()[0]
        endpoint = f"http://127.0.0.1:{published.rsplit(':', 1)[-1]}"
        wait_for_worker(endpoint)

        print(
            "2/5 shaping once: "
            f"{BOTTLENECK_CAPACITY_MBPS} Mbps / {BOTTLENECK_LATENCY_MS} ms / "
            f"{BOTTLENECK_QUEUE} ({BOTTLENECK_BUFFER_PACKETS} packets)"
        )
        shaping = request_json(
            "POST",
            f"{endpoint}/shape",
            {
                "upstream_iface": "veth4",
                "downstream_iface": "veth2",
                "download_mbps": BOTTLENECK_CAPACITY_MBPS,
                "upload_mbps": BOTTLENECK_CAPACITY_MBPS,
                "latency_ms": BOTTLENECK_LATENCY_MS,
                "latency_location": "upstream",
                "qdisc": BOTTLENECK_QUEUE,
                "buffer_packets": BOTTLENECK_BUFFER_PACKETS,
            },
        )
        write_json(result_dir / "shaping.json", shaping)
        if shaping.get("status") != "shaped":
            raise RuntimeError(f"unexpected shaping response: {shaping}")
        request_json(
            "POST",
            f"{endpoint}/congestion",
            {"algorithm": "cubic", "namespace": "ns1"},
        )

        print("3/5 starting packet capture on the bottleneck")
        capture = request_json(
            "POST",
            f"{endpoint}/capture",
            {
                "interface": "veth2",
                "capture_filter": "",
                "filename": experiment_id,
                "duration_seconds": 240,
            },
        )
        capture_id = capture["capture_id"]
        time.sleep(1)

        print("4/5 joining Google Meet and collecting inbound WebRTC QoE")
        job_options: dict[str, dict[str, Any]] = {
            "google_meet": {
                "guest_name": GOOGLE_MEET_GUEST_NAME,
                "join_timeout_seconds": GOOGLE_MEET_JOIN_TIMEOUT_SECONDS,
            }
        }
        volumes: list[str] = []
        if profile is not None:
            job_options["google_meet"]["user_data_dir"] = "/profiles/google-meet"
            volumes.append(f"{profile}:/profiles/google-meet")
        run_video_collectors_concurrently(
            container,
            result_dir,
            EXPERIMENT_DURATION_SECONDS,
            video_urls={"google_meet": GOOGLE_MEET_URL},
            display_nums={"google_meet": 99},
            job_options=job_options,
            volume_mounts=volumes,
        )

        summary = summarize_stats_jsonl(result_dir / "google_meet_stats.jsonl")
        if summary["sample_count"] == 0 or not summary["advanced"]:
            raise RuntimeError(f"Google Meet inbound video did not advance: {summary}")

        print("5/5 finalizing packet capture")
        request_json("DELETE", f"{endpoint}/capture/{capture_id}", timeout=15)
        capture_id = None
        pcap = result_dir / f"{experiment_id}.pcap"
        if not pcap.is_file() or pcap.stat().st_size <= 24:
            raise RuntimeError(f"PCAP is missing or empty: {pcap}")
        (result_dir / "failure.log").unlink(missing_ok=True)
        print(f"PCAP:           {pcap}")
        print(f"Google Meet QoE: {result_dir / 'google_meet_stats.jsonl'}")
        print(json.dumps(summary, indent=2))
        return 0
    except Exception as exc:
        failed = True
        print(f"FAILED: {exc}")
        return 1
    finally:
        if capture_id and endpoint:
            try:
                request_json("DELETE", f"{endpoint}/capture/{capture_id}", timeout=15)
            except Exception:
                pass
        if failed:
            logs = docker("logs", container, check=False)
            (result_dir / "failure.log").write_text(logs + "\n", encoding="utf-8")
        docker("rm", "--force", container, check=False)
        ctp_temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
