# ADR-0013 — Production sur la branche `release`

**Statut :** Acceptée (écart E5)
**Date :** 24 octobre 2026

## Contexte

Le cahier (5.7) prévoit une mise en production manuelle par tag ; Railway et Vercel déploient à partir d'une branche.

## Décision

`main` → staging (Railway `staging`, Vercel Preview), automatiquement à chaque fusion. `release` → production (Railway `production`, Vercel Production). Seul le workflow **Deploy production** fait avancer `release` : sur un tag `vX.Y.Z` (ou à la main), il vérifie que le commit est sur `main`, que sa CI est verte, puis avance `release` en avance rapide. Procédure : `docs/runbooks/deploy.md`.

## Conséquences

+ La production ne reçoit que du code passé par staging et par une CI verte.
− Tant que le dépôt est privé sur un compte GitHub gratuit, la protection des branches n'est pas appliquée par GitHub : la règle repose sur la discipline (PR obligatoire, fusion seulement en vert).
