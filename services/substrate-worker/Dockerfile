FROM golang:1.25-bookworm AS ndt-builder

RUN go install github.com/m-lab/ndt7-client-go/cmd/ndt7-client@latest

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

COPY --from=ndt-builder /go/bin/ndt7-client /usr/local/bin/ndt-client

COPY services/substrate-worker/requirements.txt .
RUN pip3 install -r requirements.txt

COPY services/substrate-worker/ .
COPY shared/ shared/


EXPOSE 8002

CMD ["bash", "-lc", "cd app && chmod +x setup.sh && ./setup.sh && uvicorn main:app --host 0.0.0.0 --port 8002"]
