# Passation — fin de P1 (Identité et comptes)

**Date :** 25 octobre 2026. **Phase suivante :** P2, après validation de la porte P1 par Arcel. Plan de la phase : `docs/plans/P1-identite-comptes.md` (chaque tâche y a son paragraphe « réalisé »).

## Ce que P1 a ajouté

| Brique | Où | Points clés |
|---|---|---|
| Comptes | `apps/api/src/trovelya/modules/identity` | Lien magique (15 min, usage unique, même réponse que l'e-mail existe ou non), Google et Apple derrière leurs drapeaux, passkeys (drapeau `auth.passkeys`), sessions opaques révocables, preuve forte de moins de 12 h pour les actions sensibles |
| Profil et lieux | même module | Profil complété obligatoire (pseudo, nom, année de naissance, CGU), moins de 15 ans refusé sans rien garder, adresses, zones (5 km par défaut), préférences, suivre et bloquer, profil public |
| RGPD | même module, `core/gdpr.py` | Consentements par finalité (historique gardé), export ZIP scellé construit par le worker (ADR-0016), effacement après 30 jours de grâce, annulable |
| Staff | même module | Comptes distincts, passkey obligatoire, sessions de 12 h, rôles et permissions, double validation des actions critiques (ADR-0018) |
| Relais | `apps/web/lib/relay.ts` | Toutes les requêtes passent par l'origine du site (ADR-0015) ; cookies `__Host-` ; CSRF par double soumission |
| E-mails | `core/email.py` | Resend en staging (ADR-0017, écart temporaire), SMTP vers Mailpit en local et en CI |
| Écrans web | `apps/web/app/[locale]` | Connexion et inscription (design « Welcome »), `/verifier`, accueil en 4 étapes (`/bienvenue`), compte (`/compte`, profil, sécurité, confidentialité, données), profil public (`/u/[pseudo]`), pages légales provisoires, bandeau cookies, `/confirmer`, démonstration de la maquette (`/demo`, temporaire) |
| Télémétrie | `core/logging.py`, `core/observability.py` | Même masquage pour les journaux, Sentry et les traces, sans chaîne de requête ; erreurs de base sans message ; traçage SQL actif |
| Tests | `apps/api/tests`, `apps/web/tests` | API : 507 tests, couverture 95 % ; web : tests unitaires et 84 tests de bout en bout (axe à chaque écran) ; `e2e-full` : parcours 1 sur la pile déployée |
| CI | `.github/workflows/ci.yml` | Nouveau job `e2e-full` (image de l'API, worker, Mailpit) |

## Démarrer en local

```bash
pnpm install
docker compose -f infra/docker-compose.yml up -d --build   # postgres, redis, mailpit
cd apps/api && uv sync && cp ../../.env.example .env        # puis compléter .env
uv run alembic upgrade head && uv run uvicorn --factory trovelya.main:create_app --reload
pnpm --filter @trovelya/web dev                              # http://localhost:3000/fr
pnpm turbo run lint typecheck test build                     # comme la CI (côté JS)
bash apps/web/tests/e2e/stack.sh && pnpm --filter @trovelya/web test:e2e        # bout en bout
bash apps/web/tests/e2e-full/stack.sh && pnpm --filter @trovelya/web test:e2e:full  # parcours 1
```

## Porte de P1 (cahier 17.2) — preuves

Légende : ✅ prouvé par les tests (CI verte sur `main`) ; 🟡 prouvé par les tests, démonstration sur staging attendue d'Arcel.

| # | Critère | État | Preuve |
|---|---|---|---|
| G1 | Parcours 1 vert | ✅ | Job `e2e-full` : `/fr/inscription` → e-mail envoyé par le worker en SMTP et lu dans Mailpit → « Me connecter » → profil → 2 univers → zone « Lyon 7e » → accueil connecté ; zone par défaut de 5000 m vérifiée par l'API. |
| G2 | Tiers → 404 sur toutes les routes privées | ✅ | `test_access_matrix.py` : 61 routes déclarées (14 publiques, 4 ouvertes, 31 sur son propre compte, 8 sur une ressource possédée, 4 staff) ; anonyme → 401, tiers → 404 sur les 8 routes de ressource avec contrôle positif du propriétaire, membre → 403 sur les 4 routes staff ; vérifié par mutation. Liste des routes dans la PR #63. |
| G3 | Export RGPD complet | 🟡 | `test_every_identity_table_exported` et l'e2e « request an export, then download it » ; **à faire par Arcel** : demander l'export sur staging (Mon compte → Mes données), recevoir l'e-mail, télécharger le ZIP et l'ouvrir. |
| G4 | Aucune donnée personnelle dans les journaux | 🟡 | `test_no_pii_in_telemetry.py` (journaux, Sentry, traces, stdout) ; cinq fuites trouvées et corrigées (PR #63) ; **à faire par Arcel** : après ses connexions sur staging, chercher son adresse e-mail dans les journaux Railway (API et worker) et dans Sentry : 0 résultat attendu. |
| G5 | Session révoquée inutilisable | 🟡 | `test_revoked_session_rejected_next_request` et l'e2e « revoke another session » ; **démonstration** : se connecter sur deux navigateurs, déconnecter l'autre appareil depuis Sécurité, l'autre navigateur est déconnecté à la requête suivante. |
| G6 | Énumération impossible | ✅ | `test_request_same_response_known_and_unknown_email` : même statut, même corps, mêmes en-têtes. |
| G7 | Double validation | ✅ | `test_dual_approval_grants_the_role`, `test_approval_by_requester_forbidden`, `test_approver_must_hold_permission`, `test_expired_approval_rejected`, `test_concurrent_approvals_execute_once` ; la ligne d'audit porte `actor_id` et `approver_id` différents. |
| G8 | Connexions réelles sur staging | 🟡 | **À faire par Arcel** : lien magique reçu (Resend) ; Google en mode Test s'il est configuré (les boutons Google et Apple ne s'affichent que configurés) ; passkey créée puis utilisée ; compte staff connecté par passkey. |
| G9 | Accessibilité | ✅ | axe sans violation dans les e2e : connexion et inscription (W06), accueil en 4 étapes (W07), profil public (W08), compte et ses pages (W20), pages légales ; parcours au clavier testés (formulaire de connexion, univers à la barre d'espace, focus à chaque étape et après chaque action). |
| G10 | Documentation | ✅ | ADR-0015 à 0018, `docs/data/PII.md`, `docs/security/threat-model.md` v3, `docs/GLOSSARY.md` (vocabulaire P1), ce document ; Apple prêt derrière son drapeau. |

## Écarts au plan de P1, et pourquoi

- **Anti-robot** : Turnstile (Cloudflare, hors UE) écarté ; Friendly Captcha (UE) retenu par Arcel le 25 octobre 2026, à brancher avant la production. D'ici là, ne pas poser `TURNSTILE_SECRET_KEY`.
- **Annulation de l'effacement** : se reconnecter pendant le délai de grâce donne accès à « Annuler la suppression » (bandeau sur chaque page et page Mes données) ; l'annulation est un clic, pas un effet de la seule reconnexion. Choix confirmé par Arcel le 25 octobre 2026.
- **Démonstration de la maquette** (`/fr/demo`) : gardée pour visualiser le design, à supprimer plus tard (demande d'Arcel).
- **Traçage SQL** : l'instrumentation OpenTelemetry déclare SQLAlchemy < 2.1 ; son contrôle de version est sauté, et le test de télémétrie prouve qu'elle fonctionne.
- **Tests de l'API** : rangés par type puis par module (`tests/integration/identity/…`), et non `tests/identity/integration/…` comme écrit dans le plan.

## Actions qui reviennent à Arcel

1. Faire les démonstrations G3, G4, G5 et G8 ci-dessus sur staging, puis valider la porte P1 (ce document).
2. ~~Dire si l'effacement doit s'annuler de lui-même à la reconnexion.~~ Fait le 25 octobre 2026 : un clic explicite (comportement actuel).
3. Toujours en attente depuis P0 (à la fin complète du projet, décision du 24 octobre 2026) : acheter `trovelya.com` (puis passkeys, Apple et e-mails sur ce domaine), double authentification sur GitHub, Railway, Vercel et Sentry, sauvegardes planifiées en production, nettoyage de la branche `test/P0-T13-ci-must-fail` et du service `ops-drill`, choix du prestataire de paiement avant P4.

## Points d'attention pour P2

- Toute nouvelle route doit être déclarée dans `test_access_matrix.py` (la CI échoue sinon).
- Toute nouvelle donnée personnelle s'ajoute à `docs/data/PII.md` dans la même PR, et au test de télémétrie si elle peut passer dans une URL ou un message d'erreur.
- Tout module qui garde des données de membres enregistre son exportateur et son effaceur RGPD.
- Toute action d'administration passe par `shared.audit.record_audit`.

## Annexe — P0 (Fondations)

### Porte de P0 (cahier 17.1) — validée par Arcel le 24 octobre 2026

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

### Écarts de P0

- **Configuration Railway** : réglée sur les services et non par `railway.json` (format déclaré obsolète par Railway) ; référence dans `infra/railway/README.md`.
- **Mise en production** : en plus du tag, déclenchement manuel possible ; mêmes garde-fous.
- **OpenTelemetry httpx** : pas instrumenté, l'API n'appelle encore aucun service HTTP.
- **Protection de `main`** : non appliquée par GitHub sur un dépôt privé d'un compte gratuit. Règle tenue par discipline (PR + CI verte) ; à activer avec GitHub Pro ou Team.
- **Sécurité renforcée en cours de route** : masquage des adresses IP (journaux, Sentry, Redis), après un test de bout en bout qui a montré l'IP d'un visiteur dans Sentry.
