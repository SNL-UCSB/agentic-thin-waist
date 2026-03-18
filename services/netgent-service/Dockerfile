FROM python:3.12-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/netgent-venv

# Resolve and install project dependencies with uv.
COPY services/netgent-service/pyproject.toml ./pyproject.toml
RUN uv sync --python /usr/local/bin/python3 --no-dev --no-install-project

# Copy application code
COPY services/netgent-service/src/ src/
COPY shared/ /shared/

ENV PATH="/opt/netgent-venv/bin:$PATH"
ENV PYTHONPATH="/app/src:$PYTHONPATH"

EXPOSE 8003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')"

# Run the FastAPI app by default when the container starts.
CMD ["python", "-m", "api.main"]
