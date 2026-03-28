FROM ghcr.io/browserless/chromium:latest

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        iproute2 \
        util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY services/browserless-substrate-worker/wrap-playwright-chrome.sh /usr/local/bin/wrap-playwright-chrome.sh

RUN chmod +x /usr/local/bin/wrap-playwright-chrome.sh \
    && /usr/local/bin/wrap-playwright-chrome.sh

ENV HOST=0.0.0.0
ENV PORT=3000
ENV SUBSTRATE_BROWSER_NAMESPACE=ns1
