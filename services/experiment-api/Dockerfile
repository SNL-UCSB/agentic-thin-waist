# Placeholder Dockerfile for service
# Update this file with actual service implementation

FROM python:3.10-slim

WORKDIR /app

# Copy requirements
COPY services/experiment-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/experiment-api/ .
COPY shared/ shared/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Run application
# The placeholder service uses an in-memory experiment registry, so it must
# stay single-process until it has shared persistence.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "app.main:app"]
