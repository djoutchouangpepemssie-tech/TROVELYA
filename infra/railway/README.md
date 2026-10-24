# Railway — configuration des services

Projet Railway `trovelya`, région Europe (europe-west4). La configuration des services est réglée
dans Railway (le format `railway.json` est obsolète chez Railway) ; ce fichier en est la référence :
toute modification faite dans le tableau de bord doit y être reportée.

## Environnements

| Environnement | Branche suivie | `ENV` | Domaine de l'API |
| --- | --- | --- | --- |
| `staging` | `main` | `staging` | `trovelya-staging.up.railway.app` |
| `production` | `release` | `production` | `trovelya-production.up.railway.app` |

Chaque environnement a ses propres instances de `pg`, `Redis` et de leurs volumes. Les variables
`${{pg.DATABASE_URL}}` et `${{Redis.REDIS_URL}}` pointent vers les services du même environnement.
En staging, `WEB_ORIGIN` et `ADMIN_ORIGIN` valent l'adresse de prévisualisation Vercel de `main`.
Mise en production : voir `docs/runbooks/deploy.md`.

## `pg` — PostgreSQL 17 + PostGIS + pgvector + h3

| Réglage | Valeur |
| --- | --- |
| Source | dépôt GitHub (branche selon l'environnement) |
| Répertoire racine | `/infra/postgres` |
| Dockerfile | `Dockerfile` |
| Chemins surveillés | `/infra/postgres/**` |
| Volume | `pg-data` monté sur `/var/lib/postgresql/data` |
| Variables | `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD` (`${{secret(32)}}`), `PGDATA=/var/lib/postgresql/data/pgdata`, `DATABASE_URL` (réseau privé) |

## `TROVELYA` — API FastAPI

| Réglage | Valeur |
| --- | --- |
| Source | dépôt GitHub (branche selon l'environnement) |
| Répertoire racine | `/apps/api` |
| Dockerfile | `Dockerfile` (uvicorn sur `$PORT`) |
| Chemins surveillés | `/apps/api/**` |
| Commande avant déploiement | `alembic upgrade head` |
| Healthcheck | `/ready` (120 s) |
| Redémarrage | `ON_FAILURE`, 5 essais |
| Variables | `ENV`, `DATABASE_URL=${{pg.DATABASE_URL}}`, `REDIS_URL=${{Redis.REDIS_URL}}`, `SECRET_KEY=${{secret(64)}}`, `PROXY_SHARED_SECRET=${{secret(48)}}`, `FIELD_ENCRYPTION_KEY=${{secret(64)}}`, `EMAIL_PROVIDER=resend`, `EMAIL_FROM`, `EMAIL_API_KEY`, `WEB_ORIGIN`, `ADMIN_ORIGIN`, `SENTRY_DSN` |

`DATABASE_URL` peut être en `postgresql://` : l'application et Alembic passent d'eux-mêmes au pilote asyncpg.

Uvicorn tourne sans `--proxy-headers` : l'API lit l'IP du visiteur dans les en-têtes du relais web authentifiés par `PROXY_SHARED_SECRET`, sinon dans `X-Real-IP` (ADR-0015). Création et rotation des secrets : `docs/runbooks/secrets.md`.

## `worker` — tâches de fond arq

| Réglage | Valeur |
| --- | --- |
| Source | dépôt GitHub (branche selon l'environnement) |
| Répertoire racine | `/apps/api` (même image que l'API) |
| Dockerfile | `Dockerfile` |
| Commande de démarrage | `arq trovelya.workers.main.WorkerSettings` |
| Chemins surveillés | `/apps/api/**` |
| Redémarrage | `ON_FAILURE`, 10 essais |
| Variables | références vers l'API : `${{TROVELYA.ENV}}`, `${{TROVELYA.SECRET_KEY}}`, `${{TROVELYA.PROXY_SHARED_SECRET}}`, `${{TROVELYA.FIELD_ENCRYPTION_KEY}}`, `${{TROVELYA.EMAIL_PROVIDER}}`, `${{TROVELYA.EMAIL_FROM}}`, `${{TROVELYA.EMAIL_API_KEY}}`, `${{TROVELYA.WEB_ORIGIN}}`, `${{TROVELYA.ADMIN_ORIGIN}}`, `${{TROVELYA.SENTRY_DSN}}` ; `DATABASE_URL=${{pg.DATABASE_URL}}`, `REDIS_URL=${{Redis.REDIS_URL}}` |

Pas de domaine public ni de healthcheck HTTP : les migrations restent l'affaire de l'API (commande avant déploiement).
