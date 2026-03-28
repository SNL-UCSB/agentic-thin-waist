ARG PYTHON_BASE_IMAGE=agentic-thin-waist-python-base:latest
FROM ${PYTHON_BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    bash \
    tshark iputils-ping iproute2 \
    net-tools iperf3 \
    curl wget iptables byobu nano \
    speedtest-cli tcpreplay \
    sudo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/substrate-worker/requirements.txt /tmp/service-requirements.txt
RUN pip install -r /tmp/service-requirements.txt \
    && rm -f /tmp/service-requirements.txt

COPY services/substrate-worker/ .
COPY shared/ shared/


EXPOSE 8002

CMD ["bash", "-lc", "cd app && chmod +x setup.sh && ./setup.sh && uvicorn main:app --host 0.0.0.0 --port 8002"]
