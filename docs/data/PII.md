# Registre des données personnelles

**Date :** 24 octobre 2026. Toutes les données sont hébergées dans l'UE : Railway europe-west4 (Pays-Bas), Vercel fra1 (Francfort), Sentry région UE (de.sentry.io).

P0 ne contenait que des données techniques. Les comptes arrivent en P1 (module `identity`, section 7.3 du cahier). Durées de conservation : section 14.1 du cahier ; les purges automatiques sont livrées par la tâche indiquée.

## Stockage en base

| Table.colonne | Donnée | Finalité | Base légale | Conservation |
|---|---|---|---|---|
| `users.email`, `email_verified_at` | Adresse e-mail | Connexion, e-mails transactionnels | Exécution du contrat | Durée du compte ; compte inactif 3 ans puis suppression après préavis ; anonymisée à l'effacement (P1-T09b) |
| `users.phone_e164`, `phone_verified_at` | Téléphone (non collecté en P1) | Vérification vendeur au-delà d'un seuil (P4) | Exécution du contrat | Idem |
| `users.username`, `display_name`, `bio`, `avatar_media_id` | Identité publique choisie | Profil public | Exécution du contrat | Idem ; remplacés à l'effacement |
| `users.birth_year` | Année de naissance | Âge minimum (8.18), protection des mineurs | Obligation légale | Idem ; effacée à l'effacement |
| `users.locale`, `timezone`, `country_code` | Langue, fuseau, pays | Affichage, règles par pays | Exécution du contrat | Idem |
| `users.status`, `visibility_factor`, `is_staff` | Statut du compte, sanctions | Sécurité, modération | Intérêt légitime / obligation légale (DSA) | Idem |
| `users.marketing_opt_in` | Choix marketing | Envoi d'e-mails promotionnels | Consentement | Idem |
| `users.last_seen_at`, `created_at`, `profile_completed_at`, `erasure_requested_at` | Dates d'activité | Inactivité, délai de grâce de l'effacement | Exécution du contrat / obligation légale | Idem |
| `auth_identities.provider_subject` | Identifiant chez Google ou Apple | Connexion sociale | Exécution du contrat | Supprimé à l'effacement ou à la déliaison |
| `passkeys.credential_id`, `public_key`, `name`, `transports`, `last_used_at` | Clé publique de l'appareil, nom donné | Connexion par passkey | Exécution du contrat | Supprimée par la personne ou à l'effacement |
| `magic_links.email`, `ip` | E-mail et IP de la demande de lien | Connexion, lutte contre les abus | Exécution du contrat / intérêt légitime | 24 heures après expiration (purge, P1-T02c) |
| `sessions.ip`, `user_agent`, `device_label`, `country_code` | IP, navigateur, appareil, pays de connexion | Sécurité du compte, alerte de nouvel appareil, liste des sessions | Intérêt légitime | 12 mois après la fin de la session (journaux techniques, 14.1) ; supprimées à l'effacement |
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
