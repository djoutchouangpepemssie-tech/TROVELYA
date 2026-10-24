# ADR-0009 — ORM SQLAlchemy 2 asynchrone et migrations Alembic

**Statut :** Acceptée (cahier 5.2), écart E6
**Date :** 24 octobre 2026

## Contexte

Il faut un accès base mûr, asynchrone, avec un contrôle fin des requêtes, et des migrations rangées par module (cahier 5.3).

## Décision

SQLAlchemy 2 asynchrone (asyncpg) et Alembic. SQL brut autorisé pour la recherche et le grand livre, dans des fonctions testées ; jamais de SQL construit en f-string (règle semgrep `trovelya-no-raw-sql-format`). Migrations écrites à la main en SQL (`execute_script`), sans autogénération. **Écart E6** : `version_locations` multiples, une seule histoire linéaire — `core/migrations/versions/` pour le socle, `modules/<module>/migrations/versions/` pour chaque module. Chaque migration a un `downgrade`, testé par l'aller-retour `upgrade → downgrade → upgrade` en CI.

## Conséquences

+ Migrations lisibles et proches du module propriétaire.
− Les URL `postgresql://` des hébergeurs sont converties vers asyncpg (`core/config.asyncpg_url`).
