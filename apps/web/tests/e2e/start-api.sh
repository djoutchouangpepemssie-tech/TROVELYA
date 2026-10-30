#!/usr/bin/env bash
# The API for the end-to-end tests (ENV=test mounts /v1/_test/session) and its arq worker (it
# processes the photos), with the storage of tests/e2e/stack.sh. Migrates, then serves.
set -euo pipefail

STORAGE="$(cd "$(dirname "$0")" && pwd)/.env.storage"
cd "$(dirname "$0")/../../../api"
if [ ! -f "$STORAGE" ]; then
  echo "no $STORAGE: run tests/e2e/stack.sh first (it starts Garage)" >&2
  exit 1
fi
set -a
# shellcheck source=/dev/null
source "$STORAGE"
set +a
uv run alembic upgrade head
# The worker's logs, shown by CI when a test fails (.github/workflows/ci.yml).
WORKER_LOG="${E2E_WORKER_LOG:-/tmp/trovelya-e2e-worker.log}"
uv run arq trovelya.workers.main.WorkerSettings >"$WORKER_LOG" 2>&1 &
WORKER=$!
trap 'kill 0 2>/dev/null || true' EXIT INT TERM
sleep 3
if ! kill -0 "$WORKER" 2>/dev/null; then
  echo "the worker stopped at start:" >&2
  cat "$WORKER_LOG" >&2
  exit 1
fi
uv run uvicorn --factory trovelya.main:create_app --host 127.0.0.1 --port "${E2E_API_PORT:-8100}"
