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
        unzip \
    && rm -rf /var/lib/apt/lists/*

# Install joincap (Go binary — download pre-built release)
RUN curl -fsSL \
    "https://github.com/assafmo/joincap/releases/download/v0.10.2/joincap-linux64-v0.10.2.zip" \
    -o /tmp/joincap.zip \
    && unzip /tmp/joincap.zip -d /tmp/joincap_extracted \
    && install -m 755 /tmp/joincap_extracted/joincap-linux64-* /usr/local/bin/joincap \
    && rm -rf /tmp/joincap.zip /tmp/joincap_extracted

# ---------------------------------------------------------------------------
# Python application
# ---------------------------------------------------------------------------
WORKDIR /app

COPY services/ctp-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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