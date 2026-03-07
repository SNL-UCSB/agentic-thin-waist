FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt install -y \
    python3 python3-pip \
    tshark iputils-ping net-tools iperf3 \
    curl wget iproute2 iptables byobu nano \
    speedtest-cli \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install jupyter notebook ipython

WORKDIR /workspace

COPY . /workspace

RUN chmod +x setup.sh cleanup.sh docker_setup_manual.sh

EXPOSE 8888

ENTRYPOINT ["/bin/bash"]