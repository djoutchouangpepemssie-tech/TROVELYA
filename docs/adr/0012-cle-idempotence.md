# ADR-0012 — Clé d'idempotence : identifiant technique et unicité NULLS NOT DISTINCT

**Statut :** Acceptée (écart E1)
**Date :** 24 octobre 2026

## Contexte

Le cahier (7.2) prévoit `PRIMARY KEY (key, user_id)` avec `user_id` nullable ; PostgreSQL rend NOT NULL toute colonne de clé primaire, une requête anonyme ne pourrait pas être enregistrée.

## Décision

`idempotency_keys.id BIGINT IDENTITY` en clé primaire et `UNIQUE NULLS NOT DISTINCT (key, user_id)` (PostgreSQL ≥ 15). Conservation 72 heures, purge quotidienne à 04 h 30 (worker).

## Conséquences

+ Même garantie d'unicité, anonymes compris.
− Requiert PostgreSQL ≥ 15 (nous sommes en 17).
