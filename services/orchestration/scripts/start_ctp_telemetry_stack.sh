#!/usr/bin/env bash
# Start Postgres, apply CTP schema, start ctp-service; start Minio + telemetry-service
# when ports are free (Telemetry needs Postgres + MinIO per docker-compose).
#
# Usage (from agentic-thin-waist repo root):
#   ./services/orchestration/scripts/start_ctp_telemetry_stack.sh
#
# If MinIO fails (port 9000 in use): free the port or stop the other container, then:
#   docker compose up -d minio telemetry-service

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "ERROR: missing .env — copy .env.example to .env and set DB_* and S3_*."
  exit 1
fi

set -a
# shellcheck source=/dev/null
source .env
set +a

echo "==> Starting Postgres..."
docker compose up -d postgres

echo "==> Waiting for Postgres..."
for _ in $(seq 1 60); do
  if docker compose exec -T postgres pg_isready -U "${DB_USER}" -d "${DB_NAME}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "==> Creating CTP database ctp_corpus (if missing)..."
docker compose exec -T postgres psql -U "${DB_USER}" -d postgres \
  -c "CREATE DATABASE ctp_corpus;" 2>/dev/null || true

echo "==> Applying CTP schema.sql (tables: ctp_nodes, ...)..."
docker compose exec -T postgres psql -U "${DB_USER}" -d ctp_corpus -v ON_ERROR_STOP=1 \
  < "${ROOT}/services/ctp-service/app/database/schema.sql"

echo "==> Starting CTP service (port 8001)..."
docker compose up -d --build ctp-service

echo "==> Starting MinIO (port 9000) — required for Telemetry..."
if ! docker compose up -d minio; then
  echo ""
  echo "WARN: MinIO did not start (often port 9000 already in use)."
  echo "  Fix: stop the process using :9000, then run:"
  echo "    docker compose up -d minio telemetry-service"
  echo ""
else
  echo "==> Starting Telemetry (port 8004; runs flask db upgrade on container start)..."
  docker compose up -d --build telemetry-service
fi

echo "==> Waiting for HTTP health (CTP always; Telemetry if started)..."
for _ in $(seq 1 90); do
  ctp_ok=1
  curl -sf "http://127.0.0.1:8001/health" >/dev/null && ctp_ok=0 || true
  tel_ok=1
  curl -sf "http://127.0.0.1:8004/health" >/dev/null && tel_ok=0 || true
  if [[ $ctp_ok -eq 0 ]]; then
    echo "CTP http://127.0.0.1:8001/health OK"
    if [[ $tel_ok -eq 0 ]]; then
      echo "Telemetry http://127.0.0.1:8004/health OK"
    else
      echo "Telemetry :8004 not up yet (MinIO or migrations) — check: docker compose logs telemetry-service"
    fi
    echo ""
    echo "Integration demo (activate thinwaist venv first):"
    echo "  cd services/orchestration && source ~/imp_files/virtualenvs/thinwaist/bin/activate"
    echo "  export TELEMETRY_SERVICE_URL=http://127.0.0.1:8004"
    echo "  python scripts/run_integration_pipeline_demo.py"
    exit 0
  fi
  sleep 2
done

echo "ERROR: CTP did not become healthy. Check: docker compose logs ctp-service"
exit 1
