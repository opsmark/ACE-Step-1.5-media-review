#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CONDA_ACTIVATE="${CONDA_ACTIVATE:-/root/data/repo/gongjunmin/miniconda3/bin/activate}"
CONDA_ENV_NAME="${ACESTEP_CONDA_ENV:-acestep_v15_train}"
HOST="${ACESTEP_API_HOST:-127.0.0.1}"
PORT="${ACESTEP_API_PORT:-8001}"
LOG_FILE="${ACESTEP_API_LOG_FILE:-server.log}"

cd "$ROOT_DIR"

# Temporarily disable nounset for third-party conda activate.d scripts.
set +u
# shellcheck disable=SC1090
source "$CONDA_ACTIVATE" "$CONDA_ENV_NAME"
set -u

API_ARGS=(--host "$HOST" --port "$PORT")
if [[ -n "${ACESTEP_API_KEY:-}" ]]; then
    API_ARGS+=(--api-key "$ACESTEP_API_KEY")
fi

# Use the application's security-aware entrypoint. It creates the FastAPI app
# only after CLI/environment authentication state is applied and refuses a
# keyless non-loopback bind. The in-memory queue requires one worker; the
# entrypoint enforces that setting.
nohup python -m acestep.api_server "${API_ARGS[@]}" >"$LOG_FILE" 2>&1 &
echo "ACE-Step API started in background with PID $!. Logs: $LOG_FILE"
