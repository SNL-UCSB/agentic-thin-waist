#!/usr/bin/env python3
"""Run YouTube and Google Meet concurrently on one Thin Waist bottleneck."""

from __future__ import annotations

import argparse
import json
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
# EDIT THESE VALUES TO CHANGE THE BOTTLENECK QUEUE.
# ---------------------------------------------------------------------------
BOTTLENECK_CAPACITY_MBPS = 5
BOTTLENECK_LATENCY_MS = 100
BOTTLENECK_QUEUE = "pfifo"
BOTTLENECK_BUFFER_PACKETS = 50
EXPERIMENT_DURATION_SECONDS = 30

YOUTUBE_URL = "https://www.youtube.com/watch?v=eOrNdBpGMv8&autoplay=1&mute=1"
# Replace this when the test meeting changes. It must be accessible to the
# collector without manual host admission for an unattended run.
GOOGLE_MEET_URL = "https://meet.google.com/duz-aezo-ztr"

VIDEO_URLS: dict[str, str] = {
    "youtube": YOUTUBE_URL,
    "google_meet": GOOGLE_MEET_URL,
}
DISPLAY_NUMS: dict[str, int] = {"youtube": 99, "google_meet": 100}


def build_experiment(
    capacity_mbps: int,
    duration_seconds: int,
    latency_ms: int,
    qdisc: str,
    buffer_packets: int,
) -> dict[str, Any]:
    return {
        "experiment_id": (
            f"youtube-google-meet-{capacity_mbps}mbps-{latency_ms}ms-{qdisc}"
        ),
        "applications": ["youtube", "google_meet"],
        "execution_mode": "concurrent",
        "capacity_mbps": capacity_mbps,
        "upload_mbps": capacity_mbps,
        "latency_ms": latency_ms,
        "latency_location": "upstream",
        "aqm_policy": qdisc,
        "buffer_packets": buffer_packets,
        "cc_algorithm": "cubic",
        "duration_seconds": duration_seconds,
        "urls": VIDEO_URLS,
    }


def result_dir_for(capacity_mbps: int, latency_ms: int, qdisc: str) -> Path:
    return (
        REPO_ROOT
        / "experiments"
        / f"youtube_google_meet_{latency_ms}ms_{qdisc}"
        / "results"
        / f"{capacity_mbps}mbps"
    )


def main(
    capacity_mbps: int = BOTTLENECK_CAPACITY_MBPS,
    duration_seconds: int = EXPERIMENT_DURATION_SECONDS,
    latency_ms: int = BOTTLENECK_LATENCY_MS,
    qdisc: str = BOTTLENECK_QUEUE,
    buffer_packets: int = BOTTLENECK_BUFFER_PACKETS,
) -> int:
    experiment = build_experiment(
        capacity_mbps,
        duration_seconds,
        latency_ms,
        qdisc,
        buffer_packets,
    )
    result_dir = result_dir_for(capacity_mbps, latency_ms, qdisc)
    result_dir.mkdir(parents=True, exist_ok=True)

    for artifact_name in (
        "youtube_stats.jsonl",
        "google_meet_stats.jsonl",
        f"{experiment['experiment_id']}.pcap",
        "failure.log",
    ):
        (result_dir / artifact_name).unlink(missing_ok=True)
    write_json(result_dir / "experiment.json", experiment)

    container = f"youtube-google-meet-direct-{uuid.uuid4().hex[:8]}"
    ctp_temp = tempfile.TemporaryDirectory(prefix="youtube-google-meet-ctp-")
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
            f"{capacity_mbps} Mbps / {latency_ms} ms / {qdisc} "
            f"({buffer_packets} packets)"
        )
        shaping = request_json(
            "POST",
            f"{endpoint}/shape",
            {
                "upstream_iface": "veth4",
                "downstream_iface": "veth2",
                "download_mbps": capacity_mbps,
                "upload_mbps": experiment["upload_mbps"],
                "latency_ms": latency_ms,
                "latency_location": experiment["latency_location"],
                "qdisc": qdisc,
                "buffer_packets": buffer_packets,
            },
        )
        write_json(result_dir / "shaping.json", shaping)
        if shaping.get("status") != "shaped":
            raise RuntimeError(f"unexpected shaping response: {shaping}")
        request_json(
            "POST",
            f"{endpoint}/congestion",
            {"algorithm": experiment["cc_algorithm"], "namespace": "ns1"},
        )

        print("3/5 starting one shared packet capture")
        capture = request_json(
            "POST",
            f"{endpoint}/capture",
            {
                "interface": "veth2",
                "capture_filter": "",
                "filename": experiment["experiment_id"],
                "duration_seconds": max(240, duration_seconds + 60),
            },
        )
        capture_id = capture["capture_id"]
        time.sleep(1)

        print(
            "4/5 playing YouTube and Google Meet concurrently "
            "(SeleniumBase + undetected-chromedriver)"
        )
        run_video_collectors_concurrently(
            container,
            result_dir,
            duration_seconds,
            video_urls=VIDEO_URLS,
            display_nums=DISPLAY_NUMS,
        )

        summaries: dict[str, Any] = {}
        for app in VIDEO_URLS:
            summary = summarize_stats_jsonl(result_dir / f"{app}_stats.jsonl")
            if summary["sample_count"] == 0:
                raise RuntimeError(f"{app} produced no QoE samples")
            if not summary["advanced"]:
                raise RuntimeError(
                    f"{app} playback never advanced past t=0: {summary}"
                )
            summaries[app] = summary

        print("5/5 finalizing the shared capture")
        request_json("DELETE", f"{endpoint}/capture/{capture_id}", timeout=15)
        capture_id = None
        pcap = result_dir / f"{experiment['experiment_id']}.pcap"
        if not pcap.is_file() or pcap.stat().st_size <= 24:
            raise RuntimeError(f"PCAP is missing or empty: {pcap}")
        (result_dir / "failure.log").unlink(missing_ok=True)

        print(f"PCAP:           {pcap}")
        print(f"YouTube QoE:    {result_dir / 'youtube_stats.jsonl'}")
        print(f"Google Meet QoE: {result_dir / 'google_meet_stats.jsonl'}")
        print(json.dumps(summaries, indent=2))
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capacity-mbps",
        type=int,
        default=BOTTLENECK_CAPACITY_MBPS,
        help="Shared bottleneck capacity",
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=EXPERIMENT_DURATION_SECONDS,
        help="QoE collection window",
    )
    parser.add_argument(
        "--latency-ms",
        type=int,
        default=BOTTLENECK_LATENCY_MS,
        help="Configured one-way base latency",
    )
    parser.add_argument(
        "--qdisc",
        choices=("pfifo", "fq_codel", "codel"),
        default=BOTTLENECK_QUEUE,
        help="Bottleneck queue discipline",
    )
    parser.add_argument(
        "--buffer-packets",
        type=int,
        default=BOTTLENECK_BUFFER_PACKETS,
        help="Queue packet limit",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(
        main(
            capacity_mbps=args.capacity_mbps,
            duration_seconds=args.duration_seconds,
            latency_ms=args.latency_ms,
            qdisc=args.qdisc,
            buffer_packets=args.buffer_packets,
        )
    )
