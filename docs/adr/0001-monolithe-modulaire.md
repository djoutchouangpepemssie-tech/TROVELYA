# ADR-0001 — Monolithe modulaire FastAPI

**Statut :** Acceptée (cahier 5.2)
**Date :** 24 octobre 2026

## Contexte

Une petite équipe doit livrer vite un produit large (catalogue, commandes, séquestre, enchères, live…). Des microservices dès le départ multiplieraient le déploiement, l'observabilité et les transactions distribuées sans bénéfice tant que la charge est modeste.

## Décision

Une seule application FastAPI (`apps/api`), découpée en modules métier (`trovelya.modules.<nom>`) au-dessus d'un socle (`core`, `shared`). Pas de microservices avant P13. Les frontières sont imposées par `import-linter` (`apps/api/.importlinter`) : les modules ne s'importent pas entre eux, `shared` n'importe rien du domaine, les points d'entrée (`main`, `workers`, `scripts`) sont au-dessus.

## Conséquences

+ Un déploiement, une base, des transactions ACID entre modules.
+ Extraction future facilitée : un module chaud (enchères, live, feed) a déjà une frontière nette.
− Discipline nécessaire : la CI (`lint-imports`) refuse toute dépendance interdite.
