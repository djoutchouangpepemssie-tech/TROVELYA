# Image PostgreSQL de TROVÉLYA

Décision : ADR-0011 (PostgreSQL 17 + PostGIS + pgvector + h3-pg, image identique en local, en CI et sur Railway).

- `Dockerfile` : part de l'image officielle `postgis/postgis:17-3.6` (Debian 13) et ajoute `postgresql-17-pgvector` et `postgresql-17-h3` depuis le dépôt PGDG déjà configuré dans l'image.
- `init/20-extensions.sql` : crée les extensions à la première initialisation du volume (les migrations Alembic les créent aussi, de façon idempotente).
- `check_extensions.sql` : preuve que les 9 extensions exigées par le cahier (section 7.1) se créent. Exécuté en CI (job `postgres-image`).

## Vérifier en local

```bash
docker compose -f infra/docker-compose.yml up -d --build postgres
docker compose -f infra/docker-compose.yml exec postgres psql -U trovelya -f /check_extensions.sql
```

## Mettre à jour l'image

1. Changer l'étiquette `FROM` (nouvelle version mineure de PostGIS ou correctif Debian) dans une PR dédiée.
2. La CI reconstruit l'image et rejoue `check_extensions.sql`.
3. Une montée de version majeure de PostgreSQL (17 → 18) exige une migration des données (`pg_upgrade` ou sauvegarde/restauration) : runbook dédié avant toute action sur staging ou production.
