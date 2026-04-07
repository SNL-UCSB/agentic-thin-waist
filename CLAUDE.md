# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Agentic Thin Waist applies hourglass/thin-waist design (inspired by netUnicorn) to network data generation. It bridges diverse research intents with diverse infrastructure through a composable set of microservices organized into three logical planes:

- **Intent Plane** — Experiment API (:8000) + Orchestration (:8005): natural language intent to experiment specs
- **Representation Plane** — CTP Service (:8001) + Telemetry Service (:8004): cross-traffic profiles and contextual result storage
- **Execution Plane** — Substrate Worker (:8002) + NetGent Service (:8003): traffic shaping, packet capture, browser/shell workflows

## Build & Run Commands

```bash
# Full stack (Docker Compose)
make build                  # Build all Docker images
make up                     # Start all services (waits for health checks)
make down                   # Stop all services
make clean                  # Stop services, remove volumes and caches
make logs                   # Tail logs for all services
make logs-service SERVICE=experiment-api  # Tail one service
make status                 # Check service status (docker-compose ps)
make shell                  # Open shell in experiment-api container

# Local Python development (single service)
pip install -r requirements.txt
pip install -r services/<service-name>/requirements.txt

# Run tests
make test                   # Full suite via Docker Compose (uses docker-compose.test.yml)
make test-local             # All repo-level tests locally via pytest
cd services/<service-name> && pytest tests/ -v           # Single service tests
cd services/<service-name> && pytest tests/ -v --cov=app --cov-report=term-missing  # With coverage
cd shared && pytest tests/ -v                            # Shared library tests

# Formatting (enforced in CI — only checks changed .py files on PRs)
black services/ shared/ tests/        # Format all Python
black --check services/ shared/ tests/ # Check only
```

Black version pinned at **26.3.1** in CI. Python 3.10+.

## Architecture

```
Orchestration/Client
       │
  Experiment API (controller, :8000)
  │        │         │
  v        v         v
CTP     Substrate   NetGent
:8001   Worker:8002  :8003
  │        │         │
  └────────┼─────────┘
           v
      Telemetry :8004
```

**Key principle: Dumb Services, Smart Controller.** Each service is narrow and stateless; Experiment API is the coordinator.

**Bottleneck Regime = Static + Dynamic:** Static attributes (capacity, latency, buffer, AQM) configured via Substrate Worker + dynamic pressure from CTP replay. CTP Service manages profiles but does NOT apply them — Substrate Worker does.

## Service Layout

Each service follows the same structure: `services/<name>/` with `app/`, `tests/`, `Dockerfile`, `requirements.txt`, and a `README.md` containing the full API spec. Always read the service README before implementing.

Shared code lives in `shared/` — dataclass models (`shared/models/`), HTTP clients (`shared/clients/`), database utilities (`shared/db/`), and S3 integration (`shared/s3/`).

## Docker Compose Topology

- **Browserless** (`browserless-substrate-worker`) shares network and PID namespace with `substrate-worker` via `network_mode: "service:substrate-worker"` and `pid: "service:substrate-worker"` — it runs inside the substrate worker's network namespace for traffic-shaped browsing.
- **NetGent worker** (`netgent-worker`) is a separate container from `netgent-service` that runs `python -m api.worker.main` (Procrastinate job queue). It also shares PID namespace with substrate-worker.
- **NetGent Service** and **Browserless** both require `privileged: true` + `NET_ADMIN` + `SYS_ADMIN` because they operate in the substrate worker's namespace.
- Services discover each other via Docker network hostnames (e.g., `http://ctp-service:8001`).

## Code Conventions

- **Formatter:** Black (no other linter configured)
- **Frameworks:** Flask for all services, SQLAlchemy for DB, Pydantic for validation
- **Branch naming:** `<username>/<area>/<short-description>`
- **Commit messages:** prefix with service or area (e.g., `experiment-api: add validation`)
- **Tests:** `test_*.py` naming convention, pytest discovery, one `tests/` dir per service plus `tests/` at repo root for integration
- **Environment:** copy `.env.example` to `.env` before running; services share Postgres and MinIO

## CI Pipeline

GitHub Actions (`.github/workflows/`) runs per-service on PRs touching that service's path or `shared/`:
- Each service workflow: builds Docker image, runs `pytest` inside the container, then starts the service via Compose to verify health
- `black.yml`: checks only changed `.py` files against `black==26.3.1`
- `shared-tests.yml`: runs shared library tests when `shared/` changes

## Infrastructure Notes

- Substrate Worker runs in **privileged mode** (NET_ADMIN, SYS_ADMIN) for tc/netem traffic shaping
- Browserless provides headless browser pool on port 3000 for NetGent workflows
- PostgreSQL (5432) and MinIO/S3 (9000/9001) are shared infrastructure
- `minio-init` sidecar creates required S3 buckets on startup
