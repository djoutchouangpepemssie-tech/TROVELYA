#!/usr/bin/env bash
# The full stack of journey 1 (P1 gate, G1), as deployed: our PostgreSQL image, Redis, Mailpit
# for the e-mails, Garage for the photos (as R2, ADR-0019), then the API and the arq worker
# from the image Railway runs. The web app
# (production build) is started by Playwright (playwright.full.config.ts). Idempotent; used by
# CI and locally. `bash tests/e2e-full/stack.sh down` removes everything.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
NETWORK=trovelya-full
API_PORT="${FULL_API_PORT:-8200}"
MAILPIT_PORT="${FULL_MAILPIT_PORT:-8125}"
WEB_PORT="${FULL_WEB_PORT:-3200}"
CONTAINERS=(trovelya-full-api trovelya-full-worker trovelya-full-garage trovelya-full-mailpit
  trovelya-full-redis trovelya-full-pg)
# The browser and the containers reach Garage by the same name and ports, so the URLs the API
# signs work for both: Chromium sends *.localhost to this machine, Docker to the container.
GARAGE_ENDPOINT=http://garage.localhost:3900

docker rm -f "${CONTAINERS[@]}" >/dev/null 2>&1 || true
docker network rm "$NETWORK" >/dev/null 2>&1 || true
if [ "${1:-}" = "down" ]; then
  exit 0
fi

# The database image changes rarely (CI builds it fresh); the API image is the code under test.
if ! docker image inspect trovelya/postgres:17 >/dev/null 2>&1; then
  docker build -q -t trovelya/postgres:17 "$ROOT/infra/postgres" >/dev/null
fi
docker build -q -t trovelya/api "$ROOT/apps/api" >/dev/null
docker network create "$NETWORK" >/dev/null

docker run -d --name trovelya-full-pg --network "$NETWORK" -e POSTGRES_USER=trovelya \
  -e POSTGRES_PASSWORD=full -e POSTGRES_DB=trovelya trovelya/postgres:17 >/dev/null
docker run -d --name trovelya-full-redis --network "$NETWORK" redis:8.2-alpine >/dev/null
docker run -d --name trovelya-full-mailpit --network "$NETWORK" -p "$MAILPIT_PORT:8025" \
  axllent/mailpit:v1.32.0 >/dev/null
docker run -d --name trovelya-full-garage --network "$NETWORK" --network-alias garage.localhost \
  -p 3900:3900 -p 3902:3902 -v "$ROOT/infra/garage/garage.toml:/etc/garage.toml:ro" \
  dxflrs/garage:v2.1.0 >/dev/null
# The init phase runs a socket-only server; TCP opens only once initialisation is complete.
for _ in $(seq 1 60); do
  docker exec trovelya-full-pg pg_isready -h 127.0.0.1 -U trovelya >/dev/null 2>&1 && break
  sleep 2
done
# Buckets, key and CORS for the web origin; the API image brings Python and boto3.
STORAGE_ENV="$(GARAGE_ENDPOINT="$GARAGE_ENDPOINT" GARAGE_CORS_ORIGIN="http://localhost:$WEB_PORT" \
  GARAGE_PYTHON="docker run --rm -i --network $NETWORK -e KEY_ID -e SECRET -e ENDPOINT -e CORS_ORIGIN trovelya/api python" \
  bash "$ROOT/infra/garage/init.sh" trovelya-full-garage)"

# Test-only values, never real secrets (`.gitleaks.toml` allows the `ci-only-secret-key-` prefix).
# The proxy secret is the one playwright.full.config.ts gives the web relay.
ENV_FILE="$(mktemp)"
trap 'rm -f "$ENV_FILE"' EXIT
cat >"$ENV_FILE" <<ENV
ENV=staging
DATABASE_URL=postgresql://trovelya:full@trovelya-full-pg:5432/trovelya
REDIS_URL=redis://trovelya-full-redis:6379/0
SECRET_KEY=ci-only-secret-key-full-session-0123456789abcdef0123456789abcdef0123456789
PROXY_SHARED_SECRET=ci-only-secret-key-full-proxy-0123456789abcdef
FIELD_ENCRYPTION_KEY=ci-only-secret-key-full-fields-0123456789abcdef
WEB_ORIGIN=http://localhost:$WEB_PORT
ADMIN_ORIGIN=http://localhost:3201
EMAIL_PROVIDER=smtp
SMTP_URL=smtp://trovelya-full-mailpit:1025
GEOCODER_PROVIDER=fake
PORT=8000
FEATURE_FLAGS_DEFAULT={"media.uploads": true}
$STORAGE_ENV
ENV

docker run --rm --network "$NETWORK" --env-file "$ENV_FILE" trovelya/api sh -c "alembic upgrade head && python -m trovelya.scripts.seed_catalog" >/dev/null
docker run -d --name trovelya-full-api --network "$NETWORK" --env-file "$ENV_FILE" \
  -p "$API_PORT:8000" trovelya/api >/dev/null
docker run -d --name trovelya-full-worker --network "$NETWORK" --env-file "$ENV_FILE" \
  trovelya/api arq trovelya.workers.main.WorkerSettings >/dev/null
for _ in $(seq 1 30); do
  curl -fsS "http://127.0.0.1:$API_PORT/ready" >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS "http://127.0.0.1:$API_PORT/ready" >/dev/null
echo "full stack ready: API on $API_PORT, Mailpit on $MAILPIT_PORT, Garage on 3900 and 3902 (web on $WEB_PORT from Playwright)"
