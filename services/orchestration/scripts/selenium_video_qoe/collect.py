#!/usr/bin/env python3
"""Play one or more video URLs in real (headed, Xvfb-rendered) Chrome and
sample QoE.

Headless CDP-over-Playwright works fine for YouTube but Vimeo's MSE ("blob:"
src) pipeline never advances through that path. The proven fix (see PR #6 in
netgent-dev) is SeleniumBase + undetected-chromedriver driving a real,
non-headless google-chrome-stable rendered onto an Xvfb virtual display with
a window manager (fluxbox). This script reproduces that mechanism.

Running two apps as two separate *containers* that share one network
namespace (Docker's `--network container:X`) was tried first and rejected:
even with distinct X displays, the two undetected-chromedriver sessions
cross-attached to each other's Chrome (confirmed empirically - QoE samples
from one container's URL showed up in the other's output file). Sharing a
network namespace also shares the whole loopback port space, and chromedriver
port allocation across that boundary isn't reliable. Running multiple jobs as
sibling *threads* within one process/container - the normal, well-supported
way to drive several Selenium sessions concurrently - avoids that class of
bug entirely, and matches how PR #6's own reference actually did it (one
process, DISPLAY=:99 and :100 for the two apps).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

# Runs in the page. Detects YouTube vs. a generic <video> element (Vimeo
# falls into the generic branch - that's exactly what worked in PR #6).
STATS_JS = r"""
const host = location.hostname || '';

function youtubeStats() {
    const player = document.getElementById('movie_player')
        || document.querySelector('.html5-video-player');
    const video = document.querySelector('video');
    if (!player && !video) { return {platform: 'youtube', error: 'no_player'}; }

    const out = {platform: 'youtube'};
    try {
        if (player && typeof player.getStatsForNerds === 'function') {
            Object.assign(out, player.getStatsForNerds());
        }
    } catch (e) { out.stats_for_nerds_error = String(e); }

    try {
        if (player && typeof player.getVideoData === 'function') {
            const d = player.getVideoData();
            out.video_id = d && d.video_id;
            out.title = d && d.title;
        }
        if (player && typeof player.getCurrentTime === 'function') {
            out.current_time_secs = player.getCurrentTime();
        }
        if (player && typeof player.getDuration === 'function') {
            out.duration_secs = player.getDuration();
        }
        if (player && typeof player.getVideoLoadedFraction === 'function') {
            out.loaded_fraction = player.getVideoLoadedFraction();
        }
        if (player && typeof player.getPlayerState === 'function') {
            out.player_state = player.getPlayerState();
        }
    } catch (e) { out.player_data_error = String(e); }

    addVideoElementStats(out, video);
    return out;
}

function addVideoElementStats(out, video) {
    try {
        if (!video) { return; }
        out.video_width = video.videoWidth;
        out.video_height = video.videoHeight;
        out.resolution = video.videoWidth + 'x' + video.videoHeight;
        out.playback_rate = video.playbackRate;
        out.paused = video.paused;
        out.muted = video.muted;
        out.volume = video.volume;
        out.current_time_secs = out.current_time_secs != null
            ? out.current_time_secs : video.currentTime;
        if (video.buffered && video.buffered.length) {
            const end = video.buffered.end(video.buffered.length - 1);
            out.buffer_ahead_secs = Math.max(0, end - video.currentTime);
        }
        if (typeof video.getVideoPlaybackQuality === 'function') {
            const q = video.getVideoPlaybackQuality();
            out.dropped_video_frames = q.droppedVideoFrames;
            out.total_video_frames = q.totalVideoFrames;
        }
    } catch (e) { out.video_element_error = String(e); }
}

if (host.indexOf('youtube.com') !== -1 || host.indexOf('youtu.be') !== -1) {
    return youtubeStats();
}
const video = document.querySelector('video');
if (!video) { return {platform: 'unknown', error: 'no_video'}; }
const out = {
    platform: host.indexOf('meet.google.com') !== -1 ? 'google_meet' : 'unknown'
};
addVideoElementStats(out, video);
return out;
"""


def start_display(dnum: str) -> None:
    """Start Xvfb + fluxbox on display :dnum, matching netgent-dev's start.sh."""
    resolution = os.environ.get("RESOLUTION", "1920x1080x24")
    subprocess.Popen(["Xvfb", f":{dnum}", "-screen", "0", resolution])
    time.sleep(2)
    subprocess.Popen(
        ["fluxbox"],
        env={**os.environ, "DISPLAY": f":{dnum}"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)


def build_driver():
    from seleniumbase import Driver

    args = [
        "--force-device-scale-factor=1",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        "--window-size=1920,1080",
        "--start-maximized",
        "--disable-gpu",
        # Without this, autoplay=1 in the URL is silently ignored by Chrome's
        # autoplay policy and the player sits paused at t=0 forever (found via
        # live debugging - not in the netgent-dev reference recipe).
        "--autoplay-policy=no-user-gesture-required",
    ]
    chromium_arg = ",".join(args)
    kwargs: dict[str, Any] = dict(
        uc=True,
        headed=True,
        browser="chrome",
        chromium_arg=chromium_arg,
        use_auto_ext=False,
        undetectable=True,
    )
    binary_location = os.environ.get("CHROME_BINARY")
    if binary_location:
        kwargs["binary_location"] = binary_location
    return Driver(**kwargs)


def run_job(
    job: dict[str, Any],
    launch_lock: threading.Lock,
    sampling_barrier: threading.Barrier,
) -> None:
    app = job["app"]
    video_url = job["url"]
    display_num = str(job["display_num"])
    out_path = Path(job["out_path"])
    duration_seconds = float(job["duration_seconds"])
    sample_interval_seconds = float(job.get("sample_interval_seconds", 1.0))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[{app}] starting Xvfb+fluxbox on :{display_num}")
    start_display(display_num)

    # os.environ and pyautogui's X11 backend are process-global, so only one
    # job may be mid-launch (setting DISPLAY, then constructing the Driver
    # that reads it) at a time. Each job's own Xvfb/display is independent -
    # this lock only serializes the brief "point DISPLAY here and launch
    # Chrome against it" window, not the whole job.
    with launch_lock:
        os.environ["DISPLAY"] = f":{display_num}"
        try:
            import Xlib.display
            import pyautogui

            pyautogui._pyautogui_x11._display = Xlib.display.Display(
                os.environ["DISPLAY"]
            )
        except Exception as exc:  # noqa: BLE001 - best-effort, not critical
            print(f"[{app}] warning: could not wire Xlib display for pyautogui: {exc}")

        print(f"[{app}] launching undetected-chromedriver Chrome (headed, DISPLAY=:{display_num})")
        driver = build_driver()

    samples: list[dict] = []
    try:
        print(f"[{app}] navigating to {video_url}")
        driver.set_page_load_timeout(45)
        try:
            driver.get(video_url)
        except Exception as exc:  # streaming pages may never signal full load
            print(
                f"[{app}] navigation did not finish cleanly; "
                f"sampling the loaded page anyway: {type(exc).__name__}: {exc}"
            )

        print(f"[{app}] ready; waiting for all applications before sampling")
        sampling_barrier.wait(timeout=180)
        print(f"[{app}] all applications ready; starting synchronized sampling")
        try:
            play_result = driver.execute_script(
                """
                const video = document.querySelector('video');
                if (!video) return {started: false, reason: 'no_video'};
                video.muted = true;
                video.play().catch(() => {});
                return {
                    started: true,
                    paused: video.paused,
                    ready_state: video.readyState,
                    current_time: video.currentTime,
                };
                """
            )
            print(f"[{app}] synchronized play result: {play_result}")
        except Exception as exc:  # sampling below records whether playback recovers
            print(f"[{app}] synchronized play nudge failed: {type(exc).__name__}: {exc}")
        deadline = time.monotonic() + duration_seconds
        with open(out_path, "a", buffering=1) as f:
            while time.monotonic() < deadline:
                sample = {"timestamp": time.time()}
                try:
                    sample["url"] = driver.current_url
                except Exception as exc:  # noqa: BLE001
                    sample["url"] = None
                    sample["url_error"] = str(exc)
                try:
                    sample["stats"] = driver.execute_script(STATS_JS)
                except Exception as exc:  # noqa: BLE001
                    sample["stats"] = None
                    sample["sample_error"] = str(exc)

                f.write(json.dumps(sample) + "\n")
                samples.append(sample)
                time.sleep(sample_interval_seconds)
    finally:
        try:
            driver.quit()
        except Exception as exc:  # noqa: BLE001
            print(f"[{app}] warning: driver.quit() raised: {exc}")

    times = [
        s["stats"]["current_time_secs"]
        for s in samples
        if s.get("stats") and s["stats"].get("current_time_secs") is not None
    ]
    resolutions = [
        s["stats"]["resolution"]
        for s in samples
        if s.get("stats") and s["stats"].get("resolution")
    ]
    advanced = bool(times) and max(times) > (times[0] if times else 0)
    final_resolution = resolutions[-1] if resolutions else None
    print(
        f"[{app}] summary: {len(samples)} samples written to {out_path} | "
        f"current_time_secs range=[{min(times) if times else None}, "
        f"{max(times) if times else None}] | advanced={advanced} | "
        f"final_resolution={final_resolution}"
    )


def main() -> int:
    jobs_raw = os.environ.get("JOBS")
    if jobs_raw:
        jobs = json.loads(jobs_raw)
    else:
        # Single-job mode, kept for standalone smoke testing.
        jobs = [
            {
                "app": os.environ.get("APP", "video"),
                "url": os.environ["VIDEO_URL"],
                "display_num": os.environ.get("DISPLAY_NUM", "99"),
                "out_path": os.environ.get("OUT_PATH", "/out/qoe.jsonl"),
                "duration_seconds": os.environ.get("DURATION_SECONDS", "15"),
                "sample_interval_seconds": os.environ.get(
                    "SAMPLE_INTERVAL_SECONDS", "1.0"
                ),
            }
        ]

    launch_lock = threading.Lock()
    sampling_barrier = threading.Barrier(len(jobs))
    errors: list[tuple[str, Exception]] = []

    def run_job_checked(job: dict[str, Any]) -> None:
        try:
            run_job(job, launch_lock, sampling_barrier)
        except Exception as exc:  # propagate thread failures through process exit
            errors.append((job["app"], exc))
            print(
                f"[{job['app']}] collector failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    threads = [
        threading.Thread(target=run_job_checked, args=(job,), name=job["app"])
        for job in jobs
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
