# P0 — Fondations : plan d'implémentation

> **Pour les agents qui exécutent ce plan :** skill obligatoire `subagent-driven-development` (recommandé) ou `executing-plans`, tâche par tâche. Les étapes utilisent des cases à cocher (`- [ ]`).
> Statut : **brouillon, à valider par Arcel**. Aucun code ne doit être écrit avant sa validation explicite.

**Objectif :** livrer le socle technique complet de TROVÉLYA (monorepo, API, base, socle transverse, web vide, CI/CD, staging en ligne), sur lequel les phases P1 à P21 se brancheront sans refonte.

**Architecture :** monorepo pnpm + Turborepo. `apps/api` est un monolithe modulaire FastAPI (cahier, 5.4). `apps/web` est un site Next.js App Router, mobile first et PWA. PostgreSQL 17 (PostGIS, pgvector, H3) et Redis 7+, sur Railway (UE) pour l'API et le worker, Vercel `fra1` pour le web. Le socle (argent, outbox, audit, grand livre, idempotence, flags, i18n) est posé dès maintenant, même s'il n'est consommé qu'à partir de P1.

**Pile :** Node 24 LTS, pnpm ≥ 9, Turborepo 2, Next.js ≥ 15 / React 19, Tailwind 4, next-intl, Radix UI, Vitest, Playwright. Python 3.12, uv, FastAPI, Pydantic v2, SQLAlchemy 2 async + asyncpg, Alembic, arq, structlog, ruff, pyright strict, pytest, hypothesis, testcontainers, import-linter. PostgreSQL 17 + PostGIS 3.5 + pgvector + h3-pg.

**Spécification :** `docs/CAHIER_DES_CHARGES.md` v1.1, sections 0, 4, 4.2, 5, 6.2, 7.1, 7.2, 7.8, 13.2, 16.3 à 16.5, 17.1. Règles de travail : `CLAUDE.md`.

---

## 0. Décisions prises

### 0.1 Décisions validées par Arcel dans la session de planification

| # | Décision |
|---|---|
| V1 | P0 va jusqu'à un staging **en ligne** sur les comptes Railway et Vercel existants (connectés et vérifiés le 23/10/2026). |
| V2 | Base de données : **notre propre image** `infra/postgres/Dockerfile`, basée sur `postgis/postgis:17-3.5` + pgvector + h3-pg, **PostgreSQL 17**, identique en local, en CI et sur Railway. L'image Postgres officielle de Railway (`postgres-ssl:18`, sans aucune extension) est remplacée. → ADR-0011. |

### 0.2 Réponses aux questions 1 à 13 (recommandations validées par Arcel le 23/10/2026 : « tout est ok »)

| # | Question | Défaut retenu |
|---|---|---|
| Q1 | Domaine | `trovelya.com` pas encore acheté. Staging sur `*.up.railway.app` et `*.vercel.app` ; branchement du domaine dans P0-T14 étape « domaine » dès l'achat (D4). |
| Q2 | Organisation GitHub | Rester sur `djoutchouangpepemssie-tech/TROVELYA`. |
| Q3 | Branches | Plan commité sur la branche de session. Puis une branche `feat/P0-Txx-…` et une PR vers `main` par tâche ; pousser ces branches nécessite l'accord d'Arcel. |
| Q4 | Railway | Projet renommé **trovelya** (fait par Arcel, vérifié) ; environnements **staging** et **production** ; service `TROVELYA` → **api** ; ajout de **worker** et du nouveau **postgres** ; Redis conservé. |
| Q5 | Vercel | Projet `trovelya` conservé : racine `apps/web`, framework Next.js, région `fra1`. |
| Q6 | Aperçus par PR | Activés sur Vercel (gratuits), **désactivés** sur Railway ([PARAM] du cahier, 5.7). |
| Q7 | Node | 24 LTS. |
| Q8 | Typage Python | pyright strict. |
| Q9 | Sentry | Organisation en **région UE** (à créer par Arcel si absente ; seul le DSN est nécessaire, mis dans les variables Railway/Vercel par Arcel). |
| Q10 | Traces et métriques | Grafana Cloud UE (offre gratuite) via OTLP. |
| Q11 | E-mails | Brevo (branché en P1 ; P0 = Mailpit local). |
| Q12 | Stockage objet | Cloudflare R2, juridiction UE (branché en P2 ; P0 = MinIO local). |
| Q13 | Revue des documents | Une PR de documentation en fin de phase (P0-T16). |

### 0.3 Écarts et précisions par rapport au cahier (à valider, chacun donne un ADR)

| # | Point du cahier | Problème | Proposition |
|---|---|---|---|
| E1 | 7.2 `idempotency_keys` : `PRIMARY KEY (key, user_id)` avec `user_id` nullable | PostgreSQL rend toute colonne de clé primaire `NOT NULL` : une requête anonyme ne pourrait pas être enregistrée. | `id BIGINT IDENTITY` en clé primaire + `UNIQUE NULLS NOT DISTINCT (key, user_id)` (PG ≥ 15). Même garantie. → ADR-0012. |
| E2 | 7.2 `audit_log.hash = SHA-256(prev_hash ‖ ligne canonique)` | Le cahier ne dit pas **où** le calcul est fait. Calculé en Python, deux insertions concurrentes pourraient lire le même `prev_hash` et fourcher la chaîne. | Calcul dans un trigger `BEFORE INSERT` en base, sérialisé par `pg_advisory_xact_lock`, avec la fonction native `sha256()`. Ligne canonique = `jsonb_build_object(...)::text` des colonnes listées en P0-T04. → ADR-0014. |
| E3 | 17.1 P0-T10 « Lighthouse ≥ 95 PWA » | Lighthouse a retiré la catégorie PWA (v12). | Critère remplacé par : Lighthouse **Best Practices ≥ 95**, **Accessibilité = 100** et **critères d'installabilité vérifiés** (manifeste valide, service worker actif, icônes 192/512) par un test Playwright. |
| E4 | 17.1 P0-T11 « page `/_design` » | Dans l'App Router, un dossier préfixé `_` est privé : la route n'existe pas. | Route `/[locale]/design-system`, `noindex`, servie seulement si `ENV != production`. |
| E5 | 5.7 production « déclenchement manuel (tag `vX.Y.Z`) » | Railway et Vercel déploient à partir d'une branche. | Branche **`release`** = production. Le workflow `deploy-production.yml`, déclenché par un tag `v*` avec approbation de l'environnement GitHub `production`, avance `release` sur le tag. Railway `production` et Vercel Production suivent `release` ; Railway `staging` suit `main`. → ADR-0013. |
| E6 | 5.3 « la migration qui crée une table vit dans son module » | Alembic utilise un seul dossier par défaut. | Alembic avec `version_locations` multiples : `src/trovelya/core/migrations/` (socle) et `src/trovelya/modules/<module>/migrations/` (ex. `ledger`), un seul historique linéaire. |

### 0.4 ADR produits par cette phase

ADR-0001 à ADR-0010 du cahier (5.2), plus ADR-0011 (image PostgreSQL 17), ADR-0012 (clé d'idempotence), ADR-0013 (branche `release`), ADR-0014 (chaîne d'audit calculée en base). Tous rédigés en P0-T16 ; chaque tâche qui prend la décision note le numéro d'ADR dans son message de commit.

---

## 1. Contraintes globales (s'appliquent à toutes les tâches)

- Argent : `amount_minor` entier + `currency` ISO 4217 (`CHAR(3)`), **jamais** de `float` ni de `number` JS non entier. Arrondi au centime **supérieur** pour les frais facturés à l'acheteur, **inférieur** pour les montants reversés (5.9).
- Identifiants : UUIDv7 générés par l'application (`uuid_utils.uuid7()`).
- Dates : `TIMESTAMPTZ` UTC ; jamais `datetime.now()` dans le métier → `Clock`.
- Pays : `country_code CHAR(2)` ISO 3166-1 sur toute entité qui en porte un (dès P1).
- Aucun texte d'interface en dur : tout passe par `apps/web/messages/fr.json`.
- Aucun secret dans le dépôt ; `.env.example` à jour ; aucune donnée personnelle dans les logs.
- Un module ne lit pas le `repository` ni les `models` d'un autre ; un service ne fait jamais `commit` (la route ou le job valide) (5.4).
- Migrations réversibles : `upgrade head` → `downgrade base` → `upgrade head` doit réussir.
- Commits conventionnels `type(module): …`, PR ≤ 600 lignes hors fichiers générés.
- Données hébergées dans l'UE (Railway `europe-west4`, Vercel `fra1`, Sentry UE, Grafana UE).

## 2. Points d'attention de la revue (non couverts par la spec, couverts par un test)

1. **Transaction du grand livre sans écriture ou avec une seule écriture** : le trigger d'équilibre ne se déclenche que sur des lignes insérées. Une transaction vide doit aussi être rejetée au COMMIT. → test `test_transaction_without_entries_rejected` (P0-T07).
2. **Insertions concurrentes dans `audit_log`** : la chaîne ne doit jamais fourcher (deux lignes avec le même `prev_hash`). → test `test_concurrent_inserts_keep_single_chain` (P0-T04).
3. **Deux relais d'outbox en parallèle** : un événement ne doit pas être pris par les deux dans le même lot. → test `test_two_relays_do_not_share_rows` (P0-T06, `FOR UPDATE SKIP LOCKED`).
4. **`Money` construit avec un `float`, un `bool` ou un `Decimal`**, ou opération entre deux devises : erreur explicite, jamais de conversion silencieuse. → tests `test_rejects_non_int_amount`, `test_currency_mismatch_raises` (P0-T05).
5. **Deux requêtes simultanées avec la même `Idempotency-Key`** : une seule s'exécute, l'autre reçoit `409 idempotency_in_progress`. → test `test_concurrent_same_key_single_execution` (P0-T08).

Choix de l'auteur du plan, à confirmer : si Redis est indisponible, la limite de débit **laisse passer** la requête et journalise une alerte (ne pas couper le site), `/ready` renvoie 503 et `/health` reste à 200.

---

## 3. Structure des fichiers créés en P0

```
trovelya/
├── package.json, pnpm-workspace.yaml, turbo.json, .nvmrc, .editorconfig, .env.example
├── infra/
│   ├── docker-compose.yml
│   └── postgres/{Dockerfile, init/001-extensions.sql}
├── apps/api/
│   ├── pyproject.toml, uv.lock, Dockerfile, alembic.ini, .importlinter
│   ├── src/trovelya/
│   │   ├── main.py                      # create_app()
│   │   ├── core/{config,db,errors,logging,middleware,redis,idempotency,
│   │   │         ratelimit,csrf,settings_service,flags,health}.py
│   │   ├── core/migrations/             # socle : extensions, settings, flags, outbox, audit…
│   │   ├── shared/{money,ids,clock,events,audit}.py
│   │   ├── modules/ledger/{models,repository,service,errors}.py + migrations/
│   │   ├── workers/{main,outbox_relay}.py
│   │   └── scripts/export_openapi.py
│   └── tests/{conftest.py, unit/, integration/, architecture/}
├── apps/web/
│   ├── app/[locale]/{layout,page}.tsx, app/[locale]/design-system/page.tsx
│   ├── app/manifest.ts, public/sw.js, public/icons/
│   ├── i18n/{routing,request}.ts, middleware.ts, messages/fr.json
│   └── tests/{unit/, e2e/}
├── packages/
│   ├── config-typescript/, config-eslint/
│   ├── design-tokens/{tokens.json, build.ts, dist/}
│   ├── ui/src/{components/, icons/}
│   ├── core/src/money.ts
│   └── api-client/{src/schema.d.ts, src/index.ts}
├── docs/{api/openapi.json, adr/, GLOSSARY.md, security/threat-model.md, data/PII.md, runbooks/}
└── .github/workflows/{ci.yml, deploy-production.yml}
```

## 4. Dépendances et parallélisme

```
T01 ─┬─ T02 ── T03 ── T04 ── T05 ─┬─ T06
     │                            ├─ T07
     │                            └─ T08
     │                  T03 ── T09
     └─ T10 ── T11
        T03 + T10 ── T12 ── T13 ── T14 ── T15 ── T16
```

Parallélisables après T05 : T06, T07, T08 et T09 (fichiers disjoints). Côté web, T10 et T11 peuvent avancer en parallèle de T02 à T09. T13 complète la CI minimale posée en T01.

---

## 5. Tâches

### P0-T01 — Monorepo et CI minimale

**Fichiers :** créer `package.json` (scripts `dev`, `build`, `lint`, `typecheck`, `test`, `api:generate`), `pnpm-workspace.yaml` (`apps/*`, `packages/*`), `turbo.json` (tâches `build`, `lint`, `typecheck`, `test` avec `dependsOn: ["^build"]` et `outputs`), `.nvmrc` (`24`), `.editorconfig`, `packages/config-typescript/{base,nextjs,library}.json` (`strict: true`, `noUncheckedIndexedAccess: true`), `packages/config-eslint/index.js`, `README.md` (section « Démarrer »), `.github/workflows/ci.yml` (job `js` : install avec cache pnpm, `pnpm turbo lint typecheck test build`).

**Interfaces produites :** scripts racine `pnpm lint|typecheck|test|build` utilisés par toutes les tâches suivantes.

- [ ] Créer la branche `feat/P0-T01-monorepo`.
- [ ] Écrire les fichiers ci-dessus, avec un paquet témoin `packages/core` contenant `src/index.ts` et un test Vitest `index.test.ts` qui vérifie `expect(1 + 1).toBe(2)` (supprimé en P0-T05 web, remplacé par `money.test.ts`).
- [ ] Vérifier : `pnpm install && pnpm turbo build lint typecheck test` → sortie sans erreur.
- [ ] Commit `chore(repo): bootstrap pnpm + turborepo monorepo`.

**Terminé quand :** la commande ci-dessus passe en local et le job `js` est vert sur la PR.
**Risques :** versions de pnpm et de Node différentes entre local et CI → `packageManager` épinglé dans `package.json` et `.nvmrc` lu par `actions/setup-node`.

### P0-T02 — Infrastructure locale et image PostgreSQL

**Fichiers :** créer `infra/postgres/Dockerfile` (`FROM postgis/postgis:17-3.5` ; `apt-get install postgresql-17-pgvector postgresql-17-h3` depuis le dépôt PGDG déjà configuré dans l'image ; aucune autre couche), `infra/postgres/init/001-extensions.sql`, `infra/docker-compose.yml` (services `postgres` construit depuis `infra/postgres`, `redis:7-alpine`, `mailpit`, `minio`, ports locaux, volumes nommés), `.env.example` (variables de 5.8 sans valeur secrète), `infra/postgres/README.md` (procédure de mise à jour de l'image).

**Interfaces produites :** image locale `trovelya/postgres:17` ; URL locale `postgresql+asyncpg://trovelya:trovelya@localhost:5432/trovelya`.

- [ ] Écrire `infra/postgres/check_extensions.sql` : `CREATE EXTENSION IF NOT EXISTS` pour `postgis, vector, pg_trgm, unaccent, citext, btree_gist, ltree, h3, h3_postgis`, puis `SELECT extname FROM pg_extension ORDER BY 1`.
- [ ] Lancer `docker compose -f infra/docker-compose.yml up -d --build` puis `docker compose exec postgres psql -U trovelya -f /check_extensions.sql` **avant** le Dockerfile final : attendu ÉCHEC sur `vector` et `h3` avec l'image `postgis/postgis` brute.
- [ ] Compléter le Dockerfile (pgvector, h3-pg).
- [ ] Relancer : la requête liste les 9 extensions, plus `plpgsql`.
- [ ] Vérifier `redis-cli ping` → `PONG`, Mailpit sur `:8025`, MinIO sur `:9001`.
- [ ] Commit `chore(infra): local stack with postgres 17 + postgis + pgvector + h3 (ADR-0011)`.

**Terminé quand :** les 9 extensions sont créées sur une base neuve.
**Risques :** paquet `postgresql-17-h3` absent pour l'architecture arm64 (Mac M) → repli documenté : compilation de h3-pg via `pgxn` dans une étape de build multi-stage. Si h3 est impossible, le cahier (7.1) autorise le calcul H3 côté application : demander à Arcel avant de l'appliquer.

### P0-T03 — Squelette de l'API FastAPI

**Fichiers :** `apps/api/pyproject.toml` (uv, Python 3.12, dépendances de 5.5 ; groupes `dev` et `test` ; configuration ruff, pyright strict, pytest avec `asyncio_mode = "auto"`), `src/trovelya/main.py`, `core/config.py`, `core/errors.py`, `core/logging.py`, `core/middleware.py`, `core/health.py`, l'arborescence vide `modules/` (un `__init__.py` par module de P0 seulement : `ledger`), `tests/conftest.py`, `apps/api/package.json` (pour que Turborepo lance `lint`, `typecheck`, `test` via `uv run`), job `py` ajouté à `ci.yml`.

**Interfaces produites :**
- `create_app(settings: Settings | None = None) -> FastAPI`.
- `class Settings(BaseSettings)` : champs de 5.8 utiles en P0 (`env: Literal["local","preview","staging","production","test"]`, `database_url`, `redis_url`, `secret_key: SecretStr` (min 64 octets), `web_origin`, `admin_origin`, `sentry_dsn | None`, `otel_exporter_otlp_endpoint | None`, `feature_flags_default: dict[str, bool]`). Aucune valeur secrète par défaut ; démarrage en échec si une variable obligatoire manque.
- `class ErrorCode(StrEnum)` : `internal_error`, `validation_error`, `not_found`, `idempotency_conflict`, `idempotency_in_progress`, `rate_limited`, `csrf_failed`, `precondition_failed`, `service_unavailable`.
- `class AppError(Exception)` : `(code: ErrorCode, status: int, detail: str, errors: list[FieldError] | None = None)`, transformée en réponse RFC 9457 `application/problem+json` (corps de 11.2, `type = https://docs.trovelya.com/errors/<code>`).
- Middleware `RequestIdMiddleware` : lit ou crée `X-Request-Id` (`req_` + UUIDv7), le renvoie, le lie au contexte structlog.
- `GET /health` → `200 {"status":"ok"}` ; `GET /ready` → `200` si base et Redis répondent, sinon `503` au format problem+json.

- [ ] Tests d'abord, dans `tests/integration/test_app.py` : `test_health_ok` ; `test_ready_ok` ; `test_ready_503_when_redis_down` (Redis pointé sur un port fermé) ; `test_unknown_route_problem_json` (404, `content-type` `application/problem+json`, champs `type`, `title`, `status`, `code`, `request_id`) ; `test_validation_error_problem_json` (422 avec `errors[].field`) ; `test_request_id_propagated` (l'en-tête entrant est renvoyé tel quel) ; `test_internal_error_hides_details` (500 sans trace ni message d'exception). Dans `tests/unit/test_config.py` : `test_missing_secret_key_fails` ; `test_short_secret_key_fails`.
- [ ] `uv run pytest` → ÉCHEC (module introuvable).
- [ ] Implémenter.
- [ ] `uv run pytest && uv run ruff check && uv run ruff format --check && uv run pyright` → vert.
- [ ] Commit `feat(api): fastapi skeleton with config, rfc9457 errors, request id, health`.

**Terminé quand :** les commandes ci-dessus passent et le job `py` est vert.

### P0-T04 — Base de données, Alembic et migration initiale du socle

**Fichiers :** `core/db.py`, `alembic.ini`, `core/migrations/env.py` (async, `version_locations` = `core/migrations/versions` + `modules/*/migrations/versions`, cf. E6), `core/migrations/versions/0001_extensions_and_base.py`, `tests/integration/conftest.py` (fixture testcontainers sur l'image `trovelya/postgres:17`, migrations appliquées une fois par session, transaction annulée par test), `tests/integration/test_migrations.py`, `tests/integration/test_audit_log.py`.

**Contenu de la migration 0001 :** extensions (liste de P0-T02) ; fonction et convention de trigger `set_updated_at()` ; tables `platform_settings`, `feature_flags`, `outbox_events` (+ index partiel `outbox_unpublished_idx`), `processed_events`, `idempotency_keys` (forme E1), `audit_log` exactement comme en 7.2. Rôle applicatif `app_role` avec `REVOKE UPDATE, DELETE ON audit_log`. Trigger `audit_log_immutable` (BEFORE UPDATE OR DELETE → `RAISE EXCEPTION 'audit_log is append-only'`). Trigger `audit_log_chain` (BEFORE INSERT) : `pg_advisory_xact_lock(hashtext('audit_log_chain'))`, `prev_hash` := `hash` de la dernière ligne (ou `NULL`), `hash` := `sha256(coalesce(prev_hash,''::bytea) || convert_to(<ligne canonique>, 'UTF8'))`. La ligne canonique est `jsonb_build_object('occurred_at', 'actor_type', 'actor_id', 'approver_id', 'action', 'target_type', 'target_id', 'reason', 'before', 'after', 'request_id')::text` (E2). Le `downgrade` supprime tout dans l'ordre inverse, extensions comprises.

**Interfaces produites :**
- `make_engine(url: str) -> AsyncEngine` ; `make_sessionmaker(engine) -> async_sessionmaker[AsyncSession]` ; dépendance FastAPI `get_uow() -> AsyncIterator[AsyncSession]` qui valide en fin de requête réussie et annule sinon (seule frontière qui fait `commit`, 5.4).
- Fonction SQL `audit_verify_chain() RETURNS TABLE(id bigint, ok boolean)`.

- [ ] Tests d'abord :
  - `test_upgrade_downgrade_upgrade` : sur base vide, `alembic upgrade head`, `downgrade base`, `upgrade head` réussissent ; après le premier `upgrade`, `pg_extension` contient les 9 extensions.
  - `test_audit_update_rejected` et `test_audit_delete_rejected` : `UPDATE`/`DELETE` sur `audit_log` lèvent une erreur contenant `append-only`.
  - `test_audit_chain_links` : 3 insertions ; `row[n].prev_hash == row[n-1].hash` ; `row[0].prev_hash IS NULL`.
  - `test_audit_chain_detects_tampering` : désactiver le trigger avec le rôle propriétaire, modifier `reason` de la ligne 2, réactiver ; `audit_verify_chain()` renvoie `ok = false` à partir de la ligne 2.
  - `test_concurrent_inserts_keep_single_chain` (point de revue 2) : 20 insertions concurrentes depuis 20 sessions ; tous les `prev_hash` sont distincts et la chaîne se vérifie.
  - `test_updated_at_trigger` : un `UPDATE` sur `platform_settings` change `updated_at`.
- [ ] `uv run pytest tests/integration -k "migrations or audit"` → ÉCHEC.
- [ ] Écrire `db.py`, `env.py` et la migration.
- [ ] Relancer → vert ; puis `uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head` sur la base docker locale.
- [ ] Commit `feat(core): initial migration with outbox, idempotency, flags, settings and append-only chained audit log (ADR-0012, ADR-0014)`.

**Risques :** testcontainers exige Docker en CI (disponible sur les runners `ubuntu-latest`) ; l'image doit être construite avant les tests (étape `docker build -t trovelya/postgres:17 infra/postgres` dans le job `py`).

### P0-T05 — Bibliothèque `shared/` et services de paramètres et de flags

**Fichiers :** `shared/money.py`, `shared/ids.py`, `shared/clock.py`, `shared/events.py`, `shared/audit.py`, `core/redis.py`, `core/settings_service.py`, `core/flags.py`, et côté TS `packages/core/src/money.ts`. Tests dans `tests/unit/` et `tests/integration/`, et `packages/core/src/money.test.ts`.

**Interfaces produites :**
- `@dataclass(frozen=True, slots=True) class Money: amount_minor: int; currency: str`. Le constructeur refuse tout ce qui n'est pas un `int` strict (`bool`, `float`, `Decimal` → `TypeError`) et toute devise qui ne respecte pas `^[A-Z]{3}$` (`ValueError`). `__add__`, `__sub__` et les comparaisons exigent la même devise (`CurrencyMismatchError`). Les montants négatifs sont autorisés dans `Money` (soldes), mais interdits en base par les `CHECK`.
- `ceil_div(numerator: int, denominator: int) -> int`, `floor_div(numerator: int, denominator: int) -> int` (`denominator > 0`).
- `percent_bp_ceil(amount: Money, bp: int) -> Money` (frais facturés à l'acheteur) et `percent_bp_floor(amount: Money, bp: int) -> Money` (montants reversés), `bp` en points de base (10 000 = 100 %). Chaque docstring précise le sens de l'arrondi.
- `new_id() -> uuid.UUID` (UUIDv7).
- `class Clock(Protocol): def now(self) -> datetime` (UTC, *aware*) ; `SystemClock` ; `FixedClock(at: datetime)` avec `advance(delta)`.
- `async def emit_event(session: AsyncSession, *, type: str, aggregate_type: str, aggregate_id: UUID, payload: dict[str, Any], version: int = 1) -> UUID` : ajoute une ligne à `outbox_events` **dans la session fournie**, sans `commit` ; `payload` stocké avec la clé `"v"`.
- `async def record_audit(session: AsyncSession, *, actor_type: Literal["user","staff","system","api_client"], actor_id: UUID | None, action: str, target_type: str, target_id: str, reason: str | None = None, before: dict | None = None, after: dict | None = None, approver_id: UUID | None = None, request_id: str | None = None, ip: str | None = None, user_agent: str | None = None) -> int`.
- `SettingsService(session_factory, redis, ttl_s=60)` : `async get(key: str) -> Any` (lève `SettingNotFound`) ; `async set(session, key: str, value: Any, *, actor_id: UUID, reason: str) -> None` (écrit, puis `record_audit(action="settings.update", before, after)`, puis invalide le cache **après le commit**, via `session.info` et un hook `after_commit`).
- `FlagService(session_factory, redis, defaults: dict[str,bool], ttl_s=60)` : `async is_enabled(key: str, *, user_id: UUID | None = None, country: str | None = None) -> bool`. Règle : clé inconnue → valeur de `FEATURE_FLAGS_DEFAULT`, sinon `False` ; `user_id` dans `allow_user_ids` → `True` ; `countries` non vide et pays absent → `False` ; sinon `enabled` et (`rollout_pct == 100` ou `int(sha256(f"{user_id}:{key}"), 16) % 100 < rollout_pct`) ; sans `user_id`, seul `rollout_pct == 100` compte.
- TS : `type Money = { amountMinor: number; currency: string }`, `formatMoney(m: Money, locale: string): string` (`Intl.NumberFormat`, division par 10^fraction digits de la devise) et `assertMinor(n: number): asserts n is number` (lève si `!Number.isSafeInteger(n)`).

- [ ] Tests d'abord :
  - `test_money.py` : `test_rejects_non_int_amount` (paramétré `1.0`, `True`, `Decimal("1")`) ; `test_rejects_bad_currency` (`"eur"`, `"EURO"`) ; `test_currency_mismatch_raises` ; `test_add_sub_same_currency` ; `test_percent_bp_ceil_rounds_up` (`Money(1899,"EUR")` à 500 bp → `95`, cas 8.1) ; `test_percent_bp_floor_rounds_down` (`1899` à 500 bp → `94`) ; propriétés hypothesis `test_ceil_ge_floor`, `test_ceil_minus_floor_le_1`, `test_ceil_div_exact` (`ceil_div(a,b)*b >= a > (ceil_div(a,b)-1)*b`).
  - `test_ids.py` : `test_uuid7_version` (`new_id().version == 7`) ; `test_uuid7_monotonic` (1 000 identifiés triés = ordre de génération).
  - `test_events.py` (intégration) : `test_emit_event_rolled_back_not_persisted` ; `test_emit_event_committed_persisted` (`payload["v"] == 1`).
  - `test_settings_service.py` : `test_get_cached` (deuxième lecture sans requête SQL) ; `test_set_writes_audit` ; `test_cache_invalidated_only_after_commit` (une annulation ne vide pas le cache).
  - `test_flags.py` : `test_unknown_flag_uses_default` ; `test_allow_list` ; `test_country_filter` ; `test_rollout_deterministic` (même résultat sur 100 appels) ; `test_rollout_distribution` (10 000 utilisateurs à 30 % → entre 28 % et 32 %).
  - `money.test.ts` : `formatMoney({amountMinor:24000,currency:"EUR"},"fr-FR") === "240,00 €"` (avec espace insécable) ; `assertMinor(1.5)` lève.
- [ ] Lancer → ÉCHEC.
- [ ] Implémenter.
- [ ] `uv run pytest --cov=trovelya.shared.money --cov-fail-under=100` et `pnpm --filter @trovelya/core test` → vert.
- [ ] Commit `feat(shared): money, ids, clock, outbox emit, audit, settings and flags services`.

### P0-T06 — Worker arq et relais de l'outbox

**Fichiers :** `workers/main.py` (`class WorkerSettings` arq : `functions`, `cron_jobs`, `redis_settings` depuis `Settings`), `workers/outbox_relay.py`, `shared/events.py` (ajout de la consommation idempotente), tests.

**Interfaces produites :**
- `class EventPublisher(Protocol): async def publish(self, event: OutboxEvent) -> None` ; `RedisStreamPublisher(redis, stream="trv:events")` (`XADD` avec `MAXLEN ~ 100000`) ; `InMemoryPublisher` pour les tests.
- `async def relay_outbox_batch(session_factory, publisher: EventPublisher, *, limit: int = 100, clock: Clock) -> int` : dans une transaction, `SELECT … WHERE published_at IS NULL ORDER BY id LIMIT :limit FOR UPDATE SKIP LOCKED`, publie dans l'ordre, met `published_at = clock.now()`, valide, puis renvoie le nombre d'événements. Une erreur de publication annule le lot entier (au moins une fois).
- `async def consume_once(session: AsyncSession, consumer: str, event_id: UUID, handler: Callable[[], Awaitable[None]]) -> bool` : `INSERT INTO processed_events … ON CONFLICT DO NOTHING RETURNING` ; si déjà traité → `False` sans appeler `handler`.
- Tâche cron `relay_outbox` toutes les secondes (arq `cron` à la seconde) et tâche cron `audit_verify_chain_job` à 03:00 Europe/Paris, qui journalise une erreur et envoie une alerte Sentry si une ligne est `ok = false`.

- [ ] Tests d'abord : `test_rolled_back_event_never_published` (événement émis puis transaction annulée → `relay_outbox_batch` renvoie 0, `InMemoryPublisher.events == []`) ; `test_relay_publishes_in_id_order` ; `test_relay_marks_published` ; `test_publish_failure_keeps_batch_unpublished` ; `test_two_relays_do_not_share_rows` (point de revue 2.3, deux relais concurrents, aucun événement publié deux fois) ; `test_consume_once_idempotent` (deux appels → handler appelé une fois) ; `test_audit_job_alerts_on_broken_chain`.
- [ ] ÉCHEC → implémenter → vert.
- [ ] Vérifier en local : `uv run arq trovelya.workers.main.WorkerSettings` démarre et vide l'outbox (événement inséré à la main → `published_at` renseigné, entrée visible avec `redis-cli XRANGE trv:events - +`).
- [ ] Commit `feat(workers): arq worker with transactional outbox relay and idempotent consumers`.

### P0-T07 — Squelette du grand livre en partie double

**Fichiers :** `modules/ledger/models.py`, `modules/ledger/repository.py`, `modules/ledger/service.py`, `modules/ledger/errors.py`, `modules/ledger/migrations/versions/0002_ledger.py`, `modules/ledger/tests/`.

**Contenu de la migration 0002 :** type `ledger_account_type`, tables `ledger_accounts`, `ledger_transactions`, `ledger_entries` exactement comme en 7.8, plus l'index `ledger_entries_account_idx`. Puis :
- fonction `ledger_check_balance()` + `CREATE CONSTRAINT TRIGGER ledger_entries_balanced AFTER INSERT ON ledger_entries DEFERRABLE INITIALLY DEFERRED FOR EACH ROW` : pour `NEW.transaction_id`, pour chaque devise, `sum(D) = sum(C)`, sinon `RAISE EXCEPTION 'ledger transaction % unbalanced'` ;
- `CREATE CONSTRAINT TRIGGER ledger_transactions_has_entries AFTER INSERT ON ledger_transactions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW` : au moins 2 écritures (point de revue 2.1) ;
- triggers `BEFORE UPDATE OR DELETE` sur `ledger_entries` et `ledger_transactions` → exception (écritures immuables) ;
- vue matérialisée `ledger_balances` (7.8) avec index unique `(account_id, currency)` pour `REFRESH … CONCURRENTLY`.
Le plan de comptes complet (7.8) et les écritures types (10.4) relèvent de P4 ; P0 ne crée aucun compte en dur.

**Interfaces produites :**
- `@dataclass(frozen=True) class EntryInput: account_id: UUID; direction: Literal["D","C"]; amount: Money` (`amount.amount_minor > 0`).
- `async def get_or_create_account(session, *, code: str, type: LedgerAccountType, currency: str, description: str, owner_user_id: UUID | None = None) -> UUID`.
- `async def post_transaction(session: AsyncSession, *, kind: str, reference_type: str, reference_id: UUID, idempotency_key: str, description: str, entries: Sequence[EntryInput], created_by: str = "system") -> PostedTransaction`. Contrôle aussi l'équilibre en Python avant l'insertion (`LedgerUnbalancedError`), ce qui donne un message clair, mais la base reste la garantie. Si la clé existe déjà : même contenu (`kind`, `reference`, multiset d'écritures) → renvoie la transaction existante avec `replayed=True` ; contenu différent → `LedgerIdempotencyConflict`. Jamais de `commit`.
- `async def account_balance(session, account_id: UUID, currency: str) -> Money` (débit − crédit, requête directe).

- [ ] Tests d'abord :
  - `test_unbalanced_rejected_at_commit` : insertion SQL directe d'une écriture D 100 sans contrepartie ; l'`INSERT` réussit, le `COMMIT` lève `unbalanced` (preuve que le trigger est différé).
  - `test_balanced_with_temporary_imbalance_commits` : D 100, puis C 60, puis C 40 dans la même transaction → `COMMIT` OK.
  - `test_multi_currency_each_balanced` : EUR équilibré + PLN déséquilibré → rejet.
  - `test_transaction_without_entries_rejected` et `test_transaction_with_single_entry_rejected`.
  - `test_entries_immutable` : `UPDATE` et `DELETE` → exception.
  - `test_idempotent_replay_no_duplicate` : deux `post_transaction` avec la même clé et le même contenu → 1 ligne dans `ledger_transactions`, 2 écritures, `replayed=True` au second appel.
  - `test_idempotency_conflict` : même clé, montant différent → `LedgerIdempotencyConflict`.
  - `test_service_rejects_unbalanced_before_db`.
  - Propriétés hypothesis (`max_examples=500`) : `test_property_random_balanced_sets_commit` (listes aléatoires de 2 à 12 écritures construites équilibrées, sur 1 à 3 devises) ; `test_property_random_unbalanced_sets_rejected` ; `test_property_sum_of_all_balances_is_zero` (après N transactions, la somme des soldes de tous les comptes est 0 par devise).
- [ ] ÉCHEC → implémenter → vert ; `upgrade → downgrade → upgrade` toujours vert.
- [ ] Commit `feat(ledger): double-entry ledger skeleton with deferred balance constraint and idempotent posting`.

### P0-T08 — Idempotence HTTP, limites de débit, CSRF

**Fichiers :** `core/idempotency.py`, `core/ratelimit.py`, `core/csrf.py`, branchement dans `main.py`, tests d'intégration. En P0, seule une route de test `POST /v1/_test/echo` (montée uniquement si `env in {"local","test"}`) sert de cible.

**Interfaces produites :**
- Dépendance `require_idempotency_key()` (obligatoire sur les routes déclarées) et middleware `IdempotencyMiddleware` : clé `Idempotency-Key` (UUID, sinon 400) ; `request_hash = sha256(method ‖ path ‖ corps canonique)`. Clé connue avec le même hash et une réponse stockée → rejoue le statut et le corps avec l'en-tête `Idempotent-Replayed: true`. Hash différent → `409 idempotency_conflict`. Clé en cours (ligne sans réponse) → `409 idempotency_in_progress`. Purge des clés de plus de 72 h par une tâche cron arq quotidienne.
- `rate_limit(scope: str, limit: int, window_s: int, key_func: Callable[[Request], str])` : dépendance FastAPI, fenêtre glissante Redis (ZSET + script Lua atomique) ; au-delà → `429 rate_limited` avec `Retry-After`. Limite globale anonyme par défaut : 120 req/min par IP (11.4). Redis indisponible → laisser passer et journaliser `ratelimit.redis_unavailable` (§2).
- CSRF « double-submit » signé : cookie `trv_csrf` (non `HttpOnly`, `Secure`, `SameSite=Lax`) = `token.HMAC(SECRET_KEY, token)` ; pour toute méthode non sûre **qui porte le cookie `trv_session`**, l'en-tête `X-CSRF-Token` doit égaler le cookie et la signature doit être valide, sinon `403 csrf_failed`. Route `GET /v1/csrf` qui pose le cookie.

- [ ] Tests d'abord : `test_missing_key_400` ; `test_replay_same_response` ; `test_same_key_different_body_409` ; `test_concurrent_same_key_single_execution` (point de revue 2.5) ; `test_keys_scoped_by_user` (`user_id` nul en P0 : même clé et même hash → rejoue) ; `test_rate_limit_429_with_retry_after` (limite abaissée à 3 dans le test) ; `test_rate_limit_fail_open_when_redis_down` ; `test_csrf_required_with_session_cookie` ; `test_csrf_bad_signature_403` ; `test_csrf_not_required_without_session_cookie`.
- [ ] ÉCHEC → implémenter → vert.
- [ ] Commit `feat(core): http idempotency keys, redis sliding-window rate limit and signed double-submit csrf`.

### P0-T09 — Test d'architecture

**Fichiers :** `apps/api/.importlinter`, `tests/architecture/test_architecture.py`, deux modules vides témoins `modules/catalog/` et `modules/orders/` (`__init__.py` et `service.py` vides), créés **uniquement** pour que le contrat ait au moins deux modules. Ils sont signalés comme tels dans leur docstring.

**Contrats import-linter :**
1. `independence` entre les sous-paquets `trovelya.modules.*`, avec exception permise uniquement vers `trovelya.modules.<x>.service` (règle 5.4.1 : on passe par le `service.py` public). Implémenté comme un contrat `forbidden` généré par module : `trovelya.modules.<a>` ne peut pas importer `trovelya.modules.<b>.repository` ni `trovelya.modules.<b>.models`.
2. `layers` : `trovelya.main` > `trovelya.modules` > `trovelya.core` | `trovelya.shared` (le socle n'importe jamais un module).

- [ ] Test d'abord : `test_import_contracts_pass` lance `lint-imports` et attend le code 0 ; `test_violation_detected` copie le paquet dans un dossier temporaire, ajoute `from trovelya.modules.catalog.models import X` dans `orders/service.py`, puis attend un code non nul.
- [ ] ÉCHEC → configurer → vert ; ajout de l'étape `uv run lint-imports` au job `py`.
- [ ] Commit `test(architecture): enforce module boundaries with import-linter`.

### P0-T10 — Application web Next.js

**Fichiers :** `apps/web/` (Next.js App Router, TypeScript strict qui étend `config-typescript/nextjs.json`), `next.config.ts` (en-têtes de 13.2 : HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` avec `camera=(), microphone=(), geolocation=()`, `frame-ancestors 'none'` dans la CSP), `middleware.ts` (next-intl + CSP avec **nonce** par requête ; `script-src 'self' 'nonce-…' 'strict-dynamic'`, sans `unsafe-inline` pour les scripts), `i18n/routing.ts` (`locales: ["fr"]`, `defaultLocale: "fr"`, `localePrefix: "always"`), `i18n/request.ts`, `messages/fr.json`, `app/[locale]/layout.tsx` (`<html lang>`, polices Geist et Geist Mono via le paquet `geist`, thème clair et sombre par `prefers-color-scheme` et attribut `data-theme`), `app/[locale]/page.tsx` (page d'accueil vide : logo, slogan « La belle trouvaille », tout le texte venant de `fr.json`), `app/manifest.ts`, `public/sw.js` (service worker minimal : mise en cache de la page hors ligne), `public/icons/` (192, 512, maskable), `packages/design-tokens/{tokens.json,build.ts}` (tokens de 6.2 → `dist/tokens.css` avec variables `--trv-*` clair/sombre, plus `dist/theme.css` pour le `@theme` de Tailwind 4), `tests/e2e/home.spec.ts`, `playwright.config.ts`.

**Interfaces produites :** `@trovelya/design-tokens/tokens.css` et `@trovelya/design-tokens/theme.css` ; fonction `getTranslations` de next-intl utilisée partout ; aucune chaîne en dur (règle ESLint `i18next/no-literal-string` ou équivalent, appliquée à `app/` et `packages/ui`).

- [ ] Tests d'abord (Playwright, `tests/e2e/home.spec.ts`) : `redirects root to /fr` ; `home has lang=fr and slogan from messages` ; `security headers present` (CSP sans `unsafe-inline` dans `script-src`, HSTS, `frame-ancestors 'none'`) ; `csp nonce differs between two requests` ; `dark mode tokens applied` (émulation `colorScheme: 'dark'` → `--trv-color-surface` = `#0B0B0F`) ; `manifest is installable` (manifeste avec `name`, `start_url`, `display: standalone`, icônes 192 et 512 ; service worker en état `activated`) ; `axe has no violations` (`@axe-core/playwright`, 0 violation critique ou sérieuse, 360 px et 1 280 px). Test Vitest `tokens.test.ts` : `build` produit `--trv-color-brand: #1D2BFF` (clair) et `#4D5BFF` (sombre).
- [ ] ÉCHEC → implémenter → vert : `pnpm --filter web build && pnpm --filter web test:e2e`.
- [ ] Mesure : `pnpm dlx @lhci/cli autorun` sur le build de production local → Best Practices ≥ 95, Accessibilité = 100, Performance ≥ 95 sur mobile (E3). Enregistrer la sortie dans la PR.
- [ ] Commit `feat(web): next.js app with next-intl, design tokens, csp nonces, dark mode and pwa`.

**Risques :** next-intl et le nonce CSP doivent cohabiter dans un seul `middleware.ts` ; les polices passent par `next/font` pour rester compatibles avec la CSP.

### P0-T11 — `packages/ui` : composants de base

**Fichiers :** `packages/ui/src/components/` : `Button`, `IconButton`, `Input`, `Select`, `Checkbox`, `Switch`, `Dialog`, `Sheet`, `Tabs`, `Toast`, `Badge`, `Avatar`, `Card`, `Skeleton`, `Price`, `Distance`, `EmptyState`, `Squircle`, `LiquidGlass`. Également `packages/ui/src/icons/` (icône `Logo` avec le chemin `M4.5 4h15v3.8h-5.6V20.5h-3.8V7.8H4.5z` de 6.2, plus les icônes nécessaires à ces composants, trait de 1,75 px) et la page `apps/web/app/[locale]/design-system/page.tsx` (E4).

**Interfaces produites (props clés) :**
- `Button`/`IconButton` : `variant: "primary"|"secondary"|"ghost"|"danger"`, `size: "sm"|"md"|"lg"` ; cible ≥ 44 px ; `IconButton` exige `label: string`.
- `Price({ amountMinor, currency, locale })` utilise `formatMoney` de `@trovelya/core` en police mono ; refuse un nombre non entier.
- `Distance({ meters })` : arrondi d'affichage de 8.11 (< 1 km → « moins de 1 km » ; < 10 km → au km ; ≥ 10 km → à 5 km près ; ≥ 100 km → à 10 km près), textes passés par un paramètre `t` pour rester traduisibles.
- `LiquidGlass` : style de 6.2, avec une variante opaque si `@supports not (backdrop-filter)` ou si `prefers-reduced-transparency`.
- Les primitives `Dialog`, `Sheet`, `Tabs`, `Select`, `Checkbox`, `Switch` et `Toast` reposent sur Radix.
- Animations : durées 120/200/320 ms, désactivées si `prefers-reduced-motion`.

- [ ] Tests d'abord (Vitest + Testing Library) : `Price` (`24000 EUR fr-FR` → `240,00 €`, `1.5` lève) ; `Distance` (cas 800 m, 3 400 m, 12 000 m, 392 000 m → « moins de 1 km », « 3 km », « 10 km », « 390 km ») ; `IconButton requires label` (erreur de type, vérifiée par un `@ts-expect-error`) ; `Dialog traps focus and closes on Escape`. Playwright : `design-system page has no axe violations` en clair et en sombre ; `design-system returns 404 when ENV=production`.
- [ ] ÉCHEC → implémenter → vert.
- [ ] Commit `feat(ui): accessible base components, house icons, squircles and liquid glass`.

**Question ouverte, non bloquante pour P0 :** le jeu d'icônes maison complet (6.2) dépend de la maquette. P0 ne livre que les icônes utilisées par ces composants.

### P0-T12 — `packages/api-client` généré depuis OpenAPI

**Fichiers :** `apps/api/src/trovelya/scripts/export_openapi.py` (écrit `create_app().openapi()` en JSON trié et indenté), `docs/api/openapi.json`, `packages/api-client/{package.json,src/schema.d.ts,src/index.ts}`, script racine `api:generate` = `uv run --project apps/api python -m trovelya.scripts.export_openapi docs/api/openapi.json && openapi-typescript docs/api/openapi.json -o packages/api-client/src/schema.d.ts`. Chaque route FastAPI a un `operation_id` explicite (`health_get`, `ready_get`, `csrf_get`) ; un test l'impose.

**Interfaces produites :** `createApiClient(baseUrl: string, init?: { fetch?: typeof fetch }) -> Client<paths>` (`openapi-fetch`), avec `credentials: "include"` et l'ajout automatique de `X-CSRF-Token` sur les méthodes non sûres.

- [ ] Tests d'abord : `test_all_routes_have_explicit_operation_id` (Python) ; `api-client.test.ts` : `client.GET("/health")` contre un serveur simulé renvoie `{status:"ok"}`, avec un typage vérifié par `tsc`.
- [ ] ÉCHEC → implémenter → vert.
- [ ] Ajouter au CI l'étape `pnpm api:generate && git diff --exit-code docs/api packages/api-client/src`.
- [ ] Vérifier que la CI échoue si l'on ajoute une route sans régénérer (essai sur la branche, puis annulation).
- [ ] Commit `feat(api-client): generated typescript client from openapi with ci drift check`.

### P0-T13 — CI GitHub Actions complète (16.3)

**Fichiers :** `.github/workflows/ci.yml` complété, `.semgrep.yml` (règles `p/python`, `p/typescript`, `p/secrets`, `p/owasp-top-ten` ; bloquant à partir de la sévérité `ERROR`), `.gitleaks.toml`, `.github/dependabot.yml` (npm, pip/uv, actions, docker ; hebdomadaire).

**Jobs (déclenchés sur chaque PR et chaque push sur `main`) :**
1. `js` : lint, typecheck, test, build (cache pnpm et Turborepo).
2. `py` : `docker build infra/postgres`, ruff, pyright, `lint-imports`, pytest avec couverture (seuil global 85 % ; `shared/money.py` à 100 %), migrations `upgrade → downgrade → upgrade`.
3. `contract` : `pnpm api:generate` + `git diff --exit-code`.
4. `e2e-web` : build de production web, Playwright et axe.
5. `security` : semgrep, gitleaks (historique complet), `uv run pip-audit`, `pnpm audit --audit-level high` ; bloquant sur une sévérité haute.
6. `sbom` (sur `main` seulement) : CycloneDX pour Python et JS, publié en artefact.

Le cache distant de Turborepo n'est **pas** activé en P0 : il faut un jeton Vercel dans les secrets GitHub. Ce sera une étape optionnelle de P0-T14 si Arcel fournit le jeton.

- [ ] Ouvrir une PR de test contenant volontairement (a) une fausse clé AWS, (b) une erreur de type, (c) une migration sans `downgrade` : chaque job concerné doit être rouge. Retirer ensuite ces trois erreurs : tout doit repasser au vert.
- [ ] Demander à Arcel d'activer la protection de `main` (checks obligatoires : les 5 jobs, au moins 1 revue, pas de push direct). Cette action se fait dans les réglages GitHub et lui revient.
- [ ] Commit `ci: full pipeline with contract check, e2e, migrations roundtrip and blocking security scans`.

### P0-T14 — Déploiements Railway et Vercel

**Fichiers :** `apps/api/Dockerfile` (multi-stage, uv, utilisateur non-root, `CMD uvicorn trovelya.main:app --host 0.0.0.0 --port $PORT --proxy-headers`), `apps/api/railway.json` (pré-déploiement `alembic upgrade head`, `healthcheckPath: /ready`), `apps/api/railway.worker.json` (démarrage `arq trovelya.workers.main.WorkerSettings`), `infra/postgres/railway.json`, `apps/web/vercel.json` si nécessaire, `.github/workflows/deploy-production.yml` (E5), `docs/runbooks/deploy.md`.

**Étapes sur Railway (via le connecteur ; chaque action destructrice demande d'abord l'accord d'Arcel) :**
- [x] Renommer le projet en `trovelya` (fait par Arcel le 23/10/2026).
- [ ] Créer l'environnement `staging`. Vérifier la région `europe-west4` pour chaque service.
- [ ] Créer le service `postgres` depuis le dépôt (dossier racine `infra/postgres`) avec un volume monté sur `/var/lib/postgresql/data`, dans `staging` puis dans `production`. Vérifier les extensions en ligne avec `psql` via une connexion temporaire : les 9 extensions doivent être présentes. **Porte de la tâche : on ne continue pas si une extension manque.**
- [ ] Renommer le service `TROVELYA` en `api` (racine `apps/api`), et créer le service `worker` (même image, configuration `railway.worker.json`). Variables par référence (`DATABASE_URL=${{postgres.DATABASE_URL}}` réécrite en `postgresql+asyncpg`, `REDIS_URL=${{Redis.REDIS_URL}}`). `SECRET_KEY` est générée par Railway (`${{secret(64)}}`), **jamais** saisie ni affichée ici.
- [ ] Ajouter Redis dans `staging`.
- [ ] Branches : `staging` suit `main` avec l'attente de la CI activée ; `production` suit `release`. Aperçus par PR désactivés.
- [ ] Générer les domaines `*.up.railway.app` pour `api`.
- [ ] Avec l'accord d'Arcel : supprimer l'ancien service `Postgres` (vide) une fois le nouveau vérifié.

**Étapes sur Vercel :**
- [ ] Projet `trovelya` : racine `apps/web`, framework Next.js, Node 24, région des fonctions `fra1`, branche de production `release`. Variables `NEXT_PUBLIC_API_URL` : Preview (dont `main`) = API staging, Production = API production.
- [ ] Staging web = alias de branche `trovelya-git-main-arcels-projects-b0c39648.vercel.app` (protection SSO Vercel conservée sur les aperçus).

**Vérifications :**
- [ ] `curl -sf https://<api-staging>.up.railway.app/health` → `{"status":"ok"}` ; `/ready` → 200 ; `alembic current` sur staging = `head`.
- [ ] Fusion d'un commit anodin sur `main` → API, worker et web staging redéployés automatiquement après la CI, sans action manuelle.
- [ ] Tag `v0.0.1` → le workflow attend l'approbation de l'environnement `production`, puis `release` avance et la production se déploie. `/health` de production → 200.
- [ ] **Domaine** (dès qu'Arcel a acheté `trovelya.com`) : `api.`, `staging.`, `admin.` et la racine, avec les enregistrements DNS donnés par Railway et Vercel.

**Risque important pour P1 :** sans domaine commun, le web (`vercel.app`) et l'API (`railway.app`) sont sur deux sites différents, et un cookie de session `SameSite=Lax` ne sera pas envoyé. Pas d'impact en P0 (pas de session). Recommandation : acheter le domaine **avant P1**, ou faire passer l'API par une réécriture Next.js (`/api/v1/*` → API) sur le même site. À trancher au lancement de P1.

### P0-T15 — Observabilité

**Fichiers :** `core/logging.py` (structlog JSON ; processeur `redact_pii` qui masque e-mails, numéros de téléphone, IBAN, jetons `Bearer`, cookies, et toute clé nommée `password|token|secret|authorization|cookie|email|phone|iban|address`), `core/observability.py` (Sentry avec `send_default_pii=False` et `environment=settings.env` ; OpenTelemetry pour FastAPI, SQLAlchemy, httpx et redis, exportateur OTLP si l'endpoint est défini), Sentry côté web (`@sentry/nextjs`, région UE), route `GET /v1/_debug/error` montée seulement si `env != "production"`, `docs/runbooks/observability.md` (tableau de bord Grafana de base : taux d'erreur, p95, âge du plus ancien événement d'outbox non publié).

**Interfaces produites :** métrique `trovelya_outbox_oldest_unpublished_seconds` (jauge mise à jour par le relais) ; `configure_logging(settings) -> None` ; `configure_observability(app, settings) -> None`.

- [ ] Tests d'abord : `test_redact_email_phone_iban_token` (paramétré : `jean.dupont@gmail.com`, `06 12 34 56 78`, `FR76 3000 6000 0112 3456 7890 189`, `Bearer abc.def`) → aucune valeur en clair dans la ligne JSON produite ; `test_redact_sensitive_keys` ; `test_log_line_has_request_id` ; `test_debug_error_route_absent_in_production` ; `test_sentry_not_initialised_without_dsn`.
- [ ] ÉCHEC → implémenter → vert.
- [ ] En staging, après qu'Arcel a mis `SENTRY_DSN` : appeler `/v1/_debug/error`, l'erreur doit apparaître dans Sentry (capture d'écran dans la PR). Configurer un moniteur de disponibilité Sentry sur `/health` (alerte au-delà de 1 min d'indisponibilité, 16.4).
- [ ] Commit `feat(observability): structlog json with pii redaction, sentry eu and opentelemetry`.

### P0-T16 — Documentation

**Fichiers :** `docs/adr/0001` à `0014` (format : contexte, décision, conséquences ; 0001-0010 repris de 5.2, 0011-0014 de la section 0 de ce plan), `docs/GLOSSARY.md` (section 2 du cahier, plus les termes techniques de P0 : outbox, clé d'idempotence, chaîne d'audit, transaction différée), `docs/security/threat-model.md` v1 (STRIDE sur le périmètre P0 : API, base, worker, CI, secrets, chaîne d'approvisionnement ; skill `stride-analysis-patterns`), `docs/data/PII.md` (P0 : `audit_log.ip`, `audit_log.user_agent`, `idempotency_keys.user_id` ; finalité ; durée de conservation 10 ans pour l'audit et 72 h pour l'idempotence), `docs/runbooks/{deploy,rollback,restore}.md`, `docs/HANDOFF.md`.

- [ ] Rédiger. Exercice réel de `restore.md` sur staging : sauvegarde logique avec `pg_dump` de staging, restauration dans une base jetable, puis vérification de `audit_verify_chain()` et du nombre de lignes. La sortie est collée dans le runbook.
- [ ] Exercice réel de `rollback.md` : redéploiement du déploiement précédent de l'API staging depuis Railway, puis vérification de `/health`.
- [ ] PR unique de documentation pour revue par Arcel (Q13).
- [ ] Commit `docs: adr 0001-0014, glossary, threat model v1, pii register and runbooks`.

---

## 6. Porte de P0 (cahier 17.1) : checklist et preuves

| # | Critère | Preuve attendue |
|---|---|---|
| G1 | Une PR déclenche toute la CI | Lien vers une PR avec les jobs `js`, `py`, `contract`, `e2e-web` et `security` exécutés ; PR de test de T13 rouge puis verte. |
| G2 | `main` se déploie seule en staging | Commit fusionné sur `main` → identifiants des déploiements Railway (`api`, `worker`) et Vercel horodatés après la CI, sans action manuelle. |
| G3 | Base avec extensions | Sortie de `SELECT extname FROM pg_extension` **sur staging** : les 9 extensions. |
| G4 | Outbox testée | Sortie pytest de `test_rolled_back_event_never_published`, `test_two_relays_do_not_share_rows` et `test_consume_once_idempotent`. |
| G5 | Audit inaltérable et chaîné | Sortie pytest des tests d'audit ; sur staging, `SELECT bool_and(ok) FROM audit_verify_chain()` → `t`. |
| G6 | Grand livre équilibré | Sortie pytest de T07, dont les propriétés hypothesis (nombre d'exemples affiché). |
| G7 | Money couverte à 100 % | Rapport `--cov-fail-under=100` sur `shared/money.py`. |
| G8 | Architecture protégée | Sortie de `lint-imports` (0) et du test de violation (≠ 0). |
| G9 | Page web rapide, accessible, traduite, installable | Rapport Lighthouse (Performance ≥ 95 mobile, Accessibilité 100, Best Practices ≥ 95), Playwright `manifest is installable`, axe à 0 violation, `lang="fr"` et textes issus de `fr.json`. |
| G10 | Sécurité web | En-têtes de staging (`curl -I`) : CSP à nonce, HSTS, `frame-ancestors 'none'`. |
| G11 | Observabilité | Erreur volontaire visible dans Sentry (capture) ; moniteur de disponibilité actif. |
| G12 | Production déployable | Tag `v0.0.1` → `/health` de production à 200. |
| G13 | Documentation | ADR-0001 à 0014, `GLOSSARY.md`, `threat-model.md` v1, `PII.md`, les trois runbooks, dont les exercices de restauration et de retour arrière réellement joués. |

**Hors périmètre de P0 (explicitement) :** toute table métier (utilisateurs, annonces…), l'authentification, l'envoi réel d'e-mails, le stockage objet réel, le plan de comptes du grand livre et les écritures de 10.4 (P4), la double validation des paramètres (P8), le domaine `trovelya.com` si non acheté, et le cache distant Turborepo sans jeton.

## 7. Actions qui reviennent à Arcel pendant P0

1. Valider ce plan et les écarts E1 à E6 (Q1 à Q13 déjà validés).
2. Autoriser le push des branches `feat/P0-*` et l'ouverture des PR.
3. Créer l'organisation Sentry UE et coller le DSN dans Railway et Vercel (je n'ai pas besoin de le voir).
4. Activer la protection de `main` et créer l'environnement GitHub `production` avec toi comme approbateur.
5. Acheter `trovelya.com` (de préférence avant P1).
6. Approuver la suppression de l'ancien Postgres Railway, une fois le nouveau vérifié.
