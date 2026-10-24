# TROVÉLYA

*La belle trouvaille.* Marketplace européenne : boutiques, vente entre particuliers, enchères, live shopping, recherche locale et séquestre.

- `CLAUDE.md` : décisions techniques et façon de travailler avec Claude Code.
- `SKILLS.md` : les skills installés dans `.claude/skills/`.

Pile prévue : monorepo pnpm + Turborepo (`apps/web` Next.js, `apps/mobile` Expo, `apps/api` FastAPI), PostgreSQL + Redis sur Railway (région Europe).

## Démarrer

Prérequis : Node.js 24 LTS (voir `.nvmrc`, minimum 22.13) et pnpm (version épinglée dans `package.json`, via `corepack enable`).

```bash
pnpm install
pnpm turbo run lint typecheck test build
```

Organisation : `apps/*` (applications) et `packages/*` (paquets partagés), orchestrés par Turborepo. Le plan de la phase en cours est dans `docs/plans/`.
