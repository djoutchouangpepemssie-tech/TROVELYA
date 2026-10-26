# Cloudflare R2 — stockage des médias (ADR-0019)

Créé par Arcel avant la tâche P2-T02a2 (envoi des photos). Rien de ce qui suit ne passe par la conversation avec Claude : les clés vont directement dans les variables Railway.

## 1. Buckets (juridiction UE)

Dans le tableau de bord Cloudflare → **R2** → **Create bucket** :

| Bucket | Juridiction | Accès public |
|---|---|---|
| `trovelya-originals` (staging : `trovelya-staging-originals`) | **European Union (EU)** | Aucun |
| `trovelya-variants` (staging : `trovelya-staging-variants`) | **European Union (EU)** | Domaine `r2.dev` activé sur staging ; `media.trovelya.com` en production |

La juridiction se choisit **à la création** et ne se change plus : vérifier « European Union » avant de valider.

## 2. Règles des buckets

- `originals` → **Object lifecycle rules** : supprimer les objets après **1 jour** (envois jamais terminés).
- `originals` → **CORS policy** :

```json
[
  {
    "AllowedOrigins": ["https://<origine du web>"],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["content-type"],
    "MaxAgeSeconds": 3600
  }
]
```

  `<origine du web>` = l'URL Vercel de l'environnement (staging, puis production) ; jamais `*`.
- `variants` : aucune règle CORS nécessaire (images affichées par `<img>`).

## 3. Jeton d'accès (API et worker)

**R2** → **Manage API tokens** → **Create API token** : permission **Object Read & Write**, limitée aux deux buckets de l'environnement. Copier dans Railway (service API **et** worker), sans les afficher ailleurs :

| Variable Railway | Valeur |
|---|---|
| `STORAGE_PROVIDER` | `s3` |
| `STORAGE_ENDPOINT` | `https://<account-id>.eu.r2.cloudflarestorage.com` (point d'accès **eu**) |
| `STORAGE_REGION` | `auto` |
| `STORAGE_ACCESS_KEY_ID` / `STORAGE_SECRET_ACCESS_KEY` | clés du jeton |
| `STORAGE_BUCKET_ORIGINALS` / `STORAGE_BUCKET_VARIANTS` | noms des buckets ci-dessus |
| `MEDIA_PUBLIC_URL` | URL publique du bucket `variants` (`https://pub-….r2.dev` sur staging) |

Côté Vercel : `MEDIA_PUBLIC_URL` (même valeur) et `MEDIA_UPLOAD_ORIGIN` (`https://<account-id>.eu.r2.cloudflarestorage.com`), pour la CSP.
