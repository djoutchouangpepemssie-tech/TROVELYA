#!/usr/bin/env bash
# The API for the end-to-end tests (ENV=test mounts /v1/_test/session) and its arq worker (it
# processes the photos), with the storage of tests/e2e/stack.sh. Migrates, then serves.
set -euo pipefail

STORAGE="$(cd "$(dirname "$0")" && pwd)/.env.storage"
cd "$(dirname "$0")/../../../api"
if [ -f "$STORAGE" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$STORAGE"
  set +a
fi
uv run alembic upgrade head
uv run arq trovelya.workers.main.WorkerSettings &
WORKER=$!
trap 'kill "$WORKER" 2>/dev/null || true' EXIT
uv run uvicorn --factory trovelya.main:create_app --host 127.0.0.1 --port "${E2E_API_PORT:-8100}"
