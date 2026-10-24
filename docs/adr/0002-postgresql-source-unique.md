# ADR-0002 — PostgreSQL, source de vérité unique

**Statut :** Acceptée (cahier 5.2)
**Date :** 24 octobre 2026

## Contexte

Le produit mêle argent, géographie, recherche et messagerie. Multiplier les bases (MongoDB, moteur de recherche dédié…) multiplie les incohérences et l'exploitation.

## Décision

PostgreSQL est l'unique source de vérité, y compris pour le feed, la messagerie et la recherche jusqu'à preuve du contraire. Pas de MongoDB. Redis ne sert qu'au cache, aux files `arq`, au flux d'événements et aux limites de débit : il peut être vidé sans perte.

## Conséquences

+ Transactions ACID partout, PostGIS et pgvector dans la même base.
+ Un seul système de données à sauvegarder et restaurer (`docs/runbooks/restore.md`).
− Les besoins de recherche avancée passent par l'ADR-0003.
