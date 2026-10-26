# ADR-0019 — Médias : stockage R2 en juridiction UE, envoi direct, variantes précalculées

**Statut :** Acceptée (décisions Q4 à Q7 et Q14 d'Arcel, écarts E2 à E4, E6 et E11 du plan P2)
**Date :** 26 octobre 2026

## Contexte

Le cahier (11.5, 13.2) prévoit des URL d'envoi présignées, des photos nettoyées (EXIF et GPS retirés, ré-encodage) et des variantes AVIF et WebP en 320, 640, 1080 et 1600 px. Trois contraintes pèsent sur la conception :

- le relais same-origin (ADR-0015) passe par des fonctions Vercel limitées à environ 4,5 Mo par requête, alors qu'une photo peut peser 15 Mo ;
- l'optimisation d'images de Vercel facture chaque transformation, et ce traitement échappe à notre contrôle ;
- les données doivent rester dans l'UE (CLAUDE.md).

## Décision

1. **Stockage : Cloudflare R2, juridiction UE**, avec deux buckets :
   - `originaux`, privé : ce que le navigateur envoie, supprimé après traitement ;
   - `variantes`, public : seulement les images ré-encodées par le worker.

   Le code passe par l'interface `ObjectStorage` (`modules/media/adapters/storage.py`) ; `S3Storage` parle S3, `MemoryStorage` sert aux tests unitaires.
2. **Envoi direct navigateur → R2** par une URL `PUT` présignée de **5 minutes**, pour **un** objet. Son `Content-Type` et sa `Content-Length` font partie de la signature : tout autre fichier est refusé par le stockage lui-même. Le test `test_s3_storage.py` le vérifie contre un vrai serveur S3. R2 n'accepte pas les formulaires `POST` à politique, d'où le `PUT` signé. Le worker revérifie toujours la taille réelle et le type réel.
3. **Clés aléatoires de 128 bits** (32 caractères hexadécimaux), sans nom, identifiant ni donnée personnelle. Une variante publique est une URL de capacité : impossible à deviner ou à énumérer. Elle est supprimée dès le retrait par la modération ou l'effacement du compte.
4. **Variantes précalculées** par le worker (AVIF et WebP × 320/640/1080/1600, sans agrandissement), servies avec `srcset` par un chargeur `next/image` personnalisé ; pas d'optimisation Vercel. Les variantes sont immuables : `Cache-Control: public, max-age=31536000, immutable`.
5. **Diffusion** : `MEDIA_PUBLIC_URL` (domaine `r2.dev` du bucket sur staging, `media.trovelya.com` après l'achat du domaine). Côté CSP, l'hôte d'envoi va dans `connect-src` et `MEDIA_PUBLIC_URL` dans `img-src`.
6. **Vidéos reportées en P5** : `media.kind` accepte `'video'`, sans traitement en P2.
7. **Local et CI : Garage** (logiciel libre européen, Deuxfleurs, compatible S3) au lieu de MinIO, qui ne publie plus d'image Docker libre depuis fin 2025. Composition : `infra/docker-compose.yml` ; préparation : `infra/garage/init.sh` ; tests : conteneur Garage lancé par `tests/integration/media/conftest.py`.

## Conséquences

+ Aucune photo ne transite par Vercel ni par l'API ; une photo de 15 Mo passe.
+ Le stockage refuse de lui-même un fichier plus gros ou d'un autre type que celui déclaré.
+ Pas de coût de transformation à la volée ; les variantes sont en cache longtemps.
− **Cloudflare est une société américaine** (CLOUD Act) : même avec des données stockées dans l'UE, une autorité américaine pourrait en demander l'accès. Écart accepté par Arcel (Q4). Les photos d'annonces sont publiques, ce qui limite l'enjeu ; en revanche, les originaux contiennent des métadonnées jusqu'au traitement, qui les supprime en quelques secondes. À réévaluer avant le lancement public (fournisseur européen : Scaleway, OVHcloud).
− Une URL de variante reste valable tant que l'objet existe : la confidentialité d'une photo retirée repose sur sa suppression immédiate (tâches T02b, T05c et T02c).
− Le navigateur parle à un second hôte : CORS du bucket limité à l'origine du web, réglé à la création des buckets (`infra/r2/README.md`).
