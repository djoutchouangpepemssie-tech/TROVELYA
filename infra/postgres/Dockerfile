# TROVÉLYA PostgreSQL image (ADR-0011): PostgreSQL 17 + PostGIS 3.6 + pgvector + h3-pg.
# Same image locally (docker compose), in CI (testcontainers) and on Railway.
FROM postgis/postgis:18-3.6

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      postgresql-17-pgvector \
      postgresql-17-h3 \
 && rm -rf /var/lib/apt/lists/*

COPY init/ /docker-entrypoint-initdb.d/
