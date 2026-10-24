# Runbook — observabilité

## Ce qui est en place (P0-T15)

| Signal | Où | Réglage |
| --- | --- | --- |
| Journaux JSON | Railway (API, worker) | `core/logging.py` : structlog, une ligne JSON par événement, `request_id` sur chaque ligne d'une requête |
| Erreurs et traces | Sentry, région UE (`de.sentry.io`), organisation `trovelya` | API : `SENTRY_DSN` (Railway) ; web : `NEXT_PUBLIC_SENTRY_DSN` (Vercel) |
| Traces et métriques OpenTelemetry | Grafana Cloud UE (à brancher) | `OTEL_EXPORTER_OTLP_ENDPOINT` ; rien n'est envoyé tant qu'elle est vide |

## Données personnelles (RGPD)

- Les journaux passent tous par `redact_pii` : e-mails, téléphones, IBAN, jetons `Bearer` sont
  remplacés par `[REDACTED]`, ainsi que la valeur de toute clé contenant `password`, `token`,
  `secret`, `authorization`, `cookie`, `email`, `phone`, `iban` ou `address`. Les journaux
  d'uvicorn et d'arq passent par le même filtre.
- Sentry (API) : `data_collection` interdit l'identité de l'utilisateur, les cookies, les corps et
  paramètres de requête, les données SQL et les variables locales ; seuls les en-têtes
  `x-request-id` et `content-type` sont envoyés. Sentry (web) : `sendDefaultPii: false`, pas de
  rejeu de session.

## Vérifier Sentry de bout en bout

1. Ouvrir `https://trovelya-staging.up.railway.app/v1/_debug/error` : réponse 500 (voulue).
   Cette route n'existe pas en production (404).
2. Dans Sentry (projet de l'API), l'erreur `DebugError` apparaît en moins d'une minute,
   environnement `staging`, avec le `x-request-id` de la réponse.

## Retrouver une requête

L'en-tête de réponse `x-request-id` est aussi dans chaque ligne de journal de la requête et dans
l'événement Sentry : filtrer les journaux Railway sur `request_id`.

## Métriques et alertes

| Métrique | Sens | Alerte proposée |
| --- | --- | --- |
| `trovelya_outbox_oldest_unpublished_seconds` | âge du plus ancien événement d'outbox non publié (jauge du worker) | > 60 s pendant 5 min : le relais est bloqué |
| taux d'erreur HTTP 5xx (traces FastAPI) | santé de l'API | > 2 % sur 5 min |
| latence p95 (traces FastAPI) | performance | > 800 ms sur 10 min |

Tableau de bord Grafana de base (dès que l'endpoint OTLP est configuré) : ces trois courbes,
filtrées par `deployment.environment`.

Disponibilité : moniteur Sentry *Uptime* sur `/health` de la production, alerte au-delà d'une
minute d'indisponibilité (section 16.4).
