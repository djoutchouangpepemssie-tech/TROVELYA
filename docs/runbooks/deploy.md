# Runbook — déployer TROVÉLYA

## Environnements

| Environnement | Branche | API (Railway) | Web (Vercel) |
| --- | --- | --- | --- |
| staging | `main` | `trovelya-staging.up.railway.app` | prévisualisation de `main` |
| production | `release` | `trovelya-production.up.railway.app` | production du projet `trovelya` |

Toute PR fusionnée dans `main` part en staging automatiquement (Railway et Vercel).
La production ne bouge que par le workflow **Deploy production** (décision E5).

## Mettre en production

1. Vérifier staging : `/ready` répond 200, parcours principaux du web, aucune nouvelle erreur dans Sentry.
2. Poser un tag de version sur le commit de `main` voulu, ce qui lance **Deploy production** :
   `git tag v0.1.0 <commit> && git push origin v0.1.0`.
   Variante sans tag : GitHub → Actions → **Deploy production** → *Run workflow* (laisser `sha`
   vide pour la tête de `main`).
3. Le workflow refuse si la CI de ce commit n'est pas verte ou si `release` n'est pas un ancêtre (pas d'avance rapide possible).
4. Railway (production) reconstruit `pg`, `TROVELYA` et `worker` ; `alembic upgrade head` puis `python -m trovelya.scripts.seed_catalog` tournent avant le basculement, le healthcheck `/ready` conditionne la mise en service.
5. Contrôler le déploiement dans Railway, puis Sentry pendant 15 minutes.

## Revenir en arrière

- Code : Railway → service → *Deployments* → *Rollback* sur le déploiement précédent. Puis relancer
  **Deploy production** avec le `sha` voulu une fois le correctif fusionné.
- Migrations : chaque migration a un `downgrade` testé en CI (aller-retour), mais on corrige
  de préférence par une nouvelle migration plutôt que de redescendre en production.

## Réglages hors code

Les réglages des services Railway sont décrits dans `infra/railway/README.md`.
