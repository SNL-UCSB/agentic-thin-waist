ARG PYTHON_BASE_IMAGE=agentic-thin-waist-python-base:latest
FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app

# Install packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/*

COPY services/telemetry-service/requirements.txt /tmp/service-requirements.txt
RUN pip install -r /tmp/service-requirements.txt \
    && rm -f /tmp/service-requirements.txt

# Copy application code
COPY services/telemetry-service/ .
COPY shared/ shared/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8004/health')"

# Run application
CMD ["make", "gunicorn-telemetry-app"]
