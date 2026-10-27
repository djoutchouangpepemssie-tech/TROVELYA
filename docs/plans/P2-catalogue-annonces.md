# P2 — Catalogue et annonces : plan d'implémentation

> **Pour les agents qui exécutent ce plan :** skill obligatoire `subagent-driven-development` (recommandé) ou `executing-plans`, tâche par tâche. Les étapes utilisent des cases à cocher (`- [ ]`).
> Statut : **validé par Arcel le 26 octobre 2026** (écart E13 et ordre modifié T11 → T06a → T10 compris).

**Objectif :** un membre majeur au profil complété photographie un objet sur son téléphone et publie une annonce en moins de 60 secondes. L'IA propose le titre, la catégorie, la marque, l'état, les attributs et une fourchette de prix ; le vendeur valide. La modération bloque les interdits et masque les coordonnées. Les photos sont nettoyées (EXIF et GPS retirés) avant d'être servies. La fiche publique est rapide (LCP < 2,5 s sur mobile), bien référencée, et ne révèle jamais la position exacte du vendeur.

**Architecture :** trois modules nouveaux et un module rempli (monolithe modulaire, 5.4) :
- `catalog` : catégories, attributs, marques, annonces, favoris, suivis de prix, historique des prix, machine à états, score de qualité, file de modération minimale ;
- `media` : téléversement direct du navigateur vers le stockage par URL présignée, traitement par le worker (variantes, empreintes) ;
- `circumvention` : détection des coordonnées dans un texte (première version, texte seulement ; complété en P6) ;
- `ai` : adaptateurs `AIProvider` (assistance à la publication), `ImageClassifier` (modération des images) et `Embedder` (embeddings), avec des implémentations factices déterministes.

Stockage objet Cloudflare R2 en juridiction UE (MinIO en local et en CI), deux buckets (originaux privés, variantes publiques) ; IA par Claude sur AWS Bedrock en région UE.

**Pile ajoutée :** côté API, `Pillow` (décodage et ré-encodage, AVIF et WebP compris), `h3` (cellules H3 en Python, pour les tests et le calcul hors base), `boto3` (S3 compatible R2 et MinIO, et Bedrock), `PyYAML` (graine). Côté web, aucune dépendance nouvelle prévue. Chaque ajout passe la revue `supply-chain-risk-auditor` dans la PR qui l'introduit.

**Spécification :** `docs/CAHIER_DES_CHARGES.md` sections 0, 1.3, 2, 5.4, 5.6, 5.9, 6.2 à 6.4 (W03, W09, W10), 7.1, 7.5, 7.10 (`circumvention_detections`), 8.11, 8.16, 8.17, 8.19, 9.1, 11.1 à 11.5, 13.2, 13.3, 14.1, 14.3, 16.1, 16.2 (parcours 2), 16.6, 17.3. Modèle de menaces : `docs/security/threat-model.md` (section P2). Règles : `CLAUDE.md`, contraintes globales de `docs/plans/P0-fondations.md` et `docs/plans/P1-identite-comptes.md`.

---

## 0. Décisions prises

### 0.1 Réponses d'Arcel (25 octobre 2026 : « je valide toutes tes questions et recommandations » ; 26 octobre 2026 : « je te laisse valider et trouver ce qui est mieux », puis « je valide » pour Q19 à Q21)

| # | Question | Décision |
|---|---|---|
| Q1 | Qui peut publier en P2 | Tout membre au **profil complété**, d'**âge ≥ 18 ans** (règle stricte E14 de P1), non suspendu et sans effacement en cours ; **50 publications par jour** [PARAM `listings.max_publications_per_day`]. Politique `can_publish_listing` dans `catalog/policies.py`. En P4, publier exigera l'activation vendeur ; les annonces déjà en ligne de membres non activés restent visibles, sans bouton d'achat, jusqu'à l'activation. |
| Q2 | Arbre des catégories | Graine `modules/catalog/seed/categories.yaml` validée : 430 catégories, 334 feuilles, 63 attributs. Clés `univers.niveau2.niveau3` (chemin ltree), libellés `fr` seulement (`names` JSONB extensible), attributs communs hérités, attributs spécifiques sur les feuilles, verticales sans attributs spécialisés jusqu'à P9. Arbitrages du 26/10 : pianos en main propre seulement ; sièges auto toujours vérifiés par un humain ; plafond « contact au-delà du plafond » du matériel pro non chiffré → achat protégé partout en P2, plafond fixé en P4 avec le paiement. |
| Q3 | Marques | Saisie libre avec autocomplétion ; une marque inconnue est créée non vérifiée (`is_verified = false`, doublons évités par `CITEXT`) ; graine de quelques centaines de marques courantes (`seed/brands.yaml`). |
| Q4 | Stockage | **Cloudflare R2, juridiction UE**, deux buckets : `originaux` (privé) et `variantes` (public). Arcel crée le compte avant T02a ; d'ici là, MinIO. Écart « société américaine » documenté dans l'ADR-0019. |
| Q5 | Envoi des photos | **Direct navigateur → R2** par URL `PUT` présignée de 5 minutes. Le worker vérifie la signature du fichier, retire EXIF et GPS, ré-encode, calcule les empreintes, écrit les variantes et supprime l'original. |
| Q6 | Diffusion | Variantes publiques à **clés aléatoires de 128 bits** (URL de capacité) ; supprimées du stockage dès le retrait par la modération ou l'effacement du compte. Variantes précalculées et chargeur `next/image` personnalisé (pas d'optimisation Vercel : coût et résidence UE). |
| Q7 | Vidéos | **Pas en P2** : images seulement ; vidéos en P5 (avec la vidéo de vérification). |
| Q8 | IA | **Claude sur AWS Bedrock, région UE** (Francfort ou Paris, profil d'inférence UE) derrière `AIProvider` ; plafond **2 centimes par suggestion** et **20 suggestions par jour et par compte** [PARAM] ; fourchette de prix seulement avec **au moins 5 annonces comparables actives** de la même catégorie. Arcel ouvre l'accès Bedrock avant T06b ; d'ici là, adaptateur factice. |
| Q9 | Embeddings | Un seul embedding texte par annonce (titre, description, attributs, légende de la photo principale) ; modèle d'embeddings d'AWS dans la même région UE ; dimension fixée par le modèle (`VECTOR(1024)`, écart E5) ; colonne `embedding_model` et job de ré-indexation ; le hachage perceptuel reste séparé. |
| Q10 | Classification d'images | Même fournisseur (Claude vision sur Bedrock UE) derrière `ImageClassifier` ; évaluer Sightengine (société française) avant le lancement public. |
| Q11 | Interdits et seuils | Liste de 8.17 en [PARAM `catalog.prohibited`] ; **alcool interdit à tous** (D10) ; militaria et billetterie `is_restricted` (toujours revue humaine) ; seuils : **≥ 0,9 refus automatique**, **0,5 à 0,9 revue**, **< 0,5 publication** [PARAM] ; motif lisible pour le vendeur. |
| Q12 | Coordonnées détectées | Passage **masqué** et annonce publiée, rappel pédagogique au vendeur, détection journalisée, original conservé **chiffré**. |
| Q13 | Effacement d'un compte | Pendant la grâce de 30 jours : annonces masquées. À l'effacement : annonces supprimées et médias effacés du stockage. Médias supprimés purgés après **30 jours** [PARAM `retention.deleted_media_days`]. |
| Q14 | Photos | **12 au plus** pour les objets (30 pour l'immobilier et les véhicules, P9), **au moins 1** pour publier. |
| Q15 | Expiration | **120 jours** [PARAM `listings.expiry_days`] après la dernière publication, le dernier renouvellement ou la dernière modification. |
| Q16 | File de revue | Page staff minimale `/fr/staff/moderation`, permission nouvelle `moderation.review`, chaque décision auditée. La Tour de contrôle complète arrive en P8. |
| Q17 | Distance sur la fiche | Seulement pour un visiteur connecté qui a une zone ; sinon `place_name` seul. |
| Q18 | Comptes externes | Arcel fournit R2 avant T02a et Bedrock avant T06b ; d'ici là, MinIO et adaptateurs factices. |
| Q19 | Conservation des annonces terminées (section 14.1 muette) | Paramètres en jours, purge quotidienne livrée avec T04 : supprimée par le vendeur → effacée après **30 jours** [PARAM `retention.deleted_listing_days`] ; retirée ou expirée → effacée après **365 jours** sans republication [PARAM `retention.ended_listing_days`] ; vendue → contenu (description, attributs, photos, position) effacé après **365 jours** [PARAM `retention.sold_listing_days`], fiche minimale (titre, prix, date de vente) gardée tant qu'une commande y renvoie (P4) ; retirée par la modération → effacée après **180 jours** [PARAM `retention.removed_listing_days`], délai de contestation du DSA (article 20) ; effacement du compte : immédiat, inchangé (Q13). |
| Q20 | Décalage public partagé | **Un décalage par source de position** (adresse ou zone du vendeur), tiré une fois, partagé par toutes les annonces de cette source, retiré au sort si la source change ; jamais un décalage par annonce (la moyenne de N annonces approcherait la position réelle d'environ 350/√N m). |
| Q21 | Bornes des attributs entiers et années | `int` et `year` bornés à l'entier signé 32 bits ; `year` borné en plus à **l'année courante + 1** (millésimes vendus d'avance), calculée par l'horloge au moment de la validation ; le minimum reste celui de la graine. |

### 0.2 Écarts et précisions par rapport au cahier

| # | Point du cahier | Problème | Décision | ADR |
|---|---|---|---|---|
| E1 | 3.2 `listing.publish` réservé aux vendeurs | L'activation vendeur arrive en P4. | Q1 : politique `can_publish_listing` (profil complété, âge ≥ 18, non suspendu, pas d'effacement en cours). La permission `listing.publish` sera exigée en plus à partir de P4. | — |
| E2 | 11.5 `POST /media/uploads` | Le relais same-origin (ADR-0015) passe par des fonctions Vercel limitées à environ 4,5 Mo par requête : une photo de 15 Mo ne passe pas. R2 n'accepte pas les formulaires `POST` à politique (taille bornée). | Envoi direct navigateur → R2 par URL `PUT` présignée de 5 min, `Content-Type` et `Content-Length` signés ; taille réelle revérifiée par le worker ; CORS du bucket limité à l'origine du web ; `connect-src` élargi au seul hôte de R2. | 0019 |
| E3 | 6.x `next/image` | L'optimisation d'images de Vercel facture chaque transformation et traite hors de notre contrôle. | Variantes précalculées (AVIF et WebP en 320, 640, 1080 et 1600 px) servies avec `srcset` par un chargeur `next/image` personnalisé. | 0019 |
| E4 | 13.2 CSP `img-src` | Les images viennent d'un autre hôte. | `MEDIA_PUBLIC_URL` (r2.dev sur staging, `media.trovelya.com` après l'achat du domaine) ajouté à `img-src` ; l'hôte d'envoi ajouté à `connect-src`. | 0019 |
| E5 | 7.5 `embedding VECTOR(768)` | La dimension dépend du modèle ; le modèle d'embeddings d'AWS retenu produit 1024 dimensions. | `VECTOR(1024)` + colonne `embedding_model TEXT` ; changer de modèle = migration de la colonne + job de ré-indexation. | 0020 |
| E6 | 17.3 P2-T02 « vidéos (transcodage HLS) » | Q7. | Vidéos reportées en P5 ; `media.kind` garde `'video'` dans son `CHECK`, sans traitement. | 0019 |
| E7 | 7.10 `circumvention_detections` (P6) | P2 détecte déjà les coordonnées dans les annonces. | Table créée en P2 (`source_type = 'listing'` seulement), colonnes de 7.10 ; `circumvention_rules` et les sanctions restent en P6 (règles en [PARAM] d'ici là). | — |
| E8 | 7.11 `moderation_decisions` (P8) | Les décisions de P2 doivent être tracées sans construire la Tour de contrôle. | Table `listing_status_history` (chaque transition : acteur, motif, horodatage) + journal d'audit pour les décisions staff ; `moderation_decisions` naît en P8 et reprendra l'historique. | — |
| E9 | 3.2 permissions | Aucune permission de revue des annonces. | Permission `moderation.review` ajoutée à la graine, accordée à `staff_moderator`, `staff_trust`, `staff_admin`, `staff_superadmin` (comme `listing.remove_any`). | — |
| E10 | 6.4 W03 `/annonce/[slug]-[id]` | Un UUID complet rend l'URL longue et peu lisible. | Colonne `short_id` : 10 caractères base 62 aléatoires (≈ 59 bits), unique ; URL `/fr/annonce/[slug]-[short_id]` ; un slug faux redirige (308) vers le bon. | — |
| E11 | 7.5 `media` | Les variantes et leurs clés ne sont pas modélisées. | `media.variants JSONB` (`[{format, width, height, key, bytes}]`) ; `storage_key` = clé aléatoire de l'original (supprimé après traitement). | 0019 |
| E12 | 9.1 « 120 jours sans modification » | La date de départ n'est pas dite. | Q15 : `expires_at = max(published_at, renouvellement, dernière modification) + listings.expiry_days`. | — |
| E13 | 8.11 « distance calculée sur la position réelle puis arrondie » | Un visiteur peut créer plusieurs zones (aucune limite en P1) et trilatérer la position réelle d'un vendeur à quelques centaines de mètres près avec des distances arrondies au kilomètre. | **Validé par Arcel le 26/10/2026** : calculer la distance affichée sur `location_public` (décalée de 200 à 500 m) puis l'arrondir. Le décalage étant plus petit que l'arrondi, l'affichage ne change pas pour le visiteur, et la trilatération ne trouve plus que la position publique. Le filtrage par rayon (P3) reste sur la position réelle. | — |
| E14 | 7.5 `listings` | Le statut et ses transitions ne gardent pas trace de la source de la position. | Colonnes `location_source TEXT CHECK (IN ('address','zone'))` et `location_source_id UUID` (adresse ou zone du vendeur). Changer de source tire un nouveau décalage ; relire n'en tire jamais. | — |
| E15 | 7.5 `listings` | La légende de la photo (pour l'embedding) et la raison de refus n'ont pas de colonne. | `media.moderation` garde la légende et les étiquettes de classification ; `listing_status_history.reason_code` + `reason_text` gardent les motifs. | — |
| E16 | 11.5 rattachement des photos | Aucune route ne dit comment attacher des photos à une annonce. | Champ `media_ids` (liste ordonnée, 1 à 12) dans `POST` et `PATCH /listings` ; aucune route nouvelle. | — |
| E17 | 7.5 `listings` | Les contrôles de valeurs ne sont pas tous écrits. | Seulement des formats et des bornes déjà dans le cahier : code pays et devise, modes de vente de la section 4, compteurs et score 0-100, montants `>= 0` (7.1). Aucune règle entre colonnes (offre minimale et prix, statut et dates, remise et livraison) : la machine à états (T04) et le service (T03b) les portent. `version` et `updated_at` ne suivent que le contenu de l'annonce (ni compteurs, ni score, ni données de recherche). | — |
| E18 | 8.11 position publique, Q20 | Un décalage par source laisserait plusieurs tirages autour d'un même domicile (une adresse et une zone au même endroit, une zone supprimée puis recréée, une adresse ressaisie au mètre près) : leur moyenne approcherait l'adresse (revue de T03b2a). | Le décalage est tiré une fois par **lieu** du vendeur : une source à moins de 50 m d'un lieu déjà utilisé par ce vendeur reprend son décalage (translaté), sous un verrou par vendeur ; au-delà, nouveau tirage gardé. Table `listing_public_positions` (migration 0014). Le nom public d'une zone ou d'une ville doit être un simple nom de lieu (lettres, espaces, traits d'union, apostrophes, numéro d'arrondissement) : sinon, zone refusée et adresse nommée par son code postal. |
| E19 | Q3 marques saisies librement | Une marque inconnue créée « non vérifiée » par un simple brouillon apparaîtrait aussitôt dans l'autocomplétion publique (`GET /v1/brands`) : texte libre non modéré (coordonnées, injures), rattaché à personne pour le RGPD ; et un nom sans lettre latine (grec, cyrillique) n'avait pas de slug (revue de T03b2b). | Colonnes `brands.origin` (`seed` ou `member`) et `brands.created_by` (migration 0015). Une marque de membre n'est suggérée qu'une fois portée par une annonce active (modérée) ; elle est exportée avec le membre et, à l'effacement, supprimée si aucune annonce ne la porte, sinon détachée. Slug d'un nom sans lettre latine : `b-` et 16 caractères de l'empreinte SHA-256 du nom en minuscules. |

### 0.3 ADR produits par cette phase

- **ADR-0019** : médias (R2 juridiction UE, envoi direct par `PUT` présigné, deux buckets, variantes précalculées et chargeur `next/image`, clés de capacité, vidéos reportées, écart « société américaine »).
- **ADR-0020** : embeddings (modèle AWS en région UE, `VECTOR(1024)`, colonne de version, ré-indexation, HNSW).
- **ADR-0021** : fournisseur d'IA (Claude sur Bedrock UE pour l'assistance et la classification des images, plafonds, journalisation des coûts, écart « société américaine », Sightengine à évaluer).

Chaque ADR est écrit dans la PR de la tâche qui prend la décision (T02a, T11, T06b).

---

## 1. Contraintes globales

Celles de P0 et de P1 s'appliquent toutes :
- identifiants UUIDv7, `Clock` injectée, `country_code`, migrations réversibles ;
- un service ne commite jamais ;
- PR ≤ 600 lignes hors fichiers générés et hors graines ;
- commits conventionnels en français ;
- textes dans `messages/fr.json` ;
- toute nouvelle donnée personnelle dans `docs/data/PII.md` dans la même PR ;
- chaque route déclarée dans `test_access_matrix.py` ;
- toute action staff dans `record_audit`.

En plus :

- **Montants** : `price_minor` en centimes entiers, `CHECK (price_minor BETWEEN 100 AND 100000000)` ; coûts d'IA en micro-euros entiers (`cost_microeur`).
- **Position** : l'API ne renvoie jamais `location`, `location_public`, `h3_r7`, `h3_r9` ni aucune coordonnée en P2. Seuls `place_name` et `distance` (texte arrondi, E13) sortent. Un test parcourt toutes les réponses du catalogue et échoue s'il y trouve un nombre à virgule ressemblant à une coordonnée.
- **Réponses d'accès** : annonce non active ou média non publié d'autrui → `404 not_found` ; publication refusée par la politique → `403 publish_forbidden` (avec la raison : `profile_incomplete`, `too_young`, `account_restricted`) ; quota atteint → `429 publication_limit`.
- **Nouveaux codes d'erreur** (`ErrorCode`, traduits dans `fr.json`) : `publish_forbidden`, `publication_limit`, `invalid_transition`, `invalid_attributes`, `category_not_leaf`, `category_inactive`, `condition_not_allowed`, `media_not_ready`, `media_limit`, `media_type_rejected`, `media_too_large`, `upload_limit`, `ai_limit`, `ai_unavailable`, `precondition_failed` (412, If-Match), `precondition_required` (428).
- **Flags** (`FlagService`) : `verticals` (immobilier, véhicules, services ; désactivé jusqu'à P9), `ai.assist` (assistance IA), `ai.image_classification`.
- **[PARAM]** (`platform_settings`, graine dans la migration de la tâche qui les lit) :
  - `listings.expiry_days` = 120 ;
  - `listings.max_publications_per_day` = 50 ;
  - `listings.max_photos_by_vertical` = `{"goods":12,"real_estate":30,"vehicles":30,"services":12}` ;
  - `catalog.prohibited` (liste 8.17, mots et expressions par motif) ;
  - `moderation.thresholds` = `{"refuse":0.9,"review":0.5}` ;
  - `circumvention.payment_keywords` ;
  - `ai.max_suggestions_per_day` = 20, `ai.max_cost_microeur` = 20000, `ai.min_comparables` = 5 ;
  - `media.max_image_bytes` = 15728640, `media.uploads_per_hour` = 30, `media.uploads_per_day` = 200 ;
  - `retention.deleted_media_days` = 30.
- **Choix de l'auteur du plan, à confirmer** (garde-fous techniques sans règle métier dans le cahier) : 30 téléversements par heure et 200 par jour par compte ; 50 mégapixels au plus par image ; médias jamais attachés supprimés après 24 h ; 3 tentatives par traitement d'image puis média `rejected`.
- **Machine à états** : une seule fonction `transition(listing, event, actor, reason)` dans `catalog/service/states.py`, qui consulte la table de 9.1, écrit `listing_status_history`, émet l'événement outbox dans la même transaction et lève `InvalidTransition` sinon. Aucun autre code n'écrit `listings.status`.
- **Événements outbox** : `listing.published`, `listing.updated`, `listing.withdrawn`, `listing.expired`, `listing.removed`, `listing.renewed`, `media.ready` ; charge utile sans donnée personnelle (identifiants seulement).
- **Adaptateurs** derrière un `Protocol` avec une implémentation factice déterministe : `ObjectStorage` (`S3Storage` pour R2 et MinIO), `AIProvider`, `ImageClassifier`, `Embedder`, `Geocoder` (existant). Les implémentations réelles sont choisies par la configuration ; les tests n'appellent jamais Internet.
- **Aucune donnée personnelle** dans les clés de stockage, les URL de médias, les noms de fichiers, les clés Redis, les journaux ni les traces ; le nom d'origine d'un fichier n'est jamais conservé.
- **Rien d'une phase ultérieure** : `shop_id`, `product_variant_id`, `passport_id`, `resale_from_order_item_id`, `is_boosted_until`, `open_to_swap`, `original_price_minor`, `search_document` restent nuls ou inactifs ; aucune route de recherche, de carte ni de feed.

## 2. Points d'attention de la revue (couverts par un test)

1. **Graine rejouée après un renommage ou un déplacement** : aucune annonce ne perd sa catégorie, aucune catégorie n'est supprimée ni dupliquée. → `test_seed_idempotent`, `test_seed_rename_keeps_listings`, `test_seed_move_recomputes_path` (T01b).
2. **Clés d'univers divergentes** entre la graine et les préférences de P1. → `test_universe_keys_single_source`, `test_seed_roots_equal_universe_keys` (T01a, T01b).
3. **Fichier piégé** (script renommé `.jpg`, SVG, polyglotte JPEG + ZIP, bombe de décompression, image de 20 000 × 20 000) : refusé, rien de servi. → `test_rejects_spoofed_type`, `test_rejects_svg`, `test_rejects_decompression_bomb`, `test_polyglot_reencoded_without_trailing_bytes` (T02b).
4. **EXIF et GPS** : une photo de téléphone avec position ressort sans aucune métadonnée, dans toutes les variantes. → `test_variants_have_no_metadata` (T02b).
5. **Triangulation** : 1 000 lectures de la fiche renvoient la même réponse ; aucune coordonnée dans aucune réponse ; trilatération depuis trois zones impossible au-delà de la position publique. → `test_public_position_stable_over_1000_reads`, `test_no_coordinates_in_any_catalog_response`, `test_distance_uses_public_position` (T03b, T10).
6. **Arrondis de distance** à chaque seuil de 8.11. → `test_round_distance` paramétré : 0, 999, 1000, 1499, 1500, 9499, 9500, 9999, 10000, 12499, 12500, 99999, 100000, 104999, 105000 m (T03b).
7. **Transitions** : toutes celles de 9.1 passent, toutes les autres lèvent `InvalidTransition`, chacune écrit l'historique et l'événement. → `test_transition_table_exhaustive` (produit cartésien statuts × événements) (T04).
8. **Double clic sur « Publier »** et deux publications concurrentes : une seule transition, un seul événement, un seul décompte du quota. → `test_concurrent_publish_single_transition` (T04).
9. **IDOR** sur un brouillon, une annonce en revue, refusée ou retirée, un média non publié : tiers → 404. → matrice d'accès étendue (T03b, T12).
10. **L'IA invente une catégorie ou un prix** : la sortie est rejetée ou nettoyée ; pas de prix sans 5 comparables. → `test_assist_rejects_unknown_category`, `test_assist_no_price_without_comparables` (T06a).
11. **Panne du classifieur d'images** : l'annonce passe en revue humaine, jamais en ligne sans contrôle. → `test_classifier_outage_goes_to_review` (T05b).
12. **Coordonnées obfusquées** (« zéro six douze… », « 0 6 1 2 3 4 5 6 7 8 », « jean [at] gmail point com ») : masquées. → `test_detects_obfuscated_contacts` paramétré (T05a).

---

## 2 bis. Architecture des médias (ADR-0019)

```
navigateur ──POST /api/v1/media/uploads {purpose, mime, bytes}──▶ relais ──▶ API
   API : quota, type déclaré dans la liste blanche, taille ≤ 15 Mo → ligne media 'uploading'
         clé aléatoire originaux/<128 bits> ; URL PUT signée 5 min (Content-Type, Content-Length)
navigateur ──PUT (octets de la photo)──▶ R2 bucket « originaux » (CORS : origine du web seulement)
navigateur ──POST /api/v1/media/{id}/complete──▶ API → 'processing' → tâche arq process_media
worker : HEAD (taille réelle) → GET → signature → décodage Pillow (≤ 50 Mpx) → orientation EXIF appliquée
         → ré-encodage sans métadonnées → AVIF + WebP × 320/640/1080/1600 → bucket « variantes »
         (clés aléatoires) → SHA-256 de l'original + dHash 64 bits → suppression de l'original
         → 'ready' (ou 'rejected' avec motif) → événement media.ready
web : <Image loader={mediaLoader}> → srcset des variantes WebP/AVIF (MEDIA_PUBLIC_URL)
```

Règle de cycle de vie R2 sur « originaux » : suppression après 24 h (originaux jamais complétés). En local et en CI, MinIO fournit les deux buckets ; `apps/web/tests/e2e/stack.sh` et `tests/e2e-full/stack.sh` démarrent MinIO.

## 3. Structure des fichiers

```
apps/api/src/trovelya/
├── modules/catalog/
│   ├── universes.py (source unique des 16 clés, sans import lourd) · seed/{categories,brands}.yaml
│   ├── api/ (categories.py, listings.py, favorites.py, staff.py)   schemas.py   models.py
│   ├── repository.py   policies.py   events.py   tasks.py (expiration, embeddings, ré-indexation)
│   ├── service/ (__init__.py, categories.py, seed.py, listings.py, attributes.py, positions.py,
│   │   states.py, publishing.py, moderation.py, quality.py, favorites.py, prices.py,
│   │   similar.py, gdpr.py)
│   └── migrations/versions/ (0007_catalog_taxonomy, 0009_catalog_listings,
│       0010_catalog_moderation, 0012_catalog_ai) ; 0008_media est dans le module media
├── modules/media/
│   ├── api.py   schemas.py   models.py   repository.py   policies.py   tasks.py
│   ├── service/ (__init__.py, uploads.py, processing.py, images.py (signature, ré-encodage,
│   │   dHash), gdpr.py)
│   ├── adapters/storage.py (ObjectStorage, S3Storage, MemoryStorage)
│   └── migrations/versions/0008_media.py
├── modules/circumvention/
│   ├── service.py (detect, mask)   normalize.py   rules.py   models.py   repository.py
│   └── migrations/versions/0011_circumvention_detections.py
├── modules/ai/
│   ├── service.py   schemas.py (schéma JSON de la suggestion)   models.py   repository.py
│   ├── adapters/ (provider.py : AIProvider, FakeAIProvider, BedrockAIProvider ;
│   │   classifier.py : ImageClassifier, FakeImageClassifier, BedrockImageClassifier ;
│   │   embedder.py : Embedder, FakeEmbedder, BedrockEmbedder)
│   └── migrations/ (tables dans 0012 via catalog : voir T06a)
├── modules/identity/ (universes.py lit catalog.universes ; avatar_media_id via media.service)
└── scripts/seed_catalog.py · scripts/seed_demo.py (refusé si ENV=production)
apps/api/tests/{unit,integration}/{catalog,media,circumvention,ai}/
apps/web/
├── app/[locale]/vendre/page.tsx (+ composants SellFlow, PhotoPicker, SuggestionFields)
├── app/[locale]/compte/annonces/page.tsx
├── app/[locale]/annonce/[slug]/page.tsx (+ opengraph-image.tsx, Gallery, PriceHistory, Similar)
├── app/[locale]/staff/moderation/page.tsx
├── app/[locale]/compte/parametres/ (avatar)
├── lib/media.ts (chargeur next/image, envoi PUT avec progression), lib/csp.ts (MEDIA_PUBLIC_URL)
└── tests/e2e/{vendre,annonces,fiche,moderation}.spec.ts, tests/e2e-full/parcours-2.spec.ts
docs/adr/0019…0021, docs/data/PII.md, docs/GLOSSARY.md, docs/HANDOFF.md, infra/r2/README.md
```

Migrations numérotées dans l'ordre d'exécution (0007 taxonomie, 0008 médias, 0009 annonces qui référencent les médias, 0010 modération, 0011 anti-contournement, 0012 IA) ; une migration écrite en parallèle se renumérote avant sa fusion.

Contrats import-linter : un contrat `module-media`, `module-circumvention` et `module-ai` ; chaque module nouveau ajouté aux `source_modules` des contrats existants (`tests/architecture` échoue sinon). `identity` importe `trovelya.modules.catalog.universes` (module sans dépendance, autorisé par les contrats) et `trovelya.modules.media.service`.

## 4. Dépendances et parallélisme

```
T01a ── T01b ──────────────────────────────┐
T02a ── T02b ── T02c (avatar, RGPD médias)  │
T01b + T02b ── T03a ── T03b ── T04 ─┬─ T05a ── T05b ── T05c
                                    ├─ T07
                                    ├─ T08
                                    └─ T11 (embeddings) ── T06a (comparables) ── T06b (Bedrock)
T04 + T05b + T06a + T07 ── T09a (W09) ── T09b (W10)
T08 + T11 ── T10 (W03)
tout ── T12 (parcours 2, démo, porte)
```

- T02a peut commencer en parallèle de T01a (aucune dépendance).
- T05a, T07, T08 et T11 sont parallélisables après T04.
- **Ordre modifié par rapport à 17.3, validé par Arcel le 26/10/2026** : T11 (embeddings) passe avant T06a et T10, parce que les comparables de prix (T06) et les similaires (T10) en dépendent. Aucune tâche n'est retirée.
- Les écrans se testent en e2e avec les routes de test existantes (`POST /v1/_test/session`) et une nouvelle route de test `POST /v1/_test/process-media` (traitement synchrone, montée seulement en `local` et `test`).

---

## 5. Tâches

### P2-T01a — Tables de la taxonomie et source unique des univers

**Branche :** `feat/P2-T01a-taxonomie`.

**Fichiers :**
- `modules/catalog/{__init__,models,universes}.py` ;
- `modules/catalog/migrations/versions/0007_catalog_taxonomy.py` ;
- `alembic.ini` (`version_locations` + catalog) ;
- `modules/identity/universes.py` (réexporte `catalog.universes.UNIVERSE_KEYS`) ;
- `.importlinter` ;
- `tests/integration/catalog/test_taxonomy_schema.py`, `tests/unit/catalog/test_universes.py`.

**Contenu :**
- Tables `categories`, `attribute_definitions`, `category_attributes`, `brands`, exactement comme 7.5, plus :
  - `categories.allowed_conditions item_condition[]` (états autorisés, `NULL` = tous) ;
  - `categories.brand_policy TEXT CHECK (IN ('required','optional','none'))` ;
  - `attribute_definitions.constraints JSONB` (min, max, step, max_length).
- Types `listing_status` et `item_condition` (7.5).
- La `key` identifie une catégorie pour toujours ; le `path` (ltree) dit où elle se trouve. Une catégorie nouvelle a pour chemin sa clé ; une catégorie déplacée garde sa clé et prend un chemin sous son nouveau parent (seul le dernier libellé est commun).
- Cohérence de l'arbre garantie par la base : chemin = chemin du parent + libellé (déclencheur de contrainte vérifié à la validation de la transaction) ; changer le chemin d'une catégorie déplace tout son sous-arbre (déclencheur, enfants trouvés par `parent_id`) ; chemins uniques, catégories inactives comprises (contrainte vérifiée à la validation, pour permettre les échanges).
- `names` exige `fr` ; `enum_values` est une liste ordonnée (`[{"key": "noir", "names": {"fr": "Noir"}}]`, un objet JSONB ne garde pas l'ordre) ; `enum_values` réservé au type `enum` ; formats de clés contrôlés ; `category_attributes` sans suppression en cascade.
- Index `categories_path_gist`, `categories (parent_id)`, `brands` trigram sur `name::text` (autocomplétion par `name::text ILIKE`).
- Contrat import-linter : `catalog.universes` n'importe rien de l'application.
- `catalog/universes.py` devient la **seule** liste des 16 clés ; `identity/universes.py` la réexporte, sans changer le comportement des préférences de P1.

- [ ] Tests d'abord :
  - `test_upgrade_downgrade_upgrade` (étendu) ;
  - `test_category_key_unique`, `test_path_is_ltree` ;
  - `test_vertical_check` (`'goods'` accepté, `'cars'` refusé) ;
  - `test_brand_name_citext_unique` (`Apple` puis `apple` → violation) ;
  - `test_universe_keys_single_source` (`identity.universes.UNIVERSE_KEYS is catalog.universes.UNIVERSE_KEYS`) ;
  - `test_preferences_still_accept_universe_keys` (régression P1).
- [ ] `uv run pytest tests/unit/catalog tests/integration/catalog tests/integration/test_migrations.py` → ÉCHEC.
- [ ] Migration, modèles, contrats. → vert ; `uv run lint-imports` → contrats respectés.
- [ ] Commit `feat(catalogue): tables de la taxonomie et source unique des univers`.

**Terminé quand :** migration réversible, contrats verts, préférences de P1 inchangées.

### P2-T01b — Graine de l'arbre, marques et `GET /v1/categories`

**Branche :** `feat/P2-T01b-graine-categories`.

**Fichiers :**
- `seed/categories.yaml` (validé), `seed/brands.yaml` ;
- `service/{seed,categories}.py`, `api/categories.py`, `schemas.py` ;
- `scripts/seed_catalog.py` (appelé au démarrage du déploiement après les migrations) ;
- `tests/unit/catalog/test_seed_file.py`, `tests/integration/catalog/{test_seed,test_categories_api}.py`.

**Contenu :**
- Chargement de la graine : validation complète du YAML (clés, parents, attributs connus, héritage), puis `INSERT … ON CONFLICT (key) DO UPDATE` dans une transaction. Le `path` et le `parent_id` sont recalculés ; une clé absente du fichier passe `is_active = false` (jamais supprimée).
- Héritage résolu au chargement : chaque feuille reçoit ses `category_attributes` complets (positions dans l'ordre du fichier).
- `GET /v1/categories` (🔓) : arbre actif avec attributs par catégorie ; verticales absentes si le flag `verticals` est désactivé ; `Cache-Control: public, max-age=3600` et `ETag`.
- `GET /v1/brands?q=` (🔓) : autocomplétion (10 résultats, trigram), limite de débit anonyme.

**Routes :**

| Méthode | Chemin | Accès | Erreurs |
|---|---|---|---|
| GET | `/v1/categories` | 🔓 | — |
| GET | `/v1/brands?q=` | 🔓 | 422 si `q` < 2 caractères |

- [ ] Tests d'abord :
  - `test_seed_file_valid` (le vrai fichier : parents, attributs connus, 16 racines) ;
  - `test_seed_roots_equal_universe_keys` ;
  - `test_seed_idempotent` (deux chargements → mêmes lignes, mêmes identifiants) ;
  - `test_seed_rename_keeps_listings`, `test_seed_move_recomputes_path` ;
  - `test_seed_removed_key_deactivated` ;
  - `test_seed_invalid_file_changes_nothing` (attribut inconnu → erreur, base inchangée) ;
  - `test_inherited_attributes_resolved` (`mode.femme.robes` a couleur, matière et taille obligatoire) ;
  - `test_categories_hide_verticals_when_flag_off`, `test_categories_show_verticals_when_flag_on` ;
  - `test_categories_cache_headers` ;
  - `test_brands_autocomplete`.
- [ ] ÉCHEC → implémenter → vert ; matrice d'accès : 2 routes publiques déclarées.
- [ ] Commit `feat(catalogue): graine des 430 catégories, marques et lecture de l'arbre`.

**Risques :** la graine grandit (24 langues) → le fichier reste la source, et un test interdit toute modification manuelle de `categories` hors graine.

### P2-T02a — Téléversement direct vers le stockage (ADR-0019)

**Branche :** `feat/P2-T02a-televersement`.

**Fichiers :**
- `modules/media/{__init__,api,schemas,models,repository,policies}.py`, `service/uploads.py` ;
- `adapters/storage.py` (`ObjectStorage`, `S3Storage`, `MemoryStorage`) ;
- `migrations/versions/0008_media.py` ;
- `core/config.py` (`storage_endpoint`, `storage_bucket_originals`, `storage_bucket_variants`, `storage_access_key: SecretStr`, `storage_secret_key: SecretStr`, `media_public_url`) ;
- `apps/web/lib/csp.ts` (+ hôte d'envoi dans `connect-src`, `MEDIA_PUBLIC_URL` dans `img-src`) ;
- `docker-compose.yml` et scripts e2e (MinIO) ;
- `infra/r2/README.md` (création des buckets, CORS, cycle de vie, jetons limités) ;
- `docs/adr/0019-medias.md`, `docs/data/PII.md`.

**Contenu :**
- Table `media` (7.5 + `variants JSONB`, `rejection_reason TEXT`, E11).
- `POST /v1/media/uploads` : contrôle du quota, du type déclaré (JPEG, PNG, WebP, AVIF) et de la taille déclarée (≤ 15 Mo). Crée la ligne `uploading` avec une clé aléatoire, puis renvoie `{media_id, upload_url, headers, expires_at}` (URL `PUT` de 5 minutes, `Content-Type` et `Content-Length` signés).
- `POST /v1/media/{id}/complete` : propriétaire seul, statut `uploading` → `processing`, tâche arq `process_media` (idempotent : rappeler ne relance pas un traitement en cours).
- `GET /v1/media/{id}` : propriétaire seul ; statut, variantes si `ready`, motif si `rejected`.

**Routes :**

| Méthode | Chemin | Accès | Erreurs |
|---|---|---|---|
| POST | `/v1/media/uploads` | 🔑 profil complété | 422 `media_type_rejected`, 413 `media_too_large`, 429 `upload_limit` |
| POST | `/v1/media/{id}/complete` | 🔑 propriétaire | 404, 409 si déjà traité |
| GET | `/v1/media/{id}` | 🔑 propriétaire | 404 |

- [ ] Tests d'abord :
  - `test_presigned_url_expires_in_5_minutes` ;
  - `test_presigned_url_signs_type_and_length` ;
  - `test_declared_type_whitelist` (SVG, GIF, HEIC, PDF refusés) ;
  - `test_declared_size_limit` (15 Mo + 1 → 413) ;
  - `test_upload_quota` (31ᵉ dans l'heure → 429) ;
  - `test_storage_key_is_random_and_has_no_pii` (128 bits, aucun identifiant ni nom) ;
  - `test_complete_by_other_member_404`, `test_get_media_by_other_member_404` ;
  - `test_complete_twice_single_job` ;
  - `csp.test.ts` (`img-src` et `connect-src` contiennent les hôtes des médias et rien d'autre de nouveau).
  - Intégration MinIO : `test_put_with_wrong_length_refused_by_storage`, `test_put_after_expiry_refused`.
- [ ] ÉCHEC → implémenter → vert ; revue `supply-chain-risk-auditor` de `boto3`.
- [ ] Commit `feat(medias): téléversement direct par URL présignée (ADR-0019)`.

**Risques :** CORS mal réglé sur R2 → test e2e réel sur staging dès que les buckets existent ; R2 ne garantit pas le rejet d'une longueur différente sur tous les clients → la taille réelle est toujours revérifiée par le worker (T02b).

### P2-T02b — Traitement des images par le worker

**Branche :** `feat/P2-T02b-traitement-images`.

**Fichiers :**
- `modules/media/service/{processing,images}.py`, `tasks.py` ;
- `workers/main.py` (file `media`, délai 120 s, 3 tentatives) ;
- `core/testing_routes.py` (`POST /v1/_test/process-media`) ;
- `tests/fixtures/media/` (vraie photo de téléphone avec GPS, PNG, WebP, AVIF, SVG, script renommé, polyglotte JPEG + ZIP, bombe de décompression, JPEG tronqué, image 20 000 × 20 000) ;
- `tests/unit/media/test_images.py`, `tests/integration/media/test_processing.py`.

**Contenu :**
- Taille réelle relue (`HEAD`) ≤ 15 Mo, sinon `rejected`.
- Signature lue dans les premiers octets (JPEG `FF D8 FF`, PNG, RIFF/WEBP, `ftypavif`) : elle doit correspondre au type déclaré.
- Décodage Pillow avec `MAX_IMAGE_PIXELS` = 50 Mpx ; orientation EXIF appliquée puis toutes les métadonnées retirées ; conversion en sRGB.
- Variantes AVIF et WebP en 320, 640, 1080 et 1600 px de large, sans agrandissement.
- SHA-256 de l'original et dHash 64 bits (calcul maison avec Pillow, sans dépendance).
- Écriture des variantes avec des clés aléatoires, suppression de l'original, `ready` et événement `media.ready`.
- Une image de même dHash (distance ≤ 6) déjà publiée par un autre vendeur → marque `moderation.duplicate_of` (signalement seulement).

- [ ] Tests d'abord :
  - `test_rejects_spoofed_type`, `test_rejects_svg`, `test_rejects_truncated_jpeg` ;
  - `test_rejects_decompression_bomb`, `test_rejects_oversized_real_bytes` ;
  - `test_polyglot_reencoded_without_trailing_bytes` ;
  - `test_variants_have_no_metadata` (aucun EXIF, XMP, IPTC, GPS dans les 8 variantes) ;
  - `test_orientation_applied` ;
  - `test_variant_sizes_and_formats` (pas d'agrandissement d'une image de 500 px) ;
  - `test_original_deleted_after_processing` ;
  - `test_sha256_and_dhash_stable` (même image → même empreinte ; image recadrée de 5 % → distance ≤ 6) ;
  - `test_processing_idempotent` (job rejoué → mêmes variantes, aucun doublon) ;
  - `test_nothing_served_before_ready` (aucune URL publique avant `ready`).
- [ ] ÉCHEC → implémenter → vert ; revue `supply-chain-risk-auditor` de `Pillow`.
- [ ] Commit `feat(medias): nettoyage, variantes et empreintes des images par le worker`.

**Risques :**
- Temps de traitement d'une photo de 12 Mpx en AVIF (≈ 1 à 3 s par variante) → mesure dans le test, file dédiée ; si plus de 10 s au total, l'AVIF passe en 2ᵉ étape après `ready` en WebP.
- Mémoire du worker Railway → limite de 50 Mpx et traitement une image à la fois.
- Recherche des doublons par balayage de `media` (acceptable tant que P2 compte peu de photos) → **avant le lancement**, index par bandes du dHash : 7 bandes, deux empreintes à 6 bits au plus en partagent au moins une (colonnes générées et index B-tree, puis `bit_count`).
- File arq commune : avec une image décodée à la fois par worker, un gros envoi de photos retarde les autres tâches (e-mails de connexion). **Avant d'ouvrir l'envoi** (`media.uploads`), file `media` dédiée (`queue_name`) servie par son propre worker.
- Mesures réelles (T02b) : photo de 12 Mpx en 3,2 s, image de 49 Mpx en 2,4 s (PNG) ou 1,3 s (JPEG) ; pas de file `media` dédiée tant que le traitement reste sous 10 s.

### P2-T02c — Avatar (fin de l'écart E13 de P1) et RGPD des médias

**Branche :** `feat/P2-T02c-avatar`.

**Fichiers :**
- `modules/media/service/gdpr.py` ;
- `modules/identity/service/profile.py` et `schemas.py` (`avatar_media_id`, URL de l'avatar dans `/v1/me` et le profil public) ;
- `modules/media/tasks.py` (purge) ;
- `apps/web/app/[locale]/compte/parametres/` (composant `AvatarField`), `components/Avatar.tsx` ;
- `messages/fr.json` ;
- `tests/integration/media/test_media_gdpr.py`, `tests/integration/identity/test_avatar.py`, `tests/e2e/avatar.spec.ts`.

**Contenu :**
- `PATCH /v1/me` accepte `avatar_media_id` : média `ready`, `purpose = 'avatar'`, appartenant au membre ; recadrage carré au traitement (variantes 320 et 640).
- Ancien avatar marqué supprimé.
- Exportateur `media` (liste des médias, sans les octets) et effaceur (variantes et originaux supprimés du stockage, lignes anonymisées).
- Job quotidien de purge des médias supprimés depuis plus de 30 jours et des médias jamais attachés depuis plus de 24 h.

- [ ] Tests d'abord :
  - `test_avatar_must_be_own_ready_avatar_media` (média d'autrui → 404, média `processing` → 409) ;
  - `test_avatar_in_public_profile` ;
  - `test_replacing_avatar_deletes_old` ;
  - `test_media_exported`, `test_media_erased_from_storage` ;
  - `test_purge_after_retention` (horloge fixe) ;
  - `test_orphan_media_purged_after_24h` ;
  - e2e : choisir une photo dans W20 → aperçu → enregistrement → avatar dans l'en-tête ; axe sans violation.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(medias): avatar téléversable, export, effacement et purge des médias`.

### P2-T03a — Tables des annonces

*Livrée en deux PR (limite de 600 lignes) : T03a1, la table `listings` avec l'exportateur et l'effaceur RGPD du catalogue (exigés dès qu'une table référence `users`) ; T03a2, les tables liées (migration 0013).*

**Branche :** `feat/P2-T03a-tables-annonces`.

**Fichiers :** `modules/catalog/migrations/versions/0012_catalog_listings.py`, `models.py`, `tests/integration/catalog/test_listing_schema.py`, `docs/data/PII.md`.

**Contenu :**
- Tables `listings` (7.5 + `short_id`, `location_source`, `location_source_id`, `embedding VECTOR(1024)`, `embedding_model`, E5, E10, E14), `listing_media`, `favorites`, `price_watches`, `listing_price_history`.
- Nouvelle table `listing_status_history (id, listing_id, from_status, to_status, event, actor_id, actor_kind, reason_code, reason_text, created_at)`.
- Index de 7.5 sauf `listings_search_idx` (P3) ; HNSW créé en T11.
- `CHECK` sur `country_code`, `short_id ~ '^[0-9A-Za-z]{10}$'`.
- Déclencheur de `version` (comme `users`, E15 de P1).
- `PII.md` : `location`, `location_public`, `h3_r7`, `h3_r9`, `place_name` (finalité, base légale contrat, durée de vie de l'annonce).

- [ ] Tests d'abord :
  - `test_price_bounds` (99 et 100 000 001 refusés) ;
  - `test_title_and_description_lengths` ;
  - `test_listing_media_position_unique` ;
  - `test_version_incremented_on_update` ;
  - `test_short_id_format` ;
  - `test_upgrade_downgrade_upgrade`.
- [ ] ÉCHEC → migration → vert. Commit `feat(catalogue): tables des annonces, photos, favoris, suivis et historiques`.

### P2-T03b — Brouillons, attributs, position et lecture d'une annonce

*Livrée en trois PR : T03b1, les briques pures (validation des attributs, position publique, cellules H3, distance arrondie ; dépendance `h3` 4.5.0) ; T03b2, création et modification des brouillons, elle-même en deux PR (T03b2a : bornes Q21, décalage par lieu du vendeur (Q20, E18) avec la table `listing_public_positions` (migration 0014) et la position tirée d'une adresse ou d'une zone ; T03b2b : `POST` en deux PR — T03b2b1, règles d'un brouillon et photos d'une annonce ; T03b2b2, route `POST /v1/listings` — puis T03b2c : `PATCH`) ; T03b3, lecture, « mes annonces », grâce de l'effacement et purge des photos jamais rattachées.*

*Questions de la revue de T03b1 tranchées par Arcel le 26 octobre 2026 : Q20 (décalage par source de position) et Q21 (bornes des entiers et des années), appliquées dans T03b2a (Q20 précisée par E18). En T03b2b, `current_year` des attributs vient de l'horloge dans le fuseau Europe/Paris (le 1er janvier à 0 h 30 à Paris, l'année est déjà la nouvelle). Nom du lieu d'une adresse : sa commune, ou l'arrondissement déduit du code postal pour Paris, Lyon et Marseille (aucun appel au géocodeur) ; pays d'une zone : `FR`, le géocodeur de l'IGN ne couvrant que la France (E10 de P1).*

**Branche :** `feat/P2-T03b-brouillons`.

**Fichiers :**
- `service/{listings,attributes,positions}.py`, `policies.py`, `api/listings.py`, `schemas.py` ;
- `service/gdpr.py` (exportateur et effaceur des annonces) ;
- `modules/identity/service/__init__.py` (fonctions publiques `member_location(db, user_id, source, source_id)`, `is_listing_visible_seller(db, user_id)`, `blocked_user_ids(db, viewer_id)`) ;
- `tests/unit/catalog/{test_attributes,test_positions,test_round_distance}.py`, `tests/integration/catalog/{test_drafts,test_listing_read}.py`.

**Contenu :**
- `POST /v1/listings` (idempotent, `Idempotency-Key` obligatoire) :
  - la catégorie doit être une feuille active (verticales refusées si le flag est désactivé) ;
  - l'état doit être autorisé par la catégorie ;
  - les attributs sont validés par un schéma généré depuis `category_attributes` (types, énumérations, bornes, obligatoires) ;
  - marque : existante, ou créée non vérifiée (Q3) ; interdite quand la politique est `none` ;
  - `media_ids` (E16) : médias du membre, `purpose = 'listing'`, nombre ≤ `max_photos`.
- Position :
  - source = une adresse ou une zone du membre (identity) ;
  - `location` réelle, `location_public` décalée de 200 à 500 m (distance et cap tirés par `secrets.SystemRandom`) ;
  - `h3_r7` et `h3_r9` calculés sur la position réelle (jamais exposés) ;
  - `place_name` repris de la zone, ou obtenu par géocodage inverse pour une adresse (commune ou arrondissement ; secours : code postal sans rue) ;
  - `country_code` ;
  - nouveau décalage seulement si la source change.
- `PATCH /v1/listings/{id}` : `If-Match` obligatoire (428 sans, 412 si périmé) ; mêmes validations ; tout changement de prix ajoute une ligne à `listing_price_history`.
- `GET /v1/listings/{id}` :
  - annonce active : tout le monde ;
  - autre statut : propriétaire seul, sinon 404 ;
  - réponse sans coordonnées, avec `place_name`, `distance` (Q17, E13), vendeur public, photos, attributs et libellés.
- `GET /v1/me/listings?status=` : annonces du membre (pagination par curseur).
- `round_distance(m) -> str` : règles de 8.11 avec arrondi à la valeur la plus proche (moitié vers le haut).
- RGPD : exportateur (annonces, historiques) ; effaceur (annonces supprimées, médias effacés via `media.service`) ; pendant la grâce, les annonces du membre ne sont lisibles par personne d'autre (Q13).

**Routes :**

| Méthode | Chemin | Accès | Erreurs |
|---|---|---|---|
| POST | `/v1/listings` | 🔑 profil complété | 422 `invalid_attributes`, `category_not_leaf`, `category_inactive`, `condition_not_allowed`, `media_limit` ; 404 média d'autrui ; 409 `media_not_ready` |
| PATCH | `/v1/listings/{id}` | 🔑 propriétaire | 404, 412, 428, 422 |
| GET | `/v1/listings/{id}` | 🔓 / propriétaire si non active | 404 |
| GET | `/v1/me/listings` | 🔑 | — |

- Suites des revues de T03a :
  - Purge des photos d'annonce jamais rattachées (24 h, comme les avatars non choisis) : `purpose = 'listing'`, sans ligne dans `listing_media` ; même verrou que pour les avatars (`FOR NO KEY UPDATE SKIP LOCKED` dans la purge, `FOR SHARE` sur la photo au rattachement), test `test_attached_photo_never_purged`.
  - Au rattachement, le service vérifie que la photo appartient au vendeur et a `purpose = 'listing'` (la base ne le garantit pas).
  - Cohérence statut et dates (`sold_at` d'une annonce vendue, `published_at` d'une annonce active) : portée par la machine à états (T04), pas par des contraintes (E17).
- [ ] Tests d'abord :
  - `test_attribute_validation` paramétré (obligatoire manquant, valeur hors énumération, entier hors bornes, attribut inconnu, attribut d'une autre catégorie) ;
  - `test_category_must_be_leaf`, `test_vertical_refused_when_flag_off`, `test_cosmetics_require_new_condition` ;
  - `test_brand_required_for_high_tech`, `test_brand_created_unverified` ;
  - `test_media_of_other_member_404`, `test_too_many_photos` ;
  - `test_public_offset_between_200_and_500_m` (10 000 tirages) ;
  - `test_public_position_stable_over_1000_reads` ;
  - `test_offset_redrawn_only_when_source_changes` ;
  - `test_place_name_never_contains_street` ;
  - `test_round_distance` (seuils du point de revue 6) ;
  - `test_distance_uses_public_position` (E13), `test_no_distance_without_viewer_zone` ;
  - `test_no_coordinates_in_any_catalog_response` ;
  - `test_draft_of_other_member_404` (brouillon, en revue, refusée, retirée) ;
  - `test_patch_requires_if_match`, `test_patch_stale_version_412` ;
  - `test_create_idempotent` ;
  - `test_price_change_recorded` ;
  - `test_listings_hidden_during_erasure_grace`, `test_listings_erased_with_account`.
- [ ] ÉCHEC → implémenter → vert ; matrice d'accès étendue (brouillon d'autrui → 404) ; `PII.md`.
- [ ] Commit `feat(catalogue): brouillons validés par catégorie, position protégée et lecture d'une annonce`.

**Risques :** PR proche de 600 lignes → découpage possible en T03b1 (attributs et brouillons) et T03b2 (position et lecture).

### P2-T04 — Machine à états, publication, retrait, renouvellement, expiration

**Branche :** `feat/P2-T04-etats`.

**Fichiers :** `service/{states,publishing}.py`, `policies.py` (`can_publish_listing`), `events.py`, `tasks.py` (`expire_listings_job`), `workers/main.py`, migration `0010` (graine des [PARAM] de publication), `tests/unit/catalog/test_states.py`, `tests/integration/catalog/test_publishing.py`.

**Contenu :**
- Table de transitions de 9.1 en donnée (`TRANSITIONS: Mapping[tuple[ListingStatus, ListingEvent], ListingStatus]`) :
  - `draft` + `publish` → `active` ou `pending_review` (décision de la modération, T05b ; en T04, toujours `active` derrière une interface `ModerationGate` factice) ;
  - `pending_review` + `approve` → `active` ; `pending_review` + `reject` → `removed` ;
  - `active` + `withdraw` → `withdrawn` ; `withdrawn` + `republish` → `active` ;
  - `active` + `remove` → `removed` ; `removed` + `appeal_accepted` → `active` ;
  - `active` + `expire` → `expired` ; `expired` + `renew` → `active` ;
  - `active` ↔ `reserved` et `reserved` → `sold` : présents dans la table, **sans route** (P4).
- Publication : politique Q1, au moins 1 photo `ready`, quota de 50 par jour compté sur `listing_status_history` (verrou `FOR UPDATE` sur l'annonce), `published_at`, `expires_at` (E12).
- Retrait, republication et renouvellement par le propriétaire.
- Job d'expiration quotidien idempotent (`UPDATE … WHERE status = 'active' AND expires_at <= now() … RETURNING`, transitions une par une).
- Purge quotidienne des annonces terminées selon Q19 (durées en [PARAM], seuils comptés depuis `deleted_at`, le statut final ou `sold_at` ; photos, historiques, favoris et alertes partent avec l'annonce) ; tests aux bornes avec horloge fixe, une annonce vendue liée à une commande garde sa fiche minimale (P4).

**Routes :**

| Méthode | Chemin | Accès | Erreurs |
|---|---|---|---|
| POST | `/v1/listings/{id}/publish` | 🔑 propriétaire, politique Q1 | 404, 403 `publish_forbidden`, 429 `publication_limit`, 409 `invalid_transition`, 422 si aucune photo prête |
| POST | `/v1/listings/{id}/withdraw` | 🔑 propriétaire | 404, 409 |
| POST | `/v1/listings/{id}/renew` | 🔑 propriétaire | 404, 409 (renouvelle `expired` ; republie `withdrawn`) |

- [ ] Tests d'abord :
  - `test_transition_table_exhaustive` (8 statuts × tous les événements) ;
  - `test_each_transition_writes_history_and_event` ;
  - `test_sold_and_removed_never_back_to_active` (sauf recours) ;
  - `test_publish_requires_completed_profile`, `test_publish_requires_adult` (règle E14, horloge fixe sur l'année limite), `test_publish_refused_during_erasure_grace` ;
  - `test_publish_requires_ready_photo` ;
  - `test_publication_limit_50_per_day` (51ᵉ → 429 ; le lendemain, horloge fixe → accepté) ;
  - `test_concurrent_publish_single_transition` ;
  - `test_expiry_after_120_days` (119 j 23 h → active ; 120 j → expired) ;
  - `test_modification_pushes_expiry` ;
  - `test_expire_job_idempotent` ;
  - `test_renew_expired`, `test_republish_withdrawn`.
- [ ] ÉCHEC → implémenter → vert ; matrice d'accès (3 routes `OWNED_ROUTES`).
- [ ] Commit `feat(catalogue): machine à états, publication, retrait, renouvellement et expiration`.

### P2-T05a — Module anti-contournement, détection dans le texte

**Branche :** `feat/P2-T05a-anti-contournement`.

**Fichiers :** `modules/circumvention/{__init__,service,normalize,rules,models,repository}.py`, `migrations/versions/0011_circumvention_detections.py`, `.importlinter`, `tests/unit/circumvention/{test_normalize,test_detect}.py`, `tests/integration/circumvention/test_detections.py`, `docs/data/PII.md`.

**Contenu :**
- `normalize(text)` : minuscules, accents retirés, chiffres en lettres convertis (« zéro six douze » → `0612`), séparateurs (espaces, points, tirets, barres) retirés entre chiffres, variantes `[at]`, `(at)`, `arobase`, `point com`.
- `detect(text) -> list[Detection]` :
  - regex de base de 8.16 (insensible à la casse) sur le texte normalisé ;
  - e-mails, IBAN (validation modulo 97), mots-clés de paiement [PARAM], `@pseudo` et réseaux sociaux, liens externes ;
  - un faux positif évident est écarté : un nombre à 8 chiffres ou plus dans un attribut connu (ISBN, référence) n'est pas analysé, car seuls le titre et la description le sont.
- `mask(text, detections)` → passages remplacés par « ••• coordonnées masquées pour ta sécurité ».
- Table `circumvention_detections` (7.10, `source_type = 'listing'`) avec l'original chiffré (`shared/crypto.py`, AES-256-GCM) et `status = 'auto_confirmed'` ou `'pending_review'`.

- [ ] Tests d'abord :
  - `test_detects_obfuscated_contacts` paramétré : `06 12 34 56 78`, `06.12.34.56.78`, `0 6 1 2 3 4 5 6 7 8`, `zéro six douze trente-quatre…`, `+33 6 12 34 56 78`, `jean [at] gmail point com`, `FR76 3000 6000 0112 3456 7890 189`, `WhatsApp`, `lydia`, `insta : @vendeur` ;
  - `test_no_false_positive` : `Lot de 12 livres`, `iPhone 13 128 Go`, `taille 38`, `année 1857`, `dimensions 120 x 80 x 75` ;
  - `test_iban_checksum` (IBAN à clé fausse non détecté comme IBAN) ;
  - `test_mask_preserves_rest_of_text` ;
  - `test_original_stored_encrypted` (aucun numéro en clair dans la table).
- [ ] ÉCHEC → implémenter → vert. Commit `feat(anti-contournement): détection et masquage des coordonnées dans un texte`.

### P2-T05b — Modération à la publication

**Branche :** `feat/P2-T05b-moderation`.

**Fichiers :**
- `modules/catalog/service/moderation.py` (implémente `ModerationGate`) ;
- `modules/ai/adapters/classifier.py` (`ImageClassifier`, `FakeImageClassifier`) ;
- `modules/media/service/processing.py` (classification et légende à la fin du traitement) ;
- migration `0010` (complétée : [PARAM] `catalog.prohibited`, `moderation.thresholds`) ;
- `tests/integration/catalog/test_moderation.py`.

**Contenu :**
- À la publication, dans l'ordre :
  1. **interdits** : texte normalisé contre `catalog.prohibited` (motif par entrée : armes, contrefaçon, médicament, tabac et vapotage, alcool, animal vivant, espèce protégée, contenu adulte, comptes numériques, billet nominatif, produit rappelé, objet volé, document d'identité) → refus avec motif lisible ;
  2. **catégorie `is_restricted`** → `pending_review` ;
  3. **coordonnées** (T05a) → titre et description masqués, annonce publiée, détection journalisée, rappel pédagogique dans la réponse ;
  4. **images** : scores de classification déjà calculés au traitement (nudité, violence, armes, drogue) ; score max ≥ 0,9 → refus ; 0,5 à 0,9 → `pending_review` ; classification absente ou en erreur → `pending_review` ;
  5. **doublon d'image** d'un autre vendeur (T02b) → `pending_review`.
- Motifs lisibles dans `fr.json` ; refus → `removed` avec `reason_code` dans l'historique.
- Le classifieur ne reçoit que l'image, sans le texte du vendeur.

- [ ] Tests d'abord :
  - `test_prohibited_refused_with_reason` paramétré (une phrase par motif, avec fautes et accents : « fusil de chasse », « r0lex contrefaçon », « bouteille de whisky ») ;
  - `test_restricted_category_goes_to_review` (militaria, siège auto, billetterie) ;
  - `test_contacts_masked_and_published` ;
  - `test_image_thresholds` (0,95 → refus ; 0,7 → revue ; 0,3 → active) ;
  - `test_classifier_outage_goes_to_review` ;
  - `test_duplicate_image_goes_to_review` ;
  - `test_moderation_reason_readable_fr`.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(catalogue): modération des annonces à la publication`.

### P2-T05c — File de revue staff minimale

**Branche :** `feat/P2-T05c-file-de-revue`.

**Fichiers :**
- `modules/catalog/api/staff.py` ;
- migration `0010` (permission `moderation.review`, E9) ;
- `apps/web/app/[locale]/staff/moderation/page.tsx`, `messages/fr.json` ;
- `tests/integration/catalog/test_review_queue.py`, `tests/e2e/moderation.spec.ts`.

**Contenu :**
- Liste des annonces `pending_review` (plus anciennes d'abord), avec motif, photos et passages surlignés.
- Approuver → `active` ; refuser (motif obligatoire, liste fermée + texte) → `removed`, variantes supprimées du stockage (Q6).
- `POST /v1/staff/listings/{id}/remove` : retrait d'une annonce active (permission `listing.remove_any`).
- Chaque décision : `record_audit` (acteur staff, annonce, décision, motif) et historique.

**Routes :**

| Méthode | Chemin | Accès | Erreurs |
|---|---|---|---|
| GET | `/v1/staff/moderation/listings` | 🛡️ `moderation.review` | 403 |
| POST | `/v1/staff/moderation/listings/{id}/approve` | 🛡️ `moderation.review` | 403, 404, 409 |
| POST | `/v1/staff/moderation/listings/{id}/reject` | 🛡️ `moderation.review` | 403, 404, 409, 422 sans motif |
| POST | `/v1/staff/listings/{id}/remove` | 🛡️ `listing.remove_any` | 403, 404, 409 |

- [ ] Tests d'abord :
  - `test_member_gets_403_on_review_routes` (matrice) ;
  - `test_approve_publishes_and_audits` ;
  - `test_reject_requires_reason`, `test_reject_deletes_public_variants` ;
  - `test_staff_cannot_review_own_listing` (un compte staff n'a pas d'annonce : vérification que la route refuse le cas) ;
  - `test_concurrent_decisions_single_transition` ;
  - e2e : connexion staff → file → approuver → l'annonce devient visible ; axe sans violation.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(catalogue): file de revue staff des annonces`.

### P2-T07 — Score de qualité de fiche

**Branche :** `feat/P2-T07-qualite`.

**Fichiers :** `service/quality.py`, `schemas.py`, `messages/fr.json` (conseils), `tests/unit/catalog/test_quality.py`.

**Contenu :** formule explicite et pure, de 0 à 100. **Choix de l'auteur du plan, à confirmer** (le cahier ne donne que les trois critères) :
- photos : 40 points (1 photo = 15, puis +5 par photo jusqu'à 6 photos) ;
- description : 30 points (proportionnel de 20 à 300 caractères) ;
- attributs facultatifs remplis : 20 points (proportion remplie) ;
- marque renseignée quand la catégorie la prévoit : 10 points (sinon les 10 points sont acquis).

Recalculé à chaque création ou modification. La réponse au propriétaire donne le score et les conseils, par exemple « Ajoute 2 photos (+10) » ou « Précise la matière (+4) ».

- [ ] Tests d'abord :
  - `test_quality_bounds` (propriété hypothesis : toujours de 0 à 100) ;
  - `test_quality_examples` (fiche minimale = 15 + 0 + 0 + 10 = 25 ; fiche complète = 100) ;
  - `test_quality_tips_ordered_by_gain` ;
  - `test_quality_recomputed_on_patch`.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(catalogue): score de qualité de fiche et conseils`.

### P2-T08 — Favoris, suivi de prix, historique des prix

**Branche :** `feat/P2-T08-favoris-prix`.

**Fichiers :** `service/{favorites,prices}.py`, `api/favorites.py`, `tests/integration/catalog/{test_favorites,test_prices}.py`.

**Contenu :**
- Favori et suivi de prix (`target_minor` facultatif) seulement sur une annonce active d'autrui ; `favorite_count` tenu à jour dans la même transaction ; idempotents (un deuxième `POST` ne change rien).
- `GET /v1/me/favorites` (annonces actives d'abord, les autres marquées indisponibles).
- `GET /v1/listings/{id}/price-history` (annonce active ; prix et dates, sans autre donnée).
- `lowest_price_30_days(listing_id, at) -> int` (Omnibus), prête pour les prix barrés de P10.
- La notification de baisse de prix arrive en P3 avec les notifications : en P2, la donnée est seulement enregistrée.

**Routes :**

| Méthode | Chemin | Accès | Erreurs |
|---|---|---|---|
| POST/DELETE | `/v1/listings/{id}/favorite` | 🔑 | 404 annonce non active, 409 sa propre annonce |
| POST/DELETE | `/v1/listings/{id}/price-watch` | 🔑 | idem ; 422 si `target_minor` hors bornes |
| GET | `/v1/me/favorites` | 🔑 | — |
| GET | `/v1/listings/{id}/price-history` | 🔓 | 404 si non active |

- [ ] Tests d'abord :
  - `test_favorite_idempotent_and_counted` ;
  - `test_cannot_favorite_own_or_inactive` ;
  - `test_concurrent_favorites_count_exact` ;
  - `test_price_watch_target_bounds` ;
  - `test_lowest_price_30_days` (changements à J-40, J-20, J-5 ; horloge fixe) ;
  - `test_price_history_hidden_for_draft`.
- [ ] ÉCHEC → implémenter → vert ; matrice d'accès. Commit `feat(catalogue): favoris, suivis de prix et historique des prix`.

### P2-T11 — Embeddings des annonces (ADR-0020)

**Branche :** `feat/P2-T11-embeddings`. Exécutée avant T06a et T10 (section 4).

**Fichiers :** `modules/ai/adapters/embedder.py` (`Embedder`, `FakeEmbedder` déterministe, `BedrockEmbedder`), `modules/catalog/{tasks,service/similar}.py`, migration `0012_catalog_ai` (index HNSW), `docs/adr/0020-embeddings.md`, `tests/integration/catalog/test_embeddings.py`.

**Contenu :**
- Sur `listing.published` et `listing.updated` (contenu modifié), le worker calcule l'embedding du texte : titre, description, libellés des attributs, marque, légende de la photo principale (T05b).
- `embedding_model` est enregistré avec le vecteur.
- `reindex_embeddings_job` (lots de 100, annonces actives dont `embedding_model` ≠ modèle courant).
- `similar_listings(listing, viewer, limit=8)` : `status = 'active'`, même univers (premier niveau du `path`), hors vendeur de l'annonce, hors vendeurs bloqués par le visiteur, hors comptes en effacement ; distance cosinus.

- [ ] Tests d'abord :
  - `test_embedding_dimension_matches_model` ;
  - `test_embedding_computed_on_publish` ;
  - `test_reindex_on_model_change` ;
  - `test_similar_filters` (annonce retirée, autre univers, vendeur bloqué, même vendeur → exclus) ;
  - `test_similar_uses_hnsw_index` (`EXPLAIN`) ;
  - `test_embedding_failure_does_not_block_publication`.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(catalogue): embeddings des annonces et annonces similaires (ADR-0020)`.

### P2-T06a — Assistance IA « Vendre en 30 s » (adaptateur factice)

**Branche :** `feat/P2-T06a-assistance-ia`.

**Fichiers :** `modules/ai/{__init__,service,schemas,models,repository}.py`, `adapters/provider.py` (`AIProvider`, `FakeAIProvider`), migration `0012` (complétée : `ai_listing_suggestions`), `.importlinter`, `modules/catalog/api/listings.py` (`POST /v1/listings/assist`), `tests/integration/ai/test_assist.py`, `docs/data/PII.md`.

**Contenu :**
- Entrée : 1 à 4 médias `ready` du membre.
- Le fournisseur reçoit les variantes 1080 px et la liste des feuilles actives (clés et libellés).
- Sortie validée par le schéma JSON : titre, `category_key`, marque, état, attributs, légende, confiance par champ. Nettoyage :
  - catégorie hors des feuilles actives → retirée ;
  - attributs → validés par catégorie, les invalides retirés ;
  - aucune valeur n'est inventée par le serveur.
- Fourchette de prix : quartiles (25ᵉ à 75ᵉ centile, arrondis à l'euro) des annonces actives de la même feuille, même état, rapprochées par embedding (T11), seulement si au moins 5 comparables ; sinon `price_range = null`.
- Plafonds : 20 par jour et par compte, 2 centimes par suggestion ; au-delà, `429 ai_limit`.
- Journalisation dans `ai_listing_suggestions` (modèle, suggestion, latence, coût) ; `accepted_fields` rempli à la création du brouillon (champs gardés tels quels).
- Flag `ai.assist` désactivé : `503 ai_unavailable` ; W09 continue sans IA.

**Routes :**

| Méthode | Chemin | Accès | Erreurs |
|---|---|---|---|
| POST | `/v1/listings/assist` | 🔑 profil complété | 404 média d'autrui, 409 média non prêt, 429 `ai_limit`, 503 `ai_unavailable` |

- [ ] Tests d'abord :
  - `test_assist_returns_schema_valid_suggestion` ;
  - `test_assist_rejects_unknown_category` ;
  - `test_assist_drops_invalid_attributes` ;
  - `test_assist_no_price_without_comparables` (4 comparables → aucun prix ; 5 → fourchette) ;
  - `test_assist_daily_limit` (21ᵉ → 429) ;
  - `test_assist_cost_cap` (fournisseur factice qui annonce un coût de 3 centimes → refus et journalisation) ;
  - `test_assist_logged_with_latency_and_cost` ;
  - `test_accepted_fields_recorded_on_draft` ;
  - `test_assist_with_others_media_404` ;
  - `test_prompt_injection_in_image_text_ignored` (le faux fournisseur renvoie une catégorie « ignore » → rejetée).
- [ ] ÉCHEC → implémenter → vert ; matrice d'accès. Commit `feat(ia): assistance à la publication derrière un adaptateur`.

### P2-T06b — Fournisseur réel : Claude sur Bedrock UE (ADR-0021)

**Branche :** `feat/P2-T06b-bedrock`. **Prérequis :** accès Bedrock ouvert par Arcel (section 7).

**Fichiers :** `modules/ai/adapters/{provider,classifier,embedder}.py` (implémentations Bedrock), `core/config.py` (`aws_region`, `bedrock_model_id`, `bedrock_embedding_model_id`, identifiants en `SecretStr`), `docs/adr/0021-fournisseur-ia.md`, `tests/unit/ai/test_bedrock_adapters.py`.

**Contenu :**
- Appels par l'API Converse de Bedrock avec un profil d'inférence UE ; modèle Claude et modèle d'embeddings choisis à cette tâche (skill `claude-api` relu, prix vérifié, coût mesuré par annonce).
- Sortie forcée en JSON par un outil à schéma ; délai de 15 s ; erreurs → `ai_unavailable`, sans le contenu de la requête dans les journaux.
- Coût calculé depuis les jetons consommés.

- [ ] Tests d'abord (client Bedrock simulé, aucun appel réseau) :
  - `test_bedrock_request_has_no_seller_text_as_instruction` ;
  - `test_bedrock_cost_computed_from_usage` ;
  - `test_bedrock_timeout_maps_to_unavailable` ;
  - `test_bedrock_errors_not_logged_with_content`.
- [ ] ÉCHEC → implémenter → vert ; revue `supply-chain-risk-auditor` (`boto3` déjà présent).
- [ ] Essai réel sur staging par Arcel (une photo → suggestion) ; coût moyen relevé dans l'ADR.
- [ ] Commit `feat(ia): Claude sur Bedrock UE pour l'assistance, la classification et les embeddings (ADR-0021)`.

**Risques :** coût par suggestion au-dessus de 2 centimes → réduire la taille d'image envoyée (640 px) ou choisir un modèle plus léger ; mesuré avant activation du flag.

### P2-T09a — Écran W09 « Vendre en 30 s »

**Branche :** `feat/P2-T09a-vendre`.

**Fichiers :** `apps/web/app/[locale]/vendre/page.tsx`, `components/sell/{SellFlow,PhotoPicker,UploadProgress,SuggestionFields,AttributeFields,LocationPicker,QualityMeter}.tsx`, `lib/media.ts`, `lib/attributes.ts` (miroir de la validation), `messages/fr.json`, `tests/e2e/vendre.spec.ts`, tests Vitest des composants.

**Contenu :**
- Mobile first. Étape 1 : photos (`<input type="file" accept="image/jpeg,image/png,image/webp" capture="environment" multiple>` et galerie), progression de chaque envoi, réordonnancement, suppression.
- Étape 2 : suggestions de l'IA pré-remplies, modifiables champ par champ, avec la mention « Proposé par l'IA ».
- Étape 3 : prix (fourchette affichée si présente), position (adresse ou zone, `place_name` affiché), envoi ou main propre.
- Étape 4 : aperçu et « Publier ».
- Brouillon enregistré automatiquement (création au premier champ, `PATCH` avec `If-Match` toutes les 2 s d'inactivité) ; reprise du brouillon.
- Erreurs de validation au niveau du champ ; score de qualité et conseils.
- Accessible : libellés, annonces de progression (`aria-live`), parcours au clavier.
- Politique refusée (mineur, profil incomplet) : message clair et lien vers le profil.

- [ ] Tests d'abord :
  - Vitest : validation miroir identique à l'API (mêmes cas que `test_attribute_validation`) ;
  - e2e `vendre.spec.ts` : viewport mobile, photo depuis un fichier → suggestions factices → publication → fiche visible ; **chronomètre < 60 s** entre le choix de la photo et la fiche active ;
  - brouillon repris après rechargement ; message de modération (coordonnées masquées) ;
  - axe sans violation à chaque étape.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(web): écran Vendre en 30 s`.

**Risques :** traitement d'image trop lent pour 60 s → les suggestions démarrent dès la première photo `ready` ; mesure dans l'e2e.

### P2-T09b — Écran W10 « Mes annonces »

**Branche :** `feat/P2-T09b-mes-annonces`.

**Fichiers :** `apps/web/app/[locale]/compte/annonces/page.tsx`, `components/listings/{ListingRow,StatusTabs}.tsx`, `messages/fr.json`, `tests/e2e/annonces.spec.ts`.

**Contenu :** onglets brouillons, en ligne, en revue, retirées, expirées, refusées (motif lisible). Actions selon la machine à états : modifier, publier, retirer, renouveler. Score de qualité. Lien depuis le hub du compte.

- [ ] Tests d'abord : e2e retirer puis republier, renouveler une annonce expirée (route de test qui avance `expires_at`), motif de refus affiché ; axe sans violation.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(web): écran Mes annonces`.

### P2-T10 — Fiche produit W03 (sans achat)

**Branche :** `feat/P2-T10-fiche`.

**Fichiers :** `apps/web/app/[locale]/annonce/[slug]/{page,opengraph-image}.tsx`, `components/listing/{Gallery,SellerCard,PriceHistory,SimilarListings,FavoriteButton,PriceWatchButton}.tsx`, `lib/media.ts` (chargeur), `next.config.ts` (`images.loader` personnalisé), `messages/fr.json`, `tests/e2e/fiche.spec.ts`, `lighthouserc` (budget de la fiche).

**Contenu :**
- Rendu côté serveur ; URL `/fr/annonce/[slug]-[short_id]`, canonique, redirection 308 si le slug est faux.
- `noindex` et page « Cette annonce n'est plus disponible » (statut HTTP 410) si l'annonce n'est plus active ; 404 pour un brouillon d'autrui.
- Galerie accessible au clavier avec textes alternatifs (titre + position) ; première image en priorité (`fetchPriority="high"`), les autres en chargement différé.
- Vendeur (pseudo, avatar, membre depuis) ; prix ; `place_name` et distance arrondie (Q17, E13).
- Onglets Description et Historique des prix ; favori et suivi de prix ; similaires.
- Données structurées schema.org `Product` + `Offer` (prix, devise, état, disponibilité) ; image OG générée depuis la première variante.
- Mention « Vendu par un particulier » (14.3).

- [ ] Tests d'abord :
  - e2e : rendu sans JavaScript (contenu dans le HTML) ; canonique et redirection du slug ; `noindex` sur une annonce retirée ; JSON-LD valide (schéma) ; galerie au clavier ; axe sans violation ; aucune coordonnée dans le HTML (recherche de motifs `\d+\.\d{4,}`).
  - Lighthouse mobile en CI sur une fiche de démonstration : LCP < 2,5 s, accessibilité 100.
- [ ] ÉCHEC → implémenter → vert. Commit `feat(web): fiche produit sans achat`.

### P2-T12 — Parcours 2 partiel, démonstration et porte de P2

**Branche :** `feat/P2-T12-porte`.

**Fichiers :** `apps/web/tests/e2e-full/parcours-2.spec.ts`, `tests/e2e-full/stack.sh` (MinIO), `apps/api/scripts/seed_demo.py`, `test_access_matrix.py`, `test_no_pii_in_telemetry.py` (étendu), `docs/HANDOFF.md`, `docs/GLOSSARY.md`, `docs/security/threat-model.md`, `docs/plans/P2-catalogue-annonces.md` (notes de réalisation).

**Contenu :**
- `parcours-2.spec.ts` (16.2 n° 2, partiel) : l'activation vendeur est en P4. Membre majeur → W09 → photo → IA factice → publication → fiche publique visible par un autre navigateur anonyme. La recherche par cercle est en P3.
- Démonstration (16.6) :
  - `seed_demo.py` idempotent, refusé si `ENV=production` ;
  - vendeurs et annonces de la maquette (« Les Fleurs du mal, édition originale 1857 » à 18 500 €, « réédition 1868 » à 240 €, montre, objectif, vinyle, lampe, vase, carte), avec des photos libres de droits ;
  - les commandes, litiges et versements de 16.6 viendront avec leurs phases ;
  - `/fr/demo` reste en place.
- Matrice d'accès : toutes les routes de P2 déclarées (publiques, propriétaires, staff).
- Télémétrie : le parcours de publication (téléversement, position, modération, IA) ne laisse ni coordonnée, ni adresse, ni clé de média, ni texte masqué dans les journaux, Sentry et les traces.

- [ ] Tests d'abord : parcours 2 ; `test_seed_demo_refused_in_production` ; `test_seed_demo_idempotent` ; matrice et télémétrie étendues.
- [ ] CI verte ; démonstration sur staging ; commit `test(catalogue): parcours 2 partiel, données de démonstration et porte de P2`.

---

## 6. Porte de P2 (cahier 17.3) : checklist et preuves

| # | Critère | Preuve attendue |
|---|---|---|
| G1 | Publication en moins de 60 s depuis une photo sur mobile web | e2e `vendre.spec.ts` (viewport mobile) avec chronomètre < 60 s, vert en CI ; démonstration d'Arcel sur son téléphone (staging). |
| G2 | Fiche produit LCP < 2,5 s | Lighthouse mobile sur staging et en CI : LCP < 2,5 s, accessibilité 100, SEO 100 ; capture jointe à la PR T10. |
| G3 | La modération bloque les interdits | `test_prohibited_refused_with_reason` (un cas par motif de 8.17) ; `test_restricted_category_goes_to_review` ; `test_image_thresholds`. |
| G4 | La modération masque les coordonnées | `test_detects_obfuscated_contacts`, `test_no_false_positive`, `test_contacts_masked_and_published` ; démonstration : annonce avec « zéro six… » publiée masquée. |
| G5 | Position publique stable et jamais exacte | `test_public_position_stable_over_1000_reads`, `test_public_offset_between_200_and_500_m`, `test_no_coordinates_in_any_catalog_response`, `test_round_distance`, `test_distance_uses_public_position`. |
| G6 | Photos nettoyées | `test_variants_have_no_metadata` sur une vraie photo de téléphone avec GPS ; sur staging, `exiftool` sur une variante publiée : aucune métadonnée. |
| G7 | Fichiers piégés refusés | Tests du point de revue 3 verts. |
| G8 | Matrice d'accès à jour | `test_access_matrix.py` vert avec toutes les routes de P2 ; brouillon et média d'autrui → 404 ; membre → 403 sur la file de revue. |
| G9 | Aucune donnée personnelle dans la télémétrie | `test_no_pii_in_telemetry.py` étendu, vert ; recherche d'une adresse d'Arcel dans les journaux Railway et Sentry après une publication : 0 résultat. |
| G10 | Clés d'univers identiques | `test_universe_keys_single_source`, `test_seed_roots_equal_universe_keys`. |
| G11 | Machine à états | `test_transition_table_exhaustive`, `test_expiry_after_120_days`, `test_concurrent_publish_single_transition`. |
| G12 | IA encadrée | Tests de T06a verts ; coût moyen par suggestion < 2 centimes mesuré sur staging (ADR-0021). |
| G13 | Parcours 2 partiel vert | Job `e2e-full` vert sur `main`. |
| G14 | Accessibilité | axe 0 violation sur W09, W10, W03, page de modération et avatar ; parcours au clavier. |
| G15 | Documentation | ADR-0019 à 0021, `PII.md`, `threat-model.md` v4, glossaire et `HANDOFF.md` à jour ; staging ressemble à la maquette (données de démonstration). |

## 7. Actions qui reviennent à Arcel pendant P2

1. ~~Valider ce plan, l'écart E13 et l'ordre modifié~~ : fait le 26 octobre 2026.
2. Avant T02a : créer le compte Cloudflare, deux buckets R2 en **juridiction UE** et un jeton limité à ces buckets (guidage pas à pas ; les clés vont directement dans Railway, jamais dans la conversation).
3. Avant T06b : créer le compte AWS, ouvrir l'accès aux modèles Claude et au modèle d'embeddings dans une région UE, fixer un budget mensuel avec alerte, créer un utilisateur limité à Bedrock (guidage ; clés dans Railway seulement).
4. Démonstrations sur staging : publier depuis son téléphone (G1), vérifier une photo nettoyée (G6), approuver une annonce dans la file de revue.
5. Plus tard : domaine `trovelya.com` (médias sur `media.trovelya.com`), évaluation de Sightengine avant le lancement public.
