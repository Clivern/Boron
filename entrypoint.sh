#!/usr/bin/env bash
# Copyright 2026 Clivern. All rights reserved.
# License can be found in the LICENSE file.

set -euo pipefail

if [[ -z "${RUN_ID:-}" ]]; then
  echo "RUN_ID is required" >&2
  exit 1
fi
if [[ -z "${PROXY_URL:-}" ]]; then
  echo "PROXY_URL is required" >&2
  exit 1
fi
if [[ -z "${PI_MODEL:-}" ]]; then
  echo "PI_MODEL is required" >&2
  exit 1
fi
if [[ -z "${RPC_API_KEY:-}" ]]; then
  echo "RPC_API_KEY is required" >&2
  exit 1
fi
if [[ ! -d /repo/.git ]]; then
  echo "/repo must be a mount of a git repository" >&2
  exit 1
fi

if [[ -n "${INIT_SCRIPT:-}" ]]; then
  repo_script="/repo/${INIT_SCRIPT}"
  if [[ ! -f "$repo_script" ]]; then
    echo "INIT_SCRIPT not found: $repo_script" >&2
    exit 1
  fi
  bash "$repo_script"
fi
if [[ -f /init.sh ]]; then
  bash /init.sh
fi

mkdir -p "${HOME}/.pi/agent"
echo "{\"providers\":{\"openrouter\":{\"baseUrl\":\"${PROXY_URL}\",\"apiKey\":\"\$RUN_ID\"}}}" > "${HOME}/.pi/agent/models.json"
echo "{\"openrouter\":{\"type\":\"api_key\",\"key\":\"${RUN_ID}\"}}" > "${HOME}/.pi/agent/auth.json"

cd /repo
echo "Running Pi RPC (model=${PI_MODEL}) on port ${RPC_PORT:-8765} ..." >&2
exec /usr/local/bin/pi-rpc
