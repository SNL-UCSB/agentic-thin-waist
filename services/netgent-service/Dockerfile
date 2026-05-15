FROM --platform=$BUILDPLATFORM golang:1.24-bookworm AS ndt-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

ENV GOARCH=amd64
ENV GOOS=linux
ENV CGO_ENABLED=0

RUN git clone https://github.com/m-lab/ndt7-client-go.git \
    && cd ndt7-client-go \
    && git checkout v0.9.1 \
    && go build -v -o ./ndt7-client ./cmd/ndt7-client \
    && test -x ./ndt7-client \
    && install -m 0755 ./ndt7-client /usr/local/bin/ndt7-client

FROM python:3.12-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY --from=ndt-builder /usr/local/bin/ndt7-client /usr/local/bin/ndt-client

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/netgent-venv

## Install NDT SpeedTest, Shell (NDT Client), Ping and IPerf 3
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        iperf3 \
        iproute2 \
        iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Resolve and install project dependencies with uv.
COPY services/netgent-service/pyproject.toml ./pyproject.toml
COPY services/netgent-service/uv.lock ./uv.lock
RUN uv sync --frozen --python /usr/local/bin/python3 --no-dev --no-install-project

# Copy application code
COPY services/netgent-service/src/ src/
COPY shared/ /shared/

ENV PATH="/opt/netgent-venv/bin:$PATH"
ENV PYTHONPATH="/app/src:/shared:/shared/clients/netgent/src:${PYTHONPATH:-}"

EXPOSE 8003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')"

# Run the FastAPI app by default when the container starts.
CMD ["python", "-m", "api.main"]
