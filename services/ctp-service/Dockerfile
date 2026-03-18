# CTP Service Dockerfile
#
# Build:  docker build -t ctp-service .
# Run:    docker run -p 8001:8001 --env-file .env ctp-service

FROM python:3.10-slim

# ---------------------------------------------------------------------------
# System tools (tshark, joincap, reordercap, tcprewrite)
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        tshark \
        tcpreplay \
        wireshark-common \
        libpcap-dev \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install joincap (Go binary — download pre-built release)
RUN curl -fsSL \
    "https://github.com/assafmo/joincap/releases/download/v0.10.1/joincap-linux64-v0.10.1.zip" \
    -o /tmp/joincap.tar.gz \
    && tar -xzf /tmp/joincap.tar.gz -C /usr/local/bin joincap \
    && rm /tmp/joincap.tar.gz \
    && chmod +x /usr/local/bin/joincap

# ---------------------------------------------------------------------------
# Python application
# ---------------------------------------------------------------------------
WORKDIR /app

COPY services/ctp-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ shared/
COPY services/ctp-service/app/ app/

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
ENV CTP_HOST=0.0.0.0
ENV CTP_PORT=8001
ENV CTP_LOG_LEVEL=INFO
ENV CTP_WORKERS=4

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8001", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--timeout", "300", \
     "--graceful-timeout", "30", \
     "app.main:app"]
