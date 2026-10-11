#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CONDA_ACTIVATE="${CONDA_ACTIVATE:-/root/data/repo/gongjunmin/miniconda3/bin/activate}"
CONDA_ENV_NAME="${ACESTEP_CONDA_ENV:-acestep_v15_train}"
HOST="${OPENROUTER_HOST:-127.0.0.1}"
PORT="${OPENROUTER_PORT:-8002}"
LOG_FILE="${OPENROUTER_LOG_FILE:-openrouter-server.log}"

cd "$ROOT_DIR"

# Temporarily disable nounset for third-party conda activate.d scripts.
set +u
# shellcheck disable=SC1090
source "$CONDA_ACTIVATE" "$CONDA_ENV_NAME"
set -u

SERVER_ARGS=(--host "$HOST" --port "$PORT")
if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    SERVER_ARGS+=(--api-key "$OPENROUTER_API_KEY")
fi

# Use the security-aware factory launcher. It refuses keyless non-loopback
# binding and publishes the validated key before creating the FastAPI app.
nohup python -m openrouter.secure_server "${SERVER_ARGS[@]}" >"$LOG_FILE" 2>&1 &
echo "ACE-Step OpenRouter API started in background with PID $!. Logs: $LOG_FILE"
