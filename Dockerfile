# Copyright 2026 Clivern. All rights reserved.
# License can be found in the LICENSE file.

FROM node:24-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g --ignore-scripts @earendil-works/pi-coding-agent

WORKDIR /repo

COPY entrypoint.sh /usr/local/bin/pi-entrypoint
COPY rpc_bridge.py /usr/local/bin/pi-rpc
RUN chmod +x /usr/local/bin/pi-entrypoint /usr/local/bin/pi-rpc

EXPOSE 8765

ENTRYPOINT ["/usr/local/bin/pi-entrypoint"]
