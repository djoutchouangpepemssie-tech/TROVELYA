# ADR-0020 — Embeddings des annonces

**Statut :** Acceptée (décision Q9 d'Arcel, écart E5 du plan P2)
**Date :** 29 octobre 2026

## Contexte

Les annonces similaires (P2-T10), les comparables de prix (P2-T06) puis la recherche (P3) ont besoin de rapprocher des annonces par leur sens, pas seulement par leurs mots. Le cahier (7.5) prévoit une colonne `embedding VECTOR(768)`. Or la dimension dépend du modèle, et les données doivent rester dans l'UE (CLAUDE.md).

## Décision

1. **Un seul embedding texte par annonce** : titre, description, attributs avec leurs libellés, marque. La légende de la photo principale s'y ajoutera avec l'assistance IA (T06a). Le hachage perceptuel des photos reste séparé.
2. **Modèle d'embeddings d'AWS en région UE**, derrière l'interface `Embedder` (`modules/catalog/adapters/embedder.py`). Il produit 1 024 dimensions, d'où `VECTOR(1024)` (écart E5). L'adaptateur Bedrock arrive quand Arcel ouvre l'accès (Q18). D'ici là :
   - `EMBEDDER=none` par défaut : pas d'embedding, donc pas d'annonces similaires ;
   - `FakeEmbedder`, un sac de mots haché, déterministe, refusé hors `local` et `test`.
3. **Version du modèle** : `embedding_model` est enregistré avec chaque vecteur. Un vecteur dont la dimension ou les valeurs sont invalides n'est jamais enregistré.
4. **Calcul par le worker**, jamais pendant la requête, et seulement avec un embedder configuré :
   - le passage en ligne d'une annonce (`listing.published`) met en file `embed_listing_job` ;
   - le fournisseur est appelé hors de toute transaction, et ne reçoit que le texte d'une annonce en ligne dont le vendeur est montré ;
   - le vecteur n'est enregistré que si, relue avant l'écriture, l'annonce est toujours en ligne avec le même texte ;
   - une panne du fournisseur est retentée (30 s, 2 min, 8 min, 32 min) ; un vecteur invalide (dimension, valeur hors des bornes, vecteur nul) ne l'est pas.
5. **Pas de vecteur hors de la vitrine** : une annonce retirée, expirée, refusée ou vendue perd son vecteur, recalculé à sa remise en ligne.
6. **Ré-indexation** chaque jour à 1 h 40 (`reindex_embeddings_job`). Elle traite les annonces actives sans embedding du modèle courant, par lots de 100, en avançant par identifiant. Elle s'arrête après 5 échecs de suite (fournisseur en panne).
7. **Index HNSW** en distance cosinus, partiel sur les annonces actives qui ont un embedding (migration 0028). Une requête de similarité (P2-T10) doit reprendre ce prédicat en littéraux (`status = 'active' AND embedding IS NOT NULL`), sinon l'index n'est pas utilisé. Elle ne compare que les vecteurs du modèle courant, car deux modèles coexistent pendant une ré-indexation.
8. **Annonces similaires** (P2-T11b, dans la réponse de `GET /v1/listings/{id}`, section 11.5) : jusqu'à 8 annonces en ligne, les plus proches en distance cosinus, du même univers (premier niveau du `path` de la catégorie). Les annonces du même vendeur sont exclues, ainsi que celles d'un vendeur bloqué par le visiteur ou qui n'est plus montré (compte suspendu, en effacement ou profil incomplet). Le vecteur de l'annonce est lu par sous-requête pour que l'index serve au tri. Les filtres s'appliquent pendant le parcours de l'index : `hnsw.iterative_scan = strict_order` (pgvector 0.8), le temps de la transaction, poursuit le parcours jusqu'à 8 résultats, dans l'ordre exact, mais s'arrête après 2 000 vecteurs lus (`hnsw.max_scan_tuples`) : mieux vaut une fiche sans similaires qu'une fiche lente. Deux annonces à égale distance sortent dans un ordre quelconque. Sans embedder, ou pour une annonce pas encore calculée : aucune annonce similaire.

## Conséquences

+ Une panne du fournisseur ne bloque jamais la publication : l'annonce reste en ligne sans embedding, et la tâche ou la ré-indexation la rattrape.
+ Changer de modèle ne demande qu'un nouveau nom de modèle et une ré-indexation, tant que la dimension reste 1 024. Une autre dimension demande une migration de la colonne. À grand volume, la ré-indexation devra être parallélisée ou passer par l'API en lots du fournisseur.
− L'index est créé sans `CONCURRENTLY`, ce qui est acceptable tant que la table est presque vide. Toute reconstruction future devra le faire en `CONCURRENTLY`.
− **AWS est une société américaine** (CLOUD Act), comme pour l'assistance IA (ADR-0021 à venir). Le texte envoyé est celui de l'annonce publiée, donc public. Les coordonnées du titre et de la description y sont déjà masquées par l'anti-contournement ; la marque et les attributs en texte libre ne le sont pas encore.
− Pendant une ré-indexation, l'index mêle les vecteurs des deux modèles : une annonce déjà passée au nouveau modèle peut n'avoir aucun similaire tant que la plupart des vecteurs lus sont de l'ancien (plafond de 2 000). Si cela dure, créer un index partiel par modèle au changement de modèle.
− Chaque remise en ligne recalcule l'embedding, même si le texte n'a pas changé. Le coût est faible ; à revoir si le volume l'exige.
