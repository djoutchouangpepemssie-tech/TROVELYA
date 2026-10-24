# P1 — Identité et comptes : plan d'implémentation

> **Pour les agents qui exécutent ce plan :** skill obligatoire `subagent-driven-development` (recommandé) ou `executing-plans`, tâche par tâche. Les étapes utilisent des cases à cocher (`- [ ]`).
> Statut : **brouillon, à valider par Arcel**. Aucun code ne doit être écrit avant sa validation explicite.

**Objectif :** toute personne de 15 ans ou plus crée un compte et se connecte sans mot de passe (lien magique, Google, Apple, passkey), gère son profil, ses adresses, ses zones et ses préférences, exerce seule ses droits RGPD, et le serveur contrôle chaque accès par permission nommée et par objet.

**Architecture :** nouveau module `apps/api/src/trovelya/modules/identity` (monolithe modulaire, 5.4). Le navigateur ne parle qu'à l'origine du web : un relais Next.js `/api/*` transmet les appels à l'API et le cookie de session `__Host-trv_session` est posé sur l'origine du web (ADR-0015). Sessions opaques en PostgreSQL (ADR-0008). E-mails par un adaptateur (`smtp` → Mailpit en local et en CI, `resend` sur staging, ADR-0017), envoyés par le worker.

**Pile ajoutée :** `webauthn` (py_webauthn) et `pyjwt[crypto]` côté API, `aiosmtplib` pour Mailpit, `httpx` passe en dépendance d'exécution (Resend, OIDC, géocodage) ; `@simplewebauthn/browser` côté web. Chaque ajout passe la revue `supply-chain-risk-auditor` dans sa PR.

**Spécification :** `docs/CAHIER_DES_CHARGES.md` sections 0, 3, 6.3 à 6.5, 7.1, 7.3, 8.18, 8.19 (clés des univers), 11.1 à 11.5, 13, 14.1, 16.2 (parcours 1 et 9), 17.2. Modèle de menaces : `docs/security/threat-model.md` (section P1). Règles : `CLAUDE.md`, contraintes globales de `docs/plans/P0-fondations.md`.

---

## 0. Décisions prises

### 0.1 Réponses d'Arcel (24 octobre 2026 : « je suis ok pour tout »)

| # | Question | Décision |
|---|---|---|
| Q1 | Domaine | `trovelya.com` acheté **à la fin du projet**. Arcel est le seul utilisateur jusque-là. |
| Q2 | Cookies | **Relais same-origin** dans Next.js (E1 à E4). |
| Q3 | Passkeys | Construites et **actives sur staging** derrière le flag `auth.passkeys` ; RP ID = hôte du web. Les passkeys de test sont perdues au passage à `trovelya.com`. |
| Q4 | Apple | Pas de compte Apple Developer : construit et testé avec un faux fournisseur, flag `auth.oauth_apple` **désactivé**. |
| Q5 | Google | Projet Google Cloud en mode « Test » (créé par Arcel avec guidage, P1-T03). Flag `auth.oauth_google`. |
| Q6 | E-mails | **Resend** (pas de compte Brevo). Sans domaine : expéditeur `onboarding@resend.dev`, distribution limitée à l'adresse du compte Resend. Écart à la règle « données dans l'UE » accepté **temporairement** (ADR-0017) ; bascule vers un fournisseur hébergé dans l'UE avant le lancement public. |
| Q7 | Turnstile | Oui, derrière un adaptateur et le flag `auth.turnstile` (désactivé tant qu'il n'y a pas de compte Cloudflare). Base légale : intérêt légitime (sécurité). |
| Q8 | Lien magique | **Non lié au navigateur** (les applis mail ouvrent les liens dans leur propre navigateur). Parades : confirmation par bouton (POST), usage unique, 15 min, jeton dans le fragment d'URL, limites de débit, notification de nouvelle connexion. |
| Q9 | Sessions | Absolue **30 jours** (`SESSION_TTL_DAYS`), inactivité **14 jours** (`SESSION_IDLE_DAYS`), `last_used_at` écrit au plus toutes les **5 minutes**. |
| Q10 | Effacement | Délai de grâce **30 jours** [PARAM `retention.erasure_grace_days`], annulable en se reconnectant ; sessions révoquées et profil masqué pendant la grâce. |
| Q11 | Inscription | Première étape de `/bienvenue` obligatoire : **pseudo** (proposé, modifiable), **nom affiché**, **année de naissance** (moins de 15 ans → refus, rien conservé), acceptation des CGU. |
| Q12 | Onboarding | 1. profil (obligatoire) ; 2. intérêts (16 univers) ; 3. zone 5 km + tailles (facultatives) ; 4. notifications. Les étapes 2 à 4 peuvent être passées. |
| Q13 | Profil public | Pseudo, nom affiché, avatar à initiales, bio, « membre depuis », nombre d'abonnés et d'abonnements. **Aucune ville.** |
| Q14 | Blocage | Annule les abonnements dans les deux sens et empêche de se suivre. Effets sur messages et offres en P4/P6. Profil public toujours visible. |
| Q15 | Bandeau cookies | Mécanisme complet (consentements, page « Gestion des cookies », composant de bandeau), mais bandeau **affiché seulement si une finalité non essentielle est active** (aucune en P1). |
| Q16 | Export RGPD | Archive chiffrée dans PostgreSQL (`data_exports`), expiration **7 jours** (ADR-0016). |
| Q17 | Double validation | L'approbateur détient lui-même la permission (par l'un de ses rôles) et n'est pas le demandeur. |
| Q18 | Staff | Arcel seul, `staff_superadmin`, passkey obligatoire ; compte staff **distinct** de son compte client (adresse `djoutchouangpepemssie+staff@gmail.com` pour le staff). Création par script, d'autres comptes plus tard. |

### 0.2 Écarts et précisions par rapport au cahier

| # | Point du cahier | Problème | Décision | ADR |
|---|---|---|---|---|
| E1 | 13.2 cookie `trv_session` sur `.trovelya.com` | Web (`vercel.app`) et API (`railway.app`) sont deux sites ; un cookie posé par l'API serait un cookie tiers bloqué. | Relais `app/api/[...path]/route.ts` ; cookies `__Host-trv_session` et `__Host-trv_csrf` sur l'origine du web. Inchangé le jour de `trovelya.com`. | 0015 |
| E2 | 11.4 limites par IP | Derrière le relais, l'API ne voit que l'IP de Vercel ; uvicorn fait aujourd'hui confiance à tout `X-Forwarded-For`. | `core/client_ip.py` : en-têtes `x-trv-client-ip` et `x-trv-client-country` crus **seulement** avec `x-trv-proxy-secret` valide (`PROXY_SHARED_SECRET`, comparaison à temps constant) ; sinon `X-Real-IP` (réécrit par Railway) ; uvicorn sans `--forwarded-allow-ips='*'`. | 0015 |
| E3 | 13.2 `connect-src`, 5.8 `NEXT_PUBLIC_API_URL` | Le navigateur ne parle plus qu'à sa propre origine. | `connect-src 'self'` (+ Sentry) ; `NEXT_PUBLIC_API_URL` remplacée par `API_INTERNAL_URL` (serveur seulement). | 0015 |
| E4 | P6 WebSocket | Vercel ne relaie pas les WebSocket. | Rien n'est construit : l'ADR prévoit un ticket à usage unique obtenu par le relais en P6. | 0015 |
| E5 | 7.3 `magic_links.purpose` | Le step-up par lien magique (13.2) n'a pas de valeur. | Ajout de `'step_up'` au `CHECK`. | — |
| E6 | 7.3 `users` | Un compte naît d'un e-mail, sans pseudo ; l'inscription doit être complétée ; l'effacement a un délai de grâce. | Pseudo provisoire `membre_<8 car.>` et nom affiché provisoire « Membre » ; colonnes `profile_completed_at TIMESTAMPTZ`, `erasure_requested_at TIMESTAMPTZ`. | — |
| E7 | 7.3 `sessions` | Notification de nouvel appareil ou pays. | Colonne `country_code CHAR(2)` (en-tête pays de Vercel transmis par le relais). | — |
| E8 | 7.3 `data_requests.result_media_id` | Pas de stockage de fichiers avant P2. | Table `data_exports (id, data_request_id, ciphertext BYTEA, expires_at)` ; `result_media_id` reste nul en P1. | 0016 |
| E9 | 3.1 staff « domaine e-mail de l'entreprise » | Aucun domaine. | Exception temporaire : adresse quelconque ; passkey obligatoire ; création et enrôlement par script (lien d'enrôlement à usage unique affiché dans le terminal, sans e-mail). | 0018 |
| E10 | 17.2 T06 « API Adresse data.gouv.fr » | Migrée vers l'IGN, ancienne adresse fermée fin janvier 2026. | Adaptateur `GeoplateformeGeocoder` sur `https://data.geopf.fr/geocodage/search` et `/reverse`. | — |
| E11 | 7.3 `user_preferences.interests` « clés de catégories » | L'arbre des catégories arrive en P2. | Clés stables des 16 univers de 8.19 (`mode`, `montres_bijoux`, `maison_jardin`, `high_tech`, `culture_loisirs`, `collection`, `enfants_bebe`, `sport_plein_air`, `art_antiquites`, `beaute_bien_etre`, `animaux`, `materiel_pro`, `vehicules`, `immobilier`, `services`, `autres`), reprises telles quelles par la graine P2-T01. | — |
| E12 | 3.2 « rôle au moins équivalent » | Hiérarchie non définie. | Q17. | — |
| E13 | Avatar (7.3 `avatar_media_id`) | Pas de stockage d'images avant P2. | Avatar à initiales ; téléversement en P2 (colonne déjà présente, nulle). | — |
| E14 | Âge (8.18) | Seule l'année est connue : quelqu'un né en 2011 a 14 ou 15 ans en 2026. | **À valider par Arcel** : âge retenu = année courante − année de naissance (peut admettre une personne à quelques mois de ses 15 ans) ; l'alternative stricte (− 1) refuse des personnes qui ont déjà 15 ans. Même règle pour 18 ans. | — |

### 0.3 ADR produits par cette phase

ADR-0015 (relais same-origin, IP de confiance, ticket WebSocket futur), ADR-0016 (export RGPD chiffré en base), ADR-0017 (Resend, écart temporaire à la résidence UE), ADR-0018 (comptes staff : passkey seule, enrôlement par script). Chaque ADR est écrit dans la PR de la tâche qui prend la décision.

---

## 1. Contraintes globales

Celles de P0 s'appliquent toutes (UUIDv7, `Clock`, `country_code`, migrations réversibles, un service ne commite jamais, PR ≤ 600 lignes hors fichiers générés, commits conventionnels, textes dans `messages/fr.json`). En plus :

- **Jetons** (session, lien magique, enrôlement) : `secrets.token_urlsafe(32)` (256 bits) ; seul `sha256(jeton)` est stocké (`BYTEA`) ; comparaison par recherche sur le hash.
- **Cookies** : `__Host-trv_session` (`HttpOnly; Secure; SameSite=Lax; Path=/`, `Max-Age` = temps restant jusqu'à l'expiration absolue), `__Host-trv_csrf` (lisible par la page), `__Host-trv_anon` (identifiant anonyme de consentement). Aucun attribut `Domain`.
- **Réponses d'accès** : non connecté → `401 unauthenticated` ; ressource d'autrui ou inexistante → `404 not_found` ; permission manquante → `403 forbidden` ; preuve forte trop ancienne → `403 step_up_required` ; profil non complété → `403 profile_incomplete`.
- **Nouveaux codes d'erreur** (`ErrorCode`, traduits dans `fr.json`) : `unauthenticated`, `forbidden`, `step_up_required`, `profile_incomplete`, `magic_link_invalid`, `oauth_failed`, `oauth_email_unverified`, `passkey_failed`, `username_taken`, `too_young`, `approval_self_forbidden`, `approval_expired`, `feature_disabled`, `captcha_failed`.
- **Flags** (`FlagService`, défaut dans `FEATURE_FLAGS_DEFAULT`) : `auth.passkeys`, `auth.oauth_google`, `auth.oauth_apple`, `auth.turnstile`.
- **[PARAM]** (`platform_settings`, graine dans la migration) : `auth.magic_link_ttl_min` = 15, `auth.step_up_max_age_h` = 12, `retention.erasure_grace_days` = 30, `retention.data_export_days` = 7, `auth.min_signup_age` = 15, `auth.min_trade_age` = 18.
- **Données personnelles** : chaque colonne personnelle ajoutée à `docs/data/PII.md` dans la PR qui la crée (finalité, base légale, durée).
- **Aucune donnée personnelle** dans les journaux, Sentry, traces, clés Redis, identifiants d'événements : clés Redis construites avec `client_fingerprint()` (HMAC) pour les e-mails comme pour les IP.
- **E-mails** : jamais envoyés dans la requête HTTP ; une tâche arq les envoie. Le jeton éventuel voyage chiffré (`shared/crypto.py`, AES-256-GCM, `FIELD_ENCRYPTION_KEY`).

## 2. Points d'attention de la revue (couverts par un test)

1. **Deux clics simultanés sur le même lien magique** : une seule session créée. → `test_magic_link_concurrent_verify_single_session` (T02c, `UPDATE … WHERE consumed_at IS NULL RETURNING`).
2. **Pseudo pris entre la proposition et l'enregistrement, ou différent seulement par la casse** : `409 username_taken`, jamais d'erreur 500. → `test_complete_profile_username_race`, `test_username_case_insensitive` (T05).
3. **Session révoquée pendant qu'une requête est en vol, puis réutilisée** : refusée dès la requête suivante, sans cache. → `test_revoked_session_rejected_next_request` (T02b).
4. **Approbation d'une demande expirée ou par le demandeur lui-même, y compris en double clic** : refusée ; une demande n'est exécutée qu'une fois. → `test_approval_by_requester_forbidden`, `test_expired_approval_rejected`, `test_concurrent_approvals_execute_once` (T11).
5. **Export demandé deux fois de suite** : une seule demande `received/processing` à la fois par personne. → `test_second_export_while_pending_returns_existing` (T09a).

Choix de l'auteur du plan, à confirmer : si l'envoi d'un e-mail échoue, arq réessaie 5 fois (attente exponentielle) puis journalise une erreur Sentry sans l'adresse ; l'utilisateur peut redemander un lien.

---

## 2 bis. Architecture du relais (ADR-0015)

```
navigateur ──(cookies __Host-trv_*)──▶ Vercel : app/api/[...path]/route.ts
   en-têtes relayés : cookie (seulement __Host-trv_*), content-type, accept, accept-language,
   x-csrf-token, idempotency-key, if-match, x-request-id
   en-têtes ajoutés : x-trv-proxy-secret, x-trv-client-ip (x-real-ip de Vercel),
   x-trv-client-country (x-vercel-ip-country)
──▶ API_INTERNAL_URL/v1/...   réponse relayée telle quelle (Set-Cookie compris), sans cache
```

Le relais ne relaie que `/api/v1/*` (le reste → 404), refuse les corps de plus de 1 Mo et renvoie `502` au format problem+json si l'API est injoignable. Les URL de rappel OAuth et le lien magique pointent vers l'origine du web.

## 3. Structure des fichiers

```
apps/api/src/trovelya/
├── core/client_ip.py, core/auth.py (dépendances current_user, require_recent_mfa,
│   require_permission, require_completed_profile), core/gdpr.py (registres)
├── shared/crypto.py, shared/email.py (EmailSender + adaptateurs)
├── modules/identity/
│   ├── api/ (auth.py, me.py, users.py, staff.py)   schemas.py   models.py
│   ├── repository.py   service/ (sessions.py, magic_links.py, oauth.py, passkeys.py,
│   │   profile.py, places.py, gdpr.py, social.py, access.py)
│   ├── policies.py   events.py   tasks.py   universes.py
│   ├── adapters/ (oidc.py, geocoder.py, turnstile.py)
│   ├── emails/ (gabarits texte + HTML en français)
│   └── migrations/versions/ (0003_identity_core, 0004_identity_access, 0005_identity_profile)
├── scripts/create_staff.py
└── workers/consumers.py (groupe de consommateurs Redis Streams + consume_once)
apps/api/tests/identity/  (unit/, integration/)
apps/web/
├── app/api/[...path]/route.ts, lib/api.ts (client côté serveur et navigateur), lib/session.ts
├── app/[locale]/(auth)/{connexion,inscription,verifier}/page.tsx
├── app/[locale]/bienvenue/page.tsx, app/[locale]/u/[pseudo]/page.tsx
├── app/[locale]/compte/parametres/{page,securite,confidentialite}/…
├── app/[locale]/legal/{cgu,confidentialite,cookies,mentions}/page.tsx
├── components/{site-header,bottom-tabs,consent-banner}.tsx
└── tests/e2e/{parcours-1.spec.ts, compte.spec.ts}
docs/adr/0015…0018, docs/runbooks/secrets.md, docs/data/PII.md, docs/GLOSSARY.md
```

## 4. Dépendances et parallélisme

```
T01a ── T01b ── T01c
T01a ── T02a ── T02b ── T02c ─┬─ T03
                              ├─ T04 ── T05 ─┬─ T06 ── T07
                              │              ├─ T09a ── T09b
                              │              └─ T10
                              └─ T08
T01b + T04 ── T11
T02c + T04 ── T12a ;  T05 + T09b + T10 ── T12b ;  tout ── T12c (porte)
```

Parallélisables : T03 et T04 après T02c ; T06, T09a et T10 après T05 ; T08 dès T02c. Les écrans d'une tâche (T07, T08) se testent en e2e avec la route de test `POST /v1/_test/session` (montée seulement en `local`/`test`), qui crée une session pour un utilisateur donné.

---

## 5. Tâches

### P1-T01a — Tables d'identité et de connexion

**Fichiers :** `modules/identity/{__init__,models}.py`, `migrations/versions/0003_identity_core.py`, `alembic.ini` (`version_locations` + identity), `.importlinter` (contrat `module-identity` ; `identity` ajouté aux sources des autres contrats), `tests/identity/integration/test_identity_schema.py`, `docs/data/PII.md`.

**Contenu :** types `user_status` ; tables `users` (7.3 + `profile_completed_at`, `erasure_requested_at`, E6), `auth_identities`, `passkeys`, `magic_links` (+ `'step_up'`, E5), `sessions` (+ `country_code`, E7), exactement comme 7.3 sinon ; triggers `set_updated_at` ; index `sessions_user_idx`, `magic_links (email, created_at)`, FK indexées.

- [ ] Tests d'abord : `test_upgrade_downgrade_upgrade` (étendu, existant) ; `test_username_format_check` (`'Ab'` et `'a b'` refusés, `'arcel.d_1'` accepté) ; `test_email_citext_unique` (`A@x.fr` puis `a@x.fr` → violation) ; `test_magic_link_purpose_check` (`'step_up'` accepté, `'reset'` refusé) ; `test_visibility_factor_bounds`.
- [ ] `uv run pytest tests/identity tests/integration/test_migrations.py` → ÉCHEC.
- [ ] Migration et modèles SQLAlchemy.
- [ ] → vert ; `uv run lint-imports` → contrats respectés.
- [ ] Commit `feat(identity): users, sessions, magic links, oauth identities and passkeys tables`.

### P1-T01b — Rôles, permissions, double validation (schéma et graine)

**Fichiers :** `migrations/versions/0004_identity_access.py`, `tests/identity/integration/test_access_seed.py`.

**Contenu :** tables `roles`, `permissions`, `role_permissions`, `user_roles`, `approval_requests` (7.3). Graine des 10 rôles de 3.1 et des permissions de 3.2 : `listing.publish`, `order.buy`, `listing.remove_any`, `conversation.read_private`, `dispute.resolve`, `refund.create`, `sanction.apply`, `user.suspend`, `payout.validate_manual`, `settings.update`, `staff_roles.manage`, `personal_data.export`. Les conditions de 3.2 deviennent : `requires_approval` (🔒) et `limit_minor` (« ≤ 500 € » → `50000`, au-delà double validation) ; les conditions d'objet (« si signalée », « niveaux 1-2 ») seront portées par les politiques de leurs phases. Graine des [PARAM] de la section 1.

- [ ] Tests d'abord : `test_seed_matches_matrix` (table de vérité de 3.2 écrite en dur dans le test : rôle × permission → absent / autorisé / 🔒 / limite) ; `test_approval_decider_differs_check` ; `test_settings_seeded`.
- [ ] ÉCHEC → migration → vert. Commit `feat(identity): roles, named permissions and approval requests seeded from the permission matrix`.

### P1-T01c — Tables de profil, social et RGPD

**Fichiers :** `migrations/versions/0005_identity_profile.py`, `tests/identity/integration/test_profile_schema.py`, `docs/data/PII.md`.

**Contenu :** `addresses`, `search_zones`, `user_preferences`, `consents`, `follows` (`followee_shop_id` sans clé étrangère jusqu'en P10), `blocks`, `data_requests`, `data_exports` (E8). Index : `follows_uniq`, `follows (followee_user_id)`, `search_zones (user_id)`, `addresses (user_id) WHERE deleted_at IS NULL`, index unique partiel « une seule zone par défaut » et « une seule adresse d'expédition par défaut » par utilisateur, unique partiel `data_requests (user_id, kind) WHERE status IN ('received','processing')` (point de revue 5).

- [ ] Tests d'abord : `test_zone_radius_allowed_values` (5000 accepté, 3000 refusé) ; `test_single_default_zone` ; `test_follow_exactly_one_target` ; `test_single_pending_request_per_kind` ; `test_upgrade_downgrade_upgrade`.
- [ ] ÉCHEC → migration → vert. Commit `feat(identity): addresses, search zones, preferences, consents, follows, blocks and gdpr requests tables`.

### P1-T02a — Relais same-origin et IP de confiance (ADR-0015)

**Fichiers :** `core/client_ip.py`, `core/config.py` (`proxy_shared_secret: SecretStr` min 32, `session_idle_days: int = 14`), `core/ratelimit.py` (utilise `client_ip`), `core/csrf.py` (cookies `__Host-trv_session`, `__Host-trv_csrf`), `apps/api/Dockerfile` (retrait de `--forwarded-allow-ips='*'`), `apps/web/app/api/[...path]/route.ts`, `apps/web/lib/api.ts`, `apps/web/lib/csp.ts`, `.env.example`, `docs/adr/0015-relais-same-origin.md`, `docs/runbooks/secrets.md`, `infra/railway/README.md`.

**Interfaces produites :**
- `def client_ip(scope: Scope, *, proxy_secret: str) -> str` et `def client_country(scope: Scope, *, proxy_secret: str) -> str | None` (code ISO à 2 lettres validé, sinon `None`).
- Web : `apiFetch(path: string, init?: RequestInit): Promise<Response>` (navigateur : `/api` + `X-CSRF-Token` lu dans `__Host-trv_csrf` ; serveur : `API_INTERNAL_URL` + cookies de la requête + en-têtes du relais).

- [ ] Tests API d'abord (`tests/unit/test_client_ip.py`) : `test_proxy_headers_trusted_with_secret` ; `test_proxy_headers_ignored_without_secret` ; `test_proxy_headers_ignored_with_wrong_secret` ; `test_x_forwarded_for_never_trusted` ; `test_x_real_ip_fallback` ; `test_invalid_ip_in_header_ignored` ; `test_country_must_be_two_letters`. Intégration : `test_rate_limit_keys_on_trusted_client_ip` (deux IP relayées → deux compteurs).
- [ ] Tests web d'abord (`app/api/[...path]/route.test.ts`, Vitest, `fetch` simulé) : seuls les en-têtes de la liste blanche passent ; cookie filtré aux `__Host-trv_*` ; `x-trv-proxy-secret` ajouté ; un en-tête `x-trv-client-ip` envoyé par le navigateur est écrasé ; `/api/admin` → 404 ; corps > 1 Mo → 413 ; API injoignable → 502 problem+json ; `Set-Cookie` relayé. `csp.test.ts` : `connect-src` ne contient plus l'origine de l'API.
- [ ] ÉCHEC → implémenter → `uv run pytest && pnpm --filter @trovelya/web test` vert.
- [ ] Variables à créer par Arcel avec guidage (Railway `PROXY_SHARED_SECRET` = `${{secret(48)}}` en staging et production ; même valeur dans Vercel, type « Sensitive », avec `API_INTERNAL_URL`) ; suppression de `NEXT_PUBLIC_API_URL`.
- [ ] Commit `feat(web): same-origin api relay with trusted client ip (ADR-0015)`.

**Risques :** `X-Real-IP` de Railway documenté de façon inégale → le chemin normal passe toujours par le relais authentifié ; vérifié sur staging (journal de la limite avec deux réseaux différents).

### P1-T02b — Sessions opaques

**Fichiers :** `modules/identity/service/sessions.py`, `repository.py`, `core/auth.py`, `modules/identity/api/me.py` (sessions), `api/auth.py` (logout), `schemas.py`, tests.

**Interfaces produites :**
- `async def create_session(session: AsyncSession, *, user_id: UUID, kind: Literal["web","admin"], ip: str, user_agent: str | None, country: str | None, strong: bool, clock: Clock) -> IssuedSession` (`IssuedSession(token: str, session_id: UUID, expires_at: datetime)`) ; `strong=True` remplit `mfa_at`.
- `async def rotate_session(session, *, current_id: UUID, …) -> IssuedSession` (révoque l'ancienne, recopie `mfa_at` mis à jour).
- `async def revoke_session(session, *, user_id: UUID, session_id: UUID) -> None` ; `revoke_all(session, *, user_id, except_id: UUID | None)`.
- Dépendances `current_user() -> CurrentUser` (`CurrentUser(id, session_id, kind, mfa_at, is_staff, profile_completed: bool)`) et `optional_user()`. Lecture du cookie → `sha256` → ligne non révoquée, non expirée, `last_used_at` > maintenant − 14 j ; mise à jour de `last_used_at` seulement si > 5 min. Limite 600 req/min par utilisateur (11.4).
- Routes : `POST /v1/auth/logout` 🔑 → 204 et cookie effacé ; `GET /v1/me/sessions` 🔑 → `[{id, current, created_at, last_used_at, device_label, country_code}]` (pas d'IP renvoyée) ; `DELETE /v1/me/sessions/{id}` 🔑 → 204, 404 si la session n'est pas à soi ; `DELETE /v1/me/sessions` 🔑 → révoque toutes les autres.

- [ ] Tests d'abord : `test_token_256_bits_and_only_hash_stored` ; `test_cookie_attributes` (`__Host-`, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, pas de `Domain`) ; `test_absolute_expiry_30_days` et `test_idle_expiry_14_days` (`FixedClock`) ; `test_last_used_at_throttled_5_min` (deux requêtes à 1 min d'écart → une seule écriture) ; `test_revoked_session_rejected_next_request` (point de revue 3) ; `test_logout_revokes_and_clears_cookie` ; `test_delete_other_users_session_404` ; `test_revoke_all_keeps_current` ; `test_rotate_invalidates_old_token` ; `test_user_rate_limit_600_per_min` ; `test_suspended_user_session_rejected` (`status` ∈ `suspended`, `banned`, `deleted` → 401).
- [ ] ÉCHEC → implémenter → vert. Commit `feat(identity): opaque server-side sessions with rotation, idle and absolute expiry (ADR-0008)`.

### P1-T02c — Lien magique, e-mails, notification de nouvelle connexion

**Fichiers :** `shared/crypto.py`, `shared/email.py`, `modules/identity/service/magic_links.py`, `adapters/turnstile.py`, `tasks.py`, `emails/*`, `events.py`, `workers/consumers.py`, `workers/main.py`, `api/auth.py`, `docs/adr/0017-resend-provisoire.md`, `docs/data/PII.md`, tests.

**Interfaces produites :**
- `seal(plaintext: bytes, *, key: bytes, aad: bytes) -> bytes` et `open_sealed(blob: bytes, *, key: bytes, aad: bytes) -> bytes` (AES-256-GCM, nonce de 96 bits en tête). `FIELD_ENCRYPTION_KEY` : 32 octets en base64, obligatoire.
- `class EmailSender(Protocol): async def send(self, message: EmailMessage) -> None` ; `SmtpEmailSender(url)` (Mailpit), `ResendEmailSender(api_key, http)` (REST `POST https://api.resend.com/emails`, sans SDK), `FakeEmailSender` (tests). Choix par `EMAIL_PROVIDER` ∈ `smtp|resend|fake`.
- `class CaptchaVerifier(Protocol): async def verify(self, token: str | None, *, ip: str) -> bool` ; `TurnstileVerifier`, `AlwaysPass` (flag éteint).
- Routes : `POST /v1/auth/magic-link` 🔓 `{email, captcha_token?}` → **toujours** `202 {}` ; `POST /v1/auth/magic-link/verify` 🔓 `{token}` → `200 {user, is_new, profile_completed}` + cookie de session (`strong=True`), ou `400 magic_link_invalid` (inconnu, expiré, consommé, compte staff ou supprimé : même réponse).
- Événements : `user.registered` (création à la vérification), `session.created` (chaque session). Consommateur `notify_new_login` (`consume_once`) : e-mail « Nouvelle connexion » si le couple (famille d'appareil, pays) est absent des sessions des 90 derniers jours, jamais pour la toute première session.
- Lien envoyé : `{WEB_ORIGIN}/fr/verifier#token=<jeton>` (fragment). La tâche arq `send_magic_link(magic_link_id, sealed_token)` reçoit le jeton chiffré.

- [ ] Tests d'abord : `test_seal_roundtrip`, `test_seal_wrong_aad_fails` ; `test_request_same_response_known_and_unknown_email` (statut, corps, en-têtes identiques ; une ligne `magic_links` et une tâche d'envoi dans les deux cas) ; `test_rate_limit_5_per_hour_per_email` (6e → 429, l'e-mail n'apparaît pas dans la clé Redis) ; `test_rate_limit_20_per_hour_per_ip` ; `test_captcha_required_when_flag_on` (`400 captcha_failed`) ; `test_verify_creates_user_once` ; `test_magic_link_single_use` ; `test_magic_link_expires_15_min` ; `test_magic_link_concurrent_verify_single_session` (point de revue 1) ; `test_staff_email_cannot_use_magic_link` ; `test_token_never_logged` (sortie structlog capturée pendant tout le parcours : ni e-mail, ni jeton, ni IP) ; `test_new_login_email_only_for_new_device_or_country` ; `test_consumer_idempotent` ; `test_resend_payload` (requête `httpx` simulée : `from`, `to`, `subject`, `text`, `html`) ; `test_smtp_sender_reaches_mailpit` (intégration, conteneur Mailpit).
- [ ] ÉCHEC → implémenter → vert.
- [ ] Vérifier en local : `docker compose up`, demander un lien, l'ouvrir depuis Mailpit (`http://localhost:8025`), confirmer → cookie posé.
- [ ] Arcel crée le compte Resend (même adresse que son compte client) et la clé ; variables `EMAIL_PROVIDER=resend`, `EMAIL_API_KEY`, `EMAIL_FROM=onboarding@resend.dev`, `FIELD_ENCRYPTION_KEY` en staging.
- [ ] Commit `feat(identity): passwordless magic link login with anti-enumeration, rate limits and new-login alerts (ADR-0017)`.

**Risques :** l'adresse de test de Resend ne livre qu'à l'adresse du compte → toute autre adresse échoue en silence côté Resend (journalisée sans l'adresse) ; attendu jusqu'à l'achat du domaine.

### P1-T03 — Google et Apple (OIDC)

**Fichiers :** `adapters/oidc.py`, `service/oauth.py`, `api/auth.py`, tests (fournisseur OIDC factice : clés RSA générées en test, JWKS servi par `httpx.MockTransport`).

**Interfaces produites :**
- `class OidcProvider` : `authorization_url(state, nonce, code_challenge) -> str` ; `async exchange(code, code_verifier) -> IdTokenClaims` (`sub`, `email`, `email_verified`, `is_private_email`). Configurations `GOOGLE` (`https://accounts.google.com`) et `APPLE` (`https://appleid.apple.com`, `response_mode=form_post`, secret client = JWT ES256 signé avec la clé `.p8`). JWKS en cache 1 h.
- `GET /v1/auth/oauth/{provider}/start` 🔓 → 302 vers le fournisseur ; `state`, `nonce`, `code_verifier` dans Redis (`oauth:<sha256(state)>`, 10 min, lus par `GETDEL`) et `sha256(state)` dans le cookie `__Host-trv_oauth` (`SameSite=Lax`, 10 min).
- `GET /v1/auth/oauth/google/callback` et `POST /v1/auth/oauth/apple/callback` 🔓 → 302 vers `/fr/bienvenue` (nouveau) ou `/fr` ; Apple : le POST inter-sites ne porte pas le cookie `Lax`, donc la réponse renvoie vers `GET /v1/auth/oauth/apple/finish?ref=<id à usage unique>` où le cookie est vérifié.
- Règles : identité connue → connexion ; e-mail inconnu → création ; e-mail connu et `email_verified` vrai → liaison + e-mail d'information ; e-mail connu non vérifié → `oauth_email_unverified` ; relais privé Apple → compte créé normalement. Flag éteint → `404`. Session `strong=False`.

- [ ] Tests d'abord : `test_state_single_use` ; `test_state_bound_to_browser_cookie` ; `test_pkce_verifier_sent` ; `test_id_token_bad_signature_rejected` ; `test_wrong_iss_rejected` ; `test_wrong_aud_rejected` ; `test_expired_token_rejected` ; `test_nonce_mismatch_rejected` ; `test_links_existing_verified_email` ; `test_refuses_link_unverified_email` ; `test_apple_private_relay_creates_account` ; `test_apple_form_post_then_finish` ; `test_provider_disabled_404`.
- [ ] ÉCHEC → implémenter → vert.
- [ ] Arcel crée le client OAuth Google (mode Test, URI de rappel `https://<web staging>/api/v1/auth/oauth/google/callback`) avec guidage ; flag `auth.oauth_google` activé sur staging après un essai réel.
- [ ] Commit `feat(identity): google and apple sign-in with pkce, state, nonce and id token validation`.

### P1-T04 — Passkeys et step-up

**Fichiers :** `service/passkeys.py`, `api/auth.py`, `core/auth.py` (`require_recent_mfa`), web `lib/passkeys.ts` (`@simplewebauthn/browser`), tests.

**Interfaces produites :**
- `POST /v1/auth/passkeys/register/options` et `/register/verify` 🔑 + step-up (13.2) ; `POST /v1/auth/passkeys/login/options` et `/login/verify` 🔓 (identifiants découvrables, `user_handle` = `users.id`) → session `strong=True` (`kind="admin"`, 12 h, si `is_staff`) ; `GET /v1/me/passkeys`, `PATCH /v1/me/passkeys/{id}` (nom), `DELETE /v1/me/passkeys/{id}` 🔑 + step-up.
- `POST /v1/auth/step-up` 🔑 `{method: "passkey", assertion}` → nouvelle session (rotation) avec `mfa_at` ; `{method: "magic_link"}` → `202` et lien `purpose='step_up'` envoyé à l'adresse du compte ; sa vérification fait la même rotation.
- `require_recent_mfa()` : `mfa_at` > maintenant − `auth.step_up_max_age_h`, sinon `403 step_up_required`.
- Challenges dans Redis (`webauthn:<sha256(challenge)>`, 5 min, `GETDEL`). Configuration : `WEBAUTHN_RP_ID`, `WEBAUTHN_RP_NAME`, `WEBAUTHN_ORIGINS` (liste). Flag `auth.passkeys`.

- [ ] Tests d'abord (authentificateur simulé avec `cryptography`, comme les tests de py_webauthn) : `test_register_and_login` ; `test_challenge_single_use` ; `test_challenge_expires` ; `test_wrong_origin_rejected` ; `test_wrong_rp_id_rejected` ; `test_sign_count_regression_rejected` ; `test_multiple_passkeys_per_user` ; `test_delete_requires_step_up` ; `test_delete_other_users_passkey_404` ; `test_step_up_rotates_session` ; `test_step_up_via_magic_link` ; `test_require_recent_mfa_12h` ; `test_staff_login_gets_admin_session_12h` ; `test_flag_off_404`.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(identity): passkeys with webauthn and step-up authentication`.

### P1-T05 — Profil privé et public, changement d'e-mail

**Fichiers :** `service/profile.py`, `policies.py`, `api/me.py`, `api/users.py`, `schemas.py`, tests.

**Interfaces produites :**
- `GET /v1/me` 🔑 → `{id, email, username, display_name, bio, locale, country_code, profile_completed, roles, flags, is_minor, erasure_requested_at, counters: {unread_messages: 0, notifications: 0}}` (compteurs à 0 jusqu'en P3/P6).
- `POST /v1/me/complete-profile` 🔑 `{username, display_name, birth_year, accept_terms: true, terms_version}` → 200 ; `too_young` (< `auth.min_signup_age`, rien n'est conservé, compte supprimé et sessions révoquées) ; `username_taken`. `GET /v1/me/username-suggestion` → pseudo libre dérivé de la partie locale de l'e-mail (normalisé `^[a-z0-9_.]{3,30}$`, suffixe numérique si pris).
- `PATCH /v1/me` 🔑 `{username?, display_name?, bio?, locale?}` (`If-Match: version`, 11.1).
- `POST /v1/me/email` 🔑 + step-up `{new_email}` → `202` et lien `change_email` à la nouvelle adresse ; sa vérification change l'e-mail, émet `user.email_changed`, prévient l'ancienne adresse.
- `GET /v1/users/{username}` 🔓 → `{username, display_name, bio, member_since, followers_count, following_count}` ; 404 si `status` ≠ `active`/`restricted` ou effacement demandé.
- `require_completed_profile()` : toutes les routes 🔑 sauf `/me`, `/me/complete-profile`, `/me/username-suggestion`, sessions, consentements, effacement et déconnexion.
- `is_minor` calculé selon E14 ; jamais exposé publiquement.

- [ ] Tests d'abord : `test_complete_profile_ok` ; `test_too_young_rejected_and_nothing_kept` ; `test_complete_profile_username_race` et `test_username_case_insensitive` (point de revue 2) ; `test_incomplete_profile_blocks_private_routes` ; `test_patch_requires_if_match` (412) ; `test_change_email_requires_step_up` ; `test_change_email_flow_emits_event` ; `test_public_profile_has_no_email_or_location` ; `test_public_profile_404_when_erasure_requested` ; `test_birth_year_not_in_logs`.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(identity): private and public profiles, profile completion and email change`.

### P1-T06 — Adresses, zones de recherche, géocodage, préférences

**Fichiers :** `adapters/geocoder.py`, `service/places.py`, `universes.py`, `api/me.py`, `api/geo.py`, tests.

**Interfaces produites :**
- `class Geocoder(Protocol)` : `async search(q: str, *, limit: int = 5) -> list[Place]` et `async reverse(lat: float, lon: float) -> Place | None` (`Place(label, city, postal_code, district | None, country_code, lat, lon)`) ; `GeoplateformeGeocoder(http)` (E10, `autocomplete=1`, délai 2 s, aucune donnée personnelle envoyée hormis le texte tapé) ; `FakeGeocoder` (Paris 11e, Lyon 7e, Bordeaux).
- `GET /v1/geo/search?q=` 🔑 (limite 30/min par utilisateur) ; `GET /v1/geo/reverse?lat=&lon=` 🔑 (position du navigateur, après consentement `location`).
- `/v1/me/addresses[/{id}]` et `/v1/me/zones[/{id}]` 🔑 (GET liste, POST, PATCH, DELETE ; 404 pour l'objet d'autrui via `policies.can_edit_address/can_edit_zone`). Rayon ∈ {1, 2, 5, 10, 25, 50, 100} km, défaut **5 km** ; place_name = « Lyon 7e ». Une zone par défaut (la première l'est).
- `GET/PUT /v1/me/preferences` 🔑 : `interests` ⊂ `UNIVERSE_KEYS` (E11) ; `sizes` : au plus 10 clés `^[a-z_]{2,20}$`, valeurs ≤ 10 caractères ; `notification_settings` : objet de booléens par canal (`email`, `push`) et par type ; les autres champs de 7.3 avec leurs contraintes.

- [ ] Tests d'abord : `test_geoplateforme_parsing` (réponse enregistrée) ; `test_geocoder_timeout_returns_503_problem` ; `test_address_crud_and_other_user_404` ; `test_zone_default_radius_5km` ; `test_zone_radius_invalid_422` ; `test_single_default_zone_switch` ; `test_preferences_unknown_universe_422` ; `test_preferences_sizes_bounds`.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(identity): addresses, search zones with geoplateforme geocoding and preferences`.

### P1-T07 — Onboarding web (W07)

**Fichiers :** `apps/web/app/[locale]/bienvenue/{page,steps/*}.tsx`, `messages/fr.json`, `tests/e2e/onboarding.spec.ts`, `packages/ui` (composant `ChoiceTile` si absent).

**Contenu :** 4 étapes (Q12) fidèles à la maquette `Onboard` (barre de progression, tuiles d'univers avec état `aria-pressed`, carte « Lyon 7e · rayon 5 km — Modifier », bouton « Continuer · N choisis » et « Passer »). Étape 3 : recherche de lieu (géocodage) ou position du navigateur après demande explicite. Étape 4 : préférences e-mail ; l'autorisation de notifications push du navigateur est reportée à P3.

- [ ] Tests e2e d'abord (session créée par la route de test) : `onboarding complete` (4 étapes, zone 5 km enregistrée via l'API) ; `onboarding skip optional steps` ; `profile step required` ; `too young message` ; axe : 0 violation à chaque étape ; navigation clavier complète ; erreurs annoncées (`aria-live`).
- [ ] ÉCHEC → implémenter → `pnpm --filter @trovelya/web test:e2e` vert. Commit `feat(web): onboarding with profile, interests, 5 km zone and notifications`.

### P1-T08 — Consentements, bandeau cookies, pages légales provisoires

**Fichiers :** `api/me.py` (consents), `service/profile.py`, web `components/consent-banner.tsx`, `app/[locale]/legal/{cgu,confidentialite,cookies,mentions}/page.tsx`, `lib/consent.ts`, tests.

**Interfaces produites :**
- `POST /v1/me/consents` 🔓/🔑 `{purpose, granted, policy_version}` (`purpose` ∈ `analytics`, `marketing_email`, `personalised_ads`, `location`) ; anonyme : identifiant `__Host-trv_anon` (aléatoire, 13 mois), rattaché au compte à la connexion. `GET /v1/me/consents` → dernier état par finalité.
- Bandeau : « Tout accepter », « Tout refuser » et « Personnaliser » de même taille et même contraste ; affiché seulement si la liste des finalités actives (configuration) est non vide (Q15) ; page « Gestion des cookies » toujours accessible depuis le pied de page, retrait en un clic.
- Pages légales provisoires : contenu factuel (éditeur, hébergeurs et sous-traitants : Railway, Vercel, Sentry, Resend, Google, Cloudflare, IGN ; finalités et durées issues de `docs/data/PII.md`), bandeau « Version provisoire — à valider par un juriste avant le lancement » ; aucune règle commerciale inventée.

- [ ] Tests d'abord : API `test_consent_recorded_with_policy_version` ; `test_anonymous_consent_attached_on_login` ; `test_latest_consent_wins`. Vitest : bandeau masqué sans finalité active ; boutons de même taille. e2e : refuser puis retirer depuis la page cookies ; aucun cookie autre que `__Host-trv_*` et `NEXT_LOCALE` avant consentement ; axe 0 violation.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(identity): consent records, cnil cookie banner and provisional legal pages`.

### P1-T09a — Export RGPD (ADR-0016)

**Fichiers :** `core/gdpr.py`, `service/gdpr.py`, `tasks.py`, `api/me.py`, `docs/adr/0016-export-rgpd.md`, tests.

**Interfaces produites :**
- `Exporter = Callable[[AsyncSession, UUID], Awaitable[dict[str, Any]]]` ; `register_exporter(name: str, fn: Exporter) -> None` ; `registered_exporters() -> Mapping[str, Exporter]`. Le module identity enregistre `identity` (users, auth_identities sans secret, passkeys sans clé publique, sessions, addresses, zones, preferences, consents, follows, blocks, data_requests). Chaque phase ajoute le sien.
- `POST /v1/me/data-export` 🔑 + step-up → `202 {request_id}` (existant renvoyé si une demande est en cours, point de revue 5) ; tâche arq `build_data_export(request_id)` : ZIP contenant `export.json` (une clé par exportateur) + `LISEZMOI.txt`, chiffré par `seal`, stocké dans `data_exports` pour `retention.data_export_days` ; e-mail « Votre export est prêt ».
- `GET /v1/me/data-requests` 🔑 ; `GET /v1/me/data-export/{request_id}/download` 🔑 + step-up → ZIP (404 si autre personne ou expiré). Purge quotidienne des exports expirés.

- [ ] Tests d'abord : `test_every_identity_table_exported` (introspection : toute table du module ayant une colonne `user_id` ou `id` utilisateur apparaît dans l'export) ; `test_export_excludes_secrets` (pas de `token_hash`, `public_key`, `credential_id`) ; `test_second_export_while_pending_returns_existing` ; `test_download_requires_step_up` ; `test_download_other_user_404` ; `test_export_expires_7_days` ; `test_export_audited`.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(identity): self-service gdpr data export with extensible exporter registry (ADR-0016)`.

### P1-T09b — Effacement RGPD

**Fichiers :** `core/gdpr.py` (registre des effaceurs), `service/gdpr.py`, `tasks.py`, `api/me.py`, tests.

**Interfaces produites :**
- `Eraser = Callable[[AsyncSession, UUID], Awaitable[None]]` ; `register_eraser(name, fn)`.
- `POST /v1/me/erasure` 🔑 + step-up → `202` : `erasure_requested_at = now`, toutes les sessions révoquées, profil public en 404, e-mail de confirmation avec la date d'effacement. `POST /v1/me/erasure/cancel` 🔑 (possible après reconnexion pendant la grâce).
- Tâche quotidienne `process_erasures` (04:00 Europe/Paris) : pour chaque compte dont la grâce est écoulée, dans une transaction : effaceurs de tous les modules, puis anonymisation de `users` (`email = 'efface+<id>@invalid'`, `username = 'efface_<8 car.>'`, `display_name = 'Compte supprimé'`, `bio`, `phone_e164`, `birth_year`, `last_seen_at` à `NULL`, `status = 'deleted'`, `deleted_at`) ; suppression des adresses, zones, préférences, passkeys, identités OAuth, sessions, abonnements, blocages, liens magiques (par e-mail) et exports ; consentements conservés (preuve) avec le seul identifiant interne ; `user.deleted` émis ; `record_audit(actor_type="system", action="user.erase")`.

- [ ] Tests d'abord : `test_erasure_requires_step_up` ; `test_erasure_revokes_sessions_and_hides_profile` ; `test_cancel_during_grace` ; `test_erasure_after_30_days_anonymises` (`FixedClock`) ; `test_no_personal_value_left` (recherche de l'ancien e-mail, pseudo et nom dans toutes les colonnes texte du schéma `public`, hors `audit_log`) ; `test_erasure_idempotent` ; `test_erasure_event_and_audit`.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(identity): gdpr erasure with 30-day grace period and anonymisation`.

### P1-T10 — Suivre et bloquer

**Fichiers :** `service/social.py`, `api/users.py`, tests.

**Interfaces :** `POST/DELETE /v1/users/{id}/follow` et `/block` 🔑 → 204 ; se suivre soi-même → 422 ; bloquer annule les abonnements dans les deux sens ; suivre une personne qui vous a bloqué ou que vous avez bloquée → `404` (ne révèle pas le blocage) ; `GET /v1/me/blocks` 🔑. Compteurs du profil public mis à jour.

- [ ] Tests d'abord : `test_follow_unfollow_idempotent` ; `test_cannot_follow_self` ; `test_block_removes_follows_both_ways` ; `test_follow_blocked_returns_404` ; `test_unknown_user_404` ; `test_counters`.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(identity): follow and block users`.

### P1-T11 — Permissions, double validation, comptes staff (ADR-0018)

**Fichiers :** `core/auth.py` (`require_permission`), `service/access.py`, `api/staff.py`, `scripts/create_staff.py`, `docs/adr/0018-comptes-staff.md`, tests.

**Interfaces produites :**
- `require_permission(key: str)` → dépendance : 401 sans session, 403 `forbidden` sans la permission ; les routes staff exigent aussi `kind == "admin"` et `require_recent_mfa()`.
- `async def request_approval(session, *, permission_key: str, requested_by: UUID, payload: dict[str, Any], reason: str, clock: Clock) -> UUID` ; `async def decide(session, *, request_id: UUID, decided_by: UUID, approve: bool, clock: Clock) -> ApprovalOutcome` ; registre `register_approval_handler(permission_key, handler)` exécuté une seule fois à l'approbation (`SELECT … FOR UPDATE`). Audit : `approval.request`, `approval.approve|reject` avec `actor_id` et `approver_id`.
- Tâche `expire_approvals` toutes les 10 minutes (24 h).
- Routes : `GET /v1/staff/approvals` 🛡️, `POST /v1/staff/approvals/{id}/approve|reject` 🛡️. Première action branchée : `staff_roles.manage` (attribuer ou retirer un rôle staff).
- `uv run python -m trovelya.scripts.create_staff --email … --role staff_superadmin` : crée le compte (`is_staff = true`, profil complet), affiche un **lien d'enrôlement de passkey** `{WEB_ORIGIN}/fr/staff/enrolement#token=<jeton>` à usage unique (15 min, `enrol:<sha256(jeton)>` dans Redis, `GETDEL`), audit `actor_type="system"`. Interdit d'utiliser l'e-mail d'un compte client existant.
- `POST /v1/auth/passkeys/enrol/options` et `/enrol/verify` 🔓 `{enrolment_token, …}` : enregistrent la première passkey d'un compte staff sans session, puis ouvrent une session `admin`. Page web minimale `app/[locale]/staff/enrolement/page.tsx` (`noindex`).

- [ ] Tests d'abord : `test_enrolment_token_single_use_and_expires` ; `test_require_permission_403` ; `test_member_calling_staff_route_403` ; `test_staff_route_requires_admin_session_and_recent_mfa` ; `test_approval_by_requester_forbidden`, `test_expired_approval_rejected`, `test_concurrent_approvals_execute_once` (point de revue 4) ; `test_approver_must_hold_permission` ; `test_both_identities_audited` ; `test_create_staff_script_enrolment_link_single_use` ; `test_create_staff_refuses_client_email`.
- [ ] ÉCHEC → implémenter → vert.
- [ ] Sur staging, avec Arcel : `railway run` du script, enrôlement de sa passkey staff, connexion staff vérifiée.
- [ ] Commit `feat(identity): named permission guard, generic dual approval and staff accounts (ADR-0018)`.

### P1-T12a — Écrans d'authentification (W06), en-tête et navigation

**Fichiers :** `app/[locale]/(auth)/{connexion,inscription,verifier}/page.tsx`, `components/{site-header,bottom-tabs,account-menu}.tsx`, `messages/fr.json`, `tests/e2e/auth.spec.ts`.

**Contenu :** connexion et inscription = même parcours (la maquette `Welcome` : « Continuer avec Apple », « Continuer avec Google », « Créer un compte avec un e-mail », + « Utiliser une passkey » si le flag est actif ; boutons masqués quand leur flag est éteint) ; message après envoi : « Si cette adresse est valide, un lien vient de partir. » ; `/verifier` lit le fragment, affiche « Me connecter » (POST), puis redirige vers `/bienvenue` ou la page d'origine. En-tête (6.5) avec les seuls éléments qui fonctionnent en P1 : logo, « Se connecter » ou menu du compte ; barre d'onglets mobile : Accueil et Profil (les autres onglets arrivent avec leurs phases, aucun lien mort).

- [ ] Tests e2e d'abord : `magic link request shows neutral message` ; `verify page requires click` (ouvrir le lien sans cliquer ne crée pas de session) ; `expired link shows error and resend` ; `header shows account menu when signed in` ; axe 0 violation ; navigation clavier.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(web): sign-in, sign-up and verify screens with site header and mobile tabs`.

### P1-T12b — Profil public (W08 partiel) et paramètres (W20)

**Fichiers :** `app/[locale]/u/[pseudo]/page.tsx`, `app/[locale]/compte/parametres/{page,securite,confidentialite}/page.tsx`, `messages/fr.json`, `tests/e2e/compte.spec.ts`.

**Contenu :** W08 rendu côté serveur (Q13, avatar à initiales, `noindex` tant que le profil n'a ni annonce ni avis) ; W20 : profil (pseudo, nom, bio, langue), sécurité (passkeys : ajouter, renommer, supprimer ; sessions : liste, révoquer, tout révoquer ; e-mail), confidentialité (consentements, export, suppression avec rappel du délai de 30 jours et annulation), préférences de feed (`personalised_feed`, niveau de découverte). Les actions soumises au step-up ouvrent la boîte de dialogue de preuve forte (passkey ou lien magique).

- [ ] Tests e2e d'abord : `edit profile` ; `revoke another session` ; `add passkey asks step-up` (authentificateur virtuel Chromium) ; `request export then download` ; `request erasure then cancel` ; `public profile shows no location` ; axe 0 violation sur chaque page.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(web): public profile and account settings`.

### P1-T12c — Parcours 1, matrice d'accès et porte de P1

**Fichiers :** `tests/e2e/parcours-1.spec.ts`, `apps/api/tests/identity/integration/test_access_matrix.py`, `apps/api/tests/identity/integration/test_no_pii_in_telemetry.py`, `.github/workflows/ci.yml` (job `e2e-full` : image Postgres, Redis, Mailpit, API et worker en conteneurs, web construit, Playwright), `docs/HANDOFF.md`, `docs/GLOSSARY.md`, `docs/security/threat-model.md`.

- [ ] `parcours-1.spec.ts` : `/fr/inscription` → e-mail → lien lu dans l'API de Mailpit → « Me connecter » → profil (pseudo, nom, 1990) → 2 univers → zone « Lyon 7e » à 5 km → accueil connecté ; vérifie par `GET /v1/me/zones` que la zone par défaut fait 5000 m.
- [ ] `test_access_matrix.py` : parcourt `app.routes` ; toute route qui dépend de `current_user` doit figurer dans `SELF_ROUTES` ou `OWNED_ROUTES` (le test échoue sinon, ce qui oblige à déclarer chaque nouvelle route) ; anonyme → 401 sur chacune ; tiers → 404 sur chaque `OWNED_ROUTES` (adresses, zones, sessions, passkeys, exports) ; membre → 403 sur chaque route staff.
- [ ] `test_no_pii_in_telemetry.py` : parcours complet (lien magique, profil, adresse, export) avec capture de la sortie structlog, des événements Sentry (`before_send` sur un transport mémoire) et des spans OpenTelemetry (exportateur mémoire) : aucune occurrence de l'e-mail, du jeton, de l'IP, du nom, de l'adresse postale ni de l'année de naissance.
- [ ] CI verte ; démonstration sur staging ; commit `test(identity): journey 1 e2e, private route access matrix and telemetry pii check`.

---

## 6. Porte de P1 (cahier 17.2) : checklist et preuves

| # | Critère | Preuve attendue |
|---|---|---|
| G1 | Parcours 1 vert | Job `e2e-full` vert sur `main` : inscription par lien magique lu dans Mailpit → onboarding → zone 5 km (P1-T12c). |
| G2 | Tiers → 404 sur toutes les routes privées | `test_access_matrix.py` vert ; liste des routes couvertes jointe à la PR. |
| G3 | Export RGPD complet | `test_every_identity_table_exported` vert + export réel téléchargé par Arcel sur staging. |
| G4 | Aucune donnée personnelle dans les journaux | `test_no_pii_in_telemetry.py` vert + recherche de son e-mail dans les journaux Railway et Sentry de staging : 0 résultat. |
| G5 | Session révoquée inutilisable | `test_revoked_session_rejected_next_request` + démonstration : révoquer une session depuis W20, l'autre navigateur est déconnecté à la requête suivante. |
| G6 | Énumération impossible | `test_request_same_response_known_and_unknown_email` vert. |
| G7 | Double validation | Tests du point de revue 4 verts ; ligne d'audit avec `actor_id` et `approver_id` différents. |
| G8 | Connexions réelles sur staging | Lien magique reçu par Arcel (Resend) ; Google en mode Test ; passkey créée et utilisée ; compte staff connecté par passkey. |
| G9 | Accessibilité | axe 0 violation sur W06, W07, W08, W20, pages légales ; parcours au clavier. |
| G10 | Documentation | ADR-0015 à 0018, `PII.md`, `threat-model.md`, glossaire et `HANDOFF.md` à jour ; Apple prêt derrière son flag. |

## 7. Actions qui reviennent à Arcel pendant P1

1. Valider ce plan, et trancher E14 (règle d'âge à partir de l'année seule).
2. Créer le compte Resend avec l'adresse de son compte client et transmettre la clé dans les variables Railway (guidage en P1-T02c).
3. Créer le client OAuth Google en mode Test (guidage en P1-T03).
4. Ajouter `PROXY_SHARED_SECRET`, `API_INTERNAL_URL` et `FIELD_ENCRYPTION_KEY` (guidage en P1-T02a et T02c).
5. Enrôler sa passkey staff sur staging (P1-T11).
6. Plus tard, à la fin du projet : domaine, compte Apple Developer, Cloudflare Turnstile, fournisseur d'e-mails hébergé dans l'UE.
