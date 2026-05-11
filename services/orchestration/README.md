# Orchestration Service

**Port**: 8005
**Deliverable**: D5 (Agentic Orchestration — Natural Language Intent → Executed Experiments)
**Lead**: Haarika | **PI**: Prof. Arpit Gupta
**Status**: Active — natural-language intent path is end-to-end working against the local Docker stack.

The Orchestration Service is the agentic brain of the Agentic Thin Waist. It accepts a natural-language research intent over HTTP, uses an LLM (Claude or Gemini) to extract structured experiment parameters, expands them into a list of concrete experiment specs, and dispatches each one through the Experiment API → CTP Service → Substrate Worker → Telemetry Service pipeline.

---

## What It Does

```
NL intent ──► OrchestratorAgent (LangGraph)
                ├─ parse_intent          (LLM → ParsedIntent)
                ├─ generate_experiments  (Cartesian product over caps × lats × CCs)
                └─ execute_experiments   (per-spec: provision worker → CTP fetch
                                          → synchronized capture+replay+run
                                          → store result in telemetry)
```

The graph nodes live in `app/agent/orchestrator/agent.py`. Per-spec execution is implemented in `app/engine/orchestration_manager.py` (`OrchestrationManager.run` and `_run_experiment_on_worker`). Substrate workers are provisioned through a pluggable `ConnectivityManager` (`app/engine/connectivity.py`) — local Docker today, AWS / GCP / remote stubs reserved.

### Per-experiment timeline (one spec)

1. `ConnectivityManager.create_worker()` — spin up an ephemeral substrate worker.
2. `CTP Service /ctps/select` — pick a cross-traffic profile that matches the spec's intensity range.
3. `Worker /ctp/fetch` — pull the CTP PCAPs (download + upload) onto the worker.
4. Wait until the next whole-minute boundary, then fire three threads simultaneously:
   - `Worker /capture` — start tshark capture.
   - `Worker /replay` — start `tcpreplay-edit` background traffic (skipped if no CTP).
   - `Experiment API /run` — apply tc shaping, set CC, launch the application workflow.
5. Stop replay, drain capture, stream the resulting PCAP to telemetry.
6. Destroy the worker.

---

## Quick Start

### Prerequisites
- Docker + Docker Compose (24+).
- A `.env` at the repo root (`cp .env.example .env`), and an LLM API key — either `ANTHROPIC_API_KEY` (default) or `GOOGLE_API_KEY` (if you switch the provider).

### Bring the stack up
From the repo root:
```bash
make build          # build all images
make up             # start everything; waits on health checks
make status         # ps
make logs-service SERVICE=orchestration   # tail one service
```

The orchestrator listens on `http://localhost:8005`.

### Submit an intent
```bash
curl -X POST http://localhost:8005/intent \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "Run iperf3 at 40 Mbps with 100 ms latency under cubic and bbr",
    "context": {"duration_seconds": 60, "num_trials": 1},
    "preferences": {}
  }'
```

Response is `202 Accepted` with an `orchestration_id`. The graph runs in the background.

### Poll progress and results
```bash
curl http://localhost:8005/orchestration/<orch_id>             # status + per-experiment progress
curl http://localhost:8005/orchestration/<orch_id>/results     # final aggregated results
curl http://localhost:8005/orchestration/<orch_id>/reasoning   # the agent's reasoning steps
```

### Health
```bash
curl http://localhost:8005/health
# Reports reachability of: experiment-api, ctp-service, substrate-worker, telemetry-service, netgent-service
```

---

## HTTP API

| Endpoint | Method | Purpose |
|---|---|---|
| `/intent` | POST | Submit a natural-language intent. Returns `202 Accepted` with `orchestration_id`. |
| `/orchestration/{id}` | GET | Status + per-experiment progress. |
| `/orchestration/{id}/results` | GET | Final aggregated results. |
| `/orchestration/{id}/reasoning` | GET | Agent reasoning steps. |
| `/tools` | GET | Tools the agent can invoke. |
| `/skills` | GET | High-level skills (parameter sweeps, comparisons). |
| `/skills/{skill_name}/execute` | POST | Run a skill directly, bypassing the LLM. |
| `/health` | GET | Downstream service health. |

### `POST /intent` request schema

```json
{
  "intent": "Compare iperf3 vs ndt at 25 and 100 Mbps with 50 ms latency",
  "context":     { "num_trials": 1, "duration_seconds": 60 },
  "preferences": { "desired_cc_algorithms": ["cubic", "bbr"] }
}
```

The LLM extracts a `ParsedIntent` (see `app/agent/orchestrator/schemas.py`) with these fields: `applications` (list of names — e.g. `["iperf3"]`, `["youtube"]`), `application_type` (`shell` or `browser`), `capacities`, `latencies`, `cc_algorithms`, `aqm_policy`, `ctp_cluster`, `ctp_capacity_range`, `duration_seconds`, `num_trials`, `workflow_parameters`.

`ExperimentGenerator.generate(parsed_intent)` then expands the Cartesian product over `capacities × latencies × cc_algorithms` and emits one `GeneratedExperiment` per combination.

---

## Experiment ID Format

Each generated experiment gets a globally-unique, descriptive ID:

```
{app}_{download_mbps}_{upload_mbps}_{latency_ms}_{aqm}_{cc}_{uuid8}
```

Examples:
- `iperf3_40_40_100_pfifo_cubic_a2d6e73d`
- `youtube_25_25_50_fq_codel_bbr_77856217`

Components:
- `app` — the **first entry** of `parsed_intent.applications`, slugified to lowercase alphanumerics. Falls back to `application_type` (`shell` / `browser`) when no applications are listed.
- `download_mbps`, `upload_mbps` — capacity (currently symmetric; `upload_mbps` falls back to `download` when not set in the spec).
- `latency_ms` — base latency.
- `aqm` — the AQM policy (e.g. `pfifo`, `fq_codel`).
- `cc` — congestion-control algorithm (e.g. `cubic`, `bbr`).
- `uuid8` — 8-char `uuid4().hex` suffix for randomness.

**Uniqueness against telemetry.** When `TELEMETRY_SERVICE_URL` is set, each candidate ID is checked against `GET /results?experiment_id=<id>&limit=1` before being accepted. If telemetry reports the ID is already persisted, a fresh UUID is drawn (up to 8 attempts; ultra-rare last-ditch fallback uses a full 32-char UUID). If telemetry is unset or unreachable, the random suffix alone guarantees uniqueness.

This is implemented in `app/engine/experiment_generator.py` (`ExperimentGenerator.generate(parsed_intent, id_taken=…)`) and wired up in `app/engine/orchestration_manager.py` (`_make_telemetry_id_taken`).

---

## CTP Replay & PNAT

Background cross-traffic is replayed by the substrate worker using `tcpreplay-edit --pnat=<rule>`. The `pnat` rule rewrites the source IPs in the CTP PCAPs to a target IP on the worker so the replayed packets traverse the shaped link.

**Default**: the orchestrator sends
```
169.231.0.0/16:172.16.1.20,128.111.0.0/16:172.16.1.20
```
The target IP `172.16.1.20` is **distinct** from the application's interface IP (`172.16.1.1`), so a captured PCAP can be cleanly split between application traffic and replayed cross-traffic by inspecting `ip.src` / `ip.dst`.

**Override per experiment.** Set `replay_pnat_ip` on `GeneratedExperiment` (or downstream on the spec dict) to use a different target IP. The standard source subnets (`169.231.0.0/16`, `128.111.0.0/16`) are reused — the orchestrator constructs `169.231.0.0/16:<ip>,128.111.0.0/16:<ip>`. Any valid IP works, including one in a different subnet (e.g. `192.168.5.10`); the only constraint is that it must not collide with the application's interface IP.

**Override globally.** Set `SUBSTRATE_REPLAY_PNAT` env var to a full rewrite rule (multiple subnets allowed). This is the advanced escape hatch — useful when you also want to change the source subnets.

Resolution order in `_build_replay_payload`:
`spec.replay_pnat_ip` → `SUBSTRATE_REPLAY_PNAT` env → built-in default.

---

## Connectivity Backends

The orchestrator provisions substrate workers through `ConnectivityManager` (`app/engine/connectivity.py`):

| Backend | `CONNECTIVITY_BACKEND` | Status |
|---|---|---|
| Local Docker | `local_docker` (default) | Implemented — uses `/var/run/docker.sock` directly via `httpx`. |
| AWS ECS | `aws` | Implemented (hybrid mode — see `Makefile` `up-aws`). |
| GCP Cloud Run | `gcp` | Stub. |
| Remote SSH | `remote` | Stub. |

Each per-spec call goes:
```python
mgr = ConnectivityManager()
worker = mgr.create_worker({})         # → WorkerInfo(worker_id, endpoint)
# … run experiment against worker.endpoint …
mgr.destroy_worker(worker.worker_id)
```

Parallel dispatch: pass `max_parallel_workers=N` to `OrchestrationManager(...)`. A `ThreadPoolExecutor` then runs N specs concurrently, each on its own worker.

---

## Environment Variables

The orchestrator is configured entirely through env vars. The most relevant ones:

| Variable | Default | Purpose |
|---|---|---|
| **LLM provider** | | |
| `ORCHESTRATOR_LLM_PROVIDER` | `anthropic` | `anthropic` or `gemini`. |
| `ANTHROPIC_API_KEY` / `CLAUDE_API_KEY` | — | Required when provider is `anthropic`. |
| `GOOGLE_API_KEY` | — | Required when provider is `gemini`. |
| **Downstream services** | | |
| `EXPERIMENT_API_URL` | `http://experiment-api:8000` | Experiment API. |
| `CTP_SERVICE_GLOBAL` | `http://128.111.5.236:8001` | Global CTP service used during selection. |
| `TELEMETRY_SERVICE_URL` | unset | When set, results are persisted there AND new experiment IDs are checked for uniqueness against `GET /results`. |
| `NETGENT_SERVICE_URL` | `http://netgent-service:8003` | NetGent. |
| **Connectivity** | | |
| `CONNECTIVITY_BACKEND` | `local_docker` | `local_docker`, `aws`, `gcp`, `remote`. |
| `SUBSTRATE_WORKER_IMAGE` | `substrate-worker` | Image used for spawned workers. |
| `SUBSTRATE_DOCKER_NETWORK` | `agentic-network` | Docker network for spawned workers. |
| `SUBSTRATE_WORKER_HOST` | `localhost` | Host fragment of worker endpoint URLs. |
| `DOCKER_SOCKET` | `/var/run/docker.sock` | Path to Docker socket (must be mounted into the orchestration container). |
| `SUBSTRATE_CTP_DIR` | `/mnt/md0/ctp_test` | CTP PCAP host path (mounted read-only into workers). |
| `SUBSTRATE_CAPTURE_DIR` | `/mnt/md0/cap_test` | Capture output host path. |
| **Capture / replay** | | |
| `SUBSTRATE_CAPTURE_IFACE` | `veth2` | Interface to capture on. |
| `ORCH_CAPTURE_DURATION_SECONDS` | `min(spec.duration, 60)` | Max capture duration (s). |
| `ORCH_CAPTURE_TIMEOUT_SECONDS` | `120` | How long to wait for capture to finish before force-stop. |
| `ORCH_POLL_INTERVAL_SECONDS` | `2` | Capture-status poll interval (s). |
| `ORCH_PCAP_DOWNLOAD_TIMEOUT_SECONDS` | `600` | Bridge timeout for streaming PCAP to telemetry. |
| `CAPTURE_DOWNLOAD_TOKEN` | unset | If set on workers, the orchestrator must send the same value in `X-Capture-Download-Token`. |
| **PNAT** | | |
| `SUBSTRATE_REPLAY_PNAT` | `169.231.0.0/16:172.16.1.20,128.111.0.0/16:172.16.1.20` | Full PNAT rewrite rule used when `spec.replay_pnat_ip` is unset. |
| **CTP selection** | | |
| `ORCH_CTP_SELECT_LIMIT` | `10` | Max candidate CTPs returned by `/ctps/select`. |
| `ORCH_CTP_INTENSITY_DIRECTION` | unset | Optional `download` or `upload` filter on `/ctps/select`. |
| `ORCH_CTP_POINTER_MODE` | `export` | `export` = HTTP zip fetch by URL; `local_path` = use `download_pcap` from select. |
| `ORCH_WORKER_STARTUP_WAIT_SECONDS` | `3` | Pause after creating a worker before first request. |
| `ORCH_TELEMETRY_TIMEOUT_SECONDS` | `5` | HTTP timeout for the telemetry uniqueness check. |
| **Persistence** | | |
| `ORCH_SQLITE_PATH` | `~/.agentic_thin_waist/orchestrations.db` | SQLite path used when `TELEMETRY_SERVICE_URL` is unset. |

Orchestration run state (`/orchestration/{id}`) is persisted in `app/engine/orchestration_store.py`: telemetry HTTP when `TELEMETRY_SERVICE_URL` is set, else SQLite.

---

## Local Development

A dedicated Python 3.10+ environment is recommended for direct, in-process work (running tests, executing scripts, hitting the API without Docker).

```bash
python3 -m venv ~/imp_files/virtualenvs/thinwaist
source ~/imp_files/virtualenvs/thinwaist/bin/activate
cd services/orchestration
pip install -r requirements.txt
pytest tests/ -q
```

### Useful scripts

```bash
# Integration demo (CTP → shape → PCAP capture)
python scripts/run_integration_pipeline_demo.py
python scripts/run_integration_pipeline_demo.py --mode executor
python scripts/run_integration_pipeline_demo.py --skip-ctp-check     # substrate-only

# Bring up just CTP + Postgres + Telemetry (Docker)
./scripts/start_ctp_telemetry_stack.sh
# (Telemetry needs MinIO; if port 9000 is busy, free it first.)
```

### Tests
- Repo root: `make test` (Docker Compose) or `make test-local` (pytest at the repo level).
- This service: `pytest services/orchestration/tests -v`.
- Formatter: `black services/orchestration` (CI pins `black==26.3.1`).

---

## Source Layout

```
services/orchestration/
├── app/
│   ├── main.py                          # FastAPI app, /health, mounts intent router
│   ├── api/
│   │   └── intent.py                    # POST /intent + status/results/reasoning routes
│   ├── agent/
│   │   ├── orchestrator/                # LangGraph: parse_intent → generate_experiments → execute → respond
│   │   │   ├── agent.py                 # Graph nodes
│   │   │   ├── prompts.py               # System prompt for the parser
│   │   │   ├── schemas.py               # ParsedIntent
│   │   │   └── tools.py                 # Tool declarations
│   │   └── browser/                     # Browser-workflow chooser sub-agent
│   ├── engine/
│   │   ├── intent_parser.py             # LLM call: NL → ParsedIntent dict
│   │   ├── experiment_generator.py      # ParsedIntent → list[GeneratedExperiment] + new ID format
│   │   ├── orchestration_manager.py     # Per-experiment dispatch on a worker
│   │   ├── executor.py                  # HTTP clients for downstream services
│   │   ├── connectivity.py              # ConnectivityManager + backends
│   │   ├── orchestration_store.py       # Persistence (telemetry or SQLite)
│   │   ├── telemetry_capture_pull.py    # Streams worker PCAPs into telemetry
│   │   ├── tools.py / skills.py         # OpenClaw tool/skill declarations
│   │   └── experiment_lifecycle.py      # Lifecycle stage recorder
│   └── models/
│       └── schemas.py                   # ResearchIntent, GeneratedExperiment (incl. replay_pnat_ip), …
├── scripts/                             # Local dev / demo scripts
├── tests/                               # pytest
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Working With Recently-Changed Surface Area

A few knobs that landed recently and may not be familiar:

- **Per-experiment PNAT override** — set `replay_pnat_ip` on `GeneratedExperiment` (or in the spec dict before it reaches `OrchestrationManager.run`) to control where replayed CTP traffic lands. Default is `172.16.1.20` (separate from app at `172.16.1.1`). See *CTP Replay & PNAT* above.
- **Experiment IDs are now globally unique** — the old `shell-40mbps-100ms-cubic-001` format was prone to collision when two intents had overlapping params. New format includes app name, download/upload, latency, AQM, CC, and a UUID suffix; uniqueness is double-checked against telemetry when `TELEMETRY_SERVICE_URL` is set. See *Experiment ID Format*.
- **Skills / direct execution** — `POST /skills/{skill_name}/execute` lets you bypass the LLM entirely and run `parameter_sweep`, `application_comparison`, etc. with a structured payload. Useful for scripted / reproducible runs.

---

## Contributing

- Branch naming: `<username>/<area>/<short-description>`.
- Commit prefix: `orchestration: <what changed>`.
- Run `black services/orchestration` before committing.
- Add tests under `services/orchestration/tests/` for any new public behavior.

## References

- LangGraph: https://langchain-ai.github.io/langgraph/
- Anthropic Claude API: https://docs.anthropic.com/claude/reference/
- Google Gemini API: https://ai.google.dev/
- NetForge (SIGCOMM submission): see top-level `README.md`.
