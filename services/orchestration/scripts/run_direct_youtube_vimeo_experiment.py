#!/usr/bin/env python3
"""Run YouTube and Vimeo concurrently on one fixed Thin Waist bottleneck."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
IMAGE = "agentic-thin-waist-substrate-worker:latest"

# Headless Chromium-over-CDP (Playwright via browserless) plays YouTube fine,
# but Vimeo's MediaSource ("blob:" src) pipeline never advances through that
# path: <video>.readyState stays at HAVE_NOTHING for the whole run regardless
# of bandwidth or background-tab-throttling flags. The proven fix (see PR #6
# in netgent-dev, commit 924441e) is a real, Xvfb-rendered Chrome driven via
# SeleniumBase + undetected-chromedriver. video-qoe-collector:latest
# (services/orchestration/scripts/selenium_video_qoe/) reproduces that
# mechanism for both apps. The collector uses nsenter to join the substrate
# worker's shaped ns1 namespace, so both browsers traverse the same bottleneck.
VIDEO_QOE_IMAGE = "video-qoe-collector:latest"

VIDEO_URLS: dict[str, str] = {
    "youtube": "https://www.youtube.com/watch?v=dQw4w9WgXcQ&autoplay=1&mute=1",
    "vimeo": "https://player.vimeo.com/video/911411289?autoplay=1&muted=1",
}

# Running the two apps as two separate *containers* sharing one network
# namespace (Docker's --network container:X) was tried first and rejected:
# even with distinct X displays, the two undetected-chromedriver sessions
# cross-attached to each other's Chrome (confirmed empirically - one
# container's output file ended up containing the other app's URL/platform).
# Sharing a network namespace also shares the whole loopback port space, and
# chromedriver's port allocation across that boundary isn't reliable. Both
# apps run as sibling threads inside ONE video-qoe-collector container
# instead - the normal, well-supported way to drive multiple Selenium
# sessions concurrently - which avoids that class of bug entirely and matches
# how PR #6's own reference actually did it (one process, DISPLAY=:99/:100).
DISPLAY_NUMS: dict[str, int] = {"youtube": 99, "vimeo": 100}


def docker(*args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["docker", *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.stdout.strip()


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {body}") from exc


def wait_for_worker(endpoint: str) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            request_json("GET", f"{endpoint}/health", timeout=3)
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("substrate worker did not become healthy within 120 seconds")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def build_experiment(capacity_mbps: int, duration_seconds: int) -> dict[str, Any]:
    return {
        "experiment_id": f"youtube-vimeo-{capacity_mbps}mbps-100ms-pfifo",
        "applications": ["youtube", "vimeo"],
        "execution_mode": "concurrent",
        "capacity_mbps": capacity_mbps,
        "upload_mbps": capacity_mbps,
        "latency_ms": 100,
        "latency_location": "upstream",
        "aqm_policy": "pfifo",
        "buffer_packets": 50,
        "cc_algorithm": "cubic",
        "duration_seconds": duration_seconds,
    }


def result_dir_for(capacity_mbps: int) -> Path:
    return (
        REPO_ROOT
        / "experiments"
        / "youtube_vimeo_100ms_pfifo"
        / "results"
        / f"{capacity_mbps}mbps"
    )


def run_video_collectors_concurrently(
    network_container: str,
    result_dir: Any,
    duration_seconds: int,
    video_urls: dict[str, str] | None = None,
    display_nums: dict[str, int] | None = None,
    job_options: dict[str, dict[str, Any]] | None = None,
    volume_mounts: list[str] | None = None,
) -> None:
    """Play multiple video applications as sibling threads inside one
    video-qoe-collector container, network-namespace-joined onto ns1 (the
    substrate worker's client-side namespace) so traffic is actually shaped
    and captured. Writes {app}_stats.jsonl per app into result_dir.

    Network shaping and capture in this harness only see traffic flowing
    between ns1 and ns2 (apply_shaping()/_verify_bottleneck_state() in
    main_local.py validate shaping with `ip netns exec ns1 iperf3 ...`).
    Docker's `--network container:X` only shares X's ROOT namespace, not ns1
    - confirmed empirically, a collector container run that way produced a
    pcap with zero real packets. ns1 is a named namespace anchored by a
    `sleep infinity` process (services/substrate-worker/.../setup_local.sh),
    whose PID is recorded at /var/run/substrate/ns1.pid *inside* the
    substrate worker container. Since that container now runs with
    --pid host, the PID it sees is already the shared PID-namespace value,
    so nsenter can join that exact network namespace directly from here.
    """
    video_urls = video_urls or VIDEO_URLS
    display_nums = display_nums or DISPLAY_NUMS
    job_options = job_options or {}
    volume_mounts = volume_mounts or []

    ns1_pid = docker(
        "exec", network_container, "cat", "/var/run/substrate/ns1.pid"
    ).strip()
    if not ns1_pid.isdigit():
        raise RuntimeError(f"could not resolve ns1 anchor PID: {ns1_pid!r}")

    jobs = []
    for app, url in video_urls.items():
        job = {
            "app": app,
            "url": url,
            "display_num": display_nums[app],
            "out_path": f"/out/{app}_stats.jsonl",
            "duration_seconds": duration_seconds,
            "sample_interval_seconds": 1.0,
        }
        job.update(job_options.get(app, {}))
        jobs.append(job)

    docker_args = [
        "run",
        "--rm",
        "--platform",
        "linux/amd64",
        "--privileged",
        "--pid",
        "host",
        # nsenter below only swaps the network namespace, not this
        # container's own /etc/resolv.conf. ns1 has no route back to
        # Docker's embedded DNS resolver, only out to the real internet (see
        # setup_local.sh, which points ns1 at 8.8.8.8) - match that here.
        "--dns",
        "8.8.8.8",
        "--env",
        f"JOBS={json.dumps(jobs)}",
        "--volume",
        f"{result_dir}:/out",
    ]
    for volume_mount in volume_mounts:
        docker_args.extend(["--volume", volume_mount])
    docker_args.extend(
        [
            "--entrypoint",
            "nsenter",
            VIDEO_QOE_IMAGE,
            f"--net=/proc/{ns1_pid}/ns/net",
            "--",
            "python3",
            "collect.py",
        ]
    )
    collector_output = docker(*docker_args)
    if collector_output:
        print(collector_output)


def summarize_stats_jsonl(path: Any) -> dict[str, Any]:
    """Summarize a {app}_stats.jsonl file written by video-qoe-collector."""
    samples: list[dict[str, Any]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    stats = [s.get("stats") or {} for s in samples]
    is_google_meet = any(s.get("platform") == "google_meet" for s in stats)
    progress_field = "frames_decoded" if is_google_meet else "current_time_secs"
    times = [s[progress_field] for s in stats if s.get(progress_field) is not None]
    resolutions = sorted(
        {s["resolution"] for s in stats if s.get("resolution") and s["resolution"] != "0x0"}
    )
    summary = {
        "sample_count": len(samples),
        "advanced": bool(times) and max(times) > (times[0] if times else 0),
        "progress_field": progress_field,
        "progress_range": [min(times), max(times)] if times else None,
        "resolutions_observed": resolutions,
        "final_resolution": stats[-1].get("resolution") if stats else None,
    }
    # Preserve the original field for existing YouTube/Vimeo consumers.
    if not is_google_meet:
        summary["current_time_range"] = summary["progress_range"]
    else:
        summary.update(
            {
                "measurement_source": "webrtc_inbound_rtp",
                "final_inbound_bitrate_mbps": stats[-1].get(
                    "inbound_bitrate_mbps"
                )
                if stats
                else None,
                "final_packets_lost": stats[-1].get("packets_lost")
                if stats
                else None,
                "final_frames_dropped": stats[-1].get("frames_dropped")
                if stats
                else None,
                "final_freeze_count": stats[-1].get("freeze_count")
                if stats
                else None,
            }
        )
    return summary


def main(capacity_mbps: int = 3, duration_seconds: int = 15) -> int:
    experiment = build_experiment(capacity_mbps, duration_seconds)
    result_dir = result_dir_for(capacity_mbps)

    result_dir.mkdir(parents=True, exist_ok=True)
    for artifact_name in (
        "youtube_stats.jsonl",
        "vimeo_stats.jsonl",
        f"{experiment['experiment_id']}.pcap",
        "failure.log",
    ):
        (result_dir / artifact_name).unlink(missing_ok=True)
    write_json(result_dir / "experiment.json", experiment)

    container = f"youtube-vimeo-direct-{uuid.uuid4().hex[:8]}"
    ctp_temp = tempfile.TemporaryDirectory(prefix="youtube-vimeo-direct-ctp-")
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
            # Shared with the video-qoe-collector container below so its PID
            # numbers line up with the ones this container sees for its own
            # ns1 anchor process - see run_video_collectors_concurrently().
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
            f"2/5 shaping once: {capacity_mbps} Mbps / 100 ms / pfifo (50 packets)"
        )
        shaping = request_json(
            "POST",
            f"{endpoint}/shape",
            {
                "upstream_iface": "veth4",
                "downstream_iface": "veth2",
                "download_mbps": experiment["capacity_mbps"],
                "upload_mbps": experiment["upload_mbps"],
                "latency_ms": experiment["latency_ms"],
                "latency_location": experiment["latency_location"],
                "qdisc": experiment["aqm_policy"],
                "buffer_packets": experiment["buffer_packets"],
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
            "4/5 playing YouTube and Vimeo concurrently "
            "(SeleniumBase + undetected-chromedriver)"
        )
        run_video_collectors_concurrently(container, result_dir, duration_seconds)

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

        print(f"PCAP:        {pcap}")
        print(f"YouTube QoE: {result_dir / 'youtube_stats.jsonl'}")
        print(f"Vimeo QoE:   {result_dir / 'vimeo_stats.jsonl'}")
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
        "--capacity-mbps", type=int, default=3, help="Shared bottleneck capacity"
    )
    parser.add_argument(
        "--duration-seconds", type=int, default=15, help="QoE collection window"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(main(args.capacity_mbps, args.duration_seconds))
