# ADR-0008 — Authentification par sessions opaques

**Statut :** Acceptée (cahier 5.2), mise en œuvre en P1
**Date :** 24 octobre 2026

## Contexte

Un JWT long ne se révoque pas ; une place de marché doit pouvoir couper un compte immédiatement.

## Décision

Web : sessions opaques côté serveur, cookie `HttpOnly`, `Secure`, `SameSite=Lax`. Mobile : jetons d'accès courts et rafraîchissement rotatif. P0 pose déjà le CSRF double soumission signé (`core/csrf.py`, `GET /v1/csrf`) et le client web qui renvoie l'en-tête `X-CSRF-Token`.

## Conséquences

+ Révocation immédiate.
− Stockage des sessions côté serveur (PostgreSQL ou Redis) à dimensionner en P1.
