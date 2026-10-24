# ADR-0011 — Notre image PostgreSQL 17 (PostGIS, pgvector, h3)

**Statut :** Acceptée (décision V2 d'Arcel)
**Date :** 24 octobre 2026

## Contexte

L'image Postgres proposée par Railway n'a aucune extension ; le produit a besoin de PostGIS, pgvector et h3 dès la recherche locale.

## Décision

Image maison `infra/postgres/Dockerfile` : `postgis/postgis:17-3.6` + `postgresql-17-pgvector` + `postgresql-17-h3`, identique en local, en CI et sur Railway (service `pg`, volume `pg-data`). La migration 0001 crée les 9 extensions (`postgis, vector, pg_trgm, unaccent, citext, btree_gist, ltree, h3, h3_postgis`) ; le job CI `postgres-image` les vérifie sur une base neuve.

## Conséquences

+ Même moteur partout, extensions garanties.
− Mises à jour de l'image à notre charge (Dependabot surveille la base Docker ; procédure dans `infra/postgres/README.md`).
