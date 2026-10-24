# Glossaire TROVÉLYA

Source de vérité du vocabulaire du projet. La partie métier reprend la section 2 du cahier des charges ; la partie technique décrit les notions introduites en P0.

## Vocabulaire métier (cahier, section 2)

Les identifiants de code sont en anglais (`snake_case` en Python et SQL, `camelCase` en TypeScript). Les libellés d'interface sont en français.

| Terme (interface) | Identifiant code | Définition |
|---|---|---|
| Utilisateur | `user` | Personne disposant d'un compte. Peut être acheteur et vendeur. |
| Vendeur particulier | `seller` (`seller_type = 'individual'`) | Vend des biens personnels, sans activité commerciale. |
| Vendeur professionnel | `seller` (`seller_type = 'business'`) | Entreprise identifiée (SIREN/numéro de TVA). Soumis aux obligations DSA de traçabilité et au droit de rétractation de 14 jours. |
| Boutique | `shop` | Vitrine de marque d'un vendeur pro, avec son domaine (phase P10). |
| Annonce | `listing` | Objet mis en vente, avec un ou plusieurs modes de vente. |
| Univers | `category` (racine) | Grande famille du catalogue (Mode, Maison et jardin, Immobilier, Véhicules…). 16 univers (section 8.19). |
| Verticale | `vertical` | Univers aux règles et champs propres : `real_estate`, `vehicles`, `services`. Les autres univers sont `goods`. |
| Modèle transactionnel | `transaction_model` | `protected_purchase` (paiement + séquestre), `contact` (mise en relation, aucun paiement) ou `mixed` (contact, paiement protégé optionnel). Porté par la catégorie. |
| Mise en relation | `lead` | Demande de contact, de visite ou de rendez-vous sur une annonce en modèle `contact`. |
| Annonce immobilière | `real_estate_details` | Détails d'un bien : type de transaction, surface, pièces, DPE, charges, honoraires… |
| DPE | `energy_class` / `ghg_class` | Diagnostic de performance énergétique : classes A à G (énergie et gaz à effet de serre), mention obligatoire dans les annonces immobilières en France. |
| Annonce véhicule | `vehicle_details` | Détails d'un véhicule : marque, modèle, année, kilométrage, carburant, contrôle technique… |
| Mode de vente | `sale_mode` | `fixed_price`, `auction` (P12), `live` (P13), `drop` (P14), `group_buy` (P14). |
| Offre | `offer` | Proposition de prix d'un acheteur sur une annonce à prix fixe (négociation). |
| Commande | `order` | Engagement d'achat entre un acheteur et un vendeur, regroupant un ou plusieurs articles d'un même vendeur. |
| Séquestre | `escrow` | Fonds bloqués chez le prestataire de paiement entre le paiement et la validation de la réception. |
| Libération | `escrow_release` | Passage des fonds du séquestre au solde disponible du vendeur. |
| Remise en main propre | `handover` | Remise physique de l'objet, validée par un **code de remise**. |
| Code de remise | `handover_code` | Code à 6 chiffres + QR code détenu par l'acheteur, saisi ou scanné par le vendeur pour valider la remise. |
| Expédition | `shipment` | Envoi par transporteur avec étiquette générée. |
| Litige | `dispute` | Contestation ouverte par l'acheteur avant la libération des fonds. |
| Grand livre | `ledger` | Comptabilité interne en partie double de tous les mouvements d'argent. |
| Écriture | `ledger_entry` | Ligne de débit ou de crédit d'une transaction du grand livre. |
| Frais de protection acheteur | `buyer_protection_fee` | Frais payés par l'acheteur sur les ventes entre particuliers. |
| Commission | `seller_commission` | Pourcentage prélevé au vendeur pro quand TROVÉLYA apporte la vente. |
| Score de confiance | `trust_score` | Note de 0 à 1 000 par utilisateur, recalculée chaque jour sur 90 jours glissants. |
| Badge | `badge` | Distinction attribuée automatiquement selon des critères mesurés. |
| Rang | `rank` | Bronze, Argent, Or, Platine, Légende : niveau de volume et de régularité, avec avantages. |
| Priorité territoriale | `geo_priority` | Classement des résultats par cercles de distance autour de l'acheteur. |
| Zone | `search_zone` | Point ou ville de référence de l'acheteur, avec un rayon. |
| Cercle | `geo_ring` | Tranche de distance : rayon choisi, ville, région, pays, UE. |
| Vérification vidéo | `verification_video` | Vidéo horodatée de l'objet, filmée par le vendeur avant l'envoi ou la remise. |
| Passeport produit | `product_passport` | Identifiant et historique d'un objet à travers ses reventes (P17). |
| Contournement | `circumvention` | Tentative de conclure une vente hors plateforme (coordonnées, paiement externe). |
| Sanction | `sanction` | Mesure graduée contre un compte (rappel, avertissement, réduction de visibilité, suspension). |
| Signalement | `report` | Notification d'un contenu ou comportement par un utilisateur (DSA « notice »). |
| Exposé des motifs | `statement_of_reasons` | Justification envoyée à l'utilisateur pour toute décision de modération (obligation DSA). |
| Tour de contrôle | `admin` | Console d'administration interne. |
| Journal d'audit | `audit_log` | Historique inaltérable des actions sensibles. |
| Atelier marchand | `merchant_studio` | Espace de gestion des vendeurs pros sur ordinateur. |
| TROVÉLYA Pass | `buyer_wallet` | Compte acheteur universel avec moyens de paiement enregistrés chez le prestataire. |
| Cercle (communauté) | `circle` | Communauté thématique (P15). Ne pas confondre avec `geo_ring`. |

## Vocabulaire technique (P0)

| Terme | Identifiant code | Définition |
|---|---|---|
| Outbox transactionnelle | `outbox_events` | Table où un événement de domaine est écrit dans la même transaction que la donnée qui le provoque. Un événement d'une transaction annulée n'existe donc jamais (ADR-0007). |
| Relais de l'outbox | `relay_outbox` | Tâche du worker qui publie chaque seconde les événements non publiés dans le flux Redis `trv:events`, au moins une fois. |
| Consommateur idempotent | `consume_once`, `processed_events` | Traitement d'un événement qui ne produit son effet qu'une fois, même si l'événement est reçu plusieurs fois. |
| Clé d'idempotence | `Idempotency-Key`, `idempotency_keys` | En-tête envoyé par le client sur une requête qui modifie quelque chose ; une même clé rejouée renvoie la même réponse sans refaire l'action. Conservée 72 heures (ADR-0012). |
| Chaîne d'audit | `audit_log.prev_hash`, `audit_log.hash` | Chaque ligne du journal d'audit contient le hash SHA-256 de la précédente : toute modification ou suppression casse la chaîne, ce que `audit_verify_chain()` détecte (ADR-0014). |
| Transaction différée (contrainte) | `DEFERRABLE INITIALLY DEFERRED` | Contrôle exécuté à la fin de la transaction et non à chaque ligne : l'équilibre débit = crédit du grand livre est vérifié au `COMMIT` (ADR-0005). |
| Unité de travail | `get_uow`, `commit`, `on_commit` | Une requête = une transaction ; les actions à faire seulement si la transaction réussit sont enregistrées avec `on_commit`. |
| Détails du problème | RFC 9457, `application/problem+json` | Format unique des erreurs de l'API : `type`, `title`, `status`, `code`, `instance`, `request_id`. |
| Identifiant de requête | `x-request-id`, `request_id` | Identifiant de chaque requête, renvoyé au client, présent dans chaque ligne de journal et dans Sentry. |
| Empreinte client | `client_fingerprint` | HMAC-SHA-256 de l'adresse IP avec la clé secrète du serveur ; utilisée par le limiteur de débit à la place de l'IP. |
| Masquage des données personnelles | `redact_pii` | Filtre appliqué à tous les journaux et à tout ce qui part vers Sentry (e-mails, téléphones, IBAN, jetons, adresses IP, clés sensibles). |
| Staging / production | `main` / `release` | Deux environnements complets (Railway et Vercel) : `main` part en staging à chaque fusion, `release` n'avance que par le workflow *Deploy production* (ADR-0013). |
| Contrat d'API | `docs/api/openapi.json` | Description OpenAPI générée depuis le code ; le client TypeScript en est dérivé et la CI vérifie qu'ils sont à jour (ADR-0004). |
