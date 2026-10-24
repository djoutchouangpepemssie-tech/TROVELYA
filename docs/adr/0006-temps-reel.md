# ADR-0006 — Temps réel : WebSocket et un seul écrivain par enchère

**Statut :** Acceptée (cahier 5.2), mise en œuvre en P12-P13
**Date :** 24 octobre 2026

## Contexte

Les enchères exigent un ordre strict des offres ; le live exige une diffusion à faible latence.

## Décision

WebSocket FastAPI + Redis pub/sub pour la diffusion ; un seul écrivain par enchère (verrou Redis + séquence PostgreSQL) pour l'ordre des offres.

## Conséquences

+ Ordre strict, sans infrastructure supplémentaire.
− Rien n'est construit en P0 ; la décision fixe le cadre.
