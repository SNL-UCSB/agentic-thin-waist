FROM python:3.10-alpine

WORKDIR /app

# Install packages
RUN apk add --no-cache make && \
    pip install gunicorn

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8004/health')"

# Run application
CMD ["make", "gunicorn-telemetry-app"]
