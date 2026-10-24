#!/usr/bin/env bash
# Database and cache for the end-to-end tests: our PostgreSQL image and Redis in Docker, on
# ports that do not clash with a local development stack. Idempotent; used by CI and locally.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
PG_PORT="${E2E_PG_PORT:-5433}"
REDIS_PORT="${E2E_REDIS_PORT:-6380}"

if ! docker image inspect trovelya/postgres:17 >/dev/null 2>&1; then
  docker build -t trovelya/postgres:17 "$ROOT/infra/postgres"
fi
docker rm -f trovelya-e2e-pg trovelya-e2e-redis >/dev/null 2>&1 || true
docker run -d --name trovelya-e2e-pg -e POSTGRES_PASSWORD=e2e -p "$PG_PORT:5432" \
  trovelya/postgres:17 >/dev/null
docker run -d --name trovelya-e2e-redis -p "$REDIS_PORT:6379" redis:7-alpine >/dev/null
# The init phase runs a socket-only server; TCP opens only once initialisation is complete.
for _ in $(seq 1 60); do
  docker exec trovelya-e2e-pg pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1 && break
  sleep 2
done
echo "e2e stack ready: postgres on $PG_PORT, redis on $REDIS_PORT"
