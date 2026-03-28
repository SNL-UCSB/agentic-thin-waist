ARG PYTHON_BASE_IMAGE=agentic-thin-waist-python-base:latest
FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app

COPY services/experiment-api/requirements.txt /tmp/service-requirements.txt
RUN pip install -r /tmp/service-requirements.txt \
    && rm -f /tmp/service-requirements.txt

# Copy application code
COPY services/experiment-api/ .
COPY shared/ shared/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Run application
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "app.main:app"]
