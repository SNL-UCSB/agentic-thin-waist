FROM python:3.10-slim

WORKDIR /app

# Install Docker CLI + buildx plugin (needed for cross-platform ECR image push in AWS mode)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.4.1.tgz \
       | tar xz -C /usr/local/bin --strip-components=1 docker/docker \
    && mkdir -p /usr/local/lib/docker/cli-plugins \
    && curl -fsSL https://github.com/docker/buildx/releases/download/v0.19.3/buildx-v0.19.3.linux-amd64 \
       -o /usr/local/lib/docker/cli-plugins/docker-buildx \
    && chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx \
    && apt-get purge -y curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/orchestration/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/orchestration/ .
COPY shared/ shared/

# /app/app is added so that `netgent.src.*` absolute imports resolve correctly
ENV PYTHONPATH="/app/app:/app/shared:${PYTHONPATH:-}"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
