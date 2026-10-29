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
4. **Calcul par le worker**, jamais pendant la requête. Le passage en ligne d'une annonce (`listing.published`) met en file la tâche `embed_listing_job`. Le fournisseur est appelé hors de toute transaction. Le vecteur n'est enregistré que si l'annonce n'a pas changé entre-temps (`version`) : une annonce modifiée garde l'embedding de son nouveau texte, calculé par son propre événement.
5. **Ré-indexation** chaque jour à 1 h 40 (`reindex_embeddings_job`). Elle traite les annonces actives sans embedding du modèle courant, par lots de 100. Une annonce en échec est journalisée et ne retient pas les autres.
6. **Index HNSW** en distance cosinus, partiel sur les annonces actives qui ont un embedding (migration 0028).

## Conséquences

+ Une panne du fournisseur ne bloque jamais la publication : l'annonce reste en ligne sans embedding, et la tâche ou la ré-indexation la rattrape.
+ Changer de modèle ne demande qu'un nouveau nom de modèle et une nuit de ré-indexation, tant que la dimension reste 1 024. Une autre dimension demande une migration de la colonne.
− **AWS est une société américaine** (CLOUD Act), comme pour l'assistance IA (ADR-0021 à venir). Le texte envoyé est celui de l'annonce publiée, donc public. Les coordonnées y sont déjà masquées par l'anti-contournement.
− Chaque remise en ligne recalcule l'embedding, même si le texte n'a pas changé. Le coût est faible ; à revoir si le volume l'exige.
