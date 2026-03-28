ARG PYTHON_BASE_IMAGE=agentic-thin-waist-python-base:latest
FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app

COPY services/orchestration/requirements.txt /tmp/service-requirements.txt
RUN pip install -r /tmp/service-requirements.txt \
    && rm -f /tmp/service-requirements.txt

COPY services/orchestration/ .
COPY shared/ shared/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
