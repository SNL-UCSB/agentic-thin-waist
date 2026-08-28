#!/usr/bin/env python3
"""Run one Google Meet receiver and collect real inbound WebRTC QoE."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


# Edit these values, or set GOOGLE_MEET_PROFILE_DIR in your shell.
GOOGLE_MEET_URL = "https://meet.google.com/duz-aezo-ztr"
GOOGLE_MEET_PROFILE_DIR = os.environ.get("GOOGLE_MEET_PROFILE_DIR", "")
DURATION_SECONDS = 15
JOIN_TIMEOUT_SECONDS = 180
VIDEO_QOE_IMAGE = "video-qoe-collector:latest"

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULT_DIR = REPO_ROOT / "experiments" / "google_meet_qoe_smoke" / "results"
OUTPUT_FILE = RESULT_DIR / "google_meet_stats.jsonl"


def resolve_profile() -> Path:
    if not GOOGLE_MEET_PROFILE_DIR.strip():
        raise RuntimeError(
            "Set GOOGLE_MEET_PROFILE_DIR to a persistent Linux Chrome profile "
            "that is already logged into the receiver Google account."
        )
    profile = Path(GOOGLE_MEET_PROFILE_DIR).expanduser().resolve()
    if not profile.is_dir():
        raise RuntimeError(f"Chrome profile directory does not exist: {profile}")
    try:
        profile.relative_to(REPO_ROOT)
    except ValueError:
        return profile
    raise RuntimeError(
        "The authenticated Chrome profile must be outside the repository: "
        f"{profile}"
    )


def read_samples() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in OUTPUT_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    profile = resolve_profile()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.unlink(missing_ok=True)

    jobs = [
        {
            "app": "google_meet",
            "url": GOOGLE_MEET_URL,
            "display_num": 99,
            "out_path": "/out/google_meet_stats.jsonl",
            "duration_seconds": DURATION_SECONDS,
            "sample_interval_seconds": 1.0,
            "user_data_dir": "/profiles/google-meet",
            "join_timeout_seconds": JOIN_TIMEOUT_SECONDS,
        }
    ]
    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/amd64",
        "--shm-size",
        "2g",
        "--env",
        f"JOBS={json.dumps(jobs)}",
        "--volume",
        f"{RESULT_DIR}:/out",
        "--volume",
        f"{profile}:/profiles/google-meet",
        VIDEO_QOE_IMAGE,
    ]
    subprocess.run(command, check=True)

    samples = read_samples()
    stats = [sample.get("stats") or {} for sample in samples]
    valid = [
        item
        for item in stats
        if item.get("source") == "webrtc_inbound_rtp"
        and item.get("inbound_video_stream_count", 0) > 0
    ]
    frames = [item.get("frames_decoded", 0) for item in valid]
    received_bytes = [item.get("bytes_received", 0) for item in valid]
    if len(valid) < 2 or max(frames) <= min(frames) or max(received_bytes) <= min(
        received_bytes
    ):
        raise RuntimeError(
            "Smoke test did not observe advancing remote inbound video. "
            "Local preview metrics are intentionally rejected."
        )

    final = valid[-1]
    print(f"QoE JSONL: {OUTPUT_FILE}")
    print(
        json.dumps(
            {
                "samples": len(valid),
                "measurement_source": final.get("source"),
                "resolution": final.get("resolution"),
                "inbound_bitrate_mbps": final.get("inbound_bitrate_mbps"),
                "packets_lost": final.get("packets_lost"),
                "jitter_seconds": final.get("jitter_seconds"),
                "frames_decoded": final.get("frames_decoded"),
                "frames_dropped": final.get("frames_dropped"),
                "freeze_count": final.get("freeze_count"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
