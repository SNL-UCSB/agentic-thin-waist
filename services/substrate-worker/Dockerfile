FROM --platform=$BUILDPLATFORM golang:1.24-bookworm AS ndt-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

ENV GOARCH=amd64
ENV GOOS=linux
ENV CGO_ENABLED=0

RUN git clone https://github.com/m-lab/ndt7-client-go.git \
    && cd ndt7-client-go \
    && git checkout v0.9.1 \
    && go build -v -o ./ndt7-client ./cmd/ndt7-client \
    && test -x ./ndt7-client \
    && install -m 0755 ./ndt7-client /usr/local/bin/ndt7-client

FROM ghcr.io/browserless/chromium:latest

USER root

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV DEBIAN_FRONTEND=noninteractive
ENV UV_PROJECT_ENVIRONMENT=/opt/substrate-worker-venv

RUN apt-get update && apt-get install -y \
    python3 python-is-python3 \
    tshark iputils-ping iproute2 \
    net-tools iperf3 \
    curl wget iptables byobu nano \
    speedtest-cli tcpreplay \
    python3-flask python3-requests \
    sudo util-linux \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=ndt-builder /usr/local/bin/ndt7-client /usr/local/bin/ndt-client

RUN cd /usr/src/app \
    && npm install --no-save playwright-core@1.58.0 \
    && node ./node_modules/playwright-core/cli.js install chromium

COPY services/substrate-worker/pyproject.toml ./pyproject.toml
RUN uv sync --python /usr/bin/python3 --no-install-project

COPY services/substrate-worker/ .
COPY shared/ /shared/

RUN chmod +x src/browser/wrap-playwright-chrome.sh src/substrate/setup.sh src/substrate/setup_local.sh src/substrate/setup_aws.sh \
    && ./src/browser/wrap-playwright-chrome.sh

ENV PATH="/opt/substrate-worker-venv/bin:$PATH"
ENV PYTHONPATH="/app/src:/shared:${PYTHONPATH:-}"
ENV HOST=0.0.0.0
ENV PORT=3000
ENV BROWSERLESS_WS_ENDPOINT=ws://127.0.0.1:3000/chromium/playwright
ENV SUBSTRATE_BROWSER_NAMESPACE=ns1
ENV SUBSTRATE_SHELL_NAMESPACE=ns1

EXPOSE 3000
EXPOSE 8002

ENTRYPOINT []
CMD ["bash", "-lc", "if [ \"${CONNECTIVITY_BACKEND:-local_docker}\" = \"aws\" ]; then SETUP_SCRIPT=./src/substrate/setup_aws.sh; MAIN_MODULE=substrate.main_aws; else SETUP_SCRIPT=./src/substrate/setup_local.sh; MAIN_MODULE=substrate.main_local; fi; echo \"Starting substrate profile: ${CONNECTIVITY_BACKEND:-local_docker} setup=${SETUP_SCRIPT} module=${MAIN_MODULE}\"; \"$SETUP_SCRIPT\" && (cd /usr/src/app && ./scripts/start.sh) & browserless_pid=$! && sleep 2 && kill -0 \"$browserless_pid\" && exec uv run --no-sync python -m \"$MAIN_MODULE\""]
