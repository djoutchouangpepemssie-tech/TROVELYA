# Modèle de menaces — v2 (P0 + P1 authentification et comptes)

**Date :** 24 octobre 2026. **Méthode :** STRIDE (usurpation, altération, répudiation, divulgation, déni de service, élévation de privilèges). **À revoir :** à chaque phase qui ajoute une surface (P1 authentification, P4 paiements, P12 enchères…).

## Périmètre et frontières de confiance

```
Navigateur ──HTTPS──▶ Vercel fra1 (Next.js, CSP à nonce)
    │                         │
    └──HTTPS──▶ Railway europe-west4 : API FastAPI ──réseau privé──▶ pg (PostgreSQL 17)
                                 │                               └─▶ Redis
                                 └─HTTPS──▶ Sentry UE (de.sentry.io)
              worker arq ──réseau privé──▶ pg, Redis
GitHub (code, CI, Dependabot) ──▶ Railway / Vercel (déploiement par branche)
```

Frontières : Internet → Vercel/API ; API → base et Redis (réseau privé Railway, non exposés) ; services → Sentry ; GitHub → plateformes de déploiement.

P0 ne contient **aucune** donnée métier ni authentification : les menaces ci-dessous portent sur le socle.

## Analyse

| Composant | Menace (STRIDE) | Mesure en place (P0) | Reste à faire |
|---|---|---|---|
| API | **S** Requête forgée depuis un autre site (CSRF) | Double soumission signée HMAC (`core/csrf.py`), `SameSite`, contrôle sur toute méthode non sûre | Sessions opaques en P1 (ADR-0008) |
| API | **T** Rejeu d'une requête qui modifie | Clés d'idempotence (ADR-0012), même réponse rejouée, empreinte de la requête vérifiée | — |
| API | **I** Fuite d'informations dans les erreurs | Erreurs RFC 9457 génériques (« Erreur interne »), sans trace ni détail ; `/docs` absent en production | — |
| API | **I** Données personnelles dans les journaux ou Sentry | `redact_pii` sur tous les journaux ; Sentry `data_collection` strict + `before_send`/`before_breadcrumb` ; IP masquées ; « Prevent Storing of IP Addresses » activé dans Sentry | Revue à chaque nouveau champ personnel |
| API | **D** Saturation par un client anonyme | Limite glissante par client (Redis, 120 requêtes/minute), clé = empreinte HMAC de l'IP | Limites par compte en P1 ; protection DDoS du fournisseur |
| API | **D** Redis indisponible | Limiteur en « fail open » (journalisé), `/ready` signale la panne | Alerte sur `/ready` |
| API | **E** Route de test exposée | Routes `_test` montées seulement en `local`/`test` ; `_debug` absente en production (testé) | — |
| Base | **T** Altération du journal d'audit | Ajout seul (UPDATE/DELETE refusés), chaîne SHA-256 calculée en base (ADR-0014), vérification nocturne | Alerte si `audit_verify_chain()` signale une rupture |
| Base | **T** Écriture comptable déséquilibrée | Contrainte différée d'équilibre, écritures immuables (ADR-0005) | Plan de comptes en P4 |
| Base | **I** Accès direct depuis Internet | Aucun port public : `pg` et Redis seulement sur le réseau privé Railway | — |
| Base | **R/D** Perte de données | Volume persistant ; exercice de restauration joué (`docs/runbooks/restore.md`) | Sauvegardes planifiées et exercice trimestriel |
| Worker | **T** Événement émis pour une transaction annulée | Outbox transactionnelle (ADR-0007), testée | — |
| Worker | **D** Relais bloqué | Jauge `trovelya_outbox_oldest_unpublished_seconds` | Alerte > 60 s quand Grafana sera branché |
| Web | **T/I** Injection de script (XSS) | CSP à nonce par requête, `strict-dynamic`, `object-src 'none'`, `frame-ancestors 'none'` ; règle semgrep interdisant `dangerouslySetInnerHTML` | — |
| Web | **S** Hameçonnage par mise en cadre | `X-Frame-Options: DENY`, `frame-ancestors 'none'`, HSTS avec `preload` | Domaine `trovelya.com` + HSTS preload à l'achat |
| CI/CD | **T** Code non revu en production | Production seulement via `release`, avancé par le workflow après CI verte (ADR-0013) | Protection de `main` dès un compte GitHub Pro ou Team |
| CI/CD | **I** Secret commis dans le dépôt | gitleaks sur tout l'historique à chaque PR ; `.env` ignoré ; secrets seulement dans Railway/Vercel | — |
| Chaîne d'approvisionnement | **T** Dépendance compromise ou vulnérable | Versions épinglées, fichiers de verrouillage, `pip-audit`, `pnpm audit`, semgrep, SBOM CycloneDX sur `main`, Dependabot hebdomadaire ; binaire gitleaks vérifié par somme de contrôle | — |
| Secrets | **I/E** Vol de `SECRET_KEY` | Générée par Railway (`${{secret(64)}}`), jamais affichée, différente par environnement | Procédure de rotation en P1 |

## P1 — Authentification et comptes (ajout du 24 octobre 2026)

Nouvelles frontières :

```
Navigateur ──▶ Vercel (Next.js) ── relais /api/* (secret partagé, IP et pays du client) ──▶ API
                  cookie __Host-trv_session posé sur l'origine du web (ADR-0015)
API ──HTTPS──▶ Resend (e-mails, ADR-0017) · Google / Apple (OIDC) · Géoplateforme IGN (géocodage)
     · Cloudflare Turnstile (anti-robots, flag)
worker ──▶ envoi d'e-mails, export et effacement RGPD
```

Les colonnes « Tâches » renvoient à `docs/plans/P1-identite-comptes.md`.

| Composant | Menace (STRIDE) | Parade prévue | Tâches |
|---|---|---|---|
| Session | **S** Vol du cookie de session (XSS, réseau) | Cookie `__Host-` `HttpOnly; Secure; SameSite=Lax; Path=/` ; CSP à nonce ; jeton de 256 bits dont seul le SHA-256 est stocké | T02a, T02b |
| Session | **S** Fixation de session | Nouveau jeton à chaque connexion et à chaque step-up ; l'ancien est révoqué | T02b, T04 |
| Session | **S** Session volée utilisée longtemps | Expiration absolue 30 jours, inactivité 14 jours, révocation unitaire ou globale immédiate, notification de nouvel appareil ou pays | T02b, T02c |
| Lien magique | **S** Interception de l'e-mail | Usage unique, 15 minutes, jeton dans le fragment d'URL (jamais dans les journaux ni le `Referer`), confirmation par bouton (POST), notification de nouvelle connexion | T02c |
| Lien magique | **I** Énumération des comptes | Même parcours, même réponse `202` et même travail serveur que l'e-mail existe ou non (le compte naît à la vérification) | T02c |
| Lien magique | **D** Bombardement d'e-mails ou de requêtes | 5 par heure par e-mail, 20 par heure par IP, Turnstile (flag) | T02c |
| Lien magique | **T** Préchargement par un scanner d'e-mails qui consomme le lien | La page `/verifier` n'agit qu'après un clic (POST) | T02c, T12a |
| OAuth / OIDC | **S** Connexion forcée sur le compte d'un attaquant (CSRF de connexion), rejeu du code | `state`, `nonce` et `code_verifier` (PKCE) côté serveur, à usage unique, liés au navigateur ; `id_token` vérifié (signature JWKS, `iss`, `aud`, `exp`, `nonce`) | T03 |
| OAuth / OIDC | **E** Prise de compte par liaison sur un e-mail non vérifié | Liaison automatique seulement si `email_verified` est vrai chez le fournisseur ; sinon refus avec invitation à se connecter par lien magique | T03 |
| Passkeys | **S** Rejeu ou relais d'une assertion | Challenge à usage unique (5 min), vérification de l'origine, du RP ID et de `sign_count` | T04 |
| Step-up | **E** Action sensible depuis une session volée | Preuve forte de moins de 12 h exigée : changer d'e-mail, ajouter ou supprimer une passkey, export et effacement RGPD, actions staff sensibles | T04, T05, T09a, T09b, T11 |
| Relais web | **S** IP falsifiée pour contourner les limites | L'API ne croit l'en-tête d'IP du relais que s'il est authentifié par le secret partagé ; sinon `X-Real-IP` réécrit par Railway ; jamais `X-Forwarded-For` fourni par le client | T02a |
| Relais web | **I** Fuite de cookies ou d'en-têtes vers l'API | Liste blanche d'en-têtes relayés ; seuls les cookies `__Host-trv_*` passent | T02a |
| API | **I** IDOR sur adresses, zones, sessions, exports | Politique par objet dans `policies.py` ; 404 pour la ressource d'autrui ; test qui parcourt toutes les routes privées | T05, T06, T09a, T12c |
| API | **E** Utilisateur qui appelle une route staff | Permissions nommées vérifiées côté serveur (`require_permission`) ; comptes staff distincts, passkey obligatoire, sessions de 12 h | T11 |
| Double validation | **R/E** Un seul membre du staff fait seul une action critique | Demande `pending`, approbateur différent qui détient la permission, expiration 24 h, deux identités dans l'audit | T11 |
| RGPD | **I** Export téléchargé par un tiers | Step-up, archive chiffrée (AES-256-GCM), propriétaire seul, expiration 7 jours | T09a |
| RGPD | **T/R** Effacement incomplet ou contesté | Registre des « effaceurs » par module, anonymisation des lignes à conserver, journal d'audit, délai de grâce de 30 jours annulable | T09b |
| Journaux | **I** E-mail, jeton, IP ou adresse dans les journaux, Sentry ou traces | `redact_pii` étendu aux nouveaux champs ; test de bout en bout sur le parcours de connexion | T02c, T12c |
| Inscription | **D** Création de comptes en masse | Turnstile (flag), limites de débit, pas de compte avant vérification de l'e-mail | T02c |
| Mineurs | **I** Profilage d'un mineur | Année de naissance seule ; moins de 15 ans refusé sans rien conserver ; drapeau « mineur » qui exclura toute publicité personnalisée (P11) | T05 |
| E-mails | **I** Données transférées hors UE (Resend : métadonnées aux États-Unis) | Écart temporaire documenté (ADR-0017), seul Arcel reçoit des e-mails avant l'ouverture ; bascule vers un fournisseur hébergé dans l'UE avant le lancement public | T02c |
| Secrets | **I/E** Fuite de `SECRET_KEY`, `PROXY_SHARED_SECRET` ou `FIELD_ENCRYPTION_KEY` | Variables Railway/Vercel chiffrées, différentes par environnement ; procédure de rotation dans `docs/runbooks/secrets.md` | T02a, T09a |

## Hypothèses

- Railway, Vercel, GitHub et Sentry sont des tiers de confiance ; leurs comptes sont protégés par une double authentification (à vérifier par Arcel).
- La valeur `NEXT_PUBLIC_*` n'est jamais secrète (DSN Sentry du web, clé publique Turnstile).
- Avant le lancement public, `trovelya.com` est acheté : passkeys, Apple et e-mails basculent sur ce domaine (les passkeys de test créées sur `vercel.app` sont perdues).
