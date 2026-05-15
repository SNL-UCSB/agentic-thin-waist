FROM python:3.12-slim

WORKDIR /app

# Copy requirements
COPY services/orchestration/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/orchestration/ .
COPY shared/ shared/

# /app/app is added so app.* absolute imports resolve; the netgent submodule's
# src/ is on PYTHONPATH so its modules (engine, agents, registry, main, ...) are top-level.
ENV PYTHONPATH="/app/app:/app/shared:/app/shared/clients/netgent/src:${PYTHONPATH:-}"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
