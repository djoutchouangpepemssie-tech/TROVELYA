# Registre des données personnelles — P0

**Date :** 24 octobre 2026. Toutes les données sont hébergées dans l'UE : Railway europe-west4 (Pays-Bas), Vercel fra1 (Francfort), Sentry région UE (de.sentry.io).

P0 ne crée aucune table d'utilisateurs. Les seules données personnelles possibles sont techniques.

## Stockage en base

| Table.colonne | Donnée | Finalité | Base légale | Conservation |
|---|---|---|---|---|
| `audit_log.actor_id`, `approver_id` | Identifiant interne de la personne qui agit ou approuve | Traçabilité des actions sensibles (CLAUDE.md, DSA) | Obligation légale / intérêt légitime | 10 ans |
| `audit_log.ip` | Adresse IP de l'action | Sécurité, enquête en cas d'abus | Intérêt légitime | 10 ans (avec la ligne d'audit, qui est inaltérable) |
| `audit_log.user_agent` | Navigateur et système | Sécurité | Intérêt légitime | 10 ans |
| `audit_log.before`, `after`, `reason` | Valeurs avant/après d'une action | Traçabilité | Obligation légale / intérêt légitime | 10 ans ; ne jamais y écrire de donnée sensible inutile (minimisation) |
| `idempotency_keys.user_id` | Identifiant interne | Rejouer une requête sans doublon | Exécution du contrat | 72 heures (purge quotidienne à 04 h 30) |
| `idempotency_keys.response_body` | Réponse renvoyée au client (peut contenir des données de la personne) | Idem | Exécution du contrat | 72 heures |

## Hors base

| Lieu | Donnée | Traitement |
|---|---|---|
| Journaux Railway (API, worker) | Adresse IP du visiteur, chemins appelés | IP **masquées** (`[REDACTED]`) par `redact_pii`, comme les e-mails, téléphones, IBAN et jetons ; conservation selon l'offre Railway |
| Redis (limiteur de débit) | Adresse IP | Jamais stockée : seule une empreinte HMAC-SHA-256 (clé secrète du serveur) sert de clé, avec une expiration de 60 s |
| Sentry (API et web) | Erreurs et traces | Ni identité, ni IP, ni cookies, ni en-têtes (hors `x-request-id` et `content-type`), ni corps, ni paramètres d'URL, ni variables locales ; « Prevent Storing of IP Addresses » activé côté Sentry. La localisation affichée est celle du serveur qui envoie |
| Cookie `NEXT_LOCALE` (web) | Langue choisie | Cookie fonctionnel, pas de consentement requis |
| Cookie `trv_csrf` (API) | Jeton anti-CSRF signé | Cookie de sécurité strictement nécessaire |

## Règles pour les phases suivantes

1. Toute nouvelle colonne personnelle est ajoutée à ce registre dans la même PR (finalité, base légale, durée).
2. Aucune donnée personnelle dans les noms de clés Redis, les identifiants d'événements ou les messages de journal : utiliser des identifiants internes.
3. Les droits des personnes (accès, effacement, portabilité) arrivent avec les comptes en P1 (skill `gdpr-data-handling`).
