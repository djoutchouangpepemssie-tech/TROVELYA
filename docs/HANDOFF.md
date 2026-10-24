# Passation — fin de P0 (Fondations)

**Date :** 24 octobre 2026. **Phase suivante :** P1 (comptes et authentification), après validation de la porte P0 par Arcel.

## Ce qui existe

| Brique | Où | Points clés |
|---|---|---|
| Monorepo | racine | pnpm 10 + Turborepo, Node 24, TypeScript strict, ESLint, Prettier |
| API | `apps/api` | FastAPI, Python 3.12 (uv), SQLAlchemy 2 async, Alembic, pyright strict, 152 tests, couverture 88 % |
| Socle API | `apps/api/src/trovelya/core` | configuration validée, erreurs RFC 9457, `x-request-id`, unité de travail, idempotence HTTP, limite de débit, CSRF, `/health` et `/ready`, journaux JSON sans données personnelles, Sentry, OpenTelemetry |
| Bibliothèque partagée | `…/shared` | argent en centimes (100 % couvert), UUIDv7, horloge, outbox, audit |
| Grand livre | `…/modules/ledger` | partie double, équilibre garanti par la base, idempotent |
| Worker | `…/workers` | arq : relais d'outbox chaque seconde, vérification de la chaîne d'audit à 03 h 00, purge des clés d'idempotence à 04 h 30 |
| Base | `infra/postgres` | image PostgreSQL 17 + PostGIS + pgvector + h3 |
| Web | `apps/web` | Next.js 16, next-intl (fr), Tailwind 4, CSP à nonce, PWA, Sentry, région fra1 |
| Design system | `packages/design-tokens`, `packages/ui` | jetons (contrastes WCAG AA testés), composants Radix accessibles, page `/fr/design-system` hors production |
| Client d'API | `packages/api-client` | types générés depuis `docs/api/openapi.json` |
| CI | `.github/workflows/ci.yml` | `js`, `py`, `contract`, `e2e-web`, `postgres-image`, `api-image`, `security`, `sbom` (main) ; Dependabot hebdomadaire |
| Mise en production | `.github/workflows/deploy-production.yml` | tag `vX.Y.Z` → `release` (ADR-0013) |

## Environnements

| | Staging | Production |
|---|---|---|
| Branche | `main` (chaque fusion) | `release` (tag `vX.Y.Z`) |
| API | `trovelya-staging.up.railway.app` | `trovelya-production.up.railway.app` |
| Web | prévisualisation Vercel de `main` | `trovelya.vercel.app` |
| Région | Railway europe-west4, Vercel fra1, Sentry UE | idem |

Réglages Railway : `infra/railway/README.md`. Procédures : `docs/runbooks/` (deploy, rollback, restore, observability).

## Démarrer en local

```bash
pnpm install
docker compose -f infra/docker-compose.yml up -d --build   # postgres, redis, mailpit
cd apps/api && uv sync && cp ../../.env.example .env        # puis compléter .env
uv run alembic upgrade head && uv run uvicorn --factory trovelya.main:create_app --reload
pnpm --filter @trovelya/web dev                              # http://localhost:3000/fr
pnpm turbo run lint typecheck test build                     # comme la CI (côté JS)
```

## Porte de P0 (cahier 17.1) — preuves

| # | Critère | État | Preuve |
|---|---|---|---|
| G1 | Une PR déclenche toute la CI | ✅ | PR de test #22 (fermée sans fusion) : fausse clé AWS → `security` rouge (semgrep : 2 détections bloquantes) ; erreur de type → `js` rouge ; migration sans `downgrade` → `py` rouge (`test_upgrade_downgrade_upgrade` : *no attribute 'downgrade'*). Après retrait : semgrep 0 détection ; gitleaks reste rouge car la clé est dans l'historique de la branche — comportement voulu (une clé poussée est compromise). Effet de bord corrigé par la PR #23 (gitleaks limité à l'historique du commit testé). |
| G2 | `main` se déploie seule en staging | ✅ | Fusion de la PR #19 à 12:05:21 → déploiement Railway staging API `3b0a7de9` créé à 12:05:23, SUCCESS à 12:06:30, sans action manuelle ; Vercel construit la prévisualisation de `main` au même moment. |
| G3 | Base avec extensions | ✅ | Staging, 24/10 12:33 : `btree_gist, citext, h3, h3_postgis, ltree, pg_trgm, postgis, unaccent, vector` (+ extensions de l'image PostGIS), voir `docs/runbooks/restore.md`. |
| G4 | Outbox testée | ✅ | `test_rolled_back_event_never_published`, `test_two_relays_do_not_share_rows`, `test_consume_once_idempotent` : PASSED. |
| G5 | Audit inaltérable et chaîné | ✅ | 7 tests PASSED (UPDATE/DELETE/TRUNCATE refusés, falsification détectée, insertions concurrentes) ; staging : `audit_verify_chain()` → 1 ligne, `all_ok = t`, avant et après restauration. |
| G6 | Grand livre équilibré | ✅ | 20 tests PASSED, dont 2 propriétés hypothesis à 300 exemples chacune. |
| G7 | Money couverte à 100 % | ✅ | `src/trovelya/shared/money.py 56 0 100%`, étape CI dédiée. |
| G8 | Architecture protégée | ✅ | `lint-imports` : 4 contrats respectés ; test de violation dans `tests/architecture`. |
| G9 | Page web rapide, accessible, traduite, installable | ✅ | Lighthouse mobile (accueil) : Performance 99, Accessibilité 100, Best Practices 100, SEO 100 ; Playwright + axe : 13 tests, 0 violation, manifeste installable ; `lang="fr"`, textes issus de `fr.json`. |
| G10 | Sécurité web | ✅ | En-têtes de staging (24/10 12:35) : CSP à nonce par requête avec `strict-dynamic` et `frame-ancestors 'none'`, HSTS `max-age=63072000; includeSubDomains; preload`, `X-Frame-Options: DENY`, `nosniff`. |
| G11 | Observabilité | ✅ partiel | Erreur volontaire visible dans Sentry (TROVELYA-API-1, staging), sans donnée personnelle ; moniteur de disponibilité actif sur le site de production (Sentry, 1 min). Moniteur de l'API impossible sur `*.railway.app` (limite Sentry du domaine partagé) : à créer sur `api.trovelya.com` dès l'achat du domaine. |
| G12 | Production déployable | ✅ | 24/10 : workflow « Deploy production » (run 40096300755, déclenché manuellement sur `3c4209f`, CI verte vérifiée) → `release` = `3c4209f` à 13:00:50 ; Railway production : API SUCCESS à 13:01:26 (`/ready` 200 à 13:01:23, base et Redis joignables), worker SUCCESS à 13:03:17 ; Vercel production READY sur `release` : `trovelya.vercel.app/fr` 200, exécution fra1, CSP pointant vers l'API de production. |
| G13 | Documentation | ✅ | ADR-0001 à 0014 (`docs/adr`), `GLOSSARY.md`, `security/threat-model.md` v1, `data/PII.md`, runbooks deploy/rollback/restore/observability, dont restauration et retour arrière joués sur staging. |

## Écarts au plan, et pourquoi

- **Configuration Railway** : réglée sur les services et non par `railway.json` (format déclaré obsolète par Railway) ; référence dans `infra/railway/README.md`.
- **Mise en production** : en plus du tag, déclenchement manuel possible ; mêmes garde-fous.
- **OpenTelemetry httpx** : pas instrumenté, l'API n'appelle encore aucun service HTTP.
- **Protection de `main`** : non appliquée par GitHub sur un dépôt privé d'un compte gratuit. Règle tenue par discipline (PR + CI verte) ; à activer avec GitHub Pro ou Team.
- **Sécurité renforcée en cours de route** : masquage des adresses IP (journaux, Sentry, Redis), après un test de bout en bout qui a montré l'IP d'un visiteur dans Sentry.

## Actions qui reviennent à Arcel

Porte P0 validée par Arcel le 24 octobre 2026. Décision d'Arcel : les actions 2 à 6 sont faites à la fin complète du projet.

1. ~~Valider la porte P0 (ce document).~~ Fait.
2. Acheter `trovelya.com` ; ensuite : domaines `api.` et `www.`, moniteur Sentry de l'API, HSTS preload.
3. Activer la double authentification sur GitHub, Railway, Vercel et Sentry si ce n'est pas fait.
4. Planifier les sauvegardes du volume `pg-data` en production dans Railway.
5. Supprimer la branche `test/P0-T13-ci-must-fail` sur GitHub (Branches → corbeille) et le service temporaire `ops-drill` en staging sur Railway.
6. Choisir le prestataire de paiement avant P4 (ADR-0010).

## Points d'attention pour P1

- Toute nouvelle donnée personnelle s'ajoute à `docs/data/PII.md` dans la même PR.
- Toute action d'administration passe par `shared.audit.record_audit`.
- Toute route qui modifie un état exige une clé d'idempotence quand elle touche à l'argent.
- Dependabot ouvre des PR le lundi : ne fusionner qu'en vert, vérifier les versions majeures.
