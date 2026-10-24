# ADR-0004 — Contrat API OpenAPI et client généré

**Statut :** Acceptée (cahier 5.2), en place depuis P0-T12
**Date :** 24 octobre 2026

## Contexte

Le web, puis le mobile, consomment l'API. Des types écrits à la main dérivent du serveur.

## Décision

FastAPI produit le contrat OpenAPI 3.1 (`docs/api/openapi.json`, via `scripts/export_openapi.py`) ; `packages/api-client` génère ses types avec `openapi-typescript` et appelle l'API avec `openapi-fetch`. Chaque route a un `operation_id` explicite et unique (testé). Le job CI `contract` régénère le tout et échoue sur la moindre différence.

## Conséquences

+ Zéro dérive entre front et back, vérifiée à chaque PR.
− Toute modification d'API impose `pnpm api:generate` et le commit des fichiers générés.
