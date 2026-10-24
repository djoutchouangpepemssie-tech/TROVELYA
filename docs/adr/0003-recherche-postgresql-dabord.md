# ADR-0003 — Recherche : PostgreSQL d'abord

**Statut :** Acceptée (cahier 5.2), mise en œuvre en P3
**Date :** 24 octobre 2026

## Contexte

La recherche (texte, fautes de frappe, sémantique, distance) est centrale. Un moteur dédié est coûteux à opérer et à synchroniser.

## Décision

P3 utilise PostgreSQL : `tsvector` + `pg_trgm` + `pgvector` + PostGIS. On passe à Typesense ou OpenSearch quand le p95 dépasse 150 ms ou que le catalogue dépasse 2 millions d'annonces actives.

## Conséquences

+ Les extensions nécessaires sont déjà dans notre image (ADR-0011) et vérifiées en CI.
− Seuils à mesurer dès P3 (traces OpenTelemetry, `docs/runbooks/observability.md`).
