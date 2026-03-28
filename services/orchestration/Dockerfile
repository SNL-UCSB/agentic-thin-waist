FROM python:3.10-slim

WORKDIR /app

# Copy requirements
COPY services/orchestration/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/orchestration/ .
COPY shared/ shared/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
