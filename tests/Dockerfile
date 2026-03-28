FROM python:3.12-slim

WORKDIR /workspace

COPY services/orchestration/requirements.txt /tmp/orchestration-requirements.txt
RUN pip install --no-cache-dir -r /tmp/orchestration-requirements.txt psycopg2-binary

COPY . .

ENV PYTHONPATH=/workspace/services/orchestration:/workspace

CMD ["python", "-m", "pytest", "tests/integration", "-v", "--tb=short"]
