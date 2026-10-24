# Modèle de menaces — v1 (périmètre P0)

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

## Hypothèses

- Railway, Vercel, GitHub et Sentry sont des tiers de confiance ; leurs comptes sont protégés par une double authentification (à vérifier par Arcel).
- La valeur `NEXT_PUBLIC_*` n'est jamais secrète (DSN Sentry du web, URL de l'API).
