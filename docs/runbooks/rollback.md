# Runbook — revenir à la version précédente

## Quand

Une mise en production (ou staging) casse un parcours, fait monter les erreurs dans Sentry ou fait échouer `/ready`.

## API et worker (Railway)

1. Railway → environnement concerné → service `TROVELYA` (puis `worker` si besoin) → *Deployments*.
2. Sur le dernier déploiement sain : *⋯* → **Redeploy** (ou *Rollback*). Railway relance la même image, sans reconstruire.
3. Attendre l'état **SUCCESS** : le healthcheck `/ready` conditionne la mise en service (base et Redis joignables).
4. Vérifier les journaux (une ligne `GET /ready … 200`) et Sentry pendant 15 minutes.
5. Corriger dans une PR vers `main`, laisser passer staging, puis remettre en production par un nouveau tag (`docs/runbooks/deploy.md`). Ne jamais corriger directement sur `release`.

### Migrations

Le redéploiement ne redescend pas les migrations : `alembic upgrade head` ne fait rien si la base est déjà à jour. C'est voulu : chaque migration doit rester compatible avec la version précédente du code (ajouter avant de retirer). Si une migration elle-même est en cause, écrire une **nouvelle** migration corrective ; `alembic downgrade` reste réservé à staging (le `downgrade` de chaque migration est testé en CI).

## Web (Vercel)

Vercel → projet `trovelya` → *Deployments* → déploiement de production précédent → **Promote to Production** (ou *Instant Rollback*). Effet immédiat, sans reconstruction.

## Exercice réel du 24 octobre 2026 (API staging)

| Étape | Déploiement | Version | Résultat |
|---|---|---|---|
| Situation de départ | `3b0a7de9` | PR #19 (masquage des IP) | SUCCESS |
| Retour arrière | `fade3c9e` (redéploiement de `b1bed99f`) | PR #18 | SUCCESS, conteneur démarré à 12:33:35, `GET /ready 200` à **12:33:41** (6 s) |
| Retour à la version actuelle | `c0631165` (redéploiement de `3b0a7de9`) | PR #19 | SUCCESS, `GET /ready 200` à **12:36:48** |

Effet visible : pendant le retour arrière, les journaux d'accès montraient de nouveau l'adresse IP en clair (comportement de la PR #18), puis `[REDACTED]` après le retour à la PR #19. Le retour arrière ramène donc bien le comportement exact de la version précédente.
