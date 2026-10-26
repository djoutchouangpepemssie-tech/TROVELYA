# Modèle de menaces — v4 (P0, P1 authentification et comptes, P2 catalogue et annonces)

**Date :** 24 octobre 2026, mis à jour le 25 octobre 2026 (fin de P1) et le 26 octobre 2026 (plan de P2). **Méthode :** STRIDE (usurpation, altération, répudiation, divulgation, déni de service, élévation de privilèges). **À revoir :** à chaque phase qui ajoute une surface (P1 authentification, P4 paiements, P12 enchères…).

## Périmètre et frontières de confiance

```
Navigateur ──HTTPS──▶ Vercel fra1 (Next.js, CSP à nonce)
    │                         │
    └──HTTPS──▶ Railway europe-west4 : API FastAPI ──réseau privé──▶ pg (PostgreSQL 17)
                                 │                               └─▶ Redis
                                 └─HTTPS──▶ Sentry UE (de.sentry.io)
              worker arq ──réseau privé──▶ pg, Redis
GitHub (code, CI, Dependabot) ──▶ Railway / Vercel (déploiement par branche)
```

Frontières : Internet → Vercel/API ; API → base et Redis (réseau privé Railway, non exposés) ; services → Sentry ; GitHub → plateformes de déploiement.

P0 ne contient **aucune** donnée métier ni authentification : les menaces ci-dessous portent sur le socle.

## Analyse

| Composant | Menace (STRIDE) | Mesure en place (P0) | Reste à faire |
|---|---|---|---|
| API | **S** Requête forgée depuis un autre site (CSRF) | Double soumission signée HMAC (`core/csrf.py`), `SameSite`, contrôle sur toute méthode non sûre | Sessions opaques en P1 (ADR-0008) |
| API | **T** Rejeu d'une requête qui modifie | Clés d'idempotence (ADR-0012), même réponse rejouée, empreinte de la requête vérifiée | — |
| API | **I** Fuite d'informations dans les erreurs | Erreurs RFC 9457 génériques (« Erreur interne »), sans trace ni détail ; `/docs` absent en production | — |
| API | **I** Données personnelles dans les journaux ou Sentry | `redact_pii` sur tous les journaux ; Sentry `data_collection` strict + `before_send`/`before_breadcrumb` ; IP masquées ; « Prevent Storing of IP Addresses » activé dans Sentry | Revue à chaque nouveau champ personnel |
| API | **D** Saturation par un client anonyme | Limite glissante par client (Redis, 120 requêtes/minute), clé = empreinte HMAC de l'IP | Limites par compte en P1 ; protection DDoS du fournisseur |
| API | **D** Redis indisponible | Limiteur en « fail open » (journalisé), `/ready` signale la panne | Alerte sur `/ready` |
| API | **E** Route de test exposée | Routes `_test` montées seulement en `local`/`test` ; `_debug` absente en production (testé) | — |
| Base | **T** Altération du journal d'audit | Ajout seul (UPDATE/DELETE refusés), chaîne SHA-256 calculée en base (ADR-0014), vérification nocturne | Alerte si `audit_verify_chain()` signale une rupture |
| Base | **T** Écriture comptable déséquilibrée | Contrainte différée d'équilibre, écritures immuables (ADR-0005) | Plan de comptes en P4 |
| Base | **I** Accès direct depuis Internet | Aucun port public : `pg` et Redis seulement sur le réseau privé Railway | — |
| Base | **R/D** Perte de données | Volume persistant ; exercice de restauration joué (`docs/runbooks/restore.md`) | Sauvegardes planifiées et exercice trimestriel |
| Worker | **T** Événement émis pour une transaction annulée | Outbox transactionnelle (ADR-0007), testée | — |
| Worker | **D** Relais bloqué | Jauge `trovelya_outbox_oldest_unpublished_seconds` | Alerte > 60 s quand Grafana sera branché |
| Web | **T/I** Injection de script (XSS) | CSP à nonce par requête, `strict-dynamic`, `object-src 'none'`, `frame-ancestors 'none'` ; règle semgrep interdisant `dangerouslySetInnerHTML` | — |
| Web | **S** Hameçonnage par mise en cadre | `X-Frame-Options: DENY`, `frame-ancestors 'none'`, HSTS avec `preload` | Domaine `trovelya.com` + HSTS preload à l'achat |
| CI/CD | **T** Code non revu en production | Production seulement via `release`, avancé par le workflow après CI verte (ADR-0013) | Protection de `main` dès un compte GitHub Pro ou Team |
| CI/CD | **I** Secret commis dans le dépôt | gitleaks sur tout l'historique à chaque PR ; `.env` ignoré ; secrets seulement dans Railway/Vercel | — |
| Chaîne d'approvisionnement | **T** Dépendance compromise ou vulnérable | Versions épinglées, fichiers de verrouillage, `pip-audit`, `pnpm audit`, semgrep, SBOM CycloneDX sur `main`, Dependabot hebdomadaire ; binaire gitleaks vérifié par somme de contrôle | — |
| Secrets | **I/E** Vol de `SECRET_KEY` | Générée par Railway (`${{secret(64)}}`), jamais affichée, différente par environnement | Procédure de rotation en P1 |

## P1 — Authentification et comptes (ajout du 24 octobre 2026)

Nouvelles frontières :

```
Navigateur ──▶ Vercel (Next.js) ── relais /api/* (secret partagé, IP et pays du client) ──▶ API
                  cookie __Host-trv_session posé sur l'origine du web (ADR-0015)
API ──HTTPS──▶ Resend (e-mails, ADR-0017) · Google / Apple (OIDC) · Géoplateforme IGN (géocodage)
     · anti-robot (Friendly Captcha, UE, avant la production)
worker ──▶ envoi d'e-mails, export et effacement RGPD
```

Les colonnes « Tâches » renvoient à `docs/plans/P1-identite-comptes.md`.

| Composant | Menace (STRIDE) | Parade prévue | Tâches |
|---|---|---|---|
| Session | **S** Vol du cookie de session (XSS, réseau) | Cookie `__Host-` `HttpOnly; Secure; SameSite=Lax; Path=/` ; CSP à nonce ; jeton de 256 bits dont seul le SHA-256 est stocké | T02a, T02b |
| Session | **S** Fixation de session | Nouveau jeton à chaque connexion et à chaque step-up ; l'ancien est révoqué | T02b, T04 |
| Session | **S** Session volée utilisée longtemps | Expiration absolue 30 jours, inactivité 14 jours, révocation unitaire ou globale immédiate, notification de nouvel appareil ou pays | T02b, T02c |
| Lien magique | **S** Interception de l'e-mail | Usage unique, 15 minutes, jeton dans le fragment d'URL (jamais dans les journaux ni le `Referer`), confirmation par bouton (POST), notification de nouvelle connexion | T02c |
| Lien magique | **I** Énumération des comptes | Même parcours, même réponse `202` et même travail serveur que l'e-mail existe ou non (le compte naît à la vérification) | T02c |
| Lien magique | **D** Bombardement d'e-mails ou de requêtes | 5 par heure par e-mail, 20 par heure par IP ; anti-robot Friendly Captcha avant la production (décision d'Arcel du 25 octobre 2026, Turnstile écarté : hors UE) | T02c |
| Lien magique | **T** Préchargement par un scanner d'e-mails qui consomme le lien | La page `/verifier` n'agit qu'après un clic (POST) | T02c, T12a |
| OAuth / OIDC | **S** Connexion forcée sur le compte d'un attaquant (CSRF de connexion), rejeu du code | `state`, `nonce` et `code_verifier` (PKCE) côté serveur, à usage unique, liés au navigateur ; `id_token` vérifié (signature JWKS, `iss`, `aud`, `exp`, `nonce`) | T03 |
| OAuth / OIDC | **E** Prise de compte par liaison sur un e-mail non vérifié | Liaison automatique seulement si `email_verified` est vrai chez le fournisseur ; sinon refus avec invitation à se connecter par lien magique | T03 |
| Passkeys | **S** Rejeu ou relais d'une assertion | Challenge à usage unique (5 min), vérification de l'origine, du RP ID et de `sign_count` | T04 |
| Step-up | **E** Action sensible depuis une session volée | Preuve forte de moins de 12 h exigée : changer d'e-mail, ajouter ou supprimer une passkey, export et effacement RGPD, actions staff sensibles | T04, T05, T09a, T09b, T11 |
| Relais web | **S** IP falsifiée pour contourner les limites | L'API ne croit l'en-tête d'IP du relais que s'il est authentifié par le secret partagé ; sinon `X-Real-IP` réécrit par Railway ; jamais `X-Forwarded-For` fourni par le client | T02a |
| Relais web | **I** Fuite de cookies ou d'en-têtes vers l'API | Liste blanche d'en-têtes relayés ; seuls les cookies `__Host-trv_*` passent | T02a |
| API | **I** IDOR sur adresses, zones, sessions, exports | Politique par objet dans `policies.py` ; 404 pour la ressource d'autrui ; test qui parcourt toutes les routes privées | T05, T06, T09a, T12c |
| API | **E** Utilisateur qui appelle une route staff | Permissions nommées vérifiées côté serveur (`require_permission`) ; comptes staff distincts, passkey obligatoire, sessions de 12 h | T11 |
| Double validation | **R/E** Un seul membre du staff fait seul une action critique | Demande `pending`, approbateur différent qui détient la permission, expiration 24 h, deux identités dans l'audit | T11 |
| RGPD | **I** Export téléchargé par un tiers | Step-up, archive chiffrée (AES-256-GCM), propriétaire seul, expiration 7 jours | T09a |
| RGPD | **T/R** Effacement incomplet ou contesté | Registre des « effaceurs » par module, anonymisation des lignes à conserver, journal d'audit, délai de grâce de 30 jours annulable | T09b |
| Journaux | **I** E-mail, jeton, IP ou adresse dans les journaux, Sentry ou traces | `redact_pii` étendu aux nouveaux champs ; Sentry et traces passent par le même masquage, sans chaîne de requête (`scrub_telemetry`, `RedactingSpanExporter`) ; erreurs de base sans message ; `test_no_pii_in_telemetry` sur un parcours complet | T02c, T12c |
| Inscription | **D** Création de comptes en masse | Limites de débit, pas de compte avant vérification de l'e-mail ; anti-robot Friendly Captcha avant la production | T02c |
| Mineurs | **I** Profilage d'un mineur | Année de naissance seule ; moins de 15 ans refusé sans rien conserver ; drapeau « mineur » qui exclura toute publicité personnalisée (P11) | T05 |
| E-mails | **I** Données transférées hors UE (Resend : métadonnées aux États-Unis) | Écart temporaire documenté (ADR-0017), seul Arcel reçoit des e-mails avant l'ouverture ; bascule vers un fournisseur hébergé dans l'UE avant le lancement public | T02c |
| Secrets | **I/E** Fuite de `SECRET_KEY`, `PROXY_SHARED_SECRET` ou `FIELD_ENCRYPTION_KEY` | Variables Railway/Vercel chiffrées, différentes par environnement ; procédure de rotation dans `docs/runbooks/secrets.md` | T02a, T09a |

## État à la fin de P1 (25 octobre 2026)

Toutes les parades du tableau P1 sont en place et testées, sauf l'anti-robot, à brancher avant la production (Friendly Captcha). Deux tests gardent les frontières :
- `test_access_matrix` : les 61 routes de l'API sont déclarées ; anonyme → 401, tiers → 404 sur toute ressource d'autrui, membre → 403 sur les routes staff.
- `test_no_pii_in_telemetry` : aucun e-mail, jeton, IP, nom, adresse, téléphone, coordonnée ni année de naissance dans les journaux, Sentry ou les traces, sur un parcours complet.

Ce second test a trouvé et fait corriger cinq fuites qui seraient parties en production : la chaîne de requête (adresse recherchée) dans les traces et dans la ligne d'accès d'uvicorn ; l'URL des appels sortants dans les journaux de `httpx` et dans les transactions Sentry ; les valeurs d'une requête SQL en échec citées par le pilote `asyncpg`.

Reste ouvert : rotation des secrets (procédure écrite, non jouée) ; e-mails par Resend (métadonnées aux États-Unis, ADR-0017) jusqu'au fournisseur UE ; passkeys et Apple sur le domaine `trovelya.com` après son achat.

## P2 — Catalogue et annonces (ajout du 26 octobre 2026)

Nouvelles frontières :

```
Navigateur ──PUT (URL présignée 5 min)──▶ Cloudflare R2, juridiction UE : bucket privé « originaux »
Navigateur ◀──GET──  bucket public « variantes » (clés aléatoires de 128 bits ; r2.dev puis media.trovelya.com)
worker arq ──S3──▶ R2 (lecture de l'original, écriture des variantes, suppression de l'original)
worker / API ──HTTPS──▶ AWS Bedrock, région UE (Claude : vision, assistance, classification ;
                        modèle d'embeddings) — adaptateurs AIProvider, ImageClassifier, Embedder
API ──HTTPS──▶ Géoplateforme IGN (géocodage inverse de la position de l'annonce)
```

En local et en CI, MinIO remplace R2 et des adaptateurs factices déterministes remplacent Bedrock. Les colonnes « Tâches » renvoient à `docs/plans/P2-catalogue-annonces.md`.

### Téléversements et médias

| Composant | Menace (STRIDE) | Parade prévue | Tâches |
|---|---|---|---|
| URL présignée | **S/E** URL réutilisée pour écrire ailleurs ou plus tard | URL `PUT` signée pour **une** clé aléatoire, **5 minutes**, `Content-Type` et `Content-Length` déclarés inclus dans la signature (R2 n'accepte pas les formulaires `POST` à politique) ; une seule URL par média, média lié à son propriétaire | T02a |
| Fichier envoyé | **T** Type falsifié (script renommé `.jpg`, SVG avec JavaScript, polyglotte) | Type réel lu dans les premiers octets (signature) par le worker, liste blanche JPEG, PNG, WebP, AVIF ; SVG, HEIC et tout le reste refusés ; l'original n'est **jamais** servi : seules les variantes ré-encodées par le worker sont publiques | T02b |
| Fichier envoyé | **D** Bombe de décompression, image géante, fichier énorme | Taille réelle relue (`HEAD`) ≤ 15 Mo avant lecture ; `Image.MAX_IMAGE_PIXELS` = 50 Mpx, au-delà refus ; traitement dans une file dédiée avec délai maximal ; objets non complétés supprimés par une règle de cycle de vie (24 h) | T02a, T02b |
| Fichier envoyé | **E** Faille de la bibliothèque d'images (exécution de code) | Pillow épinglé, revue `supply-chain-risk-auditor`, Dependabot ; décodage seulement dans le worker (jamais dans l'API) ; aucune autre bibliothèque de décodage | T02b |
| Métadonnées | **I** Position GPS, numéro de série de l'appareil, nom dans l'EXIF | Ré-encodage complet sans aucune métadonnée (EXIF, XMP, IPTC, ICC hors sRGB) ; `exif_stripped = true` ; test sur une photo de téléphone réelle avec GPS | T02b |
| Variantes publiques | **I** Énumération des photos de brouillons ou d'annonces retirées | Clés aléatoires de 128 bits sans identifiant ni nom ; médias non publiés jamais listés par l'API (tiers → 404) ; variantes supprimées du stockage dès le retrait par la modération ou l'effacement du compte | T02b, T05c, T02c |
| Noms et URL | **I** Donnée personnelle dans un nom de fichier ou une URL | Nom d'origine jamais conservé ; clé = aléa ; `test_no_pii_in_telemetry` étendu au téléversement | T02a, T12 |
| Empreintes | **R** Image volée à un autre vendeur | SHA-256 (doublon exact) et hachage perceptuel de 64 bits (doublon proche) : signalement en revue seulement, jamais de refus automatique | T02b, T05b |
| Stockage | **I** Données hors UE | Buckets créés en juridiction UE ; Cloudflare est une société américaine (CLOUD Act) : écart documenté dans l'ADR-0019 | T02a |
| Coût | **D** Remplissage du stockage par un compte | 30 téléversements par heure et 200 par jour par compte [PARAM] ; médias orphelins (jamais attachés) supprimés après 24 h | T02a |

### Annonces et position

| Composant | Menace (STRIDE) | Parade prévue | Tâches |
|---|---|---|---|
| Position | **I** Adresse du vendeur exposée | La position réelle vient d'une adresse ou d'une zone du vendeur (jamais du GPS sans accord) ; l'API ne renvoie **jamais** de coordonnées en P2, seulement `place_name` (commune ou arrondissement) et une distance arrondie (8.11) | T03b |
| Position | **I** Triangulation par lectures répétées | Décalage de 200 à 500 m tiré **une fois** (générateur cryptographique) et conservé ; 1 000 lectures renvoient la même chose | T03b |
| Position | **I** Trilatération en créant plusieurs zones (distances arrondies au km depuis plusieurs points) | Distance calculée sur la position publique décalée (écart E13, validé le 26/10/2026), cellules H3 jamais exposées ; arrondis de 8.11 testés à chaque seuil | T03b, T10 |
| Brouillons | **I** IDOR sur un brouillon, une annonce retirée, refusée ou en revue | Politiques `can_view_listing` / `can_edit_listing` ; tiers → 404 ; matrice d'accès étendue | T03b, T12 |
| Modification | **T** Écrasement concurrent | `If-Match` sur `version` (412) ; idempotence de la création | T03b |
| Publication | **D** Inondation d'annonces | 50 publications par jour par compte [PARAM `listings.max_publications_per_day`] ; limite par compte de 11.4 | T04 |
| Publication | **E** Publication par un compte qui n'en a pas le droit (mineur, profil incomplet) | Politique `can_publish_listing` : profil complété, âge ≥ 18 (règle E14 de P1), compte non suspendu ni en effacement | T04 |
| Prix | **T** Faux prix barré | Historique des prix ajouté seul ; prix de référence = plus bas sur 30 jours (Omnibus), prix barré inactif jusqu'en P10 | T08 |
| Effacement | **I** Annonces d'un compte supprimé encore visibles | Pendant la grâce : annonces masquées ; à l'effacement : annonces supprimées et médias effacés du stockage | T03b, T02c |

### Modération et anti-contournement

| Composant | Menace (STRIDE) | Parade prévue | Tâches |
|---|---|---|---|
| Interdits | **T** Contournement de la liste (fautes, espaces, lettres accentuées) | Normalisation (minuscules, accents retirés, chiffres en lettres, séparateurs retirés) avant les règles ; liste [PARAM `catalog.prohibited`] ; catégories `is_restricted` toujours en revue humaine | T05a, T05b |
| Coordonnées | **I/R** Téléphone, e-mail ou IBAN dans le titre ou la description pour vendre hors application | Regex de 8.16 + normalisation ; passage masqué avant publication, rappel pédagogique ; original **chiffré** (AES-256-GCM) dans `circumvention_detections` pour la revue | T05a |
| Classification d'images | **T** Image interdite (nudité, armes, violence) | Adaptateur `ImageClassifier` (Claude sur Bedrock UE) ; ≥ 0,9 refus, 0,5 à 0,9 revue, < 0,5 publication [PARAM] ; en cas de panne du fournisseur : revue humaine (jamais publication sans contrôle) | T05b |
| Entrées de l'IA | **T** Injection de consignes dans le titre, la description ou une image (« ignore tes règles ») | Le texte du vendeur est passé comme donnée, jamais comme consigne ; sortie contrainte par un schéma JSON validé côté serveur ; catégories hors de l'arbre rejetées ; l'IA ne décide seule que dans les seuils, et un refus automatique est motivé et contestable | T05b, T06a |
| File de revue | **E** Membre qui approuve sa propre annonce | Routes staff avec la permission `moderation.review` ; comptes staff distincts ; matrice d'accès (membre → 403) | T05c |
| File de revue | **R** Décision contestée | Chaque décision inscrite dans l'audit (acteur, motif, annonce) et dans l'historique de l'annonce ; motif lisible envoyé au vendeur | T05c |

### Assistance IA et embeddings

| Composant | Menace (STRIDE) | Parade prévue | Tâches |
|---|---|---|---|
| Coût | **D** Appels répétés qui font exploser la facture | 20 suggestions par jour par compte et 2 centimes par suggestion au plus [PARAM] ; coût et latence journalisés (`ai_listing_suggestions`) ; budget mensuel AWS avec alerte (Arcel) | T06a, T06b |
| Fournisseur | **I** Photos et textes conservés ou réutilisés par le fournisseur | Bedrock dans une région UE avec profil d'inférence UE ; Bedrock ne conserve ni n'utilise les données pour l'entraînement ; AWS est une société américaine : écart documenté dans l'ADR-0021 | T06b |
| Sortie | **T** Valeur inventée (catégorie, marque, prix) | Schéma JSON strict ; catégorie seulement parmi les feuilles actives ; fourchette de prix seulement avec au moins 5 annonces comparables actives ; rien n'est publié sans action du vendeur | T06a |
| Embeddings | **I** Similaires qui montrent un vendeur bloqué ou une annonce retirée | Filtre `status = 'active'`, même univers, hors vendeurs bloqués par le visiteur et comptes en effacement | T11, T10 |

## Hypothèses

- Railway, Vercel, GitHub et Sentry sont des tiers de confiance ; leurs comptes sont protégés par une double authentification (à vérifier par Arcel).
- Cloudflare (R2) et AWS (Bedrock) sont des sous-traitants traitant les données dans l'UE, sous contrat de sous-traitance (DPA) ; leur nationalité américaine est un écart documenté (ADR-0019, ADR-0021).
- La valeur `NEXT_PUBLIC_*` n'est jamais secrète (DSN Sentry du web, clé publique de l'anti-robot).
- Avant le lancement public, `trovelya.com` est acheté : passkeys, Apple et e-mails basculent sur ce domaine (les passkeys de test créées sur `vercel.app` sont perdues).
