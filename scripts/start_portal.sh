#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8090}"

# Stop any previous instance occupying the port
EXISTING_PIDS=$(lsof -t -i:"${PORT}" 2>/dev/null || true)
if [ -n "${EXISTING_PIDS}" ]; then
  echo "Stopping existing process on port ${PORT} (PID: ${EXISTING_PIDS})..."
  kill -9 ${EXISTING_PIDS} 2>/dev/null || true
  sleep 1
fi

echo "Starting SRMA Clinical Evidence Synthesis Portal on http://localhost:${PORT} ..."
exec ./.venv/bin/uvicorn srma_agent.web_server:app --host 0.0.0.0 --port "${PORT}"
