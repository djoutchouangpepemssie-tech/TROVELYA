# Runbook — secrets et leur rotation

Aucun secret dans le dépôt (gitleaks en CI). Chaque secret existe en **staging** et en **production**, avec une valeur différente. Ne jamais le copier dans un ticket, une PR, un message ou un journal.

| Secret | Où | Rôle | Rotation |
|---|---|---|---|
| `SECRET_KEY` | Railway, service `TROVELYA` (le worker y fait référence) | Signatures internes (CSRF), empreinte des IP dans Redis | Voir ci-dessous ; invalide les jetons CSRF en cours (rechargés automatiquement par le web) |
| `PROXY_SHARED_SECRET` | Railway `TROVELYA` (le worker y fait référence) **et** Vercel (variable « Sensitive », environnement correspondant) | Authentifie l'IP et le pays transmis par le relais web (ADR-0015) | Voir ci-dessous |

## Créer `PROXY_SHARED_SECRET` (une fois par environnement)

1. Railway → projet `trovelya` → environnement (staging ou production) → service `TROVELYA` → **Variables** → **New Variable** : nom `PROXY_SHARED_SECRET`, valeur `${{secret(48)}}`. Railway génère une valeur aléatoire.
2. Même environnement → service `worker` → **Variables** → `PROXY_SHARED_SECRET` = `${{TROVELYA.PROXY_SHARED_SECRET}}`.
3. Ne pas encore déployer : Railway affiche « Apply N changes ». Appliquer, puis attendre que les deux services soient « Active ».
4. Dans Railway, afficher la valeur générée (icône œil) et la copier.
5. Vercel → projet `trovelya` → **Settings** → **Environment Variables** → **Add** : nom `PROXY_SHARED_SECRET`, type **Sensitive**, environnement **Preview** pour la valeur de staging (ou **Production** pour celle de production), coller la valeur.
6. Vérifier : après le redéploiement de Vercel, une requête du site vers `/api/v1/csrf` renvoie 200, et les journaux de limite de débit de l'API montrent des empreintes différentes pour deux réseaux différents.

## Variable associée côté Vercel : `API_INTERNAL_URL` (non secrète)

Adresse vers laquelle le relais envoie les appels, lue seulement par le serveur. Vercel → **Settings** → **Environment Variables**, type **Configuration** :

| Environnement Vercel | Valeur |
|---|---|
| Preview (dont `main`) | `https://trovelya-staging.up.railway.app` |
| Production | `https://trovelya-production.up.railway.app` |

L'ancienne variable `NEXT_PUBLIC_API_URL` n'est plus lue : la supprimer.

## Rotation de `PROXY_SHARED_SECRET`

Le secret doit être le même des deux côtés. Pendant la bascule, les requêtes relayées avec l'ancien secret ne sont plus reconnues : elles restent servies, mais avec l'IP de Vercel (limite de débit partagée pendant quelques minutes, sans coupure).

1. Railway : remplacer la valeur (`${{secret(48)}}`), appliquer.
2. Vercel : remplacer la valeur dans l'environnement correspondant, puis redéployer le dernier déploiement de cet environnement.
3. Faire la vérification de l'étape 6 ci-dessus.

## Rotation de `SECRET_KEY`

1. Railway : remplacer la valeur (`${{secret(64)}}`) du service `TROVELYA`, appliquer ; le worker suit par référence.
2. Les jetons CSRF émis avant la rotation deviennent invalides : le web en redemande un (`apiFetch`).
