FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 python3-pip python-is-python3 \
    tshark iputils-ping iproute2 \
    net-tools iperf3 \
    curl wget iptables byobu nano \
    speedtest-cli tcpreplay \
    python3-flask python3-requests \
    sudo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY . .


EXPOSE 8002

# Run topology setup once, then start the HTTP service
# CMD ["bash", "-lc", "cd app && chmod +x setup.sh && ./setup.sh && python3 main.py"]

CMD ["bash", "-lc", "cd app && chmod +x setup.sh && ./setup.sh && uvicorn main:app --host 0.0.0.0 --port 8002 --reload"]