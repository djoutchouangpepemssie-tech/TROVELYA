#!/usr/bin/env bash
# Database, cache and photo storage for the end-to-end tests: our PostgreSQL image, Redis and
# Garage (as R2, ADR-0019) in Docker, on ports that do not clash with a local development
# stack but Garage's (3900 and 3902: the signed URLs name them; stop the development Garage
# first). The storage variables go to tests/e2e/.env.storage, read by start-api.sh (the API and
# its arq worker, which processes the photos). Idempotent; used by CI and locally.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
PG_PORT="${E2E_PG_PORT:-5433}"
REDIS_PORT="${E2E_REDIS_PORT:-6380}"
WEB_PORT="${E2E_WEB_PORT:-3100}"

if ! docker image inspect trovelya/postgres:17 >/dev/null 2>&1; then
  docker build -t trovelya/postgres:17 "$ROOT/infra/postgres"
fi
docker rm -f trovelya-e2e-pg trovelya-e2e-redis trovelya-e2e-garage >/dev/null 2>&1 || true
docker run -d --name trovelya-e2e-pg -e POSTGRES_PASSWORD=e2e -p "$PG_PORT:5432" \
  trovelya/postgres:17 >/dev/null
docker run -d --name trovelya-e2e-redis -p "$REDIS_PORT:6379" redis:7-alpine >/dev/null
docker run -d --name trovelya-e2e-garage -p 3900:3900 -p 3902:3902 \
  -v "$ROOT/infra/garage/garage.toml:/etc/garage.toml:ro" dxflrs/garage:v2.1.0 >/dev/null
# The init phase runs a socket-only server; TCP opens only once initialisation is complete.
for _ in $(seq 1 60); do
  docker exec trovelya-e2e-pg pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1 && break
  sleep 2
done
# The API, its worker and the browser all run on this machine: one endpoint for the three.
GARAGE_ENDPOINT=http://localhost:3900 GARAGE_CORS_ORIGIN="http://localhost:$WEB_PORT" \
  bash "$ROOT/infra/garage/init.sh" trovelya-e2e-garage >"$(dirname "$0")/.env.storage"
echo "e2e stack ready: postgres on $PG_PORT, redis on $REDIS_PORT, Garage on 3900 and 3902"
