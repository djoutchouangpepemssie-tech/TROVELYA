# Skills installés dans TROVÉLYA

72 skills pour Claude Code, sélectionnés le 23 octobre 2026 parmi les dépôts les plus suivis de GitHub (obra/superpowers, mattpocock/skills, anthropics/skills, vercel-labs, Expo, Stripe, Trail of Bits, github/awesome-copilot, everything-claude-code…). Ils sont dans `.claude/skills/` : Claude Code les charge automatiquement. Tape `/skills` pour les voir.

Aucun skill ne dépend de Supabase : tout est valable pour PostgreSQL sur Railway.

Chaque dossier garde sa licence d'origine (MIT ou Apache 2.0 ; CC BY-SA 4.0 pour Trail of Bits : en cas de modification partagée, garder la même licence et citer la source).

## Méthode de travail (20)

| Skill | À quoi il sert pour TROVÉLYA | Source | Licence |
|---|---|---|---|
| `brainstorming` | Clarifier une fonctionnalité avant d'écrire du code (questions, options, conception validée). | [obra/superpowers](https://github.com/obra/superpowers/tree/main/skills/brainstorming) | MIT |
| `writing-plans` | Transformer un cahier des charges en plan d'implémentation par étapes, avec points de contrôle. | [obra/superpowers](https://github.com/obra/superpowers/tree/main/skills/writing-plans) | MIT |
| `executing-plans` | Exécuter un plan étape par étape, avec vérification à chaque tâche. | [obra/superpowers](https://github.com/obra/superpowers/tree/main/skills/executing-plans) | MIT |
| `subagent-driven-development` | Confier chaque tâche du plan à un sous-agent et relire son travail. | [obra/superpowers](https://github.com/obra/superpowers/tree/main/skills/subagent-driven-development) | MIT |
| `dispatching-parallel-agents` | Lancer plusieurs tâches indépendantes en parallèle (ex. API + écran). | [obra/superpowers](https://github.com/obra/superpowers/tree/main/skills/dispatching-parallel-agents) | MIT |
| `test-driven-development` | Écrire le test d'abord : indispensable pour le séquestre, les enchères et le grand livre. | [obra/superpowers](https://github.com/obra/superpowers/tree/main/skills/test-driven-development) | MIT |
| `systematic-debugging` | Trouver la vraie cause d'un bug avant de corriger. | [obra/superpowers](https://github.com/obra/superpowers/tree/main/skills/systematic-debugging) | MIT |
| `verification-before-completion` | Prouver que ça marche (tests, commandes) avant de dire « terminé ». | [obra/superpowers](https://github.com/obra/superpowers/tree/main/skills/verification-before-completion) | MIT |
| `requesting-code-review` | Faire relire une fonctionnalité avant de la fusionner. | [obra/superpowers](https://github.com/obra/superpowers/tree/main/skills/requesting-code-review) | MIT |
| `receiving-code-review` | Traiter une relecture avec rigueur, sans tout accepter aveuglément. | [obra/superpowers](https://github.com/obra/superpowers/tree/main/skills/receiving-code-review) | MIT |
| `using-git-worktrees` | Travailler sur plusieurs branches en parallèle sans mélanger. | [obra/superpowers](https://github.com/obra/superpowers/tree/main/skills/using-git-worktrees) | MIT |
| `finishing-a-development-branch` | Clore une branche proprement : tests, fusion ou pull request. | [obra/superpowers](https://github.com/obra/superpowers/tree/main/skills/finishing-a-development-branch) | MIT |
| `grilling` | Interrogatoire méthodique d'un plan jusqu'à lever toutes les zones floues (moteur de grill-me). | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/grilling) | MIT |
| `grill-me` | Commande `/grill-me` : Claude te challenge sur une idée avant d'écrire une ligne de code. | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/grill-me) | MIT |
| `grill-with-docs` | Même chose, en rédigeant au passage les décisions (ADR) et le glossaire métier. | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs) | MIT |
| `domain-modeling` | Glossaire et modèle métier : annonce, lot, séquestre, remise, passeport produit… | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/domain-modeling) | MIT |
| `improve-codebase-architecture` | Repère les faiblesses d'architecture et propose des améliorations, rapport visuel à l'appui. | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/improve-codebase-architecture) | MIT |
| `prototype` | Prototype jetable pour trancher une question de conception (ex. machine à états d'une enchère). | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/engineering/prototype) | MIT |
| `handoff` | Résumer une session pour la reprendre dans une nouvelle conversation sans rien perdre. | [mattpocock/skills](https://github.com/mattpocock/skills/tree/main/skills/productivity/handoff) | MIT |
| `karpathy-guidelines` | Règles anti-erreurs des IA : pas d'hypothèse cachée, pas de sur-ingénierie, changements ciblés. | [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills/tree/main/skills/karpathy-guidelines) | MIT |

## Backend Python et FastAPI (11)

| Skill | À quoi il sert pour TROVÉLYA | Source | Licence |
|---|---|---|---|
| `async-python-patterns` | Code Python asynchrone (FastAPI, appels réseau, temps réel). | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/python-development/skills/async-python-patterns) | MIT |
| `python-testing-patterns` | Tests pytest : fixtures, mocks, tests d'API. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/python-development/skills/python-testing-patterns) | MIT |
| `python-background-jobs` | Tâches de fond : e-mails, versements, calcul du fil, relances. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/python-development/skills/python-background-jobs) | MIT |
| `python-error-handling` | Gestion d'erreurs robuste, indispensable autour des paiements. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/python-development/skills/python-error-handling) | MIT |
| `python-type-safety` | Typage strict (mypy/pyright) pour un backend fiable. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/python-development/skills/python-type-safety) | MIT |
| `python-observability` | Logs, métriques et traces pour la Tour de contrôle et le débogage en production. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/python-development/skills/python-observability) | MIT |
| `uv-package-manager` | Gérer les dépendances Python avec uv, comme recommandé pour le monorepo. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/python-development/skills/uv-package-manager) | MIT |
| `modern-python` | Outillage Python moderne (uv, ruff, ty, pre-commit) par Trail of Bits. | [trailofbits/skills](https://github.com/trailofbits/skills/tree/main/plugins/modern-python/skills/modern-python) | CC BY-SA 4.0 |
| `fastapi-patterns` | FastAPI complet : structure, Pydantic v2, dépendances, auth, async, tests. | [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code/tree/main/skills/fastapi-patterns) | MIT |
| `api-design` | Conception d'API REST : nommage, codes d'erreur, pagination, versions. | [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code/tree/main/skills/api-design) | MIT |
| `redis-patterns` | Redis : cache du fil, verrous pour les enchères, limitation de débit, pub/sub pour le temps réel. | [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code/tree/main/skills/redis-patterns) | MIT |

## Base de données PostgreSQL (5)

| Skill | À quoi il sert pour TROVÉLYA | Source | Licence |
|---|---|---|---|
| `postgresql-table-design` | Concevoir les tables : utilisateurs, annonces, commandes, grand livre. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/database-design/skills/postgresql-table-design) | MIT |
| `sql-optimization-patterns` | Accélérer les requêtes lentes (catalogue, recherche, fil). | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/developer-essentials/skills/sql-optimization-patterns) | MIT |
| `database-migration` | Migrations de schéma sans casser la production. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/framework-migration/skills/database-migration) | MIT |
| `postgresql-optimization` | Fonctions avancées de PostgreSQL : JSONB, recherche plein texte, index, extensions (PostGIS, pgvector). | [github/awesome-copilot](https://github.com/github/awesome-copilot/tree/main/skills/postgresql-optimization) | MIT |
| `postgresql-code-review` | Relecture des requêtes et du schéma PostgreSQL : anti-patterns et bonnes pratiques. | [github/awesome-copilot](https://github.com/github/awesome-copilot/tree/main/skills/postgresql-code-review) | MIT |

## Paiements (2)

| Skill | À quoi il sert pour TROVÉLYA | Source | Licence |
|---|---|---|---|
| `stripe-best-practices` | Intégrer Stripe correctement (API récentes, webhooks, sécurité). | [stripe/ai](https://github.com/stripe/ai/tree/main/skills/stripe-best-practices) | MIT |
| `connect-recommend` | Choisir la bonne configuration Stripe Connect pour une marketplace. | [stripe/ai](https://github.com/stripe/ai/tree/main/skills/connect-recommend) | MIT |

## Site web Next.js (7)

| Skill | À quoi il sert pour TROVÉLYA | Source | Licence |
|---|---|---|---|
| `vercel-react-best-practices` | Performance React et Next.js selon l'équipe Vercel. | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills/tree/main/skills/react-best-practices) | MIT |
| `vercel-composition-patterns` | Composants React réutilisables et bien découpés. | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills/tree/main/skills/composition-patterns) | MIT |
| `web-design-guidelines` | Relire l'interface : accessibilité, ergonomie, détails visuels. | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines) | MIT |
| `deploy-to-vercel` | Déployer le site Next.js sur Vercel. | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills/tree/main/skills/deploy-to-vercel) | MIT |
| `nextjs-app-router-patterns` | Next.js App Router : rendu serveur, cache, pages SEO. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/frontend-mobile-development/skills/nextjs-app-router-patterns) | MIT |
| `frontend-design` | Interfaces au design soigné et distinctif (style de la maquette). | [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/frontend-design) | Apache 2.0 |
| `next-intl-add-language` | Ajouter une langue au site Next.js (24 langues de l'UE à terme). | [github/awesome-copilot](https://github.com/github/awesome-copilot/tree/main/skills/next-intl-add-language) | MIT |

## App mobile Expo (9)

| Skill | À quoi il sert pour TROVÉLYA | Source | Licence |
|---|---|---|---|
| `vercel-react-native-skills` | Bonnes pratiques React Native selon Vercel. | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills/tree/main/skills/react-native-skills) | MIT |
| `expo-overview` | Point d'entrée pour toute tâche Expo/EAS : à charger en premier. | [expo/skills](https://github.com/expo/skills/tree/main/plugins/expo/skills/expo-overview) | MIT |
| `expo-project-structure` | Organisation des dossiers d'une app Expo. | [expo/skills](https://github.com/expo/skills/tree/main/plugins/expo/skills/expo-project-structure) | MIT |
| `expo-router` | Navigation de l'app (onglets, pages, liens profonds). | [expo/skills](https://github.com/expo/skills/tree/main/plugins/expo/skills/expo-router) | MIT |
| `expo-data-fetching` | Appels API, cache et chargement des données dans l'app. | [expo/skills](https://github.com/expo/skills/tree/main/plugins/expo/skills/expo-data-fetching) | MIT |
| `expo-native-ui` | Écrans au rendu natif iOS (style Apple, Liquid Glass). | [expo/skills](https://github.com/expo/skills/tree/main/plugins/expo/skills/expo-native-ui) | MIT |
| `expo-design-system` | Système de design de l'app : couleurs, typo, composants. | [expo/skills](https://github.com/expo/skills/tree/main/plugins/expo/skills/expo-design-system) | MIT |
| `eas-app-stores` | Publier sur l'App Store et Google Play. | [expo/skills](https://github.com/expo/skills/tree/main/plugins/expo/skills/eas-app-stores) | MIT |
| `eas-update` | Mises à jour à distance de l'app sans repasser par les stores. | [expo/skills](https://github.com/expo/skills/tree/main/plugins/expo/skills/eas-update) | MIT |

## Monorepo (2)

| Skill | À quoi il sert pour TROVÉLYA | Source | Licence |
|---|---|---|---|
| `monorepo-management` | Organiser le monorepo (web, mobile, api, packages partagés). | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/developer-essentials/skills/monorepo-management) | MIT |
| `turborepo-caching` | Builds rapides avec Turborepo. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/developer-essentials/skills/turborepo-caching) | MIT |

## Déploiement (2)

| Skill | À quoi il sert pour TROVÉLYA | Source | Licence |
|---|---|---|---|
| `deployment-patterns` | Déploiement : CI/CD, health checks, retours arrière (Railway, Vercel). | [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code/tree/main/skills/deployment-patterns) | MIT |
| `docker-patterns` | Conteneurs Docker et Docker Compose pour le dev local et Railway. | [affaan-m/everything-claude-code](https://github.com/affaan-m/everything-claude-code/tree/main/skills/docker-patterns) | MIT |

## Sécurité et conformité (7)

| Skill | À quoi il sert pour TROVÉLYA | Source | Licence |
|---|---|---|---|
| `auth-implementation-patterns` | Authentification : sessions, JWT, OAuth (Apple, Google), rôles. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/developer-essentials/skills/auth-implementation-patterns) | MIT |
| `gdpr-data-handling` | Conformité RGPD : consentement, export, suppression des données. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/hr-legal-compliance/skills/gdpr-data-handling) | MIT |
| `stride-analysis-patterns` | Analyse des menaces (STRIDE) sur le paiement, le séquestre et les comptes. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/security-scanning/skills/stride-analysis-patterns) | MIT |
| `semgrep` | Scanner le code pour trouver des failles de sécurité. | [trailofbits/skills](https://github.com/trailofbits/skills/tree/main/plugins/static-analysis/skills/semgrep) | CC BY-SA 4.0 |
| `supply-chain-risk-auditor` | Auditer les dépendances npm/pip à risque. | [trailofbits/skills](https://github.com/trailofbits/skills/tree/main/plugins/supply-chain-risk-auditor/skills/supply-chain-risk-auditor) | CC BY-SA 4.0 |
| `sharp-edges` | Repérer les API et réglages dangereux par défaut. | [trailofbits/skills](https://github.com/trailofbits/skills/tree/main/plugins/sharp-edges/skills/sharp-edges) | CC BY-SA 4.0 |
| `security-review` | Audit de sécurité qui suit les flux de données comme un chercheur en sécurité (GitHub). | [github/awesome-copilot](https://github.com/github/awesome-copilot/tree/main/skills/security-review) | MIT |

## Tests (2)

| Skill | À quoi il sert pour TROVÉLYA | Source | Licence |
|---|---|---|---|
| `webapp-testing` | Tester le site dans un vrai navigateur avec Playwright. | [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/webapp-testing) | Apache 2.0 |
| `e2e-testing-patterns` | Tests de bout en bout : parcours d'achat, enchère, remise. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/developer-essentials/skills/e2e-testing-patterns) | MIT |

## Recherche et fil (2)

| Skill | À quoi il sert pour TROVÉLYA | Source | Licence |
|---|---|---|---|
| `hybrid-search-implementation` | Recherche hybride mots-clés + sens (pgvector), base de la recherche et de la photo. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/llm-application-dev/skills/hybrid-search-implementation) | MIT |
| `recsys-pipeline-architect` | Architecture d'un système de recommandation, base du fil personnalisé. | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/machine-learning-ops/skills/recsys-pipeline-architect) | MIT |

## Accessibilité (1)

| Skill | À quoi il sert pour TROVÉLYA | Source | Licence |
|---|---|---|---|
| `wcag-audit-patterns` | Audit d'accessibilité WCAG (obligation européenne, loi de 2025). | [wshobson/agents](https://github.com/wshobson/agents/tree/main/plugins/accessibility-compliance/skills/wcag-audit-patterns) | MIT |

## Outils (2)

| Skill | À quoi il sert pour TROVÉLYA | Source | Licence |
|---|---|---|---|
| `skill-creator` | Créer tes propres skills TROVÉLYA (règles métier, style, procédures). | [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/skill-creator) | Apache 2.0 |
| `find-skills` | Chercher et installer d'autres skills quand un besoin apparaît (le skill le plus installé au monde). | [vercel-labs/skills](https://github.com/vercel-labs/skills/tree/main/skills/find-skills) | MIT |

## À créer pour TROVÉLYA (avec `skill-creator`)

- Règles métier : séquestre, commission plafonnée, frais acheteur, code de remise, sanctions graduées.
- Grand livre comptable en partie double.
- Anti-contournement : détection et niveaux de sanction.
- Charte visuelle : Bleu #1D2BFF, Geist, Liquid Glass.
- Prestataire de paiement si autre que Stripe (Mangopay, Adyen) : aucun skill public sérieux.
