# Orchestration Test Scripts Guide

This document explains the orchestration real-time test scripts in this directory:

- `test_orchestration_ndt.py`
- `test_orchestration_youtube.py`
- `test_orchestration_parallel_ping.py`
- `test_orchestration_manager.py` (single-run ping)

All of these scripts are end-to-end drivers for the orchestration service. They submit a natural-language intent, watch execution progress, and print outputs (`results` + `reasoning`) so you can validate behavior quickly.

## Common Behavior Across Scripts

Most scripts follow this same lifecycle:

1. Health check with `GET /health`
2. Submit intent with `POST /intent`
3. Stream logs from the orchestration container (`docker logs --follow`)
4. Watch for ephemeral `worker-*` container starts and stream worker logs
5. Poll `GET /orchestration/{id}` until terminal status (`complete`, `failed`, `partial`)
6. Fetch and print:
   - `GET /orchestration/{id}/results`
   - `GET /orchestration/{id}/reasoning`

## Shared Runtime Requirements

- Python 3
- `requests` package (`pip install requests`)
- Docker CLI available (for log streaming and pcap checks)
- Orchestration service reachable (default: `http://localhost:8005`)

## Shared Environment Variables

These variables are used by one or more scripts:

- `ORCH_URL` (default `http://localhost:8005`)
- `ORCH_CONTAINER` (default `orchestration`)
- `POLL_INTERVAL_SECONDS` (default varies, usually `3`)
- `TIMEOUT_SECONDS` (default varies by script)

## Script Details

### 1) `test_orchestration_ndt.py`

Purpose:
- Runs an NDT speedtest intent through orchestration with application context `ndt`.

Key points:
- Uses `context: {"application": "ndt"}` when submitting intent.
- Streams orchestration + worker logs while polling.
- Prints per-result summary including selected CTP details.
- Verifies reported pcap path via:
  - direct host path check
  - `NETREPLICA_CAPTURE_DIR` fallback
  - best-effort `docker exec` check in active worker container

Run:

```bash
python3 services/orchestration/scripts/test_orchestration_ndt.py
```

Optional example:

```bash
ORCH_URL=http://localhost:8005 ORCH_CONTAINER=orchestration python3 services/orchestration/scripts/test_orchestration_ndt.py
```

---

### 2) `test_orchestration_youtube.py`

Purpose:
- Runs a YouTube playback orchestration flow with application context `youtube`.

Why this script is useful:
- Validates media-playback style workflows end-to-end under orchestration.
- Useful for checking parsing, dispatch, shaping, run, and capture/replay flow for YouTube-style experiments.

Key points:
- Uses `context: {"application": "youtube"}`.
- Supports YouTube-specific environment variables:
  - `YOUTUBE_URL`
  - `WATCH_SECONDS`
- Prints target URL and watch duration at startup.
- Includes same live log streaming, polling, results summary, reasoning summary, and pcap verification pattern as NDT.

Run:

```bash
python3 services/orchestration/scripts/test_orchestration_youtube.py
```

Optional example:

```bash
ORCH_URL=http://localhost:8005 YOUTUBE_URL="https://www.youtube.com/watch?v=dQw4w9WgXcQ" WATCH_SECONDS=30 python3 services/orchestration/scripts/test_orchestration_youtube.py
```

Note:
- The script currently builds and sends its own `INTENT` string. If you want `YOUTUBE_URL` / `WATCH_SECONDS` to directly drive the submitted intent text, update the `INTENT` assignment accordingly.

---

### 3) `test_orchestration_parallel_ping.py`

Purpose:
- Runs a parallel ping campaign through orchestration (multi-experiment style intent).

Key points:
- Uses `context: {"application": "ping"}`.
- Exposes `MAX_PARALLEL_WORKERS` to stress-test parallel orchestration behavior.
- Longer default timeout (`TIMEOUT_SECONDS=1800`) to support larger campaigns.
- Prints compact aggregate results (`total`, `success`, `failed`) and first N entries.

Run:

```bash
python3 services/orchestration/scripts/test_orchestration_parallel_ping.py
```

Optional example:

```bash
MAX_PARALLEL_WORKERS=8 TIMEOUT_SECONDS=1800 python3 services/orchestration/scripts/test_orchestration_parallel_ping.py
```

---

### 4) `test_orchestration_manager.py` (Single Ping Manager Flow)

Purpose:
- General manager-style smoke test for a single intent execution path.
- Despite older naming and comments mentioning iperf3, the current intent text in this file is ping-oriented.

Key points:
- Uses `context: {"application": "iperf3"}` in payload, with ping-like intent text in `INTENT`.
- Includes robust status transition + stage-flag heartbeat printing.
- Includes result/reasoning printing and pcap verification.

Run:

```bash
python3 services/orchestration/scripts/test_orchestration_manager.py
```

## Suggested Usage Pattern

Use these scripts in this order for incremental validation:

1. `test_orchestration_manager.py` for quick single-flow checks
2. `test_orchestration_ndt.py` for NDT-specific flow
3. `test_orchestration_youtube.py` for media workflow validation
4. `test_orchestration_parallel_ping.py` for concurrency and load behavior

## Troubleshooting

- Health check fails:
  - Ensure orchestration service is running (`docker compose up orchestration`).
- No live logs:
  - Confirm Docker CLI is installed and the container name matches `ORCH_CONTAINER`.
- Polling times out:
  - Increase `TIMEOUT_SECONDS` and inspect orchestration/worker logs.
- Pcap not found:
  - Check mount configuration and/or set `NETREPLICA_CAPTURE_DIR`.
