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

## Vocabulaire technique (P1 — identité et comptes)

| Terme | Identifiant code | Définition |
|---|---|---|
| Lien magique | `magic_links`, `/fr/verifier` | Connexion sans mot de passe : un lien à usage unique (15 minutes, `auth.magic_link_ttl_min`) envoyé par e-mail ; le jeton est dans le fragment de l'URL, et la connexion n'a lieu qu'après un clic sur « Me connecter ». |
| Session | `sessions`, `__Host-trv_session` | Session opaque (ADR-0008) : le navigateur garde un jeton aléatoire, la base n'en garde que l'empreinte ; 30 jours au plus, 14 jours d'inactivité, révocable appareil par appareil. |
| Relais same-origin | `/api/*`, `lib/relay.ts`, `PROXY_SHARED_SECRET` | Le site relaie les appels à l'API depuis sa propre origine (ADR-0015) ; l'API ne croit l'IP et le pays transmis que si le secret partagé est présent. |
| Jeton CSRF | `__Host-trv_csrf`, `x-csrf-token` | Double soumission signée : toute requête qui modifie un état renvoie dans un en-tête la valeur du cookie. |
| Preuve forte (step-up) | `sessions.mfa_at`, `recent_mfa_user`, `components/StepUp.tsx` | Connexion forte de moins de 12 h (`auth.step_up_max_age_h`) exigée pour les actions sensibles ; obtenue par passkey ou par un lien envoyé par e-mail. |
| Passkey | `passkeys`, WebAuthn | Clé d'accès liée à l'appareil ; ouverte aux membres par le drapeau `auth.passkeys`, obligatoire pour le staff. |
| Profil complété | `users.profile_completed_at`, `completed_user` | Pseudo, nom, année de naissance et CGU acceptées ; sans profil complété, seules les routes du compte lui-même répondent. |
| Drapeau | `feature_flags`, `allow_user_ids` | Interrupteur d'une fonctionnalité : activé pour tous, pour une part des membres, par pays ou pour une liste de membres (bêta-testeurs), qui l'emporte sur l'interrupteur général. |
| Consentement | `consents`, `__Host-trv_anon` | Choix accordé ou retiré pour une finalité facultative, avec la version de la politique ; l'historique est conservé comme preuve. |
| Demande RGPD | `data_requests` | Demande d'export ou d'effacement, avec son état (`received`, `processing`, `completed`, `refused`). |
| Export RGPD | `data_exports`, `register_exporter` | Archive ZIP scellée de toutes les données d'un compte (ADR-0016), construite par le worker et téléchargeable 7 jours (`retention.data_export_days`) ; chaque module enregistre son exportateur. |
| Délai de grâce | `retention.erasure_grace_days`, `users.erasure_requested_at` | 30 jours entre la demande d'effacement et l'effacement ; pendant ce délai le compte est masqué et peut être rétabli par « Annuler la suppression ». |
| Effaceur | `register_eraser` | Fonction de chaque module qui efface ou anonymise ses données à la fin du délai de grâce. |
| Compte staff | `users.is_staff`, `staff_user` | Compte interne distinct, connecté par passkey en session d'administration de 12 h (ADR-0018). |
| Double validation | `approval_requests`, `require_permission` | Action critique demandée par un membre du staff et approuvée par un autre qui détient la permission, avant 24 h ; les deux identités sont dans le journal d'audit. |
| Matrice d'accès | `tests/integration/identity/test_access_matrix.py` | Liste de toutes les routes de l'API par règle d'accès (publique, ouverte, membre, ressource possédée, staff) ; une route non déclarée fait échouer la CI. |
| Masquage de la télémétrie | `scrub_telemetry`, `RedactingSpanExporter` | Le masquage des journaux appliqué à Sentry et aux traces, sans chaîne de requête ; les erreurs de base gardent leur type, jamais leur message. |
| Parcours 1 | `tests/e2e-full/parcours-1.spec.ts`, job `e2e-full` | Inscription par e-mail jusqu'à l'accueil connecté, sur la pile telle qu'elle est déployée (image de l'API, worker, Mailpit). |
