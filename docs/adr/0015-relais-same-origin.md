# ADR-0015 — Relais same-origin entre le web et l'API

**Statut :** Acceptée (écarts E1 à E4 du plan P1, décision Q2 d'Arcel)
**Date :** 24 octobre 2026

## Contexte

Le cahier (13.2) prévoit un cookie de session `trv_session` sur `.trovelya.com`, partagé par `trovelya.com` et `api.trovelya.com`. Le domaine ne sera acheté qu'à la fin du projet : le web est sur `*.vercel.app` et l'API sur `*.up.railway.app`, deux suffixes publics, donc deux sites. Un cookie posé par l'API serait un cookie tiers, refusé par les navigateurs.

Derrière un intermédiaire, l'API ne voit plus l'adresse du visiteur, dont dépendent les limites de débit (11.4). Jusqu'ici uvicorn croyait tout `X-Forwarded-For` (`--forwarded-allow-ips='*'`), qu'un client peut remplir à sa guise.

## Décision

1. **Le navigateur ne parle qu'à l'origine du web.** La route `apps/web/app/api/[...path]/route.ts` relaie `/api/v1/*` vers `API_INTERNAL_URL/v1/*` (logique dans `apps/web/lib/relay.ts`). Elle ne transmet qu'une liste blanche d'en-têtes et nos seuls cookies `__Host-trv_*`. Elle relaie la réponse telle quelle, `Set-Cookie` et redirections compris, sans cache. Elle refuse les corps de plus de 1 Mo et renvoie `502` au format problem+json si l'API ne répond pas.
2. **Cookies `__Host-`** (`__Host-trv_session`, `__Host-trv_csrf`) : `Secure`, `Path=/`, aucun `Domain`. Ils sont liés à l'hôte du web. Le jour de `trovelya.com`, le relais reste en place et aucun code ne change.
3. **IP et pays de confiance.** Le relais ajoute `x-trv-client-ip` (lu dans `x-real-ip`, que Vercel réécrit), `x-trv-client-country` (`x-vercel-ip-country`) et `x-trv-proxy-secret` (`PROXY_SHARED_SECRET`, au moins 32 caractères). L'API (`core/client_ip.py`) ne croit ces en-têtes que si le secret correspond (comparaison à temps constant). Sinon elle prend `X-Real-IP`, que le proxy de Railway réécrit, puis le pair TCP. Elle ne croit jamais `X-Forwarded-For`, et uvicorn tourne sans `--proxy-headers`.
4. **CSP** : `connect-src 'self'` (+ Sentry). L'adresse de l'API n'est plus publique : `NEXT_PUBLIC_API_URL` est remplacée par `API_INTERNAL_URL`, côté serveur seulement.
5. **Temps réel (P6), non construit ici.** Vercel ne relaie pas les WebSocket et un cookie `__Host-` ne part pas vers une autre origine. Le navigateur obtiendra, par le relais, un ticket à usage unique et de courte durée, qu'il présentera à l'API temps réel à l'ouverture de la connexion.

## Conséquences

+ Le cookie de session fonctionne aujourd'hui, sans domaine, et ne change pas avec `trovelya.com`.
+ L'adresse de l'API n'est plus exposée au navigateur, et la CSP se resserre.
+ Une IP falsifiée ne contourne plus les limites de débit.
− Chaque appel passe par une fonction Vercel (latence de quelques millisecondes, coût d'exécution).
− Un secret de plus à faire tourner (`docs/runbooks/secrets.md`), identique côté Vercel et côté Railway.
− Les appels directs à l'API (application mobile en P21, intégrations) n'ont ni cookie ni IP relayée : ils utiliseront des jetons et l'IP vue par Railway.
