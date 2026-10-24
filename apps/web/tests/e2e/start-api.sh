#!/usr/bin/env bash
# The API for the end-to-end tests (ENV=test mounts /v1/_test/session). Migrates, then serves.
set -euo pipefail

cd "$(dirname "$0")/../../../api"
uv run alembic upgrade head
exec uv run uvicorn --factory trovelya.main:create_app --host 127.0.0.1 --port "${E2E_API_PORT:-8100}"
