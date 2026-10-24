# Railway — configuration des services

Projet Railway `trovelya`, région Europe (europe-west4). La configuration des services est réglée
dans Railway (le format `railway.json` est obsolète chez Railway) ; ce fichier en est la référence :
toute modification faite dans le tableau de bord doit y être reportée.

## `pg` — PostgreSQL 17 + PostGIS + pgvector + h3

| Réglage | Valeur |
| --- | --- |
| Source | dépôt GitHub, branche `main` |
| Répertoire racine | `/infra/postgres` |
| Dockerfile | `Dockerfile` |
| Chemins surveillés | `/infra/postgres/**` |
| Volume | `pg-data` monté sur `/var/lib/postgresql/data` |
| Variables | `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD` (`${{secret(32)}}`), `PGDATA=/var/lib/postgresql/data/pgdata`, `DATABASE_URL` (réseau privé) |

## `TROVELYA` — API FastAPI

| Réglage | Valeur |
| --- | --- |
| Source | dépôt GitHub, branche `main` |
| Répertoire racine | `/apps/api` |
| Dockerfile | `Dockerfile` (uvicorn sur `$PORT`) |
| Chemins surveillés | `/apps/api/**` |
| Commande avant déploiement | `alembic upgrade head` |
| Healthcheck | `/ready` (120 s) |
| Redémarrage | `ON_FAILURE`, 5 essais |
| Variables | `ENV`, `DATABASE_URL=${{pg.DATABASE_URL}}`, `REDIS_URL=${{Redis.REDIS_URL}}`, `SECRET_KEY=${{secret(64)}}`, `WEB_ORIGIN`, `ADMIN_ORIGIN`, `SENTRY_DSN` |

`DATABASE_URL` peut être en `postgresql://` : l'application et Alembic passent d'eux-mêmes au pilote asyncpg.

## Worker arq (à créer)

Même image et mêmes variables que l'API, commande de démarrage
`arq trovelya.workers.main.WorkerSettings`, sans healthcheck HTTP ni domaine public.
