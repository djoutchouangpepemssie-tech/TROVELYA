# TROVÉLYA — instructions pour Claude Code

TROVÉLYA (« La belle trouvaille ») est une marketplace européenne : boutiques de marque, vente entre particuliers, enchères, live shopping, recherche locale (priorité 5 km), passeport produit et séquestre.

## Pile technique (décidée)
- Monorepo pnpm + Turborepo : `apps/web` (Next.js, App Router), `apps/mobile` (Expo), `apps/api` (FastAPI, Python géré avec uv), `packages/api-client` (types générés depuis l'OpenAPI de FastAPI), `packages/ui`, `packages/core`.
- PostgreSQL (extensions PostGIS et pgvector) + Redis, hébergés sur Railway en région Europe. Pas de MongoDB.
- Paiements et séquestre chez un prestataire marketplace (Stripe Connect, Mangopay ou Adyen) : l'application ne détient jamais les fonds et ne stocke jamais de numéro de carte.
- Web sur Vercel, mobile via EAS.

## Règles non négociables
- Tout ce qui touche à l'argent (commandes, séquestre, versements, commissions) passe par un grand livre en partie double, dans des transactions PostgreSQL, et commence par un test (skill `test-driven-development`).
- Montants en centimes (entiers), jamais en nombres à virgule.
- Données hébergées dans l'UE ; respect du RGPD et du DSA (skill `gdpr-data-handling`).
- Toute action d'administration est inscrite dans un journal d'audit.

## Façon de travailler
1. Nouvelle fonctionnalité : `brainstorming`, puis `writing-plans` (phases numérotées, points de validation).
2. Implémentation : `executing-plans` ou `subagent-driven-development`, en TDD.
3. Avant de dire « terminé » : `verification-before-completion`, puis `requesting-code-review`.
4. Bug : `systematic-debugging` avant toute correction.
5. Commits conventionnels (`feat:`, `fix:`…), une branche par fonctionnalité.

## Skills par domaine (liste complète dans SKILLS.md)
- Avant de coder une fonctionnalité : `grill-me` ou `brainstorming`, puis `writing-plans`. Toujours appliquer `karpathy-guidelines`.
- Backend : `fastapi-patterns`, `api-design`, `async-python-patterns`, `python-testing-patterns`, `python-background-jobs`, `redis-patterns`.
- Base de données : `postgresql-table-design`, `postgresql-optimization`, `postgresql-code-review`, `database-migration`.
- Web : `nextjs-app-router-patterns`, `vercel-react-best-practices`, `frontend-design`, `web-design-guidelines`.
- Mobile : charger `expo-overview` en premier pour toute tâche Expo.
- Paiements : `connect-recommend`, `stripe-best-practices` (si Stripe Connect est retenu).
- Déploiement : `docker-patterns`, `deployment-patterns`.
- Sécurité : `security-review`, `auth-implementation-patterns`, `stride-analysis-patterns`, `semgrep`, `supply-chain-risk-auditor`.
- Besoin non couvert : `find-skills`.
