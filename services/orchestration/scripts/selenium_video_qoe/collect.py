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

# Installed before any Google Meet page JavaScript runs. Keeping references to
# the real RTCPeerConnection objects lets the collector query receiver-side
# inbound RTP statistics instead of mistaking Meet's local preview <video> for
# remote-call QoE.
WEBRTC_HOOK_JS = r"""
(() => {
    const key = '__netgentPeerConnections';
    if (!Array.isArray(window[key])) {
        Object.defineProperty(window, key, {
            value: [], configurable: false, enumerable: false, writable: false
        });
    }

    function wrap(name) {
        const Native = window[name];
        if (!Native || Native.__netgentWrapped) return;
        const Wrapped = new Proxy(Native, {
            construct(target, args, newTarget) {
                const pc = Reflect.construct(target, args, newTarget);
                window[key].push(pc);
                return pc;
            }
        });
        Object.defineProperty(Wrapped, '__netgentWrapped', {value: true});
        window[name] = Wrapped;
    }

    wrap('RTCPeerConnection');
    wrap('webkitRTCPeerConnection');
})();
"""

# Selenium's execute_async_script supplies the final argument as a completion
# callback. Aggregate every active inbound video RTP stream: a Meet call may
# change SSRCs or receive more than one remote tile during a run.
GOOGLE_MEET_STATS_JS = r"""
const done = arguments[arguments.length - 1];
(async () => {
    const pcs = Array.from(new Set(window.__netgentPeerConnections || []));
    const inbound = [];

    for (let pcIndex = 0; pcIndex < pcs.length; pcIndex += 1) {
        const pc = pcs[pcIndex];
        const report = await pc.getStats();
        const codecs = {};
        report.forEach(stat => {
            if (stat.type === 'codec') codecs[stat.id] = stat.mimeType || null;
        });
        report.forEach(stat => {
            const mediaKind = stat.kind || stat.mediaType;
            if (stat.type !== 'inbound-rtp' || mediaKind !== 'video' || stat.isRemote) {
                return;
            }
            inbound.push({
                peer_connection_index: pcIndex,
                id: stat.id,
                ssrc: stat.ssrc ?? null,
                codec: codecs[stat.codecId] || null,
                bytes_received: stat.bytesReceived || 0,
                header_bytes_received: stat.headerBytesReceived || 0,
                packets_received: stat.packetsReceived || 0,
                packets_lost: stat.packetsLost || 0,
                packets_discarded: stat.packetsDiscarded || 0,
                jitter_seconds: stat.jitter || 0,
                frames_received: stat.framesReceived || 0,
                frames_decoded: stat.framesDecoded || 0,
                frames_rendered: stat.framesRendered || 0,
                frames_dropped: stat.framesDropped || 0,
                key_frames_decoded: stat.keyFramesDecoded || 0,
                frames_per_second: stat.framesPerSecond || 0,
                frame_width: stat.frameWidth || 0,
                frame_height: stat.frameHeight || 0,
                total_decode_time_seconds: stat.totalDecodeTime || 0,
                jitter_buffer_delay_seconds: stat.jitterBufferDelay || 0,
                jitter_buffer_emitted_count: stat.jitterBufferEmittedCount || 0,
                freeze_count: stat.freezeCount || 0,
                total_freezes_duration_seconds: stat.totalFreezesDuration || 0,
                pause_count: stat.pauseCount || 0,
                total_pauses_duration_seconds: stat.totalPausesDuration || 0,
                nack_count: stat.nackCount || 0,
                pli_count: stat.pliCount || 0,
                fir_count: stat.firCount || 0,
            });
        });
    }

    const active = inbound.filter(
        stream => stream.bytes_received > 0 || stream.frames_decoded > 0
    );
    const primary = active.reduce(
        (best, stream) => !best || stream.bytes_received > best.bytes_received
            ? stream : best,
        null,
    );
    const sum = field => active.reduce((total, stream) => total + (stream[field] || 0), 0);

    done({
        platform: 'google_meet',
        source: 'webrtc_inbound_rtp',
        peer_connection_count: pcs.length,
        inbound_video_stream_count: active.length,
        bytes_received: sum('bytes_received'),
        header_bytes_received: sum('header_bytes_received'),
        packets_received: sum('packets_received'),
        packets_lost: sum('packets_lost'),
        packets_discarded: sum('packets_discarded'),
        frames_received: sum('frames_received'),
        frames_decoded: sum('frames_decoded'),
        frames_rendered: sum('frames_rendered'),
        frames_dropped: sum('frames_dropped'),
        key_frames_decoded: sum('key_frames_decoded'),
        frames_per_second: sum('frames_per_second'),
        total_decode_time_seconds: sum('total_decode_time_seconds'),
        jitter_buffer_delay_seconds: sum('jitter_buffer_delay_seconds'),
        jitter_buffer_emitted_count: sum('jitter_buffer_emitted_count'),
        freeze_count: sum('freeze_count'),
        total_freezes_duration_seconds: sum('total_freezes_duration_seconds'),
        pause_count: sum('pause_count'),
        total_pauses_duration_seconds: sum('total_pauses_duration_seconds'),
        nack_count: sum('nack_count'),
        pli_count: sum('pli_count'),
        fir_count: sum('fir_count'),
        jitter_seconds: active.reduce(
            (maximum, stream) => Math.max(maximum, stream.jitter_seconds || 0), 0
        ),
        frame_width: primary ? primary.frame_width : 0,
        frame_height: primary ? primary.frame_height : 0,
        resolution: primary ? `${primary.frame_width}x${primary.frame_height}` : '0x0',
        codecs: Array.from(new Set(active.map(stream => stream.codec).filter(Boolean))),
        inbound_streams: active,
    });
})().catch(error => done({
    platform: 'google_meet',
    source: 'webrtc_inbound_rtp',
    error: String(error),
}));
"""

GOOGLE_MEET_JOIN_JS = r"""
const guestName = arguments[0];

// Guest rooms show a name field before "Ask to join". Use the native setter
// so Meet's React handlers observe the value instead of only the DOM changing.
const nameInput = Array.from(document.querySelectorAll('input')).find(input => {
    const label = `${input.placeholder || ''} ${input.getAttribute('aria-label') || ''}`
        .trim().toLowerCase();
    return label.includes('your name') || label === 'name';
});
if (nameInput && guestName && nameInput.value !== guestName) {
    const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
    ).set;
    setter.call(nameInput, guestName);
    nameInput.dispatchEvent(new Event('input', {bubbles: true}));
    nameInput.dispatchEvent(new Event('change', {bubbles: true}));
    return {
        clicked: false,
        guest_name_entered: true,
        state: 'waiting_for_ui_update',
    };
}

const buttons = Array.from(document.querySelectorAll('button'));
for (const button of buttons) {
    const label = `${button.innerText || ''} ${button.getAttribute('aria-label') || ''}`
        .trim().toLowerCase();
    if (label.includes('join now') || label.includes('ask to join')) {
        button.click();
        return {clicked: true, label, guest_name_entered: Boolean(nameInput)};
    }
}
return {clicked: false};
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


def build_driver(user_data_dir: str | None = None):
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
    if user_data_dir:
        kwargs["user_data_dir"] = user_data_dir
    return Driver(**kwargs)


def install_webrtc_hook(driver: Any) -> None:
    """Install the peer-connection hook before Meet loads any page scripts."""
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": WEBRTC_HOOK_JS},
    )


def get_google_meet_stats(driver: Any) -> dict[str, Any]:
    stats = driver.execute_async_script(GOOGLE_MEET_STATS_JS)
    if not isinstance(stats, dict):
        raise RuntimeError(f"Google Meet returned invalid WebRTC stats: {stats!r}")
    if stats.get("error"):
        raise RuntimeError(f"Google Meet WebRTC stats failed: {stats['error']}")
    return stats


def wait_for_google_meet_inbound(
    driver: Any,
    timeout_seconds: float,
    guest_name: str,
) -> dict[str, Any]:
    """Join Meet and require a genuinely advancing remote inbound video RTP stream."""
    deadline = time.monotonic() + timeout_seconds
    previous: dict[str, Any] | None = None
    latest: dict[str, Any] = {}

    while time.monotonic() < deadline:
        try:
            join_result = driver.execute_script(GOOGLE_MEET_JOIN_JS, guest_name)
            if join_result and join_result.get("clicked"):
                print(f"[google_meet] clicked Meet join control: {join_result}")
        except Exception as exc:  # noqa: BLE001 - retry while UI settles
            print(f"[google_meet] join control not ready: {exc}")

        try:
            latest = get_google_meet_stats(driver)
        except Exception as exc:  # noqa: BLE001 - retry while Meet initializes
            print(f"[google_meet] waiting for WebRTC stats: {exc}")
            time.sleep(1)
            continue

        if previous is not None and latest.get("inbound_video_stream_count", 0) > 0:
            bytes_advanced = latest.get("bytes_received", 0) > previous.get(
                "bytes_received", 0
            )
            frames_advanced = latest.get("frames_decoded", 0) > previous.get(
                "frames_decoded", 0
            )
            if bytes_advanced and frames_advanced:
                print(
                    "[google_meet] confirmed advancing remote inbound video: "
                    f"bytes={latest['bytes_received']} "
                    f"frames={latest['frames_decoded']}"
                )
                return latest
        previous = latest
        time.sleep(1)

    raise RuntimeError(
        "Google Meet never produced an advancing inbound video RTP stream. "
        "Confirm the profile is logged in, the browser joined the room, and "
        "another participant is publishing video. Local preview video is not accepted. "
        f"Last WebRTC stats: {latest}"
    )


def add_google_meet_interval_metrics(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    elapsed_seconds: float | None,
) -> None:
    """Add rates/deltas derived from cumulative WebRTC counters."""
    if previous is None or elapsed_seconds is None or elapsed_seconds <= 0:
        return

    def delta(field: str) -> float:
        return max(0.0, float(current.get(field, 0)) - float(previous.get(field, 0)))

    byte_delta = delta("bytes_received")
    received_delta = delta("packets_received")
    lost_delta = delta("packets_lost")
    decoded_delta = delta("frames_decoded")
    dropped_delta = delta("frames_dropped")
    current["inbound_bitrate_mbps"] = byte_delta * 8 / elapsed_seconds / 1_000_000
    current["packets_received_delta"] = int(received_delta)
    current["packets_lost_delta"] = int(lost_delta)
    packet_total = received_delta + lost_delta
    current["packet_loss_percent"] = (
        100 * lost_delta / packet_total if packet_total else 0.0
    )
    current["frames_decoded_delta"] = int(decoded_delta)
    current["frames_dropped_delta"] = int(dropped_delta)
    frame_total = decoded_delta + dropped_delta
    current["frame_drop_percent"] = (
        100 * dropped_delta / frame_total if frame_total else 0.0
    )
    current["freeze_count_delta"] = int(delta("freeze_count"))
    current["freeze_duration_delta_seconds"] = delta(
        "total_freezes_duration_seconds"
    )


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
    user_data_dir = job.get("user_data_dir")
    guest_name = str(job.get("guest_name", "NetGent QoE Collector"))
    meet_join_timeout_seconds = float(job.get("join_timeout_seconds", 180))
    barrier_timeout_seconds = float(job.get("barrier_timeout_seconds", 360))
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
        driver = build_driver(user_data_dir=user_data_dir)

    samples: list[dict] = []
    meet_ready_stats: dict[str, Any] | None = None
    meet_ready_timestamp: float | None = None
    try:
        if app == "google_meet":
            install_webrtc_hook(driver)
            driver.set_script_timeout(15)
        print(f"[{app}] navigating to {video_url}")
        driver.set_page_load_timeout(45)
        try:
            driver.get(video_url)
        except Exception as exc:  # streaming pages may never signal full load
            print(
                f"[{app}] navigation did not finish cleanly; "
                f"sampling the loaded page anyway: {type(exc).__name__}: {exc}"
            )

        if app == "google_meet":
            print(
                "[google_meet] joining room and waiting for remote inbound WebRTC video"
            )
            meet_ready_stats = wait_for_google_meet_inbound(
                driver,
                meet_join_timeout_seconds,
                guest_name,
            )
            meet_ready_timestamp = time.time()

        print(f"[{app}] ready; waiting for all applications before sampling")
        sampling_barrier.wait(timeout=barrier_timeout_seconds)
        print(f"[{app}] all applications ready; starting synchronized sampling")
        if app != "google_meet":
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
            except Exception as exc:  # sampling records whether playback recovers
                print(
                    f"[{app}] synchronized play nudge failed: "
                    f"{type(exc).__name__}: {exc}"
                )
        deadline = time.monotonic() + duration_seconds
        previous_meet_stats = meet_ready_stats
        previous_meet_timestamp = meet_ready_timestamp
        with open(out_path, "a", buffering=1) as f:
            while time.monotonic() < deadline:
                sample = {"timestamp": time.time()}
                try:
                    sample["url"] = driver.current_url
                except Exception as exc:  # noqa: BLE001
                    sample["url"] = None
                    sample["url_error"] = str(exc)
                try:
                    if app == "google_meet":
                        stats = get_google_meet_stats(driver)
                        elapsed = (
                            sample["timestamp"] - previous_meet_timestamp
                            if previous_meet_timestamp is not None
                            else None
                        )
                        add_google_meet_interval_metrics(
                            stats,
                            previous_meet_stats,
                            elapsed,
                        )
                        sample["stats"] = stats
                        previous_meet_stats = stats
                        previous_meet_timestamp = sample["timestamp"]
                    else:
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

    stats_samples = [s["stats"] for s in samples if s.get("stats")]
    if app == "google_meet":
        times = [
            stats["frames_decoded"]
            for stats in stats_samples
            if stats.get("frames_decoded") is not None
        ]
    else:
        times = [
            stats["current_time_secs"]
            for stats in stats_samples
            if stats.get("current_time_secs") is not None
        ]
    resolutions = [
        stats["resolution"]
        for stats in stats_samples
        if stats.get("resolution") and stats["resolution"] != "0x0"
    ]
    advanced = bool(times) and max(times) > times[0]
    final_resolution = resolutions[-1] if resolutions else None
    progress_label = "frames_decoded" if app == "google_meet" else "current_time_secs"
    print(
        f"[{app}] summary: {len(samples)} samples written to {out_path} | "
        f"{progress_label} range=[{min(times) if times else None}, "
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
