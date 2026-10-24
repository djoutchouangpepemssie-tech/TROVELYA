# TROVÉLYA — Cahier des charges technique et fonctionnel

> **La belle trouvaille.** Le marché vivant où l'on vend, enchérit, diffuse et construit sa confiance.

| Champ | Valeur |
|---|---|
| Version | 1.2 — token `color.ink.3` (clair) foncé pour l'accessibilité ; 1.1 — catalogue généraliste, verticales immobilier, véhicules, services (phase P9) |
| Date | 24 octobre 2026 |
| Propriétaire produit | Arcel (fondateur) |
| Statut | Référence de développement — fait foi pour Claude Code |
| Dépôt | `djoutchouangpepemssie-tech/trovelya` |
| Documents liés | `CLAUDE.md` (règles de travail), `SKILLS.md` (skills installés), vision produit (Claude Docs), maquette interactive (Claude Design) |

---

## Sommaire

0. Mode d'emploi de ce document · 1. Vision, positionnement et périmètre · 2. Glossaire métier · 3. Acteurs, rôles et permissions · 4. Stratégie de construction (22 phases, web d'abord) · 5. Architecture technique · 6. Expérience utilisateur et design system · 7. Modèle de données PostgreSQL · 8. Règles métier · 9. Machines à états · 10. Paiements, séquestre et grand livre · 11. Contrat d'API · 12. Temps réel · 13. Sécurité · 14. Conformité réglementaire · 15. Spécifications des phases P9 à P21 · 16. Qualité, tests, exploitation · 17. Plan de construction chronologique · 18. Décisions ouvertes · 19. Phases ↔ skills · Annexes

---

## 0. Mode d'emploi de ce document (à lire en premier par Claude Code)

### 0.1 Rôle du document

Ce document est la **source de vérité** du projet. Il décrit quoi construire, dans quel ordre, avec quelles règles et quels critères d'acceptation. Il ne remplace pas le jugement d'ingénierie : il le cadre.

### 0.2 Ordre de priorité en cas de conflit

1. Une instruction explicite d'Arcel dans la conversation en cours.
2. Les règles non négociables de `CLAUDE.md`.
3. Ce cahier des charges.
4. Les ADR (Architecture Decision Records) du dossier `docs/adr/`, une fois créés.
5. Les recommandations des skills installés.

Si deux sources se contredisent, **ne pas trancher seul** : signaler le conflit, proposer une option par défaut, attendre la validation.

### 0.3 Vocabulaire normatif

| Terme | Sens |
|---|---|
| **DOIT** / **NE DOIT PAS** | Exigence obligatoire. Tout écart est un défaut bloquant. |
| **DEVRAIT** / **NE DEVRAIT PAS** | Recommandation forte. Un écart doit être justifié dans la PR. |
| **PEUT** | Option laissée au choix de l'implémentation. |
| **[À VALIDER]** | Décision non encore prise par Arcel ou un juriste. Implémenter la valeur par défaut indiquée, derrière une configuration modifiable sans redéploiement. |
| **[PARAM]** | Valeur métier réglable (table `platform_settings`), jamais codée en dur. |

### 0.4 Comment travailler avec ce document

1. Avant toute fonctionnalité : relire la section concernée, puis appliquer `brainstorming` ou `grill-me`, puis `writing-plans`.
2. Chaque phase de la section 17 se termine par une **porte de validation** : ne pas commencer la phase suivante tant que tous les critères ne sont pas vérifiés (`verification-before-completion`).
3. Toute décision d'architecture prise en cours de route DOIT être consignée dans un ADR (`docs/adr/NNNN-titre.md`, format : contexte, décision, conséquences).
4. Toute nouvelle notion métier DOIT être ajoutée au glossaire (section 2) et au fichier `docs/GLOSSARY.md` (skill `domain-modeling`).
5. Ce document évolue par pull request. Toute modification de règle métier (section 8) DOIT être signalée en tête de PR.

### 0.5 Ce que Claude Code NE DOIT PAS faire

- Inventer une règle métier absente de ce document : poser la question.
- Stocker un numéro de carte, un IBAN complet en clair, un mot de passe en clair ou un secret dans le code.
- Utiliser des nombres à virgule (`float`, `Decimal` sérialisé en texte non contrôlé, `number` JS) pour l'argent : **centimes en entiers** uniquement.
- Écrire dans les tables d'un autre module (voir 5.4).
- Désactiver un test, une règle de lint ou une vérification de type pour « faire passer » la CI.
- Fusionner sur `main` sans revue (`requesting-code-review`).
- Ajouter une dépendance sans vérifier sa maintenance, sa licence et ses vulnérabilités (`supply-chain-risk-auditor`).

---

## 1. Vision, positionnement et périmètre

### 1.1 Résumé exécutif

TROVÉLYA est une **place de marché européenne** qui réunit en une seule application :

- la **revente entre particuliers** (style Vinted, Leboncoin), **dans toutes les catégories** : mode, maison, high-tech, culture, enfants, sport, collection, matériel professionnel… ;
- les **petites annonces à mise en relation** : **immobilier** (vente, location, colocation, locaux, terrains), **véhicules**, **services** ;
- les **boutiques de marque** possédées par les marchands (style Shopify) ;
- les **enchères** et le **live shopping** (style Whatnot) ;
- un **feed social** qui apporte des acheteurs aux vendeurs ;
- une **recherche locale d'abord** (priorité territoriale, 5 km par défaut) ;
- une **confiance mesurée** : séquestre, score de confiance, badges, vérification vidéo, passeport produit.

Promesse marchand : *Shopify vous donne un magasin vide. TROVÉLYA vous donne un magasin et une foule.*
Promesse acheteur : *Trouver la belle pièce, près de chez soi, en toute sécurité.*

### 1.2 Principe directeur

Chaque fonctionnalité DOIT servir à la fois le vendeur (vendre plus, garder la main) et l'acheteur (découvrir, être protégé). Une idée qui ne sert qu'un camp est mise en attente.

### 1.3 Catalogue : une place de marché généraliste

**Décision d'Arcel : TROVÉLYA n'est pas limitée à une niche.** Tout ce qui peut légalement se vendre, se louer ou se proposer entre particuliers et professionnels y a sa place, réparti en **16 univers** (section 8.19), dont trois **verticales** aux règles propres :

- **Immobilier** : vente, location, colocation, location saisonnière, bureaux et commerces, terrains, parkings (section 8.20) ;
- **Véhicules** : voitures, motos, utilitaires, caravanes et camping-cars, bateaux, pièces (section 8.21) ;
- **Services** : cours, bricolage, déménagement, ménage, événementiel… (section 8.22).

Chaque catégorie suit un **modèle transactionnel** : *achat protégé* (paiement, séquestre, remise ou livraison), *mise en relation* (contact, visite, rendez-vous, sans argent qui transite par TROVÉLYA) ou *mixte*. La seconde main de qualité et les objets de collection restent un point fort (enchères, live, authentification, passeport produit), mais **aucune catégorie n'est fermée**. Les univers mis en avant dans la communication de lancement sont un choix marketing **[À VALIDER]** par Arcel.

Zone de lancement : **Paris et petite couronne**, puis France, Belgique, Luxembourg.

### 1.4 Zone de marché

Union européenne (27 pays), une seule société en France, hébergement des données dans l'UE. Déploiement par vagues (section 15.10).

### 1.5 Ce que TROVÉLYA ne fait pas (hors périmètre permanent)

- Détenir les fonds des utilisateurs en propre : le séquestre est opéré par un prestataire de paiement agréé (section 10).
- Vendre des produits financiers : la « bourse des objets » ne porte que sur des objets réels.
- Cibler la publicité sur des données sensibles ou vers des mineurs.
- Vendre hors UE avant la couverture complète de l'UE.

---

## 2. Glossaire métier

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

---

## 3. Acteurs, rôles et permissions

### 3.1 Rôles

| Rôle | Identifiant | Description |
|---|---|---|
| Visiteur | `anonymous` | Non connecté. Peut parcourir, chercher, voir les annonces publiques. |
| Membre | `member` | Compte vérifié par e-mail ou fournisseur d'identité. Peut acheter, mettre en favori, écrire. |
| Vendeur particulier | `seller_individual` | Membre ayant activé la vente (onboarding prestataire de paiement complété). |
| Vendeur pro | `seller_business` | Vendeur avec entreprise vérifiée (KYB). |
| Modérateur | `staff_moderator` | Traite signalements, annonces, messages signalés. |
| Agent support | `staff_support` | Traite litiges et demandes. Lecture des commandes. |
| Analyste confiance | `staff_trust` | Anti-fraude, anti-contournement, sanctions jusqu'au niveau 3. |
| Finance | `staff_finance` | Versements, remboursements, rapprochements. |
| Administrateur | `staff_admin` | Configuration, rôles (hors super-admin). |
| Super-administrateur | `staff_superadmin` | Tous droits. Réservé à Arcel et à une seconde personne de confiance. |

Un utilisateur PEUT cumuler `member` + `seller_*`. Les rôles `staff_*` DOIVENT être portés par des comptes distincts des comptes clients (domaine e-mail de l'entreprise, clé de sécurité matérielle ou passkey obligatoire).

### 3.2 Matrice de permissions (extrait normatif)

Légende : ✅ autorisé · 🔒 autorisé avec double validation · — interdit.

| Action | member | seller_* | moderator | support | trust | finance | admin | superadmin |
|---|---|---|---|---|---|---|---|---|
| Publier une annonce | — | ✅ | — | — | — | — | — | — |
| Acheter | ✅ | ✅ | — | — | — | — | — | — |
| Retirer une annonce d'autrui | — | — | ✅ | — | ✅ | — | ✅ | ✅ |
| Lire une conversation privée | — | — | ✅ si signalée | ✅ si liée à un litige | ✅ si signalée ou détectée | — | — | ✅ |
| Trancher un litige | — | — | — | ✅ ≤ 500 € · 🔒 > 500 € | — | — | ✅ | ✅ |
| Rembourser | — | — | — | 🔒 | — | ✅ ≤ 500 € · 🔒 > 500 € | — | ✅ |
| Sanction niveaux 1 à 3 | — | — | ✅ (1-2) | — | ✅ | — | ✅ | ✅ |
| Suspendre un compte (niveau 4) | — | — | — | — | 🔒 | — | 🔒 | 🔒 |
| Valider un versement manuel | — | — | — | — | — | 🔒 | — | ✅ |
| Modifier `platform_settings` | — | — | — | — | — | — | 🔒 | ✅ |
| Gérer les rôles staff | — | — | — | — | — | — | — | 🔒 |
| Exporter des données personnelles | — | — | — | — | — | — | 🔒 | 🔒 |

**Double validation** : l'action crée une demande `pending_approval` ; un second membre du staff, différent du demandeur, avec un rôle au moins équivalent, DOIT approuver dans les 24 h, sinon la demande expire. Les deux identités sont inscrites au journal d'audit.

Les permissions DOIVENT être implémentées par **permissions nommées** (ex. `dispute.resolve`, `user.suspend`), associées aux rôles dans une table, et vérifiées côté serveur à chaque appel. L'interface ne fait que masquer.

---

## 4. Stratégie de construction : tout le produit, dans l'ordre chronologique, web d'abord

### 4.1 Décisions d'Arcel (font foi)

1. **Le web d'abord.** Le site Next.js (`apps/web`) est le premier client de l'API et DOIT couvrir 100 % des fonctionnalités avant que l'application mobile ne commence. Il est conçu *mobile first* (responsive dès 360 px) et installable en PWA, pour servir les utilisateurs sur téléphone en attendant l'app native.
2. **Tout le produit est construit**, sans couper de fonctionnalités de la vision. Il n'y a pas de « MVP réduit » : il y a un **ordre**.
3. **L'ordre est chronologique et strict** : chaque phase s'appuie sur la précédente. Une phase n'est commencée que lorsque la porte de la précédente est franchie (critères en section 17).
4. **L'application mobile Expo** (`apps/mobile`) est la **dernière phase de construction** (P21). Elle consomme la même API et le même `packages/api-client`, sans logique métier propre.

### 4.2 Pourquoi cet ordre

- **Toutes les catégories d'objets** (16 univers moins les verticales) sont ouvertes dès P2 ; les verticales immobilier, véhicules et services arrivent en P9, une fois la recherche, la messagerie et la confiance en place, car elles en dépendent entièrement. Leurs catégories existent dès P2 en base, masquées par le drapeau `verticals`.
- Les phases P0 à P8 forment la **colonne vertébrale transactionnelle** (identité → annonce → recherche → paiement → remise → messagerie → confiance → administration). Tout le reste (boutiques, publicité, enchères, live, IA, international) se branche dessus.
- Les briques qui coûteraient cher à ajouter plus tard sont **posées dès P0**, même si leur fonctionnalité arrive bien après :
  - **i18n** : `next-intl` installé en P0, toutes les chaînes d'interface dans des fichiers de messages (`fr` par défaut). Aucune chaîne en dur dans les composants.
  - **Multi-devise** : chaque montant est stocké avec sa devise (`amount_minor` + `currency` ISO 4217) dès P0, même si seul l'euro est actif avant P18.
  - **Pays et TVA** : chaque utilisateur, vendeur, commande porte un `country_code` (ISO 3166-1 alpha-2) dès P0.
  - **Fonctionnalités activables** (feature flags) : chaque module de P10 à P20 est derrière un drapeau, désactivé par défaut en production.
  - **Événements de domaine** : la table `outbox_events` existe dès P0 ; chaque module publie ses événements (section 5.6), ce qui permet d'ajouter feed, notifications, score, publicité sans toucher aux modules existants.
  - **Journal d'audit, grand livre, permissions nommées** : dès P0.

### 4.3 Les 22 phases

| Phase | Nom | Contenu principal | Dépend de |
|---|---|---|---|
| **P0** | Fondations | Monorepo, outillage, CI/CD, infra Railway/Vercel, squelette FastAPI, migrations, design system web, i18n, flags, outbox, audit, grand livre (squelette), observabilité | — |
| **P1** | Identité et comptes | Inscription, connexion (lien magique, Apple, Google, passkeys), sessions, profils, adresses, zones de recherche, préférences, RGPD libre-service, rôles et permissions | P0 |
| **P2** | Catalogue et annonces | Catégories et attributs, annonces, médias (photos, vidéo), création assistée par IA depuis photo, états, modération automatique à la publication, favoris, bouton « Revendre » | P1 |
| **P3** | Recherche, priorité territoriale, feed v1 | Index de recherche hybride, géo (PostGIS + H3), 5 cercles, filtres intelligents, recherches enregistrées et alertes, carte, feed « Pour toi » (règles), « Près de moi », « Abonnements », « Pourquoi je vois ça ? », plateforme de tests A/B | P2 |
| **P4** | Commande, paiement, séquestre | Panier multi-vendeurs, offres et contre-offres, lots, checkout, prestataire de paiement (Connect), séquestre, grand livre complet, frais et commissions, factures, onboarding vendeur KYC/KYB, solde et versements | P2, P3 |
| **P5** | Remise et après-vente | Remise en main propre avec code, expédition (Boxtal/Sendcloud), points relais, suivi, vérification vidéo avant envoi, confirmation de réception, libération auto 48 h, rétractation 14 jours (pros), retours, litiges, avis vérifiés | P4 |
| **P6** | Messagerie et anti-contournement | Messagerie temps réel (WebSocket), pièces jointes, rendez-vous, détection anti-contournement (texte, photo, voix plus tard), sanctions graduées, leviers d'incitation | P1, P4 |
| **P7** | Confiance | Score de confiance /1 000, badges, rangs, Garantie TROVÉLYA, score de risque transactionnel, détection de faux comptes et comptes liés | P5, P6 |
| **P8** | Tour de contrôle et conformité DSA | Console admin complète (7 espaces de la maquette + configuration), signalements, exposés des motifs, recours, rapports de transparence, DAC7, GPSR (rappels produits), double validation | P1 à P7 |
| **P9** | Verticales : immobilier, véhicules, services | Modèle transactionnel par catégorie, fiches et filtres spécialisés, mises en relation (contact, visite, rendez-vous), agenda de visites, comptes pros vérifiés (carte professionnelle immobilière, garages), import d'annonces par flux, estimation de prix (données publiques DVF, cotes véhicules), anti-arnaque spécifique, paiement protégé optionnel pour les véhicules, offres pros (packs d'annonces) | P3, P6, P7, P8 |
| **P10** | Boutiques et Atelier marchand | Abonnements (Particulier/Starter/Pro/Scale/Entreprise), Vitrine (boutique de marque, éditeur par sections, thèmes), domaines et SSL, catalogue pro (variantes, stocks multi-entrepôts, collections), import Shopify et CSV, codes promo, fidélité, analytique marchand, multi-utilisateurs, B2B, e-mails pro | P4 à P8 |
| **P11** | TROVÉLYA Ads | Régie : 7 formats, enchère au second prix avec qualité, paiement au clic ou à la vente, pilote automatique, groupe témoin, garde-fous, tableau de bord annonceur, facturation | P3, P10 |
| **P12** | Enchères | 5 formats (chronométrée, éclair, hollandaise, scellée, multi-lots), moteur à écrivain unique, anti-sniping, enchère auto, réserve, achat immédiat, empreinte bancaire, collusion | P4, P7 |
| **P13** | Live shopping | Diffusion (LiveKit/Mux), produits épinglés, achat dans la vidéo, enchères éclair, chat modéré, co-live, replay chapitré achetable, lives programmés, multidiffusion, soirées de ventes | P12 |
| **P14** | Drops, précommandes, achats groupés, demande inversée | File d'attente équitable, tirage au sort, précommande participative à seuil, prix dégressif collectif, demandes publiées par les acheteurs | P4, P10 |
| **P15** | Communauté | Abonnements sociaux, listes d'envies, collections curatées commissionnées, cercles, shopping entre amis, affiliation, défis et saisons, score d'impact | P3, P7 |
| **P16** | IA avancée | Feed appris v2 (deux tours + classement multi-objectifs), recherche par photo, conversationnelle et vocale, mode Chasse, studio photo, analyste marchand, service client IA, boutique générée, prévisions | P3, P10 |
| **P17** | Vie de l'objet | Passeport produit, royalties de revente aux marques, histoire de l'objet, patrimoine en temps réel, valeur de revente estimée | P4, P10 |
| **P18** | International UE | 24 langues, traduction des annonces, multi-devise, moyens de paiement locaux, étiquette UE, TVA par pays et OSS, vagues 2 et 3 | P4, P10 |
| **P19** | Écosystème | API publique et webhooks, apps tierces en bac à sable, templates vendus par la communauté, annuaire fournisseurs, dropshipping, TROVÉLYA+, campagnes Google/Meta, rapports de tendances | P10, P11 |
| **P20** | Innovations signature | Agents négociateurs, bourse des objets, scan de la maison, échanges en chaîne, préparation des membres copropriétaires | P16, P17 |
| **P21** | Application mobile Expo | iOS et Android, parité fonctionnelle avec le web, live natif, notifications push, scan caméra, publication App Store et Google Play | P0 à P20 |

### 4.4 Mises en ligne

Construire tout le produit ne signifie pas attendre P21 pour avoir des utilisateurs. Le déploiement en production est **continu** ; ce qui est visible au public est contrôlé par les drapeaux de fonctionnalités. Jalons de mise en ligne recommandés, **[À VALIDER]** par Arcel :

| Jalon | Après la phase | Public |
|---|---|---|
| Bêta fermée | P5 | 50 vendeurs et 200 acheteurs invités, Paris |
| Lancement public Paris | P8 | Particuliers et vendeurs pros, Île-de-France |
| Lancement immobilier, véhicules, services | P9 | Île-de-France, puis France |
| Lancement boutiques | P10 | France, Belgique, Luxembourg |
| Lancement Arène | P13 | Enchères et live |
| Vague 2 UE | P18 | 7 pays |
| Apps stores | P21 | iOS et Android |

Aucune fonctionnalité ne passe en production sans : migrations réversibles, tests verts, revue de code, flag désactivable, tableau de bord de surveillance (section 16).

### 4.5 Hors périmètre permanent

- Détenir les fonds en propre ou devenir établissement de paiement.
- Vente hors UE (Suisse, Norvège, Royaume-Uni) avant la couverture des 27 pays.
- Produits financiers, cryptomonnaies, jetons.
- Publicité ciblant des mineurs ou des données sensibles.

---

## 5. Architecture technique

### 5.1 Vue d'ensemble

```
                 ┌──────────────────────────┐        ┌──────────────────────┐
  Navigateur ───▶│ apps/web  (Next.js 15)   │        │ apps/mobile (Expo)   │  ← P21
  (PWA)          │ Vercel, région UE (fra1) │        │ EAS                  │
                 └────────────┬─────────────┘        └──────────┬───────────┘
                              │  HTTPS JSON (REST /v1) + WebSocket (/ws)    │
                              ▼                                             ▼
                 ┌──────────────────────────────────────────────────────────┐
                 │ apps/api  (FastAPI, Python 3.12, uvicorn)  — Railway UE  │
                 │  monolithe modulaire : identity, catalog, search, orders,│
                 │  payments, ledger, fulfillment, disputes, messaging,     │
                 │  trust, moderation, admin, shops, ads, auctions, live…   │
                 └───────┬───────────────┬───────────────┬──────────────────┘
                         │               │               │
               ┌─────────▼──────┐ ┌──────▼──────┐ ┌──────▼─────────────────┐
               │ PostgreSQL 16  │ │ Redis 7     │ │ Workers (arq)           │
               │ PostGIS, H3,   │ │ cache, verrous│ │ jobs, outbox relay,   │
               │ pgvector,      │ │ pub/sub WS, │ │ e-mails, index, score, │
               │ pg_trgm, unaccent│ │ rate limit │ │ webhooks entrants      │
               └────────────────┘ └─────────────┘ └────────────────────────┘
                         │
     Services externes : prestataire de paiement (Connect), Boxtal/Sendcloud,
     stockage objet S3 compatible UE (Cloudflare R2 région UE ou Scaleway),
     e-mail transactionnel (Brevo ou Postmark UE), LiveKit/Mux (P13),
     LLM / vision (API compatibles UE, P2 et P16), Sentry, Grafana/OTel.
```

### 5.2 Choix structurants (ADR à créer en P0)

| # | Décision | Raison |
|---|---|---|
| ADR-0001 | Monolithe modulaire FastAPI, pas de microservices avant P13 | Vitesse d'une petite équipe ; extraction plus tard des modules chauds (enchères, live, feed) |
| ADR-0002 | PostgreSQL unique comme source de vérité, y compris pour le feed, la messagerie et la recherche jusqu'à preuve du contraire. Pas de MongoDB | Transactions ACID, PostGIS, pgvector, un seul système à opérer sur Railway |
| ADR-0003 | Recherche : PostgreSQL (`tsvector` + `pg_trgm` + `pgvector` + PostGIS) en P3 ; passage à Typesense ou OpenSearch quand le p95 dépasse 150 ms ou le catalogue dépasse 2 millions d'annonces actives | Commencer simple, mesurer, extraire |
| ADR-0004 | Contrat API : OpenAPI 3.1 généré par FastAPI, client TypeScript généré (`openapi-typescript` + `openapi-fetch`) dans `packages/api-client` | Un seul contrat, zéro dérive entre front et back |
| ADR-0005 | Argent : centimes entiers (`BIGINT`) + devise ISO ; grand livre en partie double ; idempotence obligatoire | Exactitude comptable, rapprochement avec le prestataire |
| ADR-0006 | Temps réel : WebSocket FastAPI + Redis pub/sub ; un seul écrivain par enchère (verrou Redis + séquence PostgreSQL) | Ordre strict des offres |
| ADR-0007 | Tâches asynchrones : `arq` (Redis) ; motif *transactional outbox* pour tout événement de domaine | Aucun événement perdu ni émis pour une transaction annulée |
| ADR-0008 | Authentification : sessions opaques côté serveur (cookie `HttpOnly`, `Secure`, `SameSite=Lax`) pour le web ; jetons d'accès courts + rafraîchissement rotatif pour le mobile | Révocation immédiate, pas de JWT long |
| ADR-0009 | ORM : SQLAlchemy 2.0 asynchrone (asyncpg) + Alembic ; SQL brut autorisé pour les requêtes de recherche et de grand livre, dans des fonctions testées | Maturité, contrôle des requêtes |
| ADR-0010 | Prestataire de paiement : **[À VALIDER]**. Valeur par défaut d'implémentation : **Stripe Connect** (comptes `Express`/`Custom` via Accounts v2, *separate charges and transfers*), derrière une interface `PaymentProvider` permettant Mangopay ou Adyen | Documentation et outillage ; l'abstraction protège le choix final |

### 5.3 Structure du monorepo

```
trovelya/
├── apps/
│   ├── web/                      # Next.js 15 App Router, TypeScript strict
│   │   ├── app/
│   │   │   ├── [locale]/         # next-intl : fr (défaut), puis 23 langues
│   │   │   │   ├── (public)/     # accueil, catalogue, annonce, boutique, live, profil public
│   │   │   │   ├── (auth)/       # connexion, inscription, vérification
│   │   │   │   ├── (account)/    # compte, commandes, messages, favoris, paramètres
│   │   │   │   ├── (sell)/       # vendre, mes annonces, ventes, solde
│   │   │   │   ├── (studio)/     # Atelier marchand (P10)
│   │   │   │   └── (admin)/      # Tour de contrôle (sous-domaine admin.)
│   │   │   └── api/              # uniquement routes techniques (revalidate, og-image)
│   │   ├── components/
│   │   ├── lib/
│   │   ├── messages/             # fr.json, en.json, …
│   │   └── tests/                # Playwright e2e
│   ├── api/                      # FastAPI
│   │   ├── pyproject.toml        # géré par uv
│   │   ├── src/trovelya/
│   │   │   ├── main.py           # création de l'app, routers, middlewares
│   │   │   ├── core/             # config, db, sécurité, erreurs, pagination, i18n, flags
│   │   │   ├── shared/           # money.py, ids.py, clock.py, events.py, audit.py
│   │   │   ├── modules/
│   │   │   │   ├── identity/     # chaque module : api.py, schemas.py, models.py,
│   │   │   │   ├── catalog/      #   service.py, repository.py, events.py, tasks.py,
│   │   │   │   ├── search/       #   permissions.py, tests/
│   │   │   │   ├── geo/
│   │   │   │   ├── feed/
│   │   │   │   ├── orders/
│   │   │   │   ├── payments/
│   │   │   │   ├── ledger/
│   │   │   │   ├── fulfillment/
│   │   │   │   ├── disputes/
│   │   │   │   ├── reviews/
│   │   │   │   ├── messaging/
│   │   │   │   ├── circumvention/
│   │   │   │   ├── trust/
│   │   │   │   ├── moderation/
│   │   │   │   ├── notifications/
│   │   │   │   ├── admin/
│   │   │   │   ├── compliance/   # DSA, DAC7, GPSR, RGPD
│   │   │   │   ├── shops/        # P10
│   │   │   │   ├── billing/      # abonnements, factures plateforme (P10)
│   │   │   │   ├── ads/          # P11
│   │   │   │   ├── auctions/     # P12
│   │   │   │   ├── live/         # P13
│   │   │   │   ├── drops/        # P14
│   │   │   │   ├── community/    # P15
│   │   │   │   ├── ai/           # P2 (assistance), P16
│   │   │   │   ├── passport/     # P17
│   │   │   │   ├── i18n_market/  # P18 (pays, devises, TVA)
│   │   │   │   ├── platform/     # P19 (API publique, apps, webhooks sortants)
│   │   │   │   └── agents/       # P20
│   │   │   └── workers/          # point d'entrée arq, planification cron
│   │   ├── migrations/           # Alembic
│   │   └── tests/                # tests transverses, fixtures, factories
│   └── mobile/                   # Expo (P21)
├── packages/
│   ├── api-client/               # types + client générés depuis openapi.json
│   ├── ui/                       # composants React partagés web (tokens, icônes)
│   ├── core/                     # logique pure TS partagée (formatage monnaie, distances, validations miroir)
│   ├── config-eslint/
│   ├── config-typescript/
│   └── design-tokens/            # tokens JSON → CSS variables (web) + thème (mobile)
├── infra/
│   ├── docker-compose.yml        # postgres+postgis+pgvector, redis, mailpit, minio
│   └── railway/                  # notes et scripts de déploiement
├── docs/
│   ├── CAHIER_DES_CHARGES.md     # ce document
│   ├── GLOSSARY.md
│   ├── adr/
│   ├── runbooks/
│   └── api/                      # openapi.json versionné
├── .github/workflows/
├── turbo.json
├── pnpm-workspace.yaml
├── CLAUDE.md
└── SKILLS.md
```

### 5.4 Règles de modularité (backend)

1. Un module **possède** ses tables. Aucun autre module n'écrit dedans. La lecture croisée passe par le `service.py` public du module propriétaire, jamais par son `repository.py`.
2. Les interactions entre modules sont soit des **appels de service synchrones** dans la même transaction (cas rares et explicites : `orders` → `ledger`), soit des **événements de domaine** via l'outbox.
3. Couches dans un module : `api.py` (HTTP, validation, permissions) → `service.py` (règles métier, transactions) → `repository.py` (accès SQL). Les règles métier NE DOIVENT PAS être dans `api.py`.
4. Toute fonction de service qui modifie l'état reçoit une `UnitOfWork` (session SQLAlchemy) et ne fait **jamais** de `commit` elle-même : c'est la frontière (route ou job) qui valide.
5. Les appels à des services externes (paiement, transporteur, LLM) passent par des **adaptateurs** (`modules/<x>/adapters/`) derrière une interface `Protocol`, avec une implémentation factice pour les tests.
6. Un test d'architecture (`tests/test_architecture.py`, avec `import-linter`) DOIT échouer si un module importe le `repository` ou les `models` d'un autre module.

### 5.5 Pile et versions

| Domaine | Choix | Version minimale |
|---|---|---|
| Node | Node.js LTS | 22 |
| Gestionnaire JS | pnpm | 9 |
| Orchestration | Turborepo | 2 |
| Web | Next.js (App Router, RSC), React | 15 / 19 |
| Style | Tailwind CSS + variables CSS issues des tokens | 4 |
| Composants accessibles | Radix UI primitives (ou React Aria) | dernière stable |
| Formulaires | React Hook Form + Zod (schémas générés ou miroirs) | — |
| Données côté client | TanStack Query (lectures interactives), RSC pour le rendu initial | 5 |
| i18n | next-intl | 3 |
| Cartes | MapLibre GL + tuiles OpenStreetMap UE (MapTiler/Stadia) | — |
| Tests web | Vitest, Testing Library, Playwright | — |
| Python | CPython | 3.12 |
| Paquets Python | uv | dernière stable |
| API | FastAPI + Pydantic v2 + uvicorn | 0.115+ / 2.x |
| ORM et migrations | SQLAlchemy 2 async + asyncpg + Alembic | 2.0 |
| Jobs | arq | — |
| Lint/format Python | ruff ; typage : pyright strict (ou `ty`) | — |
| Tests Python | pytest, pytest-asyncio, httpx, factory-boy, hypothesis, testcontainers | — |
| Base | PostgreSQL + PostGIS + pgvector + pg_trgm + unaccent + h3-pg | 16 |
| Cache, files | Redis | 7 |
| Observabilité | OpenTelemetry, Sentry, logs JSON (structlog), Grafana Cloud UE ou Better Stack | — |
| Mobile (P21) | Expo SDK courant, Expo Router, EAS | — |

### 5.6 Événements de domaine (outbox)

Table `outbox_events` (section 7). Chaque événement : `id` (UUIDv7), `type` (ex. `order.paid`), `aggregate_type`, `aggregate_id`, `payload` (JSONB, versionné `v`), `occurred_at`, `published_at`. Un worker publie les événements non publiés (ordre par `id`), au moins une fois ; chaque consommateur DOIT être **idempotent** (table `processed_events(consumer, event_id)`).

Catalogue minimal des événements (à compléter phase par phase) :

| Événement | Émis par | Consommateurs |
|---|---|---|
| `user.registered` | identity | notifications, trust, analytics |
| `user.seller_activated` | payments | trust, notifications |
| `listing.published` / `listing.updated` / `listing.withdrawn` / `listing.sold` | catalog | search (réindexation), feed, notifications (alertes), ads |
| `offer.made` / `offer.accepted` / `offer.declined` / `offer.expired` | orders | notifications, messaging |
| `order.created` / `order.paid` / `order.cancelled` | orders | ledger, fulfillment, notifications, trust |
| `escrow.held` / `escrow.released` / `escrow.refunded` | payments | ledger, notifications, trust |
| `handover.confirmed` / `shipment.delivered` | fulfillment | orders (réception), notifications |
| `dispute.opened` / `dispute.resolved` | disputes | payments, trust, notifications |
| `review.published` | reviews | trust, search |
| `message.flagged` | circumvention | moderation, trust |
| `sanction.applied` / `sanction.lifted` | moderation | identity, search (visibilité), notifications |
| `payout.paid` / `payout.failed` | payments | ledger, notifications |
| `auction.bid_placed` / `auction.extended` / `auction.closed` | auctions | live, notifications, orders |
| `live.started` / `live.ended` | live | feed, notifications |

### 5.7 Environnements

| Environnement | API | Web | Base | Usage |
|---|---|---|---|---|
| `local` | docker compose | `pnpm dev` | conteneur PostGIS | Développement |
| `preview` | Railway (environnement éphémère par PR, **[PARAM]** activé si le budget le permet) | Vercel Preview | Base de preview avec données de démo | Revue de PR |
| `staging` | Railway `staging` | Vercel `staging` | Railway Postgres staging | Recette, tests e2e, données anonymisées |
| `production` | Railway `production`, région UE | Vercel production (`fra1`) | Railway Postgres production, sauvegardes PITR | Public |

### 5.8 Variables d'environnement (API)

Toutes lues par `core/config.py` (Pydantic Settings), validées au démarrage. Aucune valeur secrète par défaut. Fichier `.env.example` tenu à jour.

| Variable | Exemple | Description |
|---|---|---|
| `ENV` | `local` | `local`, `preview`, `staging`, `production` |
| `DATABASE_URL` | `postgresql+asyncpg://…` | Connexion principale |
| `DATABASE_READ_URL` | — | Réplique en lecture (optionnelle) |
| `REDIS_URL` | `redis://…` | Cache, verrous, pub/sub, jobs |
| `SECRET_KEY` | 64 octets aléatoires | Signatures internes (liens magiques, CSRF) |
| `SESSION_TTL_DAYS` | `30` | Durée de session web |
| `WEB_ORIGIN` | `https://trovelya.com` | CORS, liens dans les e-mails |
| `ADMIN_ORIGIN` | `https://admin.trovelya.com` | CORS de la Tour de contrôle |
| `PAYMENT_PROVIDER` | `stripe` | `stripe`, `mangopay`, `adyen`, `fake` |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | — | Si Stripe |
| `SHIPPING_PROVIDER` | `boxtal` | `boxtal`, `sendcloud`, `fake` |
| `STORAGE_ENDPOINT`, `STORAGE_BUCKET`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY` | — | Stockage objet UE |
| `CDN_BASE_URL` | — | URL publique des médias |
| `EMAIL_PROVIDER`, `EMAIL_API_KEY`, `EMAIL_FROM` | — | E-mails transactionnels |
| `OAUTH_GOOGLE_CLIENT_ID/SECRET`, `OAUTH_APPLE_*` | — | Connexion sociale |
| `WEBAUTHN_RP_ID`, `WEBAUTHN_RP_NAME` | `trovelya.com` | Passkeys |
| `AI_PROVIDER`, `AI_API_KEY`, `AI_REGION` | — | Vision et LLM (traitement UE exigé) |
| `EMBEDDING_MODEL`, `EMBEDDING_DIM` | `…`, `768` | Recherche sémantique |
| `SENTRY_DSN`, `OTEL_EXPORTER_OTLP_ENDPOINT` | — | Observabilité |
| `FEATURE_FLAGS_DEFAULT` | JSON | Valeurs de flags par défaut |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | — | P13 |

Côté web (`apps/web`) : seules les variables `NEXT_PUBLIC_*` sont exposées au navigateur (`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`, `NEXT_PUBLIC_MAP_STYLE_URL`, `NEXT_PUBLIC_SENTRY_DSN`). Les clés secrètes ne DOIVENT jamais avoir le préfixe `NEXT_PUBLIC_`.

### 5.9 Conventions de code

- **Identifiants** : UUIDv7 (`uuid_utils` en Python, `uuid` v7 en base via fonction `uuid_generate_v7()` ou généré côté application) pour toutes les clés primaires. Exposés tels quels dans l'API. Références lisibles en plus pour l'humain : commandes `TRV-` + 5 à 8 chiffres (ex. `TRV-47790`), litiges `LIT-…`, versements `VER-…`, certificats de passeport `TRV-PP-…`.
- **Dates** : `TIMESTAMPTZ` en UTC en base ; ISO 8601 avec `Z` dans l'API ; affichage dans le fuseau de l'utilisateur (défaut `Europe/Paris`).
- **Horloge** : jamais `datetime.now()` direct dans le métier ; injecter `Clock` (`shared/clock.py`) pour rendre le temps testable.
- **Argent** : type `Money(amount_minor: int, currency: str)` immuable dans `shared/money.py` ; arrondis explicites (`ROUND_HALF_EVEN` interdit pour les frais : utiliser **arrondi au centime supérieur** pour les frais facturés à l'acheteur, **inférieur** pour les montants reversés, documenté dans chaque fonction). Côté TS, `packages/core/money.ts` : entiers uniquement, `Intl.NumberFormat` pour l'affichage.
- **Langue du code** : anglais pour le code, les noms de tables, les commits ; français pour les libellés d'interface (via fichiers de messages) et la documentation.
- **Commits** : Conventional Commits (`feat(orders): …`), une PR par tâche numérotée du plan, PR ≤ 600 lignes modifiées hors fichiers générés.
- **Branches** : `main` protégée ; branches `feat/P4-T07-escrow-release`, `fix/…`.

---

## 6. Expérience utilisateur et design system (web)

### 6.1 Références visuelles

La **maquette interactive** fait référence : https://claude.ai/artifact/N6tHVo5hWWqmPU4ePcFra8 (33 écrans application + 4 écrans web + Tour de contrôle). En cas de doute sur un comportement visuel, reproduire la maquette ; en cas de conflit entre la maquette et une règle métier de ce document, **la règle métier gagne** et l'écart est signalé.

### 6.2 Tokens de design

Fichier source unique : `packages/design-tokens/tokens.json`, compilé en variables CSS (`--trv-*`) et en thème Tailwind.

| Token | Clair | Sombre | Usage |
|---|---|---|---|
| `color.brand` | `#1D2BFF` | `#4D5BFF` | Bleu Trovélya : actions principales, liens, focus |
| `color.brand.hover` | `#1420C8` | `#6A76FF` | Survol |
| `color.brand.soft` | `#D9DDFF` | `#1A1F4D` | Fonds d'accent |
| `color.ink` | `#0B0B0F` | `#F5F5F7` | Texte principal |
| `color.ink.2` | `#3A3A44` | `#C7C7CF` | Texte secondaire |
| `color.ink.3` | `#6E6E77` | `#8E8E96` | Texte tertiaire, légendes (v1.2 : `#86868F` → `#6E6E77` en clair, contraste ≥ 4,5:1 sur `surface` et `surface.2`, WCAG 2.2 AA) |
| `color.surface` | `#FFFFFF` | `#0B0B0F` | Fond de page |
| `color.surface.2` | `#F2F2F7` | `#16161C` | Fonds de blocs |
| `color.line` | `#E5E5EA` | `#2A2A33` | Bordures |
| `color.success` | `#16A34A` | `#22C55E` | Validé, versé |
| `color.warning` | `#F59E0B` | `#FBBF24` | Attention |
| `color.danger` | `#E5484D` | `#FF6369` | Erreur, live, sanction |
| `color.live` | `#FF2D55` | `#FF375F` | Pastille « En direct » |
| `radius.sm/md/lg/xl/pill` | 8 / 12 / 16 / 24 / 999 px | | |
| `space` | échelle 4 px : 4, 8, 12, 16, 20, 24, 32, 40, 48, 64 | | |
| `font.sans` | Geist | | Interface |
| `font.mono` | Geist Mono | | Prix, codes, références, compteurs |
| `shadow.1/2/3` | ombres douces, voir maquette | | Cartes, menus, modales |
| `motion.fast/base/slow` | 120 / 200 / 320 ms, `cubic-bezier(.2,.8,.2,1)` | | Respecter `prefers-reduced-motion` |

**Liquid Glass** (classe `.lg` de la maquette) : fond `rgba(255,255,255,.62)` (sombre : `rgba(22,22,28,.55)`), `backdrop-filter: blur(24px) saturate(180%)`, bordure 1 px `rgba(255,255,255,.5)`, ombre `shadow.2`. Réservé aux barres flottantes (en-tête, barre d'onglets mobile, barre d'enchère live). Fournir une variante opaque si `backdrop-filter` n'est pas supporté ou si `prefers-reduced-transparency`.

**Icônes** : jeu SVG maison bicolore (trait 1,75 px) dans `packages/ui/icons`. Dans le menu, icônes posées dans des **squircles** de 60 px en dégradé par famille (`blue`, `sky`, `teal`, `red`, `orange`, `gold`, `green`, `night`, `ink`), avec pastilles de compteur. Pas de bibliothèque d'icônes générique visible dans l'interface principale.

**Logo** : monogramme « T » (chemin `M4.5 4h15v3.8h-5.6V20.5h-3.8V7.8H4.5z` dans un carré arrondi bleu) + mot-symbole TROVÉLYA ; slogan « La belle trouvaille ».

### 6.3 Principes d'interface

1. **Mobile first** : chaque page est conçue à 360 px puis élargie (points de rupture 640, 768, 1024, 1280, 1440).
2. **Prix total visible** : sur chaque fiche, le total (article + protection + livraison estimée) est affiché avant le paiement (exigence Omnibus et argument de confiance).
3. **Distance toujours affichée** sur les cartes d'annonce, arrondie (« 3 km », « Lyon 5e · 392 km »).
4. **États vides utiles** : jamais de page vide ; proposer l'élargissement, une alerte ou une demande inversée.
5. **Chargements** : squelettes, pas de spinner plein écran ; optimisme pour favoris et suivis.
6. **Accessibilité** : WCAG 2.2 AA (obligation EAA). Contraste ≥ 4,5:1, focus visible, navigation clavier complète, libellés ARIA, cibles ≥ 44 px, sous-titres pour les vidéos.
7. **Performance** : LCP < 2,5 s et INP < 200 ms au 75e centile mobile, CLS < 0,1. Images via `next/image` (AVIF/WebP, tailles adaptées).
8. **SEO** : pages publiques rendues côté serveur ; `schema.org` `Product`, `Offer`, `AggregateRating`, `BreadcrumbList`, `Organization` ; sitemaps segmentés ; URL propres (`/fr/annonce/fleurs-du-mal-1857-<id court>`), balises canoniques et `hreflang`.

### 6.4 Inventaire des écrans web

Les écrans marqués ★ existent dans la maquette.

| # | Route (`/[locale]/…`) | Écran | Phase |
|---|---|---|---|
| W01 ★ | `/` | Accueil web : en-tête avec méga-menu des 16 univers, bandeau live, fil (Pour toi / Près de moi / Abonnements), univers, bloc confiance, pied de page | P2-P3 |
| W02 ★ | `/recherche`, `/c/[categorie]` | Catalogue : filtres (distance, catégories avec compteurs, modes, prix, états, vendeurs vérifiés, main propre), pastilles actives, 4 tris, grille/liste, recherche enregistrée, cercles géographiques, sponsorisés | P3 |
| W03 ★ | `/annonce/[slug]-[id]` | Fiche produit : galerie 5 vues dont vidéo, vendeur et rang, prix et revente estimée, choix main propre/envoi, total recalculé, offre, favori, suivi de prix, onglets Description / Passeport / Historique des prix, similaires | P2-P4 |
| W04 ★ | `/live/[id]` | Live : scène, barre d'enchère (+2/+5/+10), chat masquant les coordonnées, prochains passages, « Me rappeler » | P13 |
| W05 | `/carte` | Carte des annonces et boutiques | P3 |
| W06 | `/connexion`, `/inscription`, `/verifier` | Authentification | P1 |
| W07 | `/bienvenue` | Onboarding : intérêts, tailles, zone, notifications | P1 |
| W08 | `/u/[pseudo]` | Profil public : score, badges, rang, annonces, avis, collections | P1-P7 |
| W09 | `/vendre` | Création d'annonce en 30 s (photo → IA → validation) | P2 |
| W10 | `/compte/annonces` | Mes annonces (brouillons, en ligne, vendues, retirées) | P2 |
| W11 | `/favoris`, `/compte/recherches` | Favoris, recherches enregistrées et alertes | P3 |
| W12 | `/panier`, `/commande/[id]/paiement` | Panier multi-vendeurs, checkout | P4 |
| W13 | `/compte/achats/[id]` | Suivi d'achat : statut, code de remise, suivi colis, confirmer, signaler un problème | P4-P5 |
| W14 | `/compte/ventes/[id]` | Suivi de vente : saisir le code, vidéo de vérification, étiquette | P5 |
| W15 | `/compte/solde` | Solde, versements, factures, relevés | P4 |
| W16 | `/messages`, `/messages/[id]` | Messagerie protégée | P6 |
| W17 | `/compte/litiges/[id]` | Litige : chronologie, preuves, décision | P5 |
| W18 | `/notifications` | Centre de notifications | P3 |
| W19 | `/compte/confiance` | Détail du score, badges, conseils | P7 |
| W20 | `/compte/parametres` | Profil, sécurité (passkeys, sessions), confidentialité, export/suppression, préférences de feed | P1 |
| W21 | `/aide`, `/legal/*` | Centre d'aide, CGU, CGV, confidentialité, cookies, règles, transparence du classement | P1-P8 |
| W22 | `/signaler/[type]/[id]` | Formulaire de signalement DSA | P8 |
| W23 | `/boutique/[slug]` + domaine propre | Vitrine de marque | P10 |
| W24 | `/atelier/*` | Atelier marchand : tableau de bord, produits, stocks, commandes, clients, marketing, analytique, thème, domaines, équipe, abonnement, paramètres | P10 |
| W25 | `/atelier/pub/*` | Gestionnaire de campagnes Ads | P11 |
| W26 | `/encheres`, `/enchere/[id]` | Enchères qui finissent, fiche d'enchère | P12 |
| W27 | `/direct`, `/live/programmer` | Lives en cours et à venir, studio de diffusion web | P13 |
| W28 | `/drops/[id]`, `/groupe/[id]`, `/demandes` | Drops, achats groupés, demandes inversées | P14 |
| W29 | `/cercles/*`, `/collections/*` | Communauté | P15 |
| W30 | `/patrimoine`, `/objet/[passeport]` | Patrimoine, page de l'objet | P17 |
| W31 | `/bourse/[modele]` | Cote et ordres | P20 |
| W32 | `/agents` | Missions des agents négociateurs | P20 |
| W33 | `/developpeurs/*` | Portail API publique | P19 |
| W34 | `/immobilier`, `/immobilier/[vente\|location\|colocation\|saisonnier\|bureaux-commerces\|terrains\|parkings]` | Recherche immobilière : carte par défaut, dessin de zone, filtres (prix, surface, pièces, DPE, extérieur, étage, ascenseur, meublé, charges), alertes | P9 |
| W35 | `/annonce/[slug]-[id]` (gabarit immobilier) | Fiche bien : galerie, plan, visite virtuelle, DPE/GES en étiquettes, coût annuel d'énergie, surface, charges, honoraires, copropriété, quartier, estimation du prix au m² du secteur, « Demander une visite » | P9 |
| W36 | `/vehicules`, `/annonce/…` (gabarit véhicule) | Recherche et fiche véhicule : filtres (marque, modèle, année, km, carburant, boîte, Crit'Air), contrôle technique, historique, cote estimée, « Contacter », « Réserver un essai », paiement protégé optionnel | P9 |
| W37 | `/services`, `/annonce/…` (gabarit service) | Prestataires près de chez soi, tarifs, zone d'intervention, avis, demande de devis ou de rendez-vous | P9 |
| W38 | `/compte/visites`, `/compte/demandes` | Agenda des visites et rendez-vous (côté annonceur et côté demandeur), demandes reçues | P9 |
| W39 | `/pro/immobilier`, `/pro/auto` | Espace pro des verticales : flux d'import, packs d'annonces, statistiques de contacts | P9 |
| A01-A07 ★ | `admin.…/` | Tour de contrôle : Vue d'ensemble, Utilisateurs, Anti-contournement, Modération, Lives, Finances, Journal d'audit | P8 (+P13 pour Lives) |
| A08 | `admin.…/litiges` | File des litiges | P5/P8 |
| A09 | `admin.…/configuration` | Paramètres plateforme (`platform_settings`), flags, catégories | P8 |
| A10 | `admin.…/conformite` | DSA (transparence, recours), DAC7, GPSR | P8 |

Écrans de l'application mobile de la maquette (Welcome, Main, Menu, Search, Sell, Profile, etc.) : à reproduire en responsive dans le web (mêmes parcours) puis nativement en P21.

### 6.5 Navigation web

- **En-tête** (Liquid Glass, collant) : logo, barre de recherche avec choix de zone (« Paris 11e · 5 km »), bouton « Vendre », favoris, messages (pastille), notifications (pastille), avatar ; méga-menu des **16 univers** (section 8.19) en grille d'icônes squircles, avec les sous-catégories les plus demandées ; **Immobilier**, **Véhicules** et **Services** ont chacun un accès direct dans l'en-tête et une page d'accueil dédiée (recherche par carte pour l'immobilier).
- **Mobile web** : barre d'onglets inférieure (Accueil, Rechercher, Vendre, Messages, Profil) + menu grille (maquette `Menu`).
- **Pied de page** : À propos, Aide, Sécurité, Vendre sur TROVÉLYA, Boutiques, Légal, sélecteur de langue/pays, « © 2026 TROVÉLYA · La belle trouvaille ».


---

## 7. Modèle de données PostgreSQL

### 7.1 Conventions

- Schéma PostgreSQL unique `public` en P0 ; un **préfixe par module n'est pas utilisé**, mais chaque table appartient à un module (colonne « Module » ci-dessous) et la migration qui la crée vit dans ce module.
- Noms de tables au pluriel, `snake_case`. Clé primaire `id UUID` (UUIDv7, générée par l'application).
- Colonnes standard sur toute table métier : `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` (trigger `set_updated_at`). **Dans les blocs SQL ci-dessous, la notation abrégée `created_at, updated_at[, deleted_at]` désigne ces colonnes complètes** (`deleted_at TIMESTAMPTZ` nullable) ; ces blocs sont des spécifications, la migration Alembic écrit la forme complète.
- Suppression : **logique** (`deleted_at TIMESTAMPTZ`) pour les contenus utilisateur ; **jamais** de suppression des écritures comptables, commandes, journaux d'audit.
- Montants : `*_minor BIGINT NOT NULL CHECK (… >= 0)` + `currency CHAR(3) NOT NULL DEFAULT 'EUR'`.
- Énumérations : types `ENUM` PostgreSQL pour les statuts stables (avec migration pour ajouter une valeur), `TEXT` + `CHECK` pour les listes susceptibles d'évoluer souvent.
- Toute clé étrangère est indexée. Toute colonne utilisée en filtre fréquent l'est aussi.
- Données personnelles marquées dans le dictionnaire `docs/data/PII.md` (colonne, finalité, durée de conservation) — nécessaire au registre RGPD.
- Extensions à activer dans la première migration : `postgis`, `vector`, `pg_trgm`, `unaccent`, `citext`, `btree_gist`, `h3` + `h3_postgis` (si disponible sur Railway ; sinon calcul H3 côté application et stockage en `BIGINT`).

### 7.2 Socle transverse (P0)

```sql
-- Paramètres métier réglables sans redéploiement
CREATE TABLE platform_settings (
  key          TEXT PRIMARY KEY,                 -- ex. 'fees.buyer_protection.percent_bp'
  value        JSONB NOT NULL,
  description  TEXT NOT NULL,
  updated_by   UUID,                             -- staff
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Historique de chaque changement : via audit_log (action 'settings.update').

CREATE TABLE feature_flags (
  key          TEXT PRIMARY KEY,                 -- ex. 'auctions', 'ads', 'live'
  enabled      BOOLEAN NOT NULL DEFAULT false,
  rollout_pct  SMALLINT NOT NULL DEFAULT 0 CHECK (rollout_pct BETWEEN 0 AND 100),
  allow_user_ids UUID[] NOT NULL DEFAULT '{}',
  countries    CHAR(2)[] NOT NULL DEFAULT '{}',  -- vide = tous
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE outbox_events (
  id             UUID PRIMARY KEY,
  type           TEXT NOT NULL,
  aggregate_type TEXT NOT NULL,
  aggregate_id   UUID NOT NULL,
  payload        JSONB NOT NULL,
  occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at   TIMESTAMPTZ
);
CREATE INDEX outbox_unpublished_idx ON outbox_events (id) WHERE published_at IS NULL;

CREATE TABLE processed_events (
  consumer   TEXT NOT NULL,
  event_id   UUID NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (consumer, event_id)
);

CREATE TABLE idempotency_keys (
  key          TEXT NOT NULL,
  user_id      UUID,
  method       TEXT NOT NULL,
  path         TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  response_status SMALLINT,
  response_body JSONB,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (key, user_id)
);  -- purge après 72 h

CREATE TABLE audit_log (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor_type    TEXT NOT NULL CHECK (actor_type IN ('user','staff','system','api_client')),
  actor_id      UUID,
  approver_id   UUID,                           -- double validation
  action        TEXT NOT NULL,                  -- ex. 'user.suspend', 'refund.create'
  target_type   TEXT NOT NULL,
  target_id     TEXT NOT NULL,
  reason        TEXT,
  before        JSONB,
  after         JSONB,
  ip            INET,
  user_agent    TEXT,
  request_id    TEXT,
  prev_hash     BYTEA,
  hash          BYTEA NOT NULL                  -- SHA-256(prev_hash || ligne canonique)
);
-- Inaltérable : REVOKE UPDATE, DELETE ON audit_log FROM app_role ;
-- trigger qui refuse UPDATE/DELETE ; vérification de chaîne quotidienne (job).
CREATE INDEX audit_target_idx ON audit_log (target_type, target_id, occurred_at DESC);
CREATE INDEX audit_actor_idx  ON audit_log (actor_id, occurred_at DESC);
```

### 7.3 Identité et comptes (P1) — module `identity`

```sql
CREATE TYPE user_status AS ENUM ('active','restricted','suspended','banned','deleted');

CREATE TABLE users (
  id               UUID PRIMARY KEY,
  email            CITEXT NOT NULL UNIQUE,
  email_verified_at TIMESTAMPTZ,
  phone_e164       TEXT UNIQUE,                  -- vérifié par SMS (optionnel P1, obligatoire pour vendre > seuil)
  phone_verified_at TIMESTAMPTZ,
  username         CITEXT NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9_.]{3,30}$'),
  display_name     TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 60),
  avatar_media_id  UUID,
  bio              TEXT CHECK (char_length(bio) <= 500),
  locale           TEXT NOT NULL DEFAULT 'fr-FR',
  timezone         TEXT NOT NULL DEFAULT 'Europe/Paris',
  country_code     CHAR(2) NOT NULL DEFAULT 'FR',
  status           user_status NOT NULL DEFAULT 'active',
  visibility_factor NUMERIC(3,2) NOT NULL DEFAULT 1.00 CHECK (visibility_factor BETWEEN 0 AND 1), -- sanctions niveau 3
  is_staff         BOOLEAN NOT NULL DEFAULT false,
  birth_year       SMALLINT,                     -- contrôle ≥ 18 ans pour vendre et enchérir
  marketing_opt_in BOOLEAN NOT NULL DEFAULT false,
  last_seen_at     TIMESTAMPTZ,
  created_at, updated_at, deleted_at
);

CREATE TABLE auth_identities (                   -- Google, Apple
  id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id),
  provider TEXT NOT NULL CHECK (provider IN ('google','apple')),
  provider_subject TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_subject)
);

CREATE TABLE passkeys (
  id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id),
  credential_id BYTEA NOT NULL UNIQUE, public_key BYTEA NOT NULL,
  sign_count BIGINT NOT NULL DEFAULT 0, transports TEXT[],
  name TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), last_used_at TIMESTAMPTZ
);

CREATE TABLE magic_links (
  id UUID PRIMARY KEY, email CITEXT NOT NULL,
  token_hash BYTEA NOT NULL UNIQUE,              -- SHA-256 du jeton ; jeton jamais stocké en clair
  purpose TEXT NOT NULL CHECK (purpose IN ('login','verify_email','change_email')),
  expires_at TIMESTAMPTZ NOT NULL,               -- 15 min [PARAM]
  consumed_at TIMESTAMPTZ, ip INET, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  token_hash BYTEA NOT NULL UNIQUE,
  kind TEXT NOT NULL CHECK (kind IN ('web','mobile','admin')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  ip INET, user_agent TEXT, device_label TEXT,
  mfa_at TIMESTAMPTZ                             -- dernière preuve forte (passkey) ; requis < 12 h pour actions sensibles
);
CREATE INDEX sessions_user_idx ON sessions (user_id) WHERE revoked_at IS NULL;

CREATE TABLE roles (key TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE permissions (key TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE role_permissions (role_key TEXT REFERENCES roles, permission_key TEXT REFERENCES permissions,
  requires_approval BOOLEAN NOT NULL DEFAULT false, limit_minor BIGINT, PRIMARY KEY (role_key, permission_key));
CREATE TABLE user_roles (user_id UUID REFERENCES users, role_key TEXT REFERENCES roles,
  granted_by UUID, granted_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (user_id, role_key));

CREATE TABLE approval_requests (                 -- double validation
  id UUID PRIMARY KEY, permission_key TEXT NOT NULL, requested_by UUID NOT NULL,
  payload JSONB NOT NULL, reason TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','approved','rejected','expired')),
  decided_by UUID, decided_at TIMESTAMPTZ, expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (decided_by IS NULL OR decided_by <> requested_by)
);

CREATE TABLE addresses (
  id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id),
  label TEXT, full_name TEXT NOT NULL, line1 TEXT NOT NULL, line2 TEXT,
  postal_code TEXT NOT NULL, city TEXT NOT NULL, country_code CHAR(2) NOT NULL,
  phone_e164 TEXT, location GEOGRAPHY(Point,4326),
  is_default_shipping BOOLEAN NOT NULL DEFAULT false,
  created_at, updated_at, deleted_at
);

CREATE TABLE search_zones (                      -- maison, travail, résidence…
  id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id),
  label TEXT NOT NULL,                           -- 'Maison'
  place_name TEXT NOT NULL,                      -- 'Paris 11e'
  center GEOGRAPHY(Point,4326) NOT NULL,
  radius_m INTEGER NOT NULL CHECK (radius_m IN (1000,2000,5000,10000,25000,50000,100000)),
  is_default BOOLEAN NOT NULL DEFAULT false,
  created_at, updated_at
);

CREATE TABLE user_preferences (
  user_id UUID PRIMARY KEY REFERENCES users(id),
  interests TEXT[] NOT NULL DEFAULT '{}',        -- clés de catégories
  sizes JSONB NOT NULL DEFAULT '{}',             -- {"top":"M","shoe_eu":"42"}
  budget_max_minor BIGINT,
  blocked_brands TEXT[] NOT NULL DEFAULT '{}',
  feed_discovery_level SMALLINT NOT NULL DEFAULT 50 CHECK (feed_discovery_level BETWEEN 0 AND 100),
  paused_categories TEXT[] NOT NULL DEFAULT '{}',
  not_now_until TIMESTAMPTZ,                     -- mode « Pas maintenant »
  personalised_feed BOOLEAN NOT NULL DEFAULT true, -- DSA : option sans profilage
  notification_settings JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE consents (                          -- RGPD
  id UUID PRIMARY KEY, user_id UUID REFERENCES users(id), anonymous_id TEXT,
  purpose TEXT NOT NULL,                         -- 'analytics','marketing_email','personalised_ads','location'
  granted BOOLEAN NOT NULL, policy_version TEXT NOT NULL,
  source TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE follows (
  follower_id UUID NOT NULL REFERENCES users(id),
  followee_user_id UUID REFERENCES users(id),
  followee_shop_id UUID,                         -- P10
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(followee_user_id, followee_shop_id) = 1)
);
CREATE UNIQUE INDEX follows_uniq ON follows (follower_id, coalesce(followee_user_id, followee_shop_id));

CREATE TABLE blocks (blocker_id UUID REFERENCES users, blocked_id UUID REFERENCES users,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (blocker_id, blocked_id));

CREATE TABLE data_requests (                     -- export / suppression RGPD
  id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL CHECK (kind IN ('export','erasure')),
  status TEXT NOT NULL CHECK (status IN ('received','processing','completed','refused')),
  result_media_id UUID, refusal_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), completed_at TIMESTAMPTZ
);
```

### 7.4 Vendeurs et prestataire de paiement (P1/P4) — module `payments`

```sql
CREATE TYPE seller_type AS ENUM ('individual','business');
CREATE TYPE kyc_status AS ENUM ('not_started','pending','verified','rejected','restricted');

CREATE TABLE seller_accounts (
  user_id UUID PRIMARY KEY REFERENCES users(id),
  seller_type seller_type NOT NULL,
  provider TEXT NOT NULL,                        -- 'stripe','mangopay','adyen'
  provider_account_id TEXT NOT NULL UNIQUE,
  kyc_status kyc_status NOT NULL DEFAULT 'not_started',
  kyc_requirements JSONB NOT NULL DEFAULT '{}',  -- champs manquants renvoyés par le prestataire
  payouts_enabled BOOLEAN NOT NULL DEFAULT false,
  charges_enabled BOOLEAN NOT NULL DEFAULT false,
  -- Vendeur pro (DSA art. 30 : traçabilité)
  legal_name TEXT, trade_name TEXT, registration_number TEXT, -- SIREN/SIRET ou équivalent UE
  vat_number TEXT, vat_verified_at TIMESTAMPTZ,  -- vérifié via VIES
  legal_address JSONB, contact_email CITEXT, contact_phone TEXT,
  self_certified_compliance_at TIMESTAMPTZ,      -- engagement de ne proposer que des produits conformes
  -- DAC7
  tax_residence_country CHAR(2), tin_encrypted BYTEA, date_of_birth_encrypted BYTEA,
  -- Paramètres
  instant_payout_eligible BOOLEAN NOT NULL DEFAULT false,
  handling_time_days SMALLINT NOT NULL DEFAULT 2 CHECK (handling_time_days BETWEEN 1 AND 10),
  vacation_until DATE,
  created_at, updated_at
);
```

Chiffrement applicatif (`tin_encrypted`, `date_of_birth_encrypted`) : AES-256-GCM avec clé gérée hors base (variable `FIELD_ENCRYPTION_KEY`, rotation documentée). Aucun IBAN stocké : les comptes bancaires sont chez le prestataire ; seuls `bank_last4` et `bank_country` peuvent être conservés pour l'affichage.

### 7.5 Catalogue (P2) — module `catalog`

```sql
CREATE TABLE categories (
  id UUID PRIMARY KEY, parent_id UUID REFERENCES categories(id),
  key TEXT NOT NULL UNIQUE,                      -- 'books.rare'
  path LTREE NOT NULL,                           -- extension ltree à activer
  names JSONB NOT NULL,                          -- {"fr":"Livres rares","en":"Rare books"}
  icon TEXT, position SMALLINT NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT true,
  requires_verification_video_above_minor BIGINT, -- surcharge du seuil global
  is_restricted BOOLEAN NOT NULL DEFAULT false,  -- catégories soumises à contrôle (ex. couteaux)
  vertical TEXT NOT NULL DEFAULT 'goods' CHECK (vertical IN ('goods','real_estate','vehicles','services')),
  transaction_model TEXT NOT NULL DEFAULT 'protected_purchase'
    CHECK (transaction_model IN ('protected_purchase','contact','mixed')),
  shipping_allowed BOOLEAN NOT NULL DEFAULT true, -- false : véhicules, immobilier, services, meubles volumineux
  protected_payment_cap_minor BIGINT,            -- plafond du paiement protégé en modèle 'mixed'
  listing_fee_minor BIGINT,                      -- annonce payante éventuelle (pros des verticales) [PARAM]
  max_photos SMALLINT NOT NULL DEFAULT 12,       -- 30 pour l'immobilier et les véhicules
  vat_category TEXT NOT NULL DEFAULT 'standard'
);
CREATE INDEX categories_path_gist ON categories USING gist (path);

CREATE TABLE attribute_definitions (
  id UUID PRIMARY KEY, key TEXT NOT NULL UNIQUE,  -- 'size_eu','isbn','edition_year','brand','color','material'
  names JSONB NOT NULL,
  data_type TEXT NOT NULL CHECK (data_type IN ('text','int','decimal','enum','bool','year')),
  enum_values JSONB, unit TEXT
);
CREATE TABLE category_attributes (
  category_id UUID REFERENCES categories, attribute_id UUID REFERENCES attribute_definitions,
  is_required BOOLEAN NOT NULL DEFAULT false, is_filterable BOOLEAN NOT NULL DEFAULT true,
  position SMALLINT NOT NULL DEFAULT 0, PRIMARY KEY (category_id, attribute_id)
);

CREATE TABLE brands (id UUID PRIMARY KEY, name CITEXT NOT NULL UNIQUE, slug TEXT NOT NULL UNIQUE,
  shop_id UUID, is_verified BOOLEAN NOT NULL DEFAULT false);

CREATE TYPE listing_status AS ENUM ('draft','pending_review','active','reserved','sold','withdrawn','removed','expired');
CREATE TYPE item_condition AS ENUM ('new_with_tags','new_without_tags','very_good','good','fair','for_parts');

CREATE TABLE listings (
  id UUID PRIMARY KEY,
  seller_id UUID NOT NULL REFERENCES users(id),
  shop_id UUID,                                  -- P10 : annonce rattachée à une boutique
  product_variant_id UUID,                       -- P10 : lien au catalogue pro (stock unique)
  status listing_status NOT NULL DEFAULT 'draft',
  title TEXT NOT NULL CHECK (char_length(title) BETWEEN 5 AND 120),
  description TEXT NOT NULL CHECK (char_length(description) BETWEEN 20 AND 5000),
  category_id UUID NOT NULL REFERENCES categories(id),
  brand_id UUID REFERENCES brands(id),
  condition item_condition NOT NULL,
  attributes JSONB NOT NULL DEFAULT '{}',        -- validé contre category_attributes
  price_minor BIGINT NOT NULL CHECK (price_minor BETWEEN 100 AND 100000000), -- 1 € à 1 000 000 €
  currency CHAR(3) NOT NULL DEFAULT 'EUR',
  original_price_minor BIGINT,                   -- prix barré : soumis à Omnibus (P10 pros)
  quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0),
  accepts_offers BOOLEAN NOT NULL DEFAULT true,
  min_offer_minor BIGINT,                        -- offres refusées automatiquement en dessous
  handover_enabled BOOLEAN NOT NULL DEFAULT true,
  shipping_enabled BOOLEAN NOT NULL DEFAULT true,
  parcel_size TEXT CHECK (parcel_size IN ('xs','s','m','l','xl')),
  weight_g INTEGER,
  location GEOGRAPHY(Point,4326) NOT NULL,       -- position réelle (jamais exposée)
  location_public GEOGRAPHY(Point,4326) NOT NULL,-- position décalée 200-500 m (affichage carte)
  h3_r7 BIGINT NOT NULL, h3_r9 BIGINT NOT NULL,  -- cellules H3 pour pré-filtrage et agrégats
  place_name TEXT NOT NULL,                      -- 'Paris 11e', 'Lyon 5e'
  country_code CHAR(2) NOT NULL,
  sale_modes TEXT[] NOT NULL DEFAULT '{fixed_price}',
  is_boosted_until TIMESTAMPTZ,                  -- remontée d'annonce (P11)
  open_to_swap BOOLEAN NOT NULL DEFAULT false,   -- P20
  passport_id UUID,                              -- P17
  quality_score SMALLINT NOT NULL DEFAULT 0,     -- 0-100 : photos, description, attributs
  search_document TSVECTOR,                      -- titre (A), marque (A), attributs (B), description (C)
  embedding VECTOR(768),                         -- texte + image (P3)
  resale_from_order_item_id UUID,                -- bouton « Revendre »
  published_at TIMESTAMPTZ, sold_at TIMESTAMPTZ, expires_at TIMESTAMPTZ,
  view_count INTEGER NOT NULL DEFAULT 0, favorite_count INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,            -- verrou optimiste
  created_at, updated_at, deleted_at
);
CREATE INDEX listings_active_geo_idx  ON listings USING gist (location) WHERE status = 'active';
CREATE INDEX listings_active_h3_idx   ON listings (h3_r7) WHERE status = 'active';
CREATE INDEX listings_search_idx      ON listings USING gin (search_document);
CREATE INDEX listings_title_trgm_idx  ON listings USING gin (title gin_trgm_ops);
CREATE INDEX listings_embedding_idx   ON listings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX listings_seller_idx      ON listings (seller_id, status, created_at DESC);
CREATE INDEX listings_category_idx    ON listings (category_id, status, published_at DESC);
CREATE INDEX listings_attributes_idx  ON listings USING gin (attributes jsonb_path_ops);

CREATE TABLE media (
  id UUID PRIMARY KEY, owner_id UUID NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL CHECK (kind IN ('image','video','document','audio')),
  purpose TEXT NOT NULL,                         -- 'listing','avatar','verification_video','dispute_evidence','message','shop'
  storage_key TEXT NOT NULL UNIQUE, mime_type TEXT NOT NULL, bytes BIGINT NOT NULL,
  width INTEGER, height INTEGER, duration_ms INTEGER,
  sha256 BYTEA NOT NULL,                         -- doublons, preuve d'intégrité
  perceptual_hash BIGINT,                        -- détection d'images volées/réutilisées
  status TEXT NOT NULL CHECK (status IN ('uploading','processing','ready','rejected')),
  moderation JSONB NOT NULL DEFAULT '{}',        -- résultats (nudité, violence, coordonnées détectées…)
  captured_at TIMESTAMPTZ,                       -- vidéos de vérification : horodatage serveur
  exif_stripped BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), deleted_at TIMESTAMPTZ
);
CREATE TABLE listing_media (listing_id UUID REFERENCES listings, media_id UUID REFERENCES media,
  position SMALLINT NOT NULL, PRIMARY KEY (listing_id, media_id));

CREATE TABLE favorites (user_id UUID REFERENCES users, listing_id UUID REFERENCES listings,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (user_id, listing_id));

CREATE TABLE price_watches (user_id UUID REFERENCES users, listing_id UUID REFERENCES listings,
  target_minor BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (user_id, listing_id));

CREATE TABLE listing_price_history (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  listing_id UUID NOT NULL REFERENCES listings, price_minor BIGINT NOT NULL,
  changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);  -- sert à l'onglet « Historique des prix » et au contrôle Omnibus (prix le plus bas sur 30 jours)

CREATE TABLE ai_listing_suggestions (            -- traçabilité de l'IA (« l'IA propose, l'humain valide »)
  id UUID PRIMARY KEY, user_id UUID NOT NULL, media_ids UUID[] NOT NULL,
  model TEXT NOT NULL, suggestion JSONB NOT NULL, accepted_fields TEXT[],
  latency_ms INTEGER, cost_microeur INTEGER, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 7.6 Recherche, feed et signaux (P3) — modules `search`, `feed`

```sql
CREATE TABLE saved_searches (
  id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users,
  name TEXT, query TEXT, filters JSONB NOT NULL,  -- même schéma que l'API /search
  zone_id UUID REFERENCES search_zones,
  alert_channel TEXT[] NOT NULL DEFAULT '{push,email}',
  alert_frequency TEXT NOT NULL DEFAULT 'instant' CHECK (alert_frequency IN ('instant','daily','weekly','off')),
  last_alerted_at TIMESTAMPTZ, created_at, updated_at
);

CREATE TABLE interaction_events (               -- partitionnée par mois (pg_partman ou partitions natives)
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_id UUID, anonymous_id TEXT, session_id TEXT,
  type TEXT NOT NULL,                            -- 'impression','click','dwell','zoom','favorite','share','add_to_cart','purchase','hide','report'
  surface TEXT NOT NULL,                         -- 'feed_for_you','feed_nearby','search','listing_similar','shop','live'
  listing_id UUID, shop_id UUID, live_id UUID, ad_id UUID,
  position SMALLINT, request_id TEXT, experiment_assignments JSONB,
  value_ms INTEGER,                              -- durée de visionnage
  PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at);
-- Conservation : 13 mois puis agrégation anonyme.

CREATE TABLE user_embeddings (user_id UUID PRIMARY KEY, embedding VECTOR(768) NOT NULL, updated_at TIMESTAMPTZ NOT NULL);

CREATE TABLE experiments (
  key TEXT PRIMARY KEY, description TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('draft','running','stopped')),
  variants JSONB NOT NULL,                       -- [{"key":"control","weight":50},{"key":"b","weight":50}]
  primary_metric TEXT NOT NULL, guardrail_metrics TEXT[] NOT NULL DEFAULT '{}',
  started_at TIMESTAMPTZ, stopped_at TIMESTAMPTZ
);
-- Affectation déterministe : hash(user_id || experiment_key) % 10000.
```

### 7.7 Commandes, offres et paiements (P4) — modules `orders`, `payments`

```sql
CREATE TYPE offer_status AS ENUM ('pending','countered','accepted','declined','expired','cancelled');
CREATE TABLE offers (
  id UUID PRIMARY KEY, listing_id UUID NOT NULL REFERENCES listings,
  buyer_id UUID NOT NULL REFERENCES users, seller_id UUID NOT NULL REFERENCES users,
  parent_offer_id UUID REFERENCES offers,        -- chaîne de contre-offres
  made_by TEXT NOT NULL CHECK (made_by IN ('buyer','seller','buyer_agent','seller_agent')),
  amount_minor BIGINT NOT NULL CHECK (amount_minor > 0), currency CHAR(3) NOT NULL,
  status offer_status NOT NULL DEFAULT 'pending',
  expires_at TIMESTAMPTZ NOT NULL, decided_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX offers_one_pending ON offers (listing_id, buyer_id) WHERE status = 'pending';

CREATE TABLE carts (id UUID PRIMARY KEY, user_id UUID NOT NULL UNIQUE REFERENCES users, updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE cart_items (cart_id UUID REFERENCES carts, listing_id UUID REFERENCES listings,
  quantity INTEGER NOT NULL DEFAULT 1, accepted_offer_id UUID REFERENCES offers,
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (cart_id, listing_id));

CREATE TYPE order_status AS ENUM (
  'pending_payment','paid','awaiting_handover','awaiting_shipment','shipped','delivered',
  'received','completed','cancelled','disputed','refunded','partially_refunded');
CREATE TYPE fulfillment_method AS ENUM ('handover','shipping');
CREATE TYPE sale_channel AS ENUM ('marketplace','own_traffic','live_platform','live_external','auction_platform','auction_external','drop','group_buy','ad_pay_per_sale','agent');

CREATE TABLE orders (
  id UUID PRIMARY KEY,
  reference TEXT NOT NULL UNIQUE,                -- 'TRV-47790'
  buyer_id UUID NOT NULL REFERENCES users, seller_id UUID NOT NULL REFERENCES users,
  shop_id UUID,
  status order_status NOT NULL DEFAULT 'pending_payment',
  fulfillment_method fulfillment_method NOT NULL,
  sale_channel sale_channel NOT NULL,            -- détermine la commission (section 8.2)
  attribution JSONB NOT NULL DEFAULT '{}',       -- source de la vente : surface, ad_id, live_id, lien externe…
  is_b2c BOOLEAN NOT NULL,                       -- vendeur pro → droit de rétractation, TVA
  currency CHAR(3) NOT NULL DEFAULT 'EUR',
  items_total_minor BIGINT NOT NULL,
  shipping_minor BIGINT NOT NULL DEFAULT 0,
  buyer_protection_fee_minor BIGINT NOT NULL DEFAULT 0,
  discount_minor BIGINT NOT NULL DEFAULT 0,
  total_charged_minor BIGINT NOT NULL,           -- = items + shipping + protection - discount
  seller_commission_minor BIGINT NOT NULL DEFAULT 0,
  payment_margin_minor BIGINT NOT NULL DEFAULT 0,
  seller_net_minor BIGINT NOT NULL,              -- = items + shipping(si payé au vendeur) - commission - marge
  vat_breakdown JSONB NOT NULL DEFAULT '{}',
  shipping_address JSONB,                        -- copie figée
  handover_point GEOGRAPHY(Point,4326),          -- lieu de rendez-vous proposé
  paid_at TIMESTAMPTZ, received_at TIMESTAMPTZ, auto_release_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ, cancelled_at TIMESTAMPTZ, cancel_reason TEXT,
  withdrawal_deadline TIMESTAMPTZ,               -- pros : réception + 14 jours
  version INTEGER NOT NULL DEFAULT 1,
  created_at, updated_at,
  CHECK (total_charged_minor = items_total_minor + shipping_minor + buyer_protection_fee_minor - discount_minor)
);
CREATE INDEX orders_buyer_idx  ON orders (buyer_id, created_at DESC);
CREATE INDEX orders_seller_idx ON orders (seller_id, created_at DESC);
CREATE INDEX orders_autorelease_idx ON orders (auto_release_at) WHERE status IN ('delivered','received');

CREATE TABLE order_items (
  id UUID PRIMARY KEY, order_id UUID NOT NULL REFERENCES orders,
  listing_id UUID NOT NULL REFERENCES listings,
  title_snapshot TEXT NOT NULL, image_snapshot_key TEXT,
  unit_price_minor BIGINT NOT NULL, quantity INTEGER NOT NULL CHECK (quantity > 0),
  offer_id UUID REFERENCES offers
);

CREATE TABLE order_status_history (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, order_id UUID NOT NULL REFERENCES orders,
  from_status order_status, to_status order_status NOT NULL,
  actor_type TEXT NOT NULL, actor_id UUID, reason TEXT,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE payment_status AS ENUM ('requires_action','processing','succeeded','failed','cancelled','refunded','partially_refunded');
CREATE TABLE payments (
  id UUID PRIMARY KEY, order_id UUID REFERENCES orders,
  purpose TEXT NOT NULL CHECK (purpose IN ('order','subscription','ad_budget','boost','authentication','swap_adjustment')),
  provider TEXT NOT NULL, provider_payment_id TEXT NOT NULL UNIQUE,
  status payment_status NOT NULL, amount_minor BIGINT NOT NULL, currency CHAR(3) NOT NULL,
  method TEXT,                                   -- 'card','apple_pay','google_pay','sepa','ideal','bancontact',…
  card_brand TEXT, card_last4 TEXT,              -- jamais plus
  failure_code TEXT, risk_score SMALLINT,
  created_at, updated_at
);

CREATE TYPE escrow_status AS ENUM ('held','released','refunded','partially_refunded','frozen');
CREATE TABLE escrows (
  id UUID PRIMARY KEY, order_id UUID NOT NULL UNIQUE REFERENCES orders,
  status escrow_status NOT NULL DEFAULT 'held',
  amount_minor BIGINT NOT NULL,                  -- part due au vendeur (seller_net)
  held_at TIMESTAMPTZ NOT NULL, release_due_at TIMESTAMPTZ,
  released_at TIMESTAMPTZ, frozen_reason TEXT,
  provider_transfer_id TEXT UNIQUE,              -- transfert vers le compte connecté à la libération
  created_at, updated_at
);

CREATE TABLE refunds (
  id UUID PRIMARY KEY, order_id UUID NOT NULL REFERENCES orders, payment_id UUID NOT NULL REFERENCES payments,
  amount_minor BIGINT NOT NULL CHECK (amount_minor > 0), reason TEXT NOT NULL,
  initiated_by UUID, approval_request_id UUID REFERENCES approval_requests,
  provider_refund_id TEXT UNIQUE, status TEXT NOT NULL CHECK (status IN ('pending','succeeded','failed')),
  created_at, updated_at
);

CREATE TABLE payouts (
  id UUID PRIMARY KEY, reference TEXT NOT NULL UNIQUE,   -- 'VER-…'
  seller_id UUID NOT NULL REFERENCES users,
  amount_minor BIGINT NOT NULL CHECK (amount_minor > 0), currency CHAR(3) NOT NULL,
  fee_minor BIGINT NOT NULL DEFAULT 0,           -- virement instantané : 1 %
  speed TEXT NOT NULL CHECK (speed IN ('standard','instant')),
  status TEXT NOT NULL CHECK (status IN ('pending_review','pending','in_transit','paid','failed','cancelled')),
  requires_manual_review BOOLEAN NOT NULL DEFAULT false, -- > seuil [PARAM] 5 000 € ou risque élevé
  approval_request_id UUID REFERENCES approval_requests,
  provider_payout_id TEXT UNIQUE, failure_code TEXT,
  created_at, updated_at
);

CREATE TABLE provider_webhook_events (           -- journal brut des webhooks entrants
  id UUID PRIMARY KEY, provider TEXT NOT NULL, provider_event_id TEXT NOT NULL,
  type TEXT NOT NULL, payload JSONB NOT NULL, signature_valid BOOLEAN NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(), processed_at TIMESTAMPTZ, error TEXT,
  UNIQUE (provider, provider_event_id)
);

CREATE TABLE invoices (                          -- factures émises par TROVÉLYA (frais, commissions, abonnements)
  id UUID PRIMARY KEY, number TEXT NOT NULL UNIQUE, -- séquence continue sans trou par année : 'F2026-000123'
  customer_user_id UUID NOT NULL REFERENCES users, order_id UUID, subscription_id UUID,
  lines JSONB NOT NULL, subtotal_minor BIGINT NOT NULL, vat_minor BIGINT NOT NULL, total_minor BIGINT NOT NULL,
  currency CHAR(3) NOT NULL, issued_at TIMESTAMPTZ NOT NULL, pdf_media_id UUID,
  e_invoice_status TEXT                          -- facturation électronique FR (2026-2027)
);
```

### 7.8 Grand livre en partie double (P0 squelette, P4 complet) — module `ledger`

```sql
CREATE TYPE ledger_account_type AS ENUM ('asset','liability','revenue','expense','equity');

CREATE TABLE ledger_accounts (
  id UUID PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,                     -- ex. 'liability:seller:<user_id>:pending'
  type ledger_account_type NOT NULL,
  currency CHAR(3) NOT NULL,
  owner_user_id UUID,
  description TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ledger_transactions (
  id UUID PRIMARY KEY,
  kind TEXT NOT NULL,                            -- 'order_paid','escrow_released','refund','payout','fee_invoice','chargeback','adjustment'
  reference_type TEXT NOT NULL, reference_id UUID NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,          -- ex. 'order_paid:<order_id>'
  description TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by TEXT NOT NULL                       -- 'system' ou id staff
);

CREATE TABLE ledger_entries (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  transaction_id UUID NOT NULL REFERENCES ledger_transactions,
  account_id UUID NOT NULL REFERENCES ledger_accounts,
  direction CHAR(1) NOT NULL CHECK (direction IN ('D','C')),
  amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
  currency CHAR(3) NOT NULL
);
CREATE INDEX ledger_entries_account_idx ON ledger_entries (account_id, id);

-- Invariant : pour chaque transaction et chaque devise, somme(D) = somme(C).
-- Garanti par un trigger CONSTRAINT DEFERRABLE INITIALLY DEFERRED sur ledger_entries
-- qui vérifie l'équilibre au COMMIT, + test de propriété (hypothesis).
-- Écritures immuables : pas d'UPDATE ni de DELETE (trigger) ; une erreur se corrige par une transaction inverse.

CREATE MATERIALIZED VIEW ledger_balances AS
  SELECT account_id, currency,
         sum(CASE direction WHEN 'D' THEN amount_minor ELSE -amount_minor END) AS debit_balance_minor
  FROM ledger_entries GROUP BY account_id, currency;
-- Rafraîchie par job ; le solde temps réel d'un vendeur est calculé par requête directe sur ses comptes.
```

Plan de comptes (voir écritures types en section 10.4) :

| Code | Type | Rôle |
|---|---|---|
| `asset:provider:clearing` | asset | Fonds encaissés chez le prestataire, non encore répartis |
| `liability:seller:{id}:pending` | liability | Dû au vendeur, en séquestre |
| `liability:seller:{id}:available` | liability | Dû au vendeur, libéré, versable |
| `liability:buyer:{id}:refund_due` | liability | Remboursement en cours |
| `liability:carrier:payable` | liability | Dû aux transporteurs (étiquettes) |
| `asset:receivable:seller:{id}` | asset | Créance sur un vendeur (remboursement après libération, rétrofacturation) |
| `revenue:buyer_protection` | revenue | Frais de protection acheteur |
| `revenue:commission` | revenue | Commissions vendeurs |
| `revenue:payment_margin` | revenue | Marge sur frais de paiement |
| `revenue:instant_payout` | revenue | Frais de virement instantané |
| `revenue:shipping_margin` | revenue | Marge sur étiquettes |
| `revenue:ads` / `revenue:boosts` / `revenue:subscriptions` | revenue | P10-P11 |
| `liability:vat:{country}` | liability | TVA collectée à reverser |
| `expense:provider_fees` | expense | Frais facturés par le prestataire |
| `expense:chargebacks` / `expense:goodwill` | expense | Rétrofacturations, gestes commerciaux |
| `asset:bank:operating` | asset | Compte bancaire de la société (commissions versées) |

### 7.9 Remise, expédition, litiges, avis (P5) — modules `fulfillment`, `disputes`, `reviews`

```sql
CREATE TABLE handovers (
  id UUID PRIMARY KEY, order_id UUID NOT NULL UNIQUE REFERENCES orders,
  code_hash BYTEA NOT NULL,                      -- 6 chiffres, haché avec sel ; affiché uniquement à l'acheteur
  qr_payload_signature BYTEA NOT NULL,
  attempts SMALLINT NOT NULL DEFAULT 0,          -- max 5 [PARAM] puis verrouillage 30 min
  locked_until TIMESTAMPTZ,
  meeting_place_name TEXT, meeting_point GEOGRAPHY(Point,4326), meeting_at TIMESTAMPTZ,
  confirmed_at TIMESTAMPTZ, confirmed_location GEOGRAPHY(Point,4326),
  created_at, updated_at
);

CREATE TABLE shipments (
  id UUID PRIMARY KEY, order_id UUID NOT NULL REFERENCES orders,
  provider TEXT NOT NULL, carrier TEXT NOT NULL,  -- 'colissimo','mondial_relay','chronopost','relais_colis','dhl'
  service TEXT NOT NULL, relay_point_id TEXT, relay_point JSONB,
  label_media_id UUID, tracking_number TEXT, tracking_url TEXT,
  cost_minor BIGINT NOT NULL, price_charged_minor BIGINT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('label_created','dropped_off','in_transit','out_for_delivery','delivered','returned','lost','exception')),
  ship_by TIMESTAMPTZ NOT NULL,                  -- paid_at + handling_time_days
  shipped_at TIMESTAMPTZ, delivered_at TIMESTAMPTZ,
  created_at, updated_at
);
CREATE TABLE shipment_events (id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  shipment_id UUID NOT NULL REFERENCES shipments, status TEXT NOT NULL, label TEXT,
  location TEXT, occurred_at TIMESTAMPTZ NOT NULL, raw JSONB);

CREATE TABLE verification_videos (
  id UUID PRIMARY KEY, order_id UUID NOT NULL REFERENCES orders, media_id UUID NOT NULL REFERENCES media,
  recorded_in_app BOOLEAN NOT NULL,              -- refusée si importée depuis la galerie
  server_received_at TIMESTAMPTZ NOT NULL,
  checklist JSONB NOT NULL,                      -- {"front":true,"back":true,"label":true,"defects":true}
  ai_comparison JSONB,                           -- {"model_match":0.94,"color_match":true,"condition_consistent":true,"serial":"…"}
  ai_verdict TEXT CHECK (ai_verdict IN ('consistent','doubtful','inconsistent')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE dispute_reason AS ENUM ('not_received','not_as_described','damaged','counterfeit','missing_parts','empty_parcel','wrong_item','other');
CREATE TYPE dispute_status AS ENUM ('open','awaiting_seller','awaiting_buyer','under_review','resolved_buyer','resolved_seller','resolved_split','cancelled','escalated');
CREATE TABLE disputes (
  id UUID PRIMARY KEY, reference TEXT NOT NULL UNIQUE, order_id UUID NOT NULL UNIQUE REFERENCES orders,
  opened_by UUID NOT NULL, reason dispute_reason NOT NULL, description TEXT NOT NULL,
  status dispute_status NOT NULL DEFAULT 'open',
  requested_resolution TEXT CHECK (requested_resolution IN ('full_refund_with_return','full_refund_no_return','partial_refund')),
  seller_response_due_at TIMESTAMPTZ NOT NULL,   -- +72 h [PARAM]
  assigned_to UUID, decision TEXT, decision_reason TEXT,
  refund_minor BIGINT, return_required BOOLEAN,
  decided_at TIMESTAMPTZ, created_at, updated_at
);
CREATE TABLE dispute_messages (id UUID PRIMARY KEY, dispute_id UUID NOT NULL REFERENCES disputes,
  author_id UUID NOT NULL, author_role TEXT NOT NULL CHECK (author_role IN ('buyer','seller','staff')),
  body TEXT NOT NULL, media_ids UUID[] NOT NULL DEFAULT '{}', is_internal BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE returns (
  id UUID PRIMARY KEY, order_id UUID NOT NULL REFERENCES orders,
  cause TEXT NOT NULL CHECK (cause IN ('withdrawal_14d','dispute')),
  shipment_id UUID REFERENCES shipments, status TEXT NOT NULL,
  return_shipping_paid_by TEXT NOT NULL CHECK (return_shipping_paid_by IN ('buyer','seller','platform')),
  received_by_seller_at TIMESTAMPTZ, created_at, updated_at
);

CREATE TABLE reviews (
  id UUID PRIMARY KEY, order_id UUID NOT NULL REFERENCES orders,
  author_id UUID NOT NULL REFERENCES users, subject_id UUID NOT NULL REFERENCES users,
  role TEXT NOT NULL CHECK (role IN ('buyer_reviews_seller','seller_reviews_buyer')),
  rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
  criteria JSONB NOT NULL DEFAULT '{}',          -- {"as_described":5,"shipping_speed":4,"communication":5}
  body TEXT CHECK (char_length(body) <= 1000),
  reply_body TEXT, replied_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('published','hidden','removed')),
  published_at TIMESTAMPTZ NOT NULL,             -- publication simultanée : quand les deux ont noté ou à J+14
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (order_id, role)
);
```

### 7.10 Messagerie et anti-contournement (P6) — modules `messaging`, `circumvention`

```sql
CREATE TABLE conversations (
  id UUID PRIMARY KEY, listing_id UUID REFERENCES listings, order_id UUID REFERENCES orders,
  buyer_id UUID NOT NULL REFERENCES users, seller_id UUID NOT NULL REFERENCES users,
  last_message_at TIMESTAMPTZ, buyer_last_read_at TIMESTAMPTZ, seller_last_read_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','archived','locked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (listing_id, buyer_id)
);

CREATE TABLE messages (
  id UUID PRIMARY KEY, conversation_id UUID NOT NULL REFERENCES conversations,
  sender_id UUID NOT NULL REFERENCES users,
  kind TEXT NOT NULL CHECK (kind IN ('text','image','offer','system','meeting_proposal','order_event')),
  body TEXT,                                     -- texte tel qu'affiché (masqué si détection)
  body_original_encrypted BYTEA,                 -- original, chiffré, accessible au staff trust uniquement
  media_ids UUID[] NOT NULL DEFAULT '{}', payload JSONB,
  masked BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), deleted_at TIMESTAMPTZ
);
CREATE INDEX messages_conv_idx ON messages (conversation_id, created_at DESC);

CREATE TABLE circumvention_detections (
  id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users,
  source_type TEXT NOT NULL CHECK (source_type IN ('message','listing','image','live_chat','live_audio','profile')),
  source_id UUID NOT NULL,
  signals TEXT[] NOT NULL,                       -- 'phone','email','iban','payment_app','external_link','social_handle','obfuscated_number','meet_off_app'
  matched_spans JSONB NOT NULL,                  -- positions et extraits pour surlignage (<mark>)
  confidence NUMERIC(4,3) NOT NULL,
  action_taken TEXT NOT NULL CHECK (action_taken IN ('none','masked','warned','blocked','queued')),
  review_status TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending','confirmed','false_positive','auto_confirmed')),
  reviewed_by UUID, reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE circumvention_rules (                -- règles éditables depuis la Tour de contrôle
  key TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('regex','keyword_list','ml_model')),
  pattern TEXT, keywords TEXT[], weight NUMERIC(4,3) NOT NULL, enabled BOOLEAN NOT NULL DEFAULT true,
  updated_by UUID, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 7.11 Confiance et modération (P7-P8) — modules `trust`, `moderation`, `compliance`

```sql
CREATE TABLE trust_scores (
  user_id UUID PRIMARY KEY REFERENCES users,
  seller_score SMALLINT CHECK (seller_score BETWEEN 0 AND 1000),
  buyer_score  SMALLINT CHECK (buyer_score BETWEEN 0 AND 1000),
  seller_components JSONB NOT NULL DEFAULT '{}', buyer_components JSONB NOT NULL DEFAULT '{}',
  level TEXT NOT NULL,                           -- 'new','fair','good','very_good','excellent'
  computed_at TIMESTAMPTZ NOT NULL, window_days SMALLINT NOT NULL DEFAULT 90
);
CREATE TABLE trust_score_history (user_id UUID, computed_on DATE, seller_score SMALLINT, buyer_score SMALLINT,
  PRIMARY KEY (user_id, computed_on));

CREATE TABLE badges (key TEXT PRIMARY KEY, names JSONB NOT NULL, audience TEXT NOT NULL CHECK (audience IN ('seller','buyer','all')),
  criteria JSONB NOT NULL, is_automatic BOOLEAN NOT NULL DEFAULT true, icon TEXT NOT NULL);
CREATE TABLE user_badges (user_id UUID REFERENCES users, badge_key TEXT REFERENCES badges,
  awarded_at TIMESTAMPTZ NOT NULL, revoked_at TIMESTAMPTZ, PRIMARY KEY (user_id, badge_key, awarded_at));

CREATE TABLE user_ranks (user_id UUID PRIMARY KEY REFERENCES users,
  rank TEXT NOT NULL CHECK (rank IN ('bronze','silver','gold','platinum','legend')),
  since TIMESTAMPTZ NOT NULL, next_review_at TIMESTAMPTZ NOT NULL, metrics JSONB NOT NULL);

CREATE TABLE account_links (                     -- comptes liés (même appareil, carte, IP, adresse)
  user_a UUID NOT NULL, user_b UUID NOT NULL, signal TEXT NOT NULL, strength NUMERIC(4,3) NOT NULL,
  first_seen_at TIMESTAMPTZ NOT NULL, PRIMARY KEY (user_a, user_b, signal), CHECK (user_a < user_b));

CREATE TABLE risk_assessments (
  id UUID PRIMARY KEY, subject_type TEXT NOT NULL, subject_id UUID NOT NULL,
  score SMALLINT NOT NULL CHECK (score BETWEEN 0 AND 100), reasons JSONB NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('allow','review','block')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE reports (                           -- signalements DSA (« notice and action »)
  id UUID PRIMARY KEY, reporter_id UUID, reporter_email CITEXT,  -- signalement possible sans compte
  is_trusted_flagger BOOLEAN NOT NULL DEFAULT false,
  target_type TEXT NOT NULL CHECK (target_type IN ('listing','user','message','review','live','shop')),
  target_id UUID NOT NULL,
  category TEXT NOT NULL,                        -- 'counterfeit','prohibited_item','scam','harassment','illegal_content','ip_infringement','dangerous_product','other'
  explanation TEXT NOT NULL, legal_basis TEXT, evidence_media_ids UUID[] NOT NULL DEFAULT '{}',
  good_faith_declared BOOLEAN NOT NULL,
  status TEXT NOT NULL DEFAULT 'received' CHECK (status IN ('received','in_review','actioned','rejected')),
  priority SMALLINT NOT NULL DEFAULT 3,
  handled_by UUID, handled_at TIMESTAMPTZ, decision_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE moderation_decisions (
  id UUID PRIMARY KEY,
  target_type TEXT NOT NULL, target_id UUID NOT NULL, affected_user_id UUID,
  action TEXT NOT NULL,                          -- 'remove','restrict_visibility','demote','suspend','ban','warn','no_action','restore'
  ground TEXT NOT NULL CHECK (ground IN ('illegal_content','terms_violation')),
  legal_or_contractual_reference TEXT NOT NULL,
  facts TEXT NOT NULL,
  automated_detection BOOLEAN NOT NULL, automated_decision BOOLEAN NOT NULL,
  territorial_scope TEXT, duration_days INTEGER,
  decided_by UUID, decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  statement_sent_at TIMESTAMPTZ,                 -- exposé des motifs envoyé (DSA art. 17)
  transparency_db_submitted_at TIMESTAMPTZ       -- base de transparence de la Commission (DSA art. 24§5)
);

CREATE TABLE appeals (                           -- recours internes (DSA art. 20)
  id UUID PRIMARY KEY, decision_id UUID NOT NULL REFERENCES moderation_decisions,
  user_id UUID NOT NULL, explanation TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('received','in_review','upheld','reversed')),
  reviewed_by UUID, outcome_reason TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), closed_at TIMESTAMPTZ
);
-- Trigger obligatoire : reviewed_by ≠ moderation_decisions.decided_by (recours traité par une autre personne).

CREATE TABLE sanctions (
  id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users,
  level SMALLINT NOT NULL CHECK (level BETWEEN 1 AND 4),
  cause TEXT NOT NULL,                           -- 'circumvention','fraud','harassment','prohibited_items','non_payment',…
  detection_ids UUID[] NOT NULL DEFAULT '{}', decision_id UUID REFERENCES moderation_decisions,
  starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ,
  lifted_at TIMESTAMPTZ, lifted_reason TEXT,
  created_by UUID, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE product_recalls (                   -- GPSR
  id UUID PRIMARY KEY, source TEXT NOT NULL,     -- 'safety_gate','rappel_conso','manufacturer'
  external_ref TEXT, product_identifiers JSONB NOT NULL, description TEXT NOT NULL,
  matched_listing_ids UUID[] NOT NULL DEFAULT '{}', notified_buyer_ids UUID[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE dac7_reports (
  id UUID PRIMARY KEY, year SMALLINT NOT NULL, seller_id UUID NOT NULL REFERENCES users,
  sales_count INTEGER NOT NULL, gross_minor BIGINT NOT NULL, fees_minor BIGINT NOT NULL,
  per_quarter JSONB NOT NULL, reportable BOOLEAN NOT NULL,   -- ≥ 30 ventes ou ≥ 2 000 €
  seller_notified_at TIMESTAMPTZ, submitted_at TIMESTAMPTZ,
  UNIQUE (year, seller_id)
);
```

### 7.12 Notifications (P3) — module `notifications`

```sql
CREATE TABLE notifications (
  id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users,
  type TEXT NOT NULL,                            -- 'offer_received','order_paid','handover_reminder','saved_search_match',…
  title TEXT NOT NULL, body TEXT NOT NULL, link TEXT NOT NULL, image_url TEXT,
  data JSONB NOT NULL DEFAULT '{}',
  read_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX notifications_user_idx ON notifications (user_id, created_at DESC);
CREATE TABLE push_subscriptions (id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users,
  kind TEXT NOT NULL CHECK (kind IN ('webpush','expo')), endpoint TEXT NOT NULL UNIQUE,
  keys JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), last_success_at TIMESTAMPTZ);
CREATE TABLE notification_deliveries (id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  notification_id UUID NOT NULL REFERENCES notifications, channel TEXT NOT NULL,
  status TEXT NOT NULL, provider_message_id TEXT, error TEXT, sent_at TIMESTAMPTZ);
```

### 7.13 Modules ultérieurs (P10 à P20) — tables principales

Le détail des colonnes sera produit au début de chaque phase (skill `postgresql-table-design`), en respectant les conventions ci-dessus. Tables attendues :

| Phase | Module | Tables |
|---|---|---|
| P9 | `verticals` | `real_estate_details` (listing_id, transaction : `sale`/`rent`/`flatshare`/`seasonal`, type de bien, surface habitable, surface Carrez, surface terrain, pièces, chambres, étage, ascenseur, extérieurs, stationnement, année de construction, chauffage, `energy_class`, `ghg_class`, coût annuel d'énergie estimé (min-max, année de référence), DPE en cours/vierge, meublé, loyer hors charges, charges, régularisation ou forfait, dépôt de garantie, honoraires (à la charge de qui, montant ou % TTC, prix hors honoraires), copropriété (lots, charges annuelles, procédure en cours), zone d'encadrement et loyer de référence, complément de loyer, date de disponibilité, visite virtuelle), `vehicle_details` (listing_id, type, marque, modèle, version, année, 1re mise en circulation, km, carburant, boîte, puissance fiscale et DIN, Crit'Air, portes, places, couleur, nombre de propriétaires, immatriculation chiffrée + affichage partiel, VIN chiffré, date du contrôle technique et résultat, rapport d'historique fourni, garantie, non gagé déclaré), `service_details` (type, tarif horaire ou forfait, zone d'intervention en km, qualifications, assurance, statut micro-entrepreneur/SIRET), `pro_licenses` (user_id, type : `real_estate_card_t`, `real_estate_card_g`, `car_dealer`, `service_siret`, numéro, autorité, validité, vérifiée le, document), `leads` (listing_id, demandeur, type : `contact`/`visit`/`test_drive`/`quote`, message, statut, créneau), `visit_slots` (listing_id, début, fin, capacité), `visit_bookings`, `listing_feeds` (pro, URL du flux, format, fréquence, dernier import, erreurs), `price_references` (agrégats DVF par secteur et type de bien, cotes véhicules) |
| P10 | `shops` | `shops` (slug, nom, logo, thème, statut, pays, owner), `shop_members` (rôles : owner, admin, editor, support), `shop_domains` (domaine, statut DNS, certificat), `shop_pages`, `shop_sections` (éditeur), `shop_themes`, `products`, `product_variants` (SKU, prix, poids), `inventory_locations`, `inventory_levels`, `collections` (manuelles et automatiques par règles), `customers` (clients propres du marchand, exportables), `discount_codes`, `loyalty_programs`, `loyalty_ledger`, `imports` (Shopify/CSV : statut, mapping, erreurs), `redirects` (SEO après migration), `b2b_price_lists`, `quotes` |
| P10 | `billing` | `plans` (Particulier, Starter, Pro, Scale, Entreprise), `subscriptions`, `subscription_items` (sièges supplémentaires 5 €), `usage_records` (crédits IA), `platform_invoices` (via `invoices`) |
| P11 | `ads` | `ad_accounts`, `ad_campaigns` (objectif, budget journalier, pilote automatique, ROAS cible), `ad_groups`, `ads` (format, créations), `ad_keywords`, `ad_targeting`, `ad_auctions` (journal échantillonné), `ad_impressions`, `ad_clicks`, `ad_conversions`, `ad_holdout_assignments`, `ad_billing_events`, `listing_boosts` |
| P12 | `auctions` | `auctions` (format, début, fin, fin effective, réserve, achat immédiat, pas d'enchère, statut), `bids` (séquence serveur, montant, horodatage µs, auto/manuel), `proxy_bids` (maximum chiffré), `auction_holds` (empreintes bancaires), `auction_lots` (multi-lots), `sealed_bids` |
| P13 | `live` | `live_shows` (programmation, statut, salle LiveKit, replay), `live_show_items` (épinglage, chapitres), `live_viewers`, `live_chat_messages`, `live_moderation_events`, `live_cohosts`, `sales_events` (soirées de ventes) |
| P14 | `drops` | `drops`, `drop_queue_entries`, `drop_draws`, `preorder_campaigns` (seuil, date limite), `preorder_pledges`, `group_buys`, `group_buy_tiers`, `group_buy_members`, `wanted_requests` (demande inversée), `wanted_proposals` |
| P15 | `community` | `circles`, `circle_members`, `circle_posts`, `circle_events`, `collections_boards`, `board_items`, `wishlists`, `shared_carts`, `polls`, `affiliate_links`, `affiliate_commissions`, `quests`, `quest_progress`, `seasons`, `impact_counters` |
| P16 | `ai` | `ai_jobs`, `ai_usage`, `ranking_models` (versions), `feature_store_snapshots`, `hunt_missions` (mode Chasse), `merchant_assistant_threads` |
| P17 | `passport` | `product_passports` (identifiant `TRV-PP-…`, modèle, numéro de série, marque, certificat), `passport_events` (vente, revente, réparation, authentification), `object_story_chapters` (visibilité), `royalty_rules` (marque, pourcentage), `royalty_payments`, `portfolio_items`, `valuations` (quotidiennes) |
| P18 | `i18n_market` | `countries` (devise, TVA, moyens de paiement, transporteurs, langues), `vat_rates` (pays × catégorie × dates), `fx_rates` (taux quotidiens), `translations_cache` (annonces traduites) |
| P19 | `platform` | `api_clients` (OAuth 2.1, scopes), `api_tokens`, `webhook_endpoints`, `webhook_deliveries`, `apps`, `app_installations` (permissions), `templates`, `template_purchases`, `suppliers`, `supplier_reviews`, `rfq_requests`, `plus_memberships` (TROVÉLYA+) |
| P20 | `agents` / `exchange` | `agent_missions` (mandat, plafonds, validation requise), `agent_negotiation_steps`, `market_models` (cote), `market_orders` (ordres d'achat/vente), `market_trades`, `home_scans`, `swap_cycles`, `swap_participants` |


---

## 8. Règles métier (normatives)

Toutes les valeurs marquées **[PARAM]** sont stockées dans `platform_settings` et lues via `core/settings_service.py` (cache Redis 60 s, invalidé à la modification). Les clés sont indiquées entre crochets.

### 8.1 Frais de protection acheteur

S'appliquent aux achats auprès de **vendeurs particuliers** (et aux enchères entre particuliers en P12). Payés par l'acheteur, affichés sur la fiche et au paiement.

```
protection = fixe + ceil(prix_articles × pourcentage)
  fixe        = 70 centimes          [fees.buyer_protection.fixed_minor = 70]
  pourcentage = 5 %                  [fees.buyer_protection.percent_bp = 500]  (points de base)
  plafond     = 15 000 centimes      [fees.buyer_protection.cap_minor = 15000]  (150 €)
protection = min(protection, plafond)
```

- Base : somme des prix des articles de la commande (hors livraison).
- Arrondi : au centime **supérieur** (fonction `ceil_div`).
- Une commande = un seul fixe, même avec plusieurs articles (lot).
- Exemples de test obligatoires :

| Prix articles | Protection attendue |
|---|---|
| 10,00 € | 0,70 + 0,50 = **1,20 €** |
| 18,99 € | 0,70 + 0,9495 → 0,95 = **1,65 €** |
| 240,00 € | 0,70 + 12,00 = **12,70 €** |
| 18 500,00 € | 0,70 + 925,00 = 925,70 → plafond **150,00 €** |

Achat auprès d'un **vendeur pro** : pas de frais de protection acheteur ; la protection est financée par la commission vendeur.

### 8.2 Commissions vendeurs

Déterminées par `orders.sale_channel` au moment de la création de la commande (et figées) :

| Canal (`sale_channel`) | Description | Taux par défaut | Clé |
|---|---|---|---|
| `own_traffic` | Vente sur la boutique du marchand, trafic apporté par lui (lien direct, domaine, campagne externe) | **0 %** | `commission.own_traffic_bp = 0` |
| `marketplace` | Vente apportée par le feed, la recherche, la Place | **5 à 8 %** selon le rang (Bronze 8 %, Argent 7 %, Or 6 %, Platine 5,5 %, Légende 5 %) | `commission.marketplace_bp_by_rank` |
| `live_platform`, `auction_platform` | Live ou enchère, spectateurs venus de TROVÉLYA | **10 %** | `commission.live_platform_bp = 1000` |
| `live_external`, `auction_external` | Live ou enchère, spectateurs venus d'un lien externe du marchand | **5 %** | `commission.live_external_bp = 500` |
| `drop`, `group_buy` | Drops et achats groupés | **5 à 8 %** (comme `marketplace`) | — |
| `ad_pay_per_sale` | Vente issue d'une annonce payée à la vente | **0 %** de commission (la pub facture déjà 3 à 8 %) | Règle « jamais deux fois » |
| Précommande réussie | — | **5 %** si objectif atteint, 0 % sinon | `commission.preorder_bp = 500` |

Règles :

1. **Plafond par commande : 250 €** [`commission.cap_minor = 25000`]. Levier anti-contournement : les objets chers ne gagnent rien à sortir de la plateforme.
2. **Vendeurs particuliers** : commission **0 %** (ils ne paient que la protection côté acheteur) — sauf `live_*`/`auction_*` en P12-P13 **[À VALIDER]**.
3. **Base** de la commission : prix des articles (hors livraison, hors protection), après remise.
4. **Arrondi** : au centime inférieur (en faveur du vendeur).
5. **Attribution** (« qui a apporté la vente ») : modèle **dernier contact TROVÉLYA sur 7 jours** [`attribution.window_days = 7`] : si l'acheteur a cliqué sur l'article depuis une surface TROVÉLYA (feed, recherche, page similaire, notification d'alerte) dans les 7 jours, canal `marketplace` ; si la session d'achat arrive par un lien marchand traçable (`?ref=shop_<id>` signé ou domaine propre) sans contact TROVÉLYA antérieur, canal `own_traffic`. Le détail de l'attribution est stocké dans `orders.attribution` et visible par le marchand.
6. **Marge sur frais de paiement** : `payment_margin = ceil(total × 0,4 %)` [`fees.payment_margin_bp = 40`], facturée aux vendeurs pros uniquement, détaillée sur la facture.

### 8.3 Abonnements marchands (P10)

| Offre | Prix mensuel | Prix annuel | Inclus |
|---|---|---|---|
| Particulier | 0 € | — | Revente, pas de boutique |
| Starter | 19 € | 190 € | 1 boutique, domaine, feed, live, 2 utilisateurs, 100 crédits IA/mois |
| Pro | 49 € | 490 € | Enchères avancées, IA complète, 5 utilisateurs, B2B, 500 crédits IA |
| Scale | 249 € | 2 490 € | Multi-boutiques, API étendue, 15 utilisateurs, support prioritaire, 3 000 crédits IA |
| Entreprise | Sur devis | — | Hébergement souverain (+99 €/mois), gestionnaire dédié |

Utilisateur supplémentaire : **5 €/mois**. Prix HT, TVA en sus. Essai gratuit 14 jours [PARAM]. Changement d'offre au prorata. Résiliation à la fin de période. Tous ces prix sont des [PARAM] (`billing.plans`).

### 8.4 Autres tarifs (activés par phase)

| Service | Tarif par défaut | Phase |
|---|---|---|
| Remontée d'annonce (particulier) | 0,99 € (24 h), 2,99 € (3 jours), 4,99 € (7 jours) | P11 |
| Virement instantané du solde | 1 % (min 0,50 €), gratuit dès le rang Or | P4 |
| Marge sur étiquette | 0,30 € à 1 € selon transporteur | P5 |
| Produit sponsorisé | Au clic dès 0,05 € ou 3 à 8 % de la vente | P11 |
| Boutique sponsorisée | Au clic dès 0,20 € | P11 |
| Live boosté | Au spectateur gagné dès 0,05 € | P13 |
| Enchère boostée | Au clic ou forfait 1,99 € | P12 |
| Authentification expert | 10 à 30 € par article | P12 |
| Domaine | Prix registrar + 5 €/an | P10 |
| E-mail pro | 3 €/boîte/mois | P10 |
| Crédits IA | Packs dès 9 € | P10 |
| TROVÉLYA+ (acheteur) | 4,99 €/mois | P19 |
| Conversion de devises | 1 à 2 % | P18 |
| Templates, apps tierces | 20 % de commission | P19 |
| Royalties de revente | 15 % de la royalty versée à la marque | P17 |
| Affiliation et collections | 10 % de la commission du créateur | P15 |
| Fournisseur vérifié | 49 €/mois | P19 |
| Rapports de tendances | 199 à 999 €/mois | P19 |
| Sponsoring d'événement | 500 à 10 000 € | P15 |
| Campagnes Google/Meta gérées | 10 % du budget | P19 |

**Règle de cohérence** : un vendeur ne paie jamais deux fois sur la même vente (test d'invariant obligatoire sur le calcul des frais).

### 8.5 Offres et négociation (P4)

- Une offre est possible si `listing.accepts_offers` et `status = active`.
- Montant minimal : `max(listing.min_offer_minor, 50 % du prix)` [`offers.min_ratio_bp = 5000`] ; en dessous, refus immédiat avec message.
- Une seule offre `pending` par couple (annonce, acheteur).
- Expiration : **48 h** [`offers.ttl_hours = 48`].
- Contre-offre : crée une nouvelle offre liée (`parent_offer_id`) ; l'ancienne passe `countered`. Maximum **5 échanges** par négociation [PARAM].
- Offre acceptée : l'article est **réservé 24 h** pour cet acheteur au prix convenu [`offers.reservation_hours = 24`] ; s'il ne paie pas, la réservation tombe et son score acheteur est pénalisé.
- Lots : un acheteur peut regrouper plusieurs articles d'un même vendeur et proposer un prix global ; le vendeur peut définir une remise automatique sur lot (2 articles : −5 %, 3 : −10 %, 5+ : −15 %) [vendeur].

### 8.6 Séquestre et libération (P4-P5)

1. Au paiement réussi : fonds encaissés par la plateforme chez le prestataire (*separate charges and transfers*), écritures « order_paid », séquestre `held`.
2. **Remise en main propre** : la saisie du bon code par le vendeur passe la commande à `received` → libération **immédiate** du séquestre (l'acheteur a vu l'objet avant de donner le code). L'acheteur DOIT être averti à l'écran : « Ne donne ton code qu'après avoir vérifié l'objet ».
3. **Expédition** : à la livraison (`delivered` par le transporteur), un délai de **48 h** démarre [`escrow.auto_release_hours = 48`]. L'acheteur peut confirmer plus tôt (« Tout est OK ») → libération immédiate. Sans action ni litige à l'échéance → libération automatique (job `escrow_auto_release`, toutes les 5 min, idempotent).
4. **Litige ouvert avant l'échéance** → séquestre `frozen` jusqu'à décision.
5. **Non expédié** dans `handling_time_days` (défaut 2 jours ouvrés) + 2 jours de grâce → l'acheteur peut annuler avec remboursement intégral automatique ; au-delà de 7 jours, annulation automatique [`fulfillment.auto_cancel_days = 7`].
6. **Vendeurs pros** : après libération, le droit de rétractation de 14 jours reste ouvert à l'acheteur (section 14) ; un remboursement après libération est prélevé sur le solde disponible du vendeur (ou en dette sur ses prochaines ventes).
7. Libération = écritures `escrow_released` (pending → available) + transfert vers le compte connecté du vendeur.
8. **Rang Or et plus** : possibilité de versement anticipé à l'expédition **[À VALIDER]** (risque supporté par la plateforme).

### 8.7 Remise en main propre (P5)

- Code : 6 chiffres aléatoires (`secrets.randbelow`), généré au paiement, affiché seulement à l'acheteur (écran de suivi + QR code signé HMAC contenant `order_id` et code).
- Le vendeur saisit le code ou scanne le QR depuis son écran de vente.
- 5 tentatives erronées → verrouillage 30 min et alerte au support [`handover.max_attempts = 5`].
- Lieu de rendez-vous : proposé dans la messagerie (`meeting_proposal`), suggestions de **lieux publics** (gares, centres commerciaux, « points de rencontre sûrs » partenaires) [PARAM liste].
- Si le vendeur ne se présente pas : l'acheteur annule → remboursement intégral, pénalité de score vendeur.
- Délai pour réaliser la remise : 7 jours après paiement [`handover.deadline_days = 7`], sinon annulation et remboursement.

### 8.8 Vérification vidéo avant envoi (P5)

- **Obligatoire** si le prix des articles ≥ **150 €** [`verification_video.required_above_minor = 15000`] ou si la catégorie l'exige ; **facultative** en dessous (valorisée par un badge sur la commande).
- Filmée **dans l'application** (capture caméra via `getUserMedia` en web, caméra native en P21) ; l'import depuis la galerie est refusé.
- Durée 15 à 60 s, guidée par une liste : face, dos, étiquette/numéro de série, défauts signalés.
- Horodatage **serveur** à réception ; empreinte SHA-256 stockée ; rattachée à la commande.
- Analyse IA (P5, version simple ; P16, version avancée) : correspondance modèle, couleur, état, numéro de série → verdict `consistent` / `doubtful` / `inconsistent`. Un verdict `inconsistent` bloque la génération de l'étiquette et demande une confirmation au vendeur.
- Visible uniquement par l'acheteur, le vendeur et le support. Conservée 12 mois [PARAM] puis supprimée.
- Sans vidéo obligatoire : impossible de générer l'étiquette.

### 8.9 Litiges (P5)

| Motif | Ouvrable | Preuves requises |
|---|---|---|
| Non reçu | À partir de la date de livraison estimée + 3 jours, jusqu'à 30 jours après | Aucune (suivi transporteur fait foi) |
| Non conforme, endommagé, incomplet, mauvais article, colis vide | Avant libération du séquestre (48 h après livraison) | Photos obligatoires (min 2), vidéo de déballage recommandée |
| Contrefaçon | Jusqu'à 30 jours après réception, même après libération | Photos + éléments ; authentification par expert si nécessaire |

Déroulé :

1. Ouverture → séquestre `frozen`, vendeur notifié, **72 h** pour répondre [`disputes.seller_response_hours = 72`] : accepter le remboursement, proposer un remboursement partiel, contester avec preuves.
2. Sans réponse du vendeur → décision automatique en faveur de l'acheteur.
3. Accord amiable (remboursement partiel accepté par l'acheteur) → résolu.
4. Sinon → `under_review` par le support ; décision sous **5 jours ouvrés** [PARAM], motivée.
5. La **vidéo de vérification** est une preuve prioritaire : si elle montre un objet conforme et que l'acheteur conteste la conformité sans preuve contraire, la décision penche pour le vendeur.
6. Retour exigé : étiquette retour fournie ; payée par le vendeur si non-conformité avérée, par l'acheteur sinon ; remboursement à réception confirmée du retour (ou après 14 jours de suivi « livré »).
7. Décisions possibles : remboursement total avec ou sans retour, partiel, en faveur du vendeur, partage. Montant > 500 € → double validation.
8. Fraude au litige répétée (3 litiges perdus en 90 jours) → revue de compte acheteur.

### 8.10 Avis (P5)

- Seuls l'acheteur et le vendeur d'une commande `completed` peuvent noter, dans les **14 jours** suivant la fin.
- Publication **simultanée** (les deux avis sont révélés quand les deux ont noté, ou à J+14) pour éviter les représailles.
- Le vendeur peut répondre une fois. Aucun avis ne peut être acheté, échangé contre une remise, ni supprimé par le vendeur (directive Omnibus : avis vérifiés).
- Avis retiré seulement pour violation des règles (insultes, données personnelles), par décision de modération motivée.
- Page publique « Comment nous vérifions les avis » (obligation d'information).

### 8.11 Priorité territoriale (P3)

**Zone de l'acheteur** : zone enregistrée par défaut, sinon position GPS (avec accord), sinon géolocalisation IP au niveau de la ville, sinon Paris. Rayon par défaut **5 km** [`geo.default_radius_m = 5000`]. Rayons autorisés : 1, 2, 5, 10, 25, 50, 100 km.

**Cercles** (dans l'ordre strict) :

| Cercle | Clé | Définition |
|---|---|---|
| 1 | `radius` | Distance ≤ rayon choisi |
| 2 | `city` | Même commune (ou agglomération pour Paris, Lyon, Marseille) au-delà du rayon |
| 3 | `region` | Même région administrative (NUTS-2) |
| 4 | `country` | Même pays |
| 5 | `eu` | Reste de l'UE ouverte |

**Algorithme** :

1. Calculer les candidats pertinents (texte + filtres) et leur cercle.
2. Ordonner **d'abord par cercle** (1 avant 2, etc.), **puis** par score de classement à l'intérieur du cercle.
3. Si le cercle 1 contient moins de **10** résultats pertinents [`geo.auto_expand_threshold = 10`], ouvrir automatiquement le cercle suivant, avec le message « Peu d'articles près de toi : voici ceux de ta ville » (et ainsi de suite).
4. Bouton « Élargir la recherche » à la fin de chaque cercle.
5. Bloc spécial « Le plus proche de ce que tu cherches » : au maximum 3 articles très pertinents hors cercle, affichés **après** les résultats du cercle courant, jamais au-dessus.
6. Score intra-cercle : `score = 0,45 × pertinence + 0,20 × proximité + 0,15 × confiance_vendeur + 0,10 × qualité_fiche + 0,10 × compétitivité_prix` [`search.ranking_weights`], où `proximité = 1 − distance / rayon_du_cercle`.

**Confidentialité** :

- Jamais d'adresse exacte affichée ; seulement `place_name` et la distance arrondie : < 1 km → « moins de 1 km » ; < 10 km → arrondi au km ; ≥ 10 km → arrondi à 5 km ; ≥ 100 km → arrondi à 10 km.
- `location_public` = position réelle décalée aléatoirement de 200 à 500 m (décalage fixé une fois par annonce, pas recalculé à chaque requête, pour empêcher la triangulation).
- Le filtrage par distance utilise la position réelle côté serveur, mais la distance renvoyée est calculée sur la position réelle **puis arrondie** ; l'API ne renvoie jamais de coordonnées précises d'un vendeur particulier.

**Livraison suggérée selon la distance** : < 10 km → main propre en premier ; même région → point relais 24-48 h ; France → point relais, domicile ; autre pays UE → étiquette internationale (P18).

### 8.12 Feed v1 (P3)

Fils : **Pour toi** (classé), **Près de moi** (cercle 1 puis 2, classement par fraîcheur et qualité), **Abonnements** (chronologique pur, sans profilage), puis **En direct** (P13) et **Enchères qui finissent** (P12).

Pipeline (skill `recsys-pipeline-architect`) : *Source → Hydratation → Filtre → Score → Sélection → Effets de bord*.

- **Sources** v1 : annonces récentes des catégories d'intérêt, annonces proches, vendeurs suivis, articles similaires aux favoris (pgvector), tendances (favoris/heure), quota découverte (nouveaux vendeurs).
- **Filtres** : déjà vu 3 fois sans interaction, vendeur bloqué, marque bloquée, catégorie en pause, hors budget déclaré ×1,5, vendeur sanctionné (`visibility_factor`), déjà acheté.
- **Score** v1 (règles) : `0,30 × affinité_catégorie + 0,20 × similarité_favoris + 0,15 × proximité + 0,15 × qualité_fiche + 0,10 × confiance_vendeur + 0,10 × fraîcheur`, multiplié par `visibility_factor` du vendeur.
- **Sélection** : diversité (max 2 articles du même vendeur par tranche de 10, max 4 de la même catégorie feuille), **quota découverte** : 1 carte sur 8 réservée aux annonces de vendeurs ayant moins de 5 ventes [`feed.discovery_slot_every = 8`] ; publicité (P11) : max 1 sur 6.
- **« Pourquoi je vois ça ? »** sur chaque carte : raison principale lisible (« Parce que tu as aimé des montres vintage », « À 2 km de toi », « Nouveau vendeur près de chez toi »).
- **Option sans profilage** (DSA art. 38, appliqué volontairement) : bascule « Feed non personnalisé » dans les préférences → tri par fraîcheur et proximité uniquement.
- **Mode « Pas maintenant »** : suspend les notifications marketing et les incitations (compte à rebours, « plus que 1 ») pour une durée choisie.
- Journalisation de chaque requête de feed (`request_id`, candidats servis, affectation d'expérience) pour l'apprentissage en P16.

### 8.13 Score de confiance (P7)

Score de 0 à 1 000, distinct pour le rôle vendeur et le rôle acheteur, recalculé **chaque nuit** (job `trust_recompute`, 02:00 Europe/Paris) sur les **90 derniers jours** glissants [`trust.window_days = 90`]. Nouveau compte : 500 (niveau « Nouveau ») jusqu'à 3 transactions.

**Vendeur** (pondérations [`trust.seller_weights`]) :

| Composant | Poids | Mesure |
|---|---|---|
| Ponctualité d'expédition | 20 % | % des colis expédiés dans le délai annoncé |
| Conformité | 25 % | 1 − (litiges « non conforme » perdus / ventes) |
| Note moyenne | 20 % | Moyenne des avis, ramenée sur 1 (lissage bayésien : a priori 4,5 sur 5 avis) |
| Taux de litige | 15 % | 1 − litiges ouverts / ventes (pénalité doublée si perdus) |
| Réactivité | 10 % | Délai médian de première réponse en messagerie (≤ 1 h = 1 ; ≥ 24 h = 0) |
| Identité vérifiée | 5 % | KYC vérifié = 1 |
| Ancienneté | 5 % | min(1, ancienneté en jours / 365) |

**Acheteur** :

| Composant | Poids | Mesure |
|---|---|---|
| Paiement rapide | 30 % | Paiement des offres acceptées et enchères gagnées dans le délai |
| Taux de litige | 25 % | Litiges ouverts / achats, pénalité si perdus |
| Retours abusifs | 20 % | Rétractations et retours répétés |
| Avis laissés | 10 % | % de commandes notées |
| Identité vérifiée | 10 % | |
| Ancienneté | 5 % | |

`score = round(1000 × Σ poids × composant)`, puis **pénalités** : sanction niveau 2 en cours −50, niveau 3 −150 ; détection de contournement confirmée −30 par cas sur 90 jours.

Niveaux publics : < 400 « À surveiller » (non public, interne), 400-599 « Correct », 600-749 « Bon », 750-849 « Très bon », ≥ 850 « Excellent ». Le **niveau** est public ; le **détail** n'est visible que par l'intéressé, avec des conseils.

**Anti-triche** : les ventes entre comptes liés (`account_links.strength ≥ 0,7`) sont exclues du calcul ; les avis de comptes liés ne comptent pas.

### 8.14 Badges (P7)

Attribués et retirés automatiquement chaque nuit, sauf mention contraire.

| Badge | Clé | Critère |
|---|---|---|
| Vérifié | `verified` | KYC vérifié |
| Top Vendeur | `top_seller` | Top 5 % de sa catégorie principale en ventes sur 90 jours ET score vendeur ≥ 850 |
| Expédition éclair | `fast_shipper` | ≥ 95 % des colis expédiés en < 24 h, min 10 colis sur 90 jours |
| Zéro litige | `zero_dispute` | ≥ 100 ventes sans litige perdu (sur la vie du compte) |
| Vendeur du quartier | `neighborhood_seller` | ≥ 10 remises en main propre réussies sur 90 jours, aucune annulation de son fait |
| Authentifié | `authenticated` | Articles contrôlés par expert partenaire (manuel, P12) |
| Artisan / Fabriqué en France | `artisan`, `made_in_france` | Justificatifs vérifiés (manuel, P10) |
| Acheteur fiable | `reliable_buyer` | ≥ 10 achats, 100 % payés à temps, ≤ 1 retour sur 90 jours |
| Collectionneur | `collector` | ≥ 5 achats dans une même catégorie de collection sur 180 jours |
| Mécène | `patron` | ≥ 3 premiers achats chez de nouveaux vendeurs ou précommandes (P14) |
| Pionnier | `pioneer` | Inscrit pendant la première année d'ouverture publique (définitif) |

### 8.15 Rangs (P7)

Revue **mensuelle** le 1er du mois, sur les 90 derniers jours. Descente d'un seul rang maximum par revue.

| Rang | Ventes réussies (90 j) | Chiffre d'affaires (90 j) | Score vendeur min | Avantages |
|---|---|---|---|---|
| Bronze | 0+ | — | — | Base |
| Argent | 10+ | 500 €+ | 650 | Commission marketplace 7 % |
| Or | 50+ | 3 000 €+ | 750 | Commission 6 %, virement instantané gratuit, visibilité +5 % |
| Platine | 200+ | 15 000 €+ | 820 | Commission 5,5 %, soirées de ventes, support prioritaire, visibilité +10 % |
| Légende | 1 000+ | 75 000 €+ | 880 | Commission 5 %, gestionnaire dédié, accès anticipé aux nouveautés |

Seuils = [PARAM] (`ranks.thresholds`). Côté acheteur, le rang donne : accès anticipé aux drops (Or+), enchères réservées aux acheteurs fiables.

### 8.16 Anti-contournement (P6)

Objectif : rendre la transaction hors application **inutile** (leviers) et **risquée** (détection et sanctions).

**Leviers d'incitation** (chacun activable dans la Tour de contrôle) :

1. Frais payés par l'acheteur (le vendeur particulier reçoit 100 % du prix).
2. Commission plafonnée à 250 €.
3. Protection uniquement dans l'application : remboursement, médiation, vidéo de vérification.
4. Versement rapide au vendeur (libération immédiate en main propre).
5. Le score, les badges, les avis et le rang ne progressent que sur les ventes dans l'application.
6. Points de fidélité acheteurs (P15) sur les achats dans l'application.

**Détection** (module `circumvention`, appliquée **avant** l'affichage d'un message, d'une annonce, d'une description, d'un pseudo, d'un commentaire live) :

| Signal | Méthode | Exemples |
|---|---|---|
| Téléphone | Regex + normalisation (chiffres séparés par espaces, points, tirets, chiffres en lettres) | `06 12 34 56 78`, `zéro six douze…`, `0 6 1 2…` |
| E-mail | Regex + variantes obfusquées | `jean [at] gmail point com` |
| IBAN | Regex + validation clé modulo 97 | `FR76 3000…` |
| Applications de paiement | Liste de mots-clés [`circumvention.payment_keywords`] | WhatsApp, Lydia, PayPal, Telegram, Wero, Revolut, virement, espèces « en direct » |
| Réseaux sociaux | `@pseudo`, `insta`, `snap` | |
| Liens externes | Domaines hors liste blanche | |
| Texte dans les images | OCR sur les photos d'annonce et de message (P6 : OCR simple ; P16 : vision) | Numéro écrit sur un papier |
| Voix des lives | Transcription (P13) | « Envoie-moi un message sur WhatsApp » |
| Intention | Classifieur (P16) | « On peut s'arranger en direct ? » |

Regex de base obligatoire (miroir de la maquette, à enrichir) : `\d(?:[\s.\-]?\d){7,}|whats?app|lydia|paypal|telegram|@|z[ée]ro\s?(six|sept)|iban` (insensible à la casse).

**Actions** : le passage détecté est **masqué** (« ••• coordonnées masquées pour ta sécurité ») ; l'expéditeur voit un rappel pédagogique ; l'original est conservé chiffré pour la revue. Les détections à forte confiance sont enregistrées `auto_confirmed` ; les autres vont en file de revue (Tour de contrôle, espace Anti-contournement, avec preuve surlignée).

**Sanctions graduées** (cas confirmés sur 180 jours glissants) [`circumvention.sanction_ladder`] :

| Niveau | Déclencheur | Mesure |
|---|---|---|
| 1 — Rappel | 1er cas | Message pédagogique, aucune pénalité visible |
| 2 — Avertissement | 2e cas | Avertissement formel (exposé des motifs), −50 au score pendant 30 jours |
| 3 — Visibilité réduite | 3e cas | `visibility_factor = 0,5` pendant 30 jours, badges suspendus, −150 au score |
| 4 — Suspension | 4e cas ou fraude avérée | Suspension du compte (vente et messagerie), double validation obligatoire, recours possible |

Chaque niveau ≥ 2 génère une `moderation_decision` avec exposé des motifs (DSA art. 17) et ouvre un droit de recours. Le staff peut marquer un **faux positif** (annule la détection, retire la sanction associée, et alimente l'amélioration des règles).

### 8.17 Vente : interdits et restrictions (P2)

Liste [PARAM] `catalog.prohibited` (s'applique à tous les univers) : armes et munitions, contrefaçons, médicaments, produits du tabac et vapotage, alcool (sauf vendeurs pros autorisés **[À VALIDER]**), animaux vivants, espèces protégées (ivoire…), contenus pour adultes, données et comptes numériques, titres de transport et billets nominatifs, produits rappelés (GPSR), objets volés, documents d'identité. La modération automatique à la publication (texte + image) bloque ou met en revue (`pending_review`).

### 8.18 Âge et capacité

- Inscription : 15 ans minimum (majorité numérique RGPD en France) ; vendre, acheter, enchérir : **18 ans** (déclaration de l'année de naissance, puis KYC prestataire pour vendre).
- Aucune publicité personnalisée pour les comptes dont l'âge déclaré est < 18 ans.

---

### 8.19 Univers du catalogue et modèles transactionnels (P2, verticales P9)

| # | Univers | Sous-catégories principales (non exhaustif, arbre complet en graine P2-T01) | Verticale | Modèle | Livraison |
|---|---|---|---|---|---|
| 1 | Mode | Femme, Homme, Enfant, Chaussures, Sneakers, Sacs et maroquinerie, Accessoires, Mode vintage, Luxe | goods | Achat protégé | Oui |
| 2 | Montres et bijoux | Montres, Bijoux, Bijoux anciens, Montres de collection | goods | Achat protégé | Oui |
| 3 | Maison et jardin | Meubles, Décoration, Céramique et arts de la table, Luminaires, Linge, Électroménager, Bricolage et outillage, Jardin et piscine | goods | Achat protégé | Oui (sauf volumineux : main propre ou transporteur spécialisé) |
| 4 | High-tech | Téléphones, Ordinateurs, Tablettes, TV et vidéo, Audio et hi-fi, Photo et vidéo, Consoles et jeux vidéo, Objets connectés | goods | Achat protégé | Oui |
| 5 | Culture et loisirs | Livres, Livres rares et éditions originales, BD et mangas, Vinyles et CD, Films, Instruments de musique, Jeux de société, Loisirs créatifs | goods | Achat protégé | Oui |
| 6 | Collection | Cartes à collectionner, Timbres, Monnaies et billets, Figurines, Militaria autorisé, Objets publicitaires, Modélisme | goods | Achat protégé | Oui |
| 7 | Enfants et bébé | Puériculture, Poussettes, Sièges auto, Vêtements, Jouets, Chambre | goods | Achat protégé | Oui |
| 8 | Sport et plein air | Vélos et VAE, Fitness, Sports d'hiver, Glisse, Camping et randonnée, Sports collectifs, Pêche | goods | Achat protégé | Oui |
| 9 | Art, antiquités et artisanat | Tableaux, Sculptures, Photographies d'art, Antiquités, Créations artisanales, Fait main | goods | Achat protégé | Oui |
| 10 | Beauté et bien-être | Parfums, Soins et maquillage neufs scellés, Coiffure, Accessoires | goods | Achat protégé | Oui |
| 11 | Animaux (accessoires) | Accessoires, Aquariophilie (matériel), Équitation | goods | Achat protégé | Oui |
| 12 | Matériel professionnel | BTP, Restauration, Agricole, Bureau, Commerce et boutique, Médical (hors dispositifs réglementés), Industrie | goods | Achat protégé (ou contact au-delà du plafond) | Oui / transporteur |
| 13 | **Véhicules** | Voitures, Motos, Scooters, Utilitaires, Caravanes et camping-cars, Bateaux, Pièces et équipements (auto, moto, bateau) | vehicles | **Mixte** (pièces : achat protégé) | Non (pièces : oui) |
| 14 | **Immobilier** | Vente (appartement, maison, terrain, parking, immeuble, viager), Location (vide, meublée, étudiant), Colocation, Location saisonnière, Bureaux et commerces, Fonds de commerce | real_estate | **Mise en relation** | Non |
| 15 | **Services** | Cours particuliers, Bricolage et réparations, Déménagement, Ménage et repassage, Jardinage, Garde d'animaux, Informatique, Événementiel, Bien-être | services | **Mise en relation** (devis, rendez-vous) | Non |
| 16 | Autres | Billetterie non nominative, Divers | goods | Achat protégé | Oui |

Règles transverses :

1. Le **modèle transactionnel** est porté par la catégorie feuille et hérité par l'annonce ; il pilote l'interface (bouton « Acheter » ou « Contacter / Demander une visite / Demander un devis »), les frais, les règles anti-contournement et la modération.
2. **Achat protégé** : toutes les règles des sections 8.1 à 8.10 s'appliquent.
3. **Mise en relation** : aucun paiement ne transite par TROVÉLYA, donc **ni séquestre, ni frais de protection, ni commission** ; la monétisation vient des options payantes et des offres pros (8.20.6, 8.21.5). Les coordonnées restent masquées jusqu'à ce que l'annonceur accepte la demande (visite, rendez-vous) ; ensuite, l'échange de téléphone est **autorisé** et n'est pas sanctionné (il n'y a pas de commission à contourner). En revanche, la **détection d'arnaques** (8.20.5) s'applique pleinement.
4. **Mixte** (véhicules) : contact et essai d'abord ; l'acheteur PEUT ensuite payer par le paiement protégé (8.21.3).
5. Recherche : l'arbre des univers et les **filtres intelligents** dépendent de la catégorie (`category_attributes`) ; une recherche texte peut renvoyer plusieurs univers, présentés en blocs (« Objets », « Immobilier », « Véhicules »).
6. Priorité territoriale : identique pour tous les univers, avec un rayon par défaut adapté [`geo.default_radius_m_by_vertical`] : objets 5 km, services 10 km, véhicules 50 km, immobilier = zone choisie (ville, arrondissement ou zone dessinée sur la carte).

### 8.20 Verticale Immobilier (P9)

#### 8.20.1 Qui peut publier

| Annonceur | Conditions |
|---|---|
| Particulier (vente ou location de son bien) | Compte vérifié (e-mail + téléphone) ; déclaration sur l'honneur d'être propriétaire ou mandaté ; 3 annonces actives max en location [PARAM] |
| Agence immobilière, mandataire, administrateur de biens | **Carte professionnelle** (carte T « transactions », carte G « gestion ») vérifiée : numéro, CCI de délivrance, validité, garantie financière, assurance RCP ; affichage obligatoire sur les annonces ; SIREN vérifié |
| Promoteur, constructeur | SIREN vérifié, programmes neufs [À VALIDER] |
| Sous-location | Interdite sans accord écrit du propriétaire (case à cocher + justificatif sur demande) |

Une annonce pro publiée par un compte dont la carte n'est pas vérifiée est bloquée en `pending_review`.

#### 8.20.2 Champs obligatoires de l'annonce (France)

- Type de transaction et de bien, adresse (stockée) et **localisation affichée au quartier** par défaut (l'annonceur peut choisir d'afficher l'adresse exacte).
- Surface habitable ; **surface loi Carrez** pour un lot de copropriété en vente ; surface « loi Boutin » en location ; nombre de pièces.
- **DPE** : classe énergie et classe GES (ou mention « DPE vierge / en cours »), **estimation des coûts annuels d'énergie** (fourchette et année de référence) ; mention « logement à consommation énergétique excessive » pour les classes F et G.
- **Vente** : prix ; honoraires d'agence s'ils sont à la charge de l'acquéreur (montant ou pourcentage TTC et prix hors honoraires) ; copropriété : nombre de lots, charges annuelles moyennes, existence d'une procédure en cours.
- **Location** : loyer mensuel charges comprises et montant des charges (provision ou forfait), dépôt de garantie, honoraires à la charge du locataire (dont état des lieux), meublé ou non ; en **zone d'encadrement des loyers** (Paris, Lyon, Lille, Bordeaux, Montpellier… liste [PARAM]) : loyer de référence majoré et éventuel complément de loyer.
- Photos : 3 minimum, 30 maximum ; plan et visite virtuelle (lien vidéo ou 360°) recommandés.

La validation de ces champs est faite par un schéma par sous-catégorie ; les règles exactes et leur mise à jour (évolutions du DPE, des zones d'encadrement) sont **[À VALIDER]** par un juriste immobilier et conservées en [PARAM].

#### 8.20.3 Contrôles automatiques à la publication

1. **Location d'un logement classé G** : refusée (décence énergétique, interdiction de mise en location des nouveaux baux depuis 2025) ; classe F : avertissement (interdiction prévue en 2028) [`real_estate.rent_min_energy_class = 'F'`, À VALIDER].
2. Loyer au-dessus du loyer de référence majoré en zone d'encadrement sans complément justifié : refus avec explication.
3. **Discrimination** : refus des critères illégaux dans le texte (origine, nationalité, religion, situation familiale, handicap, âge…) — liste de motifs et classifieur ; « garant », « revenus » restent autorisés dans les limites légales.
4. Détection de **doublons** (mêmes photos par empreinte perceptuelle, même adresse) et d'annonces **copiées** depuis d'autres sites (arnaques classiques).
5. Prix anormalement bas pour le secteur (écart > 40 % sous la référence DVF ou loyers observés) → `pending_review`.

#### 8.20.4 Mise en relation et visites

- Bouton **« Demander une visite »** : l'annonceur publie des **créneaux** (`visit_slots`) ou valide des demandes libres ; le demandeur réserve ; rappel la veille ; possibilité de visites groupées.
- **Dossier locataire** : TROVÉLYA ne collecte **aucun justificatif** (pièce d'identité, fiches de paie, avis d'imposition) ; le candidat partage un lien vers son dossier **DossierFacile** (service public) [À VALIDER]. Rappel affiché : liste légale des pièces exigibles, interdiction de demander certaines pièces (relevés bancaires, photo d'identité…).
- **Coordonnées** : masquées jusqu'à l'acceptation d'une visite ; ensuite l'annonceur peut choisir de les partager.
- **Aucun argent** : TROVÉLYA n'encaisse jamais de prix de vente, d'acompte, de loyer, de dépôt de garantie ni d'honoraires (le maniement de fonds immobiliers exige des agréments spécifiques ; une vente passe par un notaire).
- Statistiques de l'annonceur : vues, favoris, demandes, visites.

#### 8.20.5 Anti-arnaque immobilière

Arnaques visées : faux propriétaire « à l'étranger », demande de virement ou de mandat cash avant visite, envoi de clés par courrier, faux bail, réservation payante de visite, usurpation d'agence.

- Message affiché sur chaque conversation : « Ne versez jamais d'argent avant d'avoir visité le bien et signé le bail. »
- Détection dans la messagerie et les annonces : demande de paiement avant visite, Western Union, mandat cash, coupons prépayés (PCS, Transcash…), « je suis à l'étranger », « envoi des clés », IBAN étranger, adresses e-mail de domaines jetables → **blocage du message**, alerte au destinataire et file de revue prioritaire.
- Annonceur nouveau + loyer anormalement bas + demande de contact hors application → `review`.
- Usurpation : nom d'agence non vérifié → refus.
- Signalement « Arnaque » en un clic, traité en priorité 1 (< 4 h).

#### 8.20.6 Monétisation immobilier [PARAM, À VALIDER]

| Offre | Tarif indicatif |
|---|---|
| Particulier — annonce de vente ou de location | Gratuite (1 annonce vente + 3 location) |
| Particulier — options | Remontée 9,99 € ; « À la une » 7 jours 19,99 € ; pack visibilité 30 jours 49,99 € |
| Pro Immo Essentiel | 149 €/mois HT : 50 annonces, import par flux, statistiques |
| Pro Immo Illimité | 349 €/mois HT : annonces illimitées, mise en avant d'agence, pages agence, alertes acheteurs qualifiés |
| Location saisonnière | Annonce gratuite ; réservation et paiement intégrés **hors périmètre initial** (réglementation des meublés de tourisme, numéro d'enregistrement obligatoire affiché, plafond de nuitées) — étude en P19 [À VALIDER] |

#### 8.20.7 Outils qui font la différence

- **Recherche par carte** avec dessin de zone, temps de trajet vers une adresse (travail, école) [PARAM, fournisseur d'itinéraires UE].
- **Estimation de prix** à partir des transactions réelles publiques (**DVF**, demandes de valeurs foncières) : prix au m² du secteur, ventes récentes comparables affichées sur la fiche et dans l'outil « Estimer mon bien » (porte d'entrée pour les vendeurs particuliers).
- **Alertes immobilières instantanées** (critère décisif face à la concurrence).
- Quartier : commerces, transports, écoles (données ouvertes).
- Le bien vendu ou loué alimente « Mon patrimoine » (P17) si le propriétaire le souhaite.

### 8.21 Verticale Véhicules (P9)

#### 8.21.1 Champs

Marque, modèle, version (référentiel), année et date de première mise en circulation, kilométrage, carburant, boîte, puissance fiscale et réelle, vignette **Crit'Air**, portes, places, couleur, nombre de propriétaires, équipements, **date et résultat du contrôle technique**, entretien, rapport d'historique (lien vers le rapport officiel partagé par le vendeur, HistoVec en France), garantie (pros), défauts déclarés. Immatriculation et numéro de série (VIN) : stockés chiffrés, affichés partiellement, utilisés pour vérifier la cohérence (marque, modèle, année) via un service de décodage **[À VALIDER : fournisseur]**.

#### 8.21.2 Règles

- Véhicule de plus de 4 ans vendu en France : contrôle technique de moins de 6 mois à fournir à la vente — rappel au vendeur, champ obligatoire à la publication pour les voitures.
- Vendeurs pros (garages, concessionnaires) : SIREN vérifié, garantie légale de conformité mentionnée, prix TTC.
- Kilométrage incohérent avec l'année ou l'historique → `pending_review`.
- Livraison : désactivée (essai et remise en main propre) ; **pièces et équipements** : achat protégé avec livraison.

#### 8.21.3 Paiement protégé optionnel (modèle mixte)

1. Contact, puis **réservation d'un essai** (créneau).
2. Si les deux parties le souhaitent, l'acheteur paie via TROVÉLYA ; les fonds sont en séquestre.
3. Remise du véhicule avec **code de remise** (8.7) au moment de l'échange des clés et des documents ; libération immédiate du séquestre.
4. Plafond [`vehicles.protected_payment_cap_minor = 5000000`] (50 000 €) **[À VALIDER avec le prestataire de paiement]** ; au-delà, rappel des moyens sûrs (virement instantané vérifié en présence des deux parties).
5. Frais : protection acheteur (8.1, plafond 150 €) pour un vendeur particulier ; commission plafonnée à 250 € pour un pro (8.2).
6. **Check-list de cession** générée pour les deux parties : certificat de cession, code de cession, certificat de situation administrative (non-gage), carte grise barrée, déclaration en ligne sur le site officiel — rappels, pas de dépôt de documents chez TROVÉLYA.

#### 8.21.4 Anti-arnaque véhicules

Faux acheteurs « transitaires », chèques de banque falsifiés, vendeurs à l'étranger demandant un acompte, véhicule volé ou gagé : détection des mots-clés (transitaire, chèque de banque à l'avance, acompte, livraison par transporteur pour un véhicule), message de prévention permanent, recommandation du paiement protégé.

#### 8.21.5 Monétisation véhicules [PARAM, À VALIDER]

Particulier : annonce gratuite, options de visibilité (remontée 4,99 €, « À la une » 14,99 €) ; pros : **Pro Auto** 99 €/mois (30 annonces, flux d'import) et 249 €/mois (illimité) ; frais et commission du paiement protégé ; **cote estimée** offerte (prix du marché calculé sur les annonces et ventes TROVÉLYA, puis partenaire) ; partenaires assurance et financement (commission d'apport) en P19.

### 8.22 Verticale Services (P9)

- Prestataires : particuliers (dans les limites légales, ex. cours particuliers, aide ponctuelle) ou professionnels (SIRET vérifié, assurance déclarée). Les activités réglementées (santé, droit, finance, sécurité) sont **interdites** sauf preuve de qualification vérifiée **[À VALIDER]**.
- Fiche : description, tarif (horaire, forfait ou sur devis), zone d'intervention, disponibilités, qualifications, avis vérifiés (après prestation confirmée).
- Mise en relation : demande de devis ou de rendez-vous ; coordonnées après acceptation.
- **Paiement en ligne de la prestation** : hors périmètre P9 (étude en P19 avec le prestataire de paiement : acompte, libération après prestation) [À VALIDER].
- Monétisation : offre **Pro Services** 29 €/mois (visibilité, devis illimités, page prestataire) [PARAM] ; options de remontée.
- Emploi (offres d'emploi) : **non inclus** par défaut (obligations du Code du travail sur les annonces) — décision D18.

### 8.23 Anti-contournement selon le modèle

| Modèle | Échange de coordonnées | Sanction de contournement | Détection d'arnaque |
|---|---|---|---|
| Achat protégé | Masqué, sanctionné (8.16) | Oui | Oui |
| Mixte (véhicules) | Autorisé après acceptation d'un essai | Non | Oui, renforcée |
| Mise en relation (immobilier, services) | Autorisé après acceptation d'une visite ou d'un rendez-vous | Non | Oui, renforcée (8.20.5) |

## 9. Machines à états

Chaque machine à états DOIT être implémentée par une table de transitions explicite (`modules/<x>/state_machine.py`), testée exhaustivement (toutes les transitions autorisées passent, toutes les autres lèvent `InvalidTransition`). Chaque transition est enregistrée dans l'historique et émet un événement.

### 9.1 Annonce (`listing_status`)

```
draft ──publier──▶ pending_review ──validée──▶ active
  │                      └──refusée──▶ removed
  └──publier (risque faible)──────────────────▶ active
active ──offre acceptée / paiement en cours──▶ reserved ──paiement échoué/délai──▶ active
reserved ──commande payée (quantité épuisée)──▶ sold
active ──retirer (vendeur)──▶ withdrawn ──republier──▶ active
active ──modération──▶ removed ──recours accepté──▶ active
active ──120 jours sans modification [PARAM]──▶ expired ──renouveler──▶ active
```

Une annonce `sold` ou `removed` ne revient jamais à `active` sauf `removed` → `active` par recours.

### 9.2 Commande (`order_status`)

```
pending_payment ──paiement réussi──▶ paid
pending_payment ──échec / 30 min──▶ cancelled

paid ──(main propre)──▶ awaiting_handover ──code validé──▶ received
paid ──(expédition)──▶ awaiting_shipment ──étiquette déposée──▶ shipped ──livré──▶ delivered
delivered ──confirmation acheteur OU 48 h──▶ received
received ──libération du séquestre──▶ completed

awaiting_handover / awaiting_shipment ──annulation (délai dépassé, vendeur, acheteur avant expédition)──▶ cancelled (remboursement)
shipped / delivered ──litige──▶ disputed ──décision──▶ completed | refunded | partially_refunded
completed ──rétractation 14 j (pro) ou contrefaçon 30 j──▶ refunded | partially_refunded
```

Règles : `received → completed` est automatique et immédiate (dans la même transaction que la libération). `cancelled`, `refunded` sont terminaux.

### 9.3 Séquestre (`escrow_status`)

```
held ──réception confirmée / délai──▶ released
held ──litige──▶ frozen ──décision vendeur──▶ released
                       ──décision acheteur──▶ refunded
                       ──décision partielle──▶ partially_refunded (+ released pour le reste)
held ──annulation──▶ refunded
```

### 9.4 Litige (`dispute_status`)

```
open ──notification vendeur──▶ awaiting_seller
awaiting_seller ──vendeur accepte──▶ resolved_buyer
awaiting_seller ──vendeur propose partiel──▶ awaiting_buyer ──accepte──▶ resolved_split
                                                            ──refuse──▶ under_review
awaiting_seller ──vendeur conteste──▶ under_review
awaiting_seller ──72 h sans réponse──▶ resolved_buyer
under_review ──décision──▶ resolved_buyer | resolved_seller | resolved_split
under_review ──montant élevé / fraude──▶ escalated ──▶ under_review
open | awaiting_* ──acheteur retire──▶ cancelled
```

### 9.5 Versement (`payouts.status`)

```
pending_review ──approuvé (double validation)──▶ pending
pending ──soumis au prestataire──▶ in_transit ──▶ paid
                                            ──▶ failed ──nouvelle tentative──▶ pending
pending_review / pending ──annulé──▶ cancelled
```

Entrée en `pending_review` si : montant > 5 000 € [`payouts.manual_review_above_minor = 500000`], premier versement d'un compte de moins de 30 jours > 1 000 €, risque ≥ 70, changement récent de coordonnées bancaires (< 72 h).

### 9.6 Offre (`offer_status`)

```
pending ──accepter──▶ accepted
pending ──refuser──▶ declined
pending ──contre-offre──▶ countered (+ nouvelle offre pending)
pending ──48 h──▶ expired
pending ──annonce vendue / retirée / acheteur annule──▶ cancelled
```

### 9.7 Enchère (P12)

```
scheduled ──heure de début──▶ live ──offre dans les 30 dernières secondes──▶ live (fin prolongée de 30 s)
live ──fin──▶ closing ──réserve atteinte──▶ won ──paiement du gagnant (24 h)──▶ settled
                       ──réserve non atteinte / aucune offre──▶ unsold
won ──non-paiement──▶ second_chance (offre au 2e enchérisseur) | unsold
live ──achat immédiat──▶ settled
scheduled | live ──annulation (avant toute offre)──▶ cancelled
```

### 9.8 Live (P13)

```
scheduled ──le vendeur ouvre la salle──▶ backstage ──démarrer──▶ live ──terminer──▶ ended ──traitement──▶ replay_ready
live ──modération──▶ terminated_by_staff
```

### 9.9 Sanction

```
active ──fin de durée──▶ expired
active ──faux positif / recours accepté──▶ lifted
```


---

## 10. Paiements, séquestre et grand livre

### 10.1 Principe

TROVÉLYA **ne détient jamais les fonds** et ne voit **jamais** un numéro de carte. Le prestataire de paiement agréé (établissement de paiement / monnaie électronique) encaisse, conserve et reverse. TROVÉLYA orchestre et **tient un grand livre interne** qui doit se rapprocher au centime près des relevés du prestataire.

### 10.2 Interface `PaymentProvider`

Fichier `modules/payments/adapters/base.py` :

```python
class PaymentProvider(Protocol):
    async def create_connected_account(self, user: SellerOnboardingInput) -> ConnectedAccount: ...
    async def create_onboarding_link(self, account_id: str, return_url: str, refresh_url: str) -> str: ...
    async def get_account_status(self, account_id: str) -> AccountStatus: ...
    async def create_payment(self, *, order_id: UUID, amount: Money, customer_id: str | None,
                             payment_method_types: list[str], idempotency_key: str,
                             metadata: dict[str, str]) -> PaymentIntentResult: ...
    async def capture_payment(self, provider_payment_id: str, idempotency_key: str) -> None: ...
    async def authorize_hold(self, *, amount: Money, customer_id: str, idempotency_key: str) -> HoldResult: ...   # empreinte enchères (P12)
    async def release_hold(self, hold_id: str) -> None: ...
    async def transfer_to_seller(self, *, account_id: str, amount: Money, source_payment_id: str,
                                 idempotency_key: str) -> TransferResult: ...
    async def reverse_transfer(self, transfer_id: str, amount: Money, idempotency_key: str) -> None: ...
    async def refund(self, *, provider_payment_id: str, amount: Money, idempotency_key: str, reason: str) -> RefundResult: ...
    async def create_payout(self, *, account_id: str, amount: Money, speed: Literal["standard","instant"],
                            idempotency_key: str) -> PayoutResult: ...
    def verify_webhook(self, payload: bytes, headers: Mapping[str, str]) -> ProviderEvent: ...
```

Implémentations : `StripeConnectProvider` (défaut), `FakePaymentProvider` (tests et développement local, déterministe, permet de simuler échecs, 3-D Secure, litiges bancaires). `MangopayProvider` / `AdyenProvider` seulement si le choix final l'impose.

### 10.3 Flux de paiement d'une commande

1. `POST /v1/checkout` (idempotent) : verrouille les annonces (`SELECT … FOR UPDATE`), vérifie disponibilité et prix, calcule protection, livraison, commission (section 8), crée `orders` en `pending_payment`, crée le paiement chez le prestataire (montant total, capture automatique), renvoie le `client_secret`.
2. Le navigateur confirme le paiement (Payment Element / Apple Pay / Google Pay, 3-D Secure si demandé).
3. Le **webhook** `payment_intent.succeeded` (source de vérité, pas le retour navigateur) : vérification de signature → journal `provider_webhook_events` → job idempotent `handle_payment_succeeded` → dans **une seule transaction PostgreSQL** : commande `paid`, séquestre `held`, écritures du grand livre, annonces `sold`/quantité décrémentée, code de remise généré, événement `order.paid` dans l'outbox.
4. Le retour navigateur affiche « Paiement en cours de confirmation » puis se met à jour (WebSocket ou interrogation toutes les 2 s, 30 s max).
5. Réservation : les annonces restent `reserved` 30 min pendant `pending_payment` ; au-delà, job d'expiration → `cancelled`, annonces `active`.

Paiement multi-vendeurs : un panier avec plusieurs vendeurs crée **une commande par vendeur** et **un seul paiement** ; les transferts sont faits commande par commande à la libération (`transfer_group` = identifiant du panier).

### 10.4 Écritures types du grand livre

Exemple : vente entre particuliers, article 240,00 €, livraison 6,50 € payée par l'acheteur avec l'étiquette TROVÉLYA (coût transporteur 5,60 €, marge 0,90 €), protection 12,70 €, total encaissé 259,20 €, frais prestataire 3,20 €.

**T1 — `order_paid`** (au paiement) :

| Compte | D | C |
|---|---|---|
| `asset:provider:clearing` | 259,20 | |
| `liability:seller:{s}:pending` | | 240,00 |
| `liability:carrier:payable` | | 5,60 |
| `revenue:shipping_margin` | | 0,90 |
| `revenue:buyer_protection` | | 12,70 |

**T2 — `provider_fee`** (frais du prestataire, à réception du relevé ou du webhook de balance) :

| Compte | D | C |
|---|---|---|
| `expense:provider_fees` | 3,20 | |
| `asset:provider:clearing` | | 3,20 |

**T3 — `escrow_released`** :

| Compte | D | C |
|---|---|---|
| `liability:seller:{s}:pending` | 240,00 | |
| `liability:seller:{s}:available` | | 240,00 |

**T4 — `transfer_to_connected_account`** (transfert vers le compte connecté) :

| Compte | D | C |
|---|---|---|
| `liability:seller:{s}:available` | 240,00 | |
| `asset:provider:clearing` | | 240,00 |

Vendeur pro, canal `marketplace`, rang Bronze (8 %), article 500 € : T1 crédite `liability:seller:pending` de 460,00 et `revenue:commission` de 40,00 ; TVA sur la commission : `revenue:commission` HT + `liability:vat:FR` (la commission est une prestation de TROVÉLYA facturée TTC au vendeur).

**Remboursement total avant libération** : transaction inverse de T1 (D `liability:seller:pending`, D `revenue:buyer_protection` si la protection est remboursée — elle l'est si la faute incombe au vendeur ou à la plateforme [PARAM], C `asset:provider:clearing`).

**Rétrofacturation** (chargeback) : D `expense:chargebacks`, C `asset:provider:clearing` ; si la responsabilité du vendeur est établie, refacturation : D `liability:seller:available` (ou créance `asset:receivable:seller:{s}` si solde insuffisant), C `expense:chargebacks`.

### 10.5 Invariants (tests obligatoires)

1. Chaque transaction est équilibrée par devise (trigger + test de propriété `hypothesis` sur des scénarios aléatoires : paiement, libération, remboursements partiels multiples, litiges, rétrofacturations).
2. Aucune écriture modifiée ou supprimée.
3. Pour toute commande `completed` : `pending` du vendeur pour cette commande = 0.
4. Solde `available` d'un vendeur ≥ 0 sauf créance explicite.
5. Somme des remboursements d'une commande ≤ `total_charged_minor`.
6. **Rapprochement quotidien** (job 04:00) : solde `asset:provider:clearing` = solde du compte plateforme chez le prestataire ± éléments en transit connus ; écart ≠ 0 → alerte P1 à la finance, ligne dans la Tour de contrôle.
7. Chaque écriture porte une `idempotency_key` unique : rejouer un webhook ne crée jamais de doublon.

### 10.6 Onboarding vendeur

- Activation de la vente depuis le profil : choix particulier ou professionnel.
- Création du compte connecté chez le prestataire et redirection vers son parcours hébergé (KYC/KYB, IBAN) — l'application ne collecte pas elle-même les pièces d'identité.
- Webhook `account.updated` → mise à jour de `seller_accounts` (`kyc_status`, `payouts_enabled`, exigences manquantes).
- Un vendeur peut **publier** dès l'activation, mais les **versements** n'ont lieu qu'une fois `payouts_enabled`. Plafond de ventes cumulées avant KYC complet [`kyc.max_unverified_sales_minor = 50000`] (500 €).
- Vendeur pro : informations DSA art. 30 obligatoires avant publication (raison sociale, numéro d'immatriculation, TVA vérifiée via VIES, adresse, contact, auto-certification). Affichées sur sa page.

### 10.7 Versements

- Automatiques : quotidiens [PARAM] pour tout solde disponible ≥ 1 € via le prestataire.
- Instantanés sur demande : 1 % (min 0,50 €), gratuits dès le rang Or.
- Revue manuelle : voir 9.5.

### 10.8 Facturation et TVA (cadre minimal P4, complet P10/P18)

- TROVÉLYA émet des **factures** pour ses propres prestations : frais de protection (à l'acheteur), commissions et marges (au vendeur pro), abonnements, publicité. Numérotation continue sans trou par année.
- Les ventes elles-mêmes sont facturées par le **vendeur pro** (TROVÉLYA génère la facture pour son compte, au nom du vendeur, s'il l'active — mandat de facturation **[À VALIDER]**).
- TVA : taux français par défaut (20 %) sur les services de la plateforme ; règles OSS et « plateforme réputée fournisseur » à valider par l'expert-comptable avant P18 **[À VALIDER]**.
- Facturation électronique (réforme française 2026-2027) : prévoir l'émission au format Factur-X via une plateforme agréée **[À VALIDER]** (champ `e_invoice_status`).

---

## 11. Contrat d'API

### 11.1 Conventions générales

- Base : `https://api.trovelya.com/v1`. Versionnement par chemin ; une version majeure est maintenue 12 mois après la suivante.
- JSON UTF-8, `snake_case` dans les corps (le client TS généré expose les mêmes noms).
- Authentification : cookie de session (`trv_session`) pour le web ; `Authorization: Bearer <access_token>` pour le mobile et l'API publique.
- **CSRF** : pour les requêtes à cookie, en-tête `X-CSRF-Token` obligatoire sur les méthodes non sûres (double-submit cookie signé).
- **Idempotence** : en-tête `Idempotency-Key` (UUID) **obligatoire** sur `POST /checkout`, `/payments/*`, `/offers`, `/payouts`, `/refunds`, `/bids`, et recommandé ailleurs. Même clé + même corps → même réponse (72 h) ; même clé + corps différent → `409 idempotency_conflict`.
- **Verrou optimiste** : ressources modifiables exposent `version` ; `PATCH` exige `If-Match: <version>` → `412 precondition_failed` si obsolète.
- **Langue** : `Accept-Language` pour les messages d'erreur et libellés.
- **Identifiant de requête** : chaque réponse renvoie `X-Request-Id` (propagé dans les logs et traces).
- Montants : toujours `{ "amount_minor": 24000, "currency": "EUR" }`. Jamais de flottant.
- Dates : ISO 8601 UTC.

### 11.2 Format d'erreur (RFC 9457 — Problem Details)

```json
{
  "type": "https://docs.trovelya.com/errors/offer_below_minimum",
  "title": "Offre trop basse",
  "status": 422,
  "code": "offer_below_minimum",
  "detail": "L'offre minimale pour cet article est de 120,00 €.",
  "instance": "/v1/listings/0192…/offers",
  "request_id": "req_01J…",
  "errors": [ { "field": "amount_minor", "code": "too_low", "message": "Minimum 12000" } ]
}
```

Codes HTTP : 400 requête mal formée · 401 non authentifié · 403 interdit (permission) · 404 introuvable (aussi pour ce qu'on n'a pas le droit de voir) · 409 conflit d'état / idempotence · 412 version obsolète · 422 règle métier ou validation · 429 limite de débit (avec `Retry-After`) · 500 erreur interne (jamais de détail technique au client) · 503 maintenance.

Le catalogue des `code` d'erreur est un `enum` Python (`core/errors.py`), exporté dans l'OpenAPI, traduit dans `messages/*.json`.

### 11.3 Pagination, tri, filtres

- Pagination **par curseur** : `?limit=24&cursor=<opaque>` → `{ "data": [...], "next_cursor": "...", "has_more": true }`. `limit` max 100.
- Les listes publiques volumineuses (recherche) renvoient aussi des `facets` et des `rings` (cercles).
- Tri : `?sort=relevance|newest|price_asc|price_desc|distance`.

### 11.4 Limites de débit (Redis, fenêtre glissante)

| Portée | Limite par défaut |
|---|---|
| Anonyme, par IP | 120 req/min |
| Connecté, par utilisateur | 600 req/min |
| `POST /auth/magic-link` | 5/heure par e-mail, 20/heure par IP |
| Messages | 30/min, 500/jour ; 10 nouvelles conversations/heure pour un compte de moins de 7 jours |
| Publication d'annonces | 50/jour (particulier), illimité pro [PARAM] |
| Offres | 30/heure |
| Enchères | 1 offre/s par lot et par utilisateur |
| Code de remise | 5 essais puis verrouillage 30 min |

### 11.5 Points d'accès par domaine (P1 à P8)

Notation : 🔓 public · 🔑 connecté · 🛒 vendeur · 🛡️ staff (permission indiquée).

**Authentification et compte (P1)**

| Méthode | Chemin | Accès | Description |
|---|---|---|---|
| POST | `/auth/magic-link` | 🔓 | Envoie un lien de connexion (réponse identique que l'e-mail existe ou non) |
| POST | `/auth/magic-link/verify` | 🔓 | Échange le jeton → session |
| GET | `/auth/oauth/{provider}/start` · `/callback` | 🔓 | Google, Apple (PKCE, `state`, `nonce`) |
| POST | `/auth/passkeys/register/options` · `/register/verify` | 🔑 | Enregistrer une passkey |
| POST | `/auth/passkeys/login/options` · `/login/verify` | 🔓 | Connexion par passkey |
| POST | `/auth/step-up` | 🔑 | Preuve forte récente pour actions sensibles |
| POST | `/auth/logout` | 🔑 | Révoque la session courante |
| GET | `/me` | 🔑 | Profil privé, rôles, flags actifs, compteurs (messages non lus, notifications) |
| PATCH | `/me` | 🔑 | Pseudo, nom affiché, bio, avatar, langue |
| GET/DELETE | `/me/sessions`, `/me/sessions/{id}` | 🔑 | Sessions actives, révocation |
| GET/POST/PATCH/DELETE | `/me/addresses[/{id}]` | 🔑 | Adresses |
| GET/POST/PATCH/DELETE | `/me/zones[/{id}]` | 🔑 | Zones de recherche |
| GET/PUT | `/me/preferences` | 🔑 | Intérêts, tailles, feed, notifications |
| POST | `/me/consents` | 🔓/🔑 | Enregistre un consentement |
| POST | `/me/data-export` · `/me/erasure` | 🔑 | RGPD (step-up exigé) |
| GET | `/users/{username}` | 🔓 | Profil public |
| POST/DELETE | `/users/{id}/follow` · `/users/{id}/block` | 🔑 | Suivre, bloquer |

**Vendeur (P4)**

| Méthode | Chemin | Accès | Description |
|---|---|---|---|
| POST | `/seller/activate` | 🔑 | Choix particulier/pro, crée le compte connecté |
| GET | `/seller/onboarding-link` | 🔑 | Lien du parcours KYC hébergé |
| GET | `/seller/account` | 🛒 | Statut KYC, exigences, versements activés |
| PUT | `/seller/business-info` | 🛒 | Informations DSA art. 30 (pro) |
| GET | `/seller/balance` | 🛒 | Soldes en séquestre, disponible, en transit |
| GET/POST | `/seller/payouts` | 🛒 | Historique, versement instantané (idempotent) |
| GET | `/seller/invoices` | 🛒 | Factures TROVÉLYA |

**Catalogue (P2)**

| Méthode | Chemin | Accès | Description |
|---|---|---|---|
| GET | `/categories` | 🔓 | Arbre, attributs par catégorie (cache CDN 1 h) |
| POST | `/media/uploads` | 🔑 | URL d'envoi présignée (type, taille max 15 Mo image, 200 Mo vidéo) |
| POST | `/media/{id}/complete` | 🔑 | Déclenche le traitement (EXIF retiré, variantes, modération, OCR) |
| POST | `/listings/assist` | 🛒 | IA : photos → titre, catégorie, marque, état, attributs, prix conseillé (fourchette) |
| POST | `/listings` | 🛒 | Crée un brouillon |
| PATCH | `/listings/{id}` | 🛒 | Modifie (If-Match) |
| POST | `/listings/{id}/publish` · `/withdraw` · `/renew` | 🛒 | Transitions |
| GET | `/listings/{id}` | 🔓 | Fiche publique : distance arrondie, vendeur (niveau, badges, rang), total estimé, similaires |
| GET | `/listings/{id}/price-history` | 🔓 | Historique des prix |
| GET | `/me/listings?status=` | 🛒 | Mes annonces |
| POST/DELETE | `/listings/{id}/favorite` · `/price-watch` | 🔑 | Favori, suivi de prix |
| GET | `/me/favorites` | 🔑 | |
| POST | `/orders/{id}/items/{item_id}/resell` | 🔑 | Bouton « Revendre » : brouillon pré-rempli |

**Recherche, carte, feed (P3)**

| Méthode | Chemin | Accès | Description |
|---|---|---|---|
| GET | `/search` | 🔓 | `q`, `category`, `price_min/max`, `condition[]`, `brand[]`, `attributes[key]=`, `fulfillment=handover\|shipping`, `verified_sellers`, `zone_id` ou `lat`/`lng` + `radius_m`, `ring_max`, `sort`, `cursor` → `{ rings: [{ key, title, count, data[] }], closest_matches[], facets, expanded_reason }` |
| GET | `/search/suggest` | 🔓 | Autocomplétion (< 50 ms) |
| GET | `/map/listings` | 🔓 | Agrégats par cellule H3 selon le zoom, positions publiques décalées |
| GET/POST/PATCH/DELETE | `/me/saved-searches[/{id}]` | 🔑 | Recherches enregistrées et alertes |
| GET | `/feed/{for_you\|nearby\|following}` | 🔓/🔑 | Cartes du fil, avec `reason` et `request_id` |
| POST | `/feed/feedback` | 🔑 | « Pas intéressé », masquer le vendeur, plus/moins de… |
| POST | `/events` | 🔓 | Lot d'événements d'interaction (impressions, clics, durée), max 50 par appel |

**Commandes et paiement (P4)**

| Méthode | Chemin | Accès | Description |
|---|---|---|---|
| POST | `/listings/{id}/offers` | 🔑 | Faire une offre (idempotent) |
| POST | `/offers/{id}/accept` · `/decline` · `/counter` · `/cancel` | 🔑 | |
| GET | `/me/offers?role=buyer\|seller` | 🔑 | |
| GET/POST/DELETE | `/cart`, `/cart/items[/{listing_id}]` | 🔑 | Panier multi-vendeurs |
| POST | `/checkout/quote` | 🔑 | Calcule totaux par vendeur (articles, livraison par option, protection, total) |
| POST | `/checkout` | 🔑 | Crée les commandes + paiement (idempotent) → `client_secret` |
| GET | `/me/orders?role=buyer\|seller&status=` | 🔑 | |
| GET | `/orders/{id}` | 🔑 | Détail (vue acheteur ou vendeur), chronologie, actions possibles |
| POST | `/orders/{id}/cancel` | 🔑 | Selon état et rôle |
| POST | `/webhooks/payments/{provider}` | 🔓 (signature) | Webhooks prestataire |

**Remise, expédition, après-vente (P5)**

| Méthode | Chemin | Accès | Description |
|---|---|---|---|
| GET | `/orders/{id}/handover` | 🔑 acheteur | Code et QR |
| POST | `/orders/{id}/handover/confirm` | 🛒 | Saisie du code ou du QR |
| POST | `/orders/{id}/handover/meeting` | 🔑 | Proposer ou accepter un lieu et une heure |
| GET | `/orders/{id}/shipping-options` | 🛒 | Transporteurs, points relais |
| POST | `/orders/{id}/shipments` | 🛒 | Crée l'étiquette (exige la vidéo si obligatoire) |
| POST | `/orders/{id}/verification-video` | 🛒 | Rattache une vidéo capturée |
| POST | `/orders/{id}/confirm-receipt` | 🔑 acheteur | « Tout est OK » |
| POST | `/orders/{id}/withdrawal` | 🔑 acheteur | Rétractation 14 jours (pro) |
| POST | `/orders/{id}/disputes` | 🔑 acheteur | Ouvrir un litige |
| GET/POST | `/disputes/{id}`, `/disputes/{id}/messages` | 🔑 parties | |
| POST | `/disputes/{id}/respond` | 🛒 | Accepter, proposer partiel, contester |
| POST | `/disputes/{id}/accept-proposal` | 🔑 acheteur | |
| POST | `/orders/{id}/reviews` | 🔑 | Laisser un avis |
| POST | `/reviews/{id}/reply` | 🛒 | Répondre |
| GET | `/users/{id}/reviews` | 🔓 | |
| POST | `/webhooks/shipping/{provider}` | 🔓 (signature) | Suivi transporteur |

**Messagerie (P6)**

| Méthode | Chemin | Accès | Description |
|---|---|---|---|
| GET | `/conversations` | 🔑 | Liste, non lus |
| POST | `/listings/{id}/conversations` | 🔑 | Ouvrir une conversation avec le vendeur |
| GET | `/conversations/{id}/messages?cursor=` | 🔑 | Historique |
| POST | `/conversations/{id}/messages` | 🔑 | Envoyer (analyse anti-contournement synchrone < 50 ms ; réponse indique `masked` et le rappel) |
| POST | `/conversations/{id}/read` | 🔑 | Accusé de lecture |
| POST | `/messages/{id}/report` | 🔑 | Signaler |

**Confiance, signalements, notifications (P3, P7, P8)**

| Méthode | Chemin | Accès | Description |
|---|---|---|---|
| GET | `/me/trust` | 🔑 | Score détaillé, composants, conseils, badges, rang, progression |
| POST | `/reports` | 🔓/🔑 | Signalement DSA (sans compte possible, avec e-mail) |
| GET | `/me/moderation-decisions` | 🔑 | Décisions me concernant, exposés des motifs |
| POST | `/moderation-decisions/{id}/appeal` | 🔑 | Recours |
| GET | `/notifications` · POST `/notifications/read` | 🔑 | |
| POST/DELETE | `/push-subscriptions` | 🔑 | Web Push (VAPID) |

**Tour de contrôle (P8)** — préfixe `/admin`, sessions `kind = 'admin'`, passkey obligatoire, liste d'IP autorisées optionnelle [PARAM].

| Méthode | Chemin | Permission |
|---|---|---|
| GET | `/admin/overview` (chiffres clés, séries, incidents, recommandations du copilote) | `admin.dashboard.read` |
| GET | `/admin/users?q=&status=&risk=` · `/admin/users/{id}` (360° : commandes, messages signalés, liens, sanctions, audit) | `user.read` |
| POST | `/admin/users/{id}/sanctions` · `/admin/sanctions/{id}/lift` | `user.sanction` (niveau 4 : double validation) |
| GET | `/admin/circumvention/detections?status=` | `circumvention.review` |
| POST | `/admin/circumvention/detections/{id}/decide` (`confirm`, `false_positive`, sanction a1-a4) | `circumvention.review` |
| GET/PUT | `/admin/circumvention/rules`, `/admin/circumvention/levers` | `circumvention.configure` |
| GET | `/admin/moderation/queue` (signalements, annonces en revue, médias douteux) | `moderation.review` |
| POST | `/admin/moderation/decisions` | `moderation.decide` |
| GET/POST | `/admin/appeals`, `/admin/appeals/{id}/decide` | `moderation.appeal` (≠ décideur initial) |
| GET | `/admin/disputes?status=` · POST `/admin/disputes/{id}/decide` | `dispute.resolve` |
| GET | `/admin/finance/overview` (revenus par source, séquestre total, versements, rapprochement) | `finance.read` |
| GET/POST | `/admin/payouts?status=pending_review`, `/admin/payouts/{id}/approve` · `/reject` | `payout.approve` (double validation) |
| POST | `/admin/refunds` | `refund.create` (seuils) |
| GET/POST | `/admin/approvals`, `/admin/approvals/{id}/approve` · `/reject` | selon permission demandée |
| GET | `/admin/audit?actor=&target=&action=` | `audit.read` |
| GET/PUT | `/admin/settings/{key}`, `/admin/flags/{key}` | `settings.write` (double validation) |
| GET/POST/PATCH | `/admin/categories` | `catalog.configure` |
| GET | `/admin/compliance/transparency-report?period=` · `/admin/compliance/dac7?year=` | `compliance.read` |
| POST | `/admin/recalls` | `compliance.write` |
| GET | `/admin/live/shows` · POST `/admin/live/shows/{id}/terminate` (P13) | `live.moderate` |

Les points d'accès des phases P10 à P20 sont spécifiés au début de chaque phase (skill `api-design`), dans `docs/api/` et dans l'OpenAPI, en respectant ces conventions.

### 11.6 Génération du client

- `apps/api` expose `/openapi.json`. Une commande `pnpm api:generate` (script Turborepo) l'exporte dans `docs/api/openapi.json` et régénère `packages/api-client` (`openapi-typescript`).
- La CI échoue si le fichier versionné diffère de la sortie générée (contrat non synchronisé).
- `operation_id` explicites et stables sur chaque route FastAPI (`listings_get`, `checkout_create`…), pour des noms de fonctions lisibles côté client.

---

## 12. Temps réel

### 12.1 Canal WebSocket

- Point d'entrée `wss://api.trovelya.com/v1/ws`, authentifié par la session (cookie) ou par un jeton court (`/v1/ws/ticket`, 60 s, usage unique).
- Messages JSON `{ "type": "...", "channel": "...", "data": {...}, "seq": 123 }`.
- Abonnements explicites : `{"type":"subscribe","channel":"conversation:<id>"}` ; le serveur vérifie le droit d'accès à chaque abonnement.
- Canaux : `user:<id>` (notifications, compteurs, statut de commande), `conversation:<id>`, `listing:<id>` (prix, réservé, vendu), `auction:<id>` (P12), `live:<id>` (P13, chat, épinglage, enchère éclair).
- Distribution entre instances : Redis pub/sub (`ws:<channel>`). Chaque instance FastAPI garde ses connexions locales.
- Battement de cœur toutes les 25 s ; reconnexion côté client avec délai exponentiel (1, 2, 4… 30 s) et reprise par `seq` (les 200 derniers messages par canal sont gardés 10 min dans un flux Redis `XADD … MAXLEN`).
- Le WebSocket ne fait **qu'informer** : toute action (envoyer un message, enchérir) passe par un appel REST idempotent. Exception : enchères éclair en live (P13), qui passent par REST aussi mais avec un chemin optimisé.

### 12.2 Moteur d'enchères (P12) — exigences

- **Un seul écrivain par lot** : verrou Redis `auction:<id>:lock` (`SET NX PX`), ou file Redis par lot consommée par un worker unique ; l'ordre des offres est donné par une séquence PostgreSQL et l'horodatage serveur en microsecondes.
- Validation d'une offre : enchère en cours, enchérisseur ≠ vendeur, non lié au vendeur (`account_links`), empreinte bancaire valide ≥ montant, montant ≥ prix courant + pas d'enchère.
- **Pas d'enchère** [PARAM] : < 10 € : 0,50 € ; 10-50 € : 1 € ; 50-200 € : 2 € ; 200-1 000 € : 5 € ; 1 000-5 000 € : 20 € ; > 5 000 € : 50 €.
- **Anti-sniping** : offre reçue dans les 30 dernières secondes → `ends_at = max(ends_at, now + 30 s)` [`auctions.anti_snipe_seconds = 30`].
- **Enchère automatique** : l'enchérisseur fixe un maximum (stocké chiffré, invisible) ; le moteur enchérit pour lui au pas minimal nécessaire. En cas d'égalité de maximum, le plus ancien gagne.
- **Prix de réserve** (invisible, indication « réserve non atteinte ») et **achat immédiat** (disparaît dès que la réserve est atteinte ou dès la première offre [PARAM]).
- **Empreinte bancaire** : autorisation de 10 % du montant max ou 50 € minimum [PARAM] avant la première offre ; libérée si perdu.
- **Collusion** : alerte si un compte lié au vendeur enchérit ; si un enchérisseur ne gagne jamais mais fait monter souvent les prix du même vendeur ; offres retirées → interdites.
- Diffusion du nouveau prix à tous les abonnés en **< 200 ms** au p95.
- Gagnant : paiement automatique sur le moyen enregistré (empreinte capturée + complément) sous 24 h ; à défaut, `second_chance`.
- Tests de charge obligatoires : 1 000 enchérisseurs simultanés sur un lot, 500 offres/s, aucune offre perdue ni mal ordonnée.

### 12.3 Live (P13) — exigences

- Vidéo : service managé (LiveKit Cloud UE recommandé ; Mux ou Cloudflare Stream en alternative), latence < 3 s pour les spectateurs, < 1 s pour les co-hôtes.
- Diffusion depuis le navigateur (WebRTC, page studio web) dès P13, puis depuis l'app (P21).
- Chat : canal `live:<id>`, anti-contournement appliqué à chaque message (masquage en direct), limite 1 message/2 s par spectateur, mots interdits, modérateurs délégués par le vendeur.
- Transcription audio en continu (P13 : modèle de reconnaissance vocale UE) pour la détection de contournement et le chapitrage du replay.
- Enchères éclair (15 à 90 s) lancées par le vendeur sur un produit épinglé.
- Replay chapitré par produit, achetable après le live.


---

## 13. Sécurité

Objectifs : ISO 27001 sous 18 mois après le lancement public, disponibilité 99,95 %, aucune donnée de carte (périmètre PCI DSS SAQ-A).

### 13.1 Modèle de menaces

Un document STRIDE (`docs/security/threat-model.md`, skill `stride-analysis-patterns`) DOIT être produit en P0 et mis à jour à chaque phase. Menaces prioritaires :

| Menace | Exemple | Parades |
|---|---|---|
| Usurpation | Vol de session, prise de compte | Sessions opaques révocables, passkeys, step-up pour actions sensibles, détection de connexion anormale (pays, appareil), notification de nouvelle connexion |
| Altération | Modifier un prix au checkout, rejouer un webhook | Prix recalculés serveur, signatures de webhook, idempotence, verrou optimiste |
| Répudiation | « Je n'ai jamais validé ce remboursement » | Journal d'audit chaîné, double validation |
| Divulgation | Fuite d'adresse d'un vendeur, IDOR sur commandes | Contrôle d'accès par objet sur chaque route, positions décalées, 404 pour les objets non autorisés, chiffrement des champs sensibles |
| Déni de service | Inondation de l'API, robots sur les drops | Limites de débit, WAF, défi anti-robots (Cloudflare Turnstile) sur inscription, drops, enchères éclair |
| Élévation de privilèges | Un vendeur appelle une route admin | Permissions nommées vérifiées serveur, comptes staff distincts, sous-domaine admin |
| Fraude | Carte volée, colis vide, faux litige, collusion | Score de risque, 3-D Secure, vidéo de vérification, comptes liés, sanctions |

### 13.2 Exigences techniques

- **Transport** : TLS 1.3, HSTS (`max-age=63072000; includeSubDomains; preload`).
- **En-têtes web** : CSP stricte avec nonces (pas de `unsafe-inline` pour les scripts), `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` restrictive (caméra/micro seulement sur les pages qui les utilisent), `frame-ancestors 'none'`.
- **Cookies** : `trv_session` `HttpOnly; Secure; SameSite=Lax; Path=/` ; domaine `.trovelya.com` ; session admin sur `admin.trovelya.com` uniquement, `SameSite=Strict`, durée 12 h.
- **Mots de passe** : aucun. Connexion par lien magique, fournisseur d'identité ou passkey.
- **Step-up** : passkey ou lien magique de confirmation < 12 h exigé pour : changer d'e-mail, ajouter une passkey, versement instantané, export/suppression RGPD, toute action admin sensible.
- **Secrets** : variables Railway/Vercel chiffrées ; jamais dans le dépôt (scan `gitleaks` en CI) ; rotation documentée.
- **Chiffrement au repos** : géré par l'hébergeur + chiffrement applicatif des champs sensibles (TIN, date de naissance, original des messages masqués, maximum d'enchère automatique).
- **Téléversements** : URL présignées à durée courte, types MIME vérifiés par signature de fichier, taille max, antivirus (ClamAV en job) pour les documents, suppression EXIF/GPS des photos, re-encodage des images.
- **Injection** : requêtes paramétrées uniquement ; SQL brut relu en revue ; aucun `eval`.
- **SSRF** : aucun appel sortant vers une URL fournie par l'utilisateur sans liste blanche (import Shopify : domaines `*.myshopify.com` et API officielle uniquement).
- **Dépendances** : Dependabot/Renovate, `pip-audit`, `pnpm audit`, SBOM (CycloneDX) à chaque build de production, revue `supply-chain-risk-auditor` avant tout ajout.
- **Analyse statique** : `semgrep` (règles Python, TypeScript, secrets) en CI, bloquant sur sévérité haute.
- **Journalisation** : jamais de données personnelles en clair dans les logs (masquage e-mail, téléphone, adresse, jeton) ; filtre `structlog` testé.
- **Tests d'intrusion** : avant le lancement public (après P8), puis annuellement ; bug bounty public après P13.

### 13.3 Contrôle d'accès par objet

Chaque route qui charge une ressource par identifiant DOIT passer par une fonction de politique (`policies.py` du module) : `can_view_order(user, order)`, `can_edit_listing(user, listing)`… Des tests paramétrés vérifient, pour chaque route, qu'un utilisateur tiers reçoit `404` (pas `403`, pour ne pas révéler l'existence).

---

## 14. Conformité réglementaire

> TROVÉLYA n'est pas conseil juridique. Les points **[À VALIDER]** doivent être confirmés par un avocat (droit du numérique, consommation, enchères) et un expert-comptable (TVA, DAC7) **avant le lancement public**.

### 14.1 RGPD

- Registre des traitements (`docs/compliance/registre.md`), DPO désigné (externe possible), analyses d'impact (AIPD) pour : géolocalisation, score de confiance, détection anti-contournement (lecture automatisée des messages), vérification vidéo, recommandation personnalisée.
- Bases légales : contrat (comptes, commandes), obligation légale (DAC7, facturation, DSA), intérêt légitime (fraude, sécurité, anti-contournement — avec information claire), consentement (cookies non essentiels, marketing, localisation précise, publicité personnalisée).
- Bandeau de consentement conforme CNIL (« Tout refuser » aussi visible que « Tout accepter »), aucun traceur non essentiel avant consentement.
- Droits en libre-service : accès/export (JSON + fichiers, sous 30 jours, en pratique < 24 h), rectification, suppression (anonymisation des données liées aux commandes conservées pour obligation légale), opposition au profilage (feed non personnalisé).
- Durées de conservation [`retention.*`] : compte inactif 3 ans puis suppression après préavis ; messages 3 ans après la dernière activité de la conversation ; vidéos de vérification 12 mois ; journaux techniques 12 mois ; données comptables et factures 10 ans ; données DAC7 10 ans ; journal d'audit 10 ans ; événements d'interaction 13 mois.
- Sous-traitants dans l'UE ou couverts par des garanties (clauses contractuelles types, cadre UE-US) ; liste publique tenue à jour.
- Décisions automatisées : le score de confiance et les sanctions automatiques de niveau ≥ 2 doivent offrir une intervention humaine (recours) — art. 22.

### 14.2 DSA (règlement sur les services numériques)

TROVÉLYA est une **plateforme en ligne permettant la conclusion de contrats à distance**. Obligations implémentées en P8 (au plus tard) :

| Article | Exigence | Implémentation |
|---|---|---|
| 11-12 | Points de contact autorités et utilisateurs | Page légale + adresse dédiée |
| 14 | CGU claires sur la modération | CGU + règles de la communauté |
| 15 | Rapport de transparence annuel | Généré depuis `reports`, `moderation_decisions`, `appeals` (`/admin/compliance/transparency-report`) |
| 16 | Mécanisme de notification | `POST /reports`, accessible sans compte, accusé de réception, information de la suite |
| 17 | Exposé des motifs | `moderation_decisions` + e-mail et page « Décisions me concernant », avec mention de l'automatisation et des voies de recours |
| 20 | Système interne de recours | `appeals`, gratuit, 6 mois pour agir, traité par une personne différente |
| 21 | Règlement extrajudiciaire | Information sur les organismes certifiés |
| 22 | Signaleurs de confiance | `is_trusted_flagger`, priorité de traitement |
| 23 | Abus | Suspension des signaleurs abusifs après avertissement |
| 24§5 | Base de transparence de la Commission | Envoi des exposés des motifs (API de la Commission) |
| 25 | Interfaces non trompeuses | Pas de « dark patterns » : résiliation aussi simple que l'inscription, pas de fausse urgence |
| 26 | Transparence de la publicité | Mention « Sponsorisé », annonceur, paramètres de ciblage (« Pourquoi cette pub ? ») |
| 27 | Transparence des systèmes de recommandation | Page « Comment fonctionne le classement » + « Pourquoi je vois ça ? » + réglages |
| 28 | Protection des mineurs | Pas de publicité profilée pour les mineurs |
| 30 | Traçabilité des professionnels | Collecte et vérification (VIES, registre), affichage, suspension si informations fausses |
| 31 | Conformité dès la conception | Champs obligatoires produit (identification, marquage CE si applicable, informations de sécurité GPSR) pour les pros |
| 32 | Droit à l'information | Informer les acheteurs d'un produit illégal vendu par un pro dans les 6 derniers mois |

### 14.3 Droit de la consommation

- **Vendeurs pros** : droit de rétractation de **14 jours** à compter de la réception, formulaire type, remboursement sous 14 jours (frais de livraison initiaux inclus, retour à la charge de l'acheteur sauf mention contraire) ; garantie légale de conformité (2 ans neuf, 1 an occasion minimum) mentionnée sur la fiche.
- **Particuliers** : pas de droit de rétractation légal ; la protection TROVÉLYA s'applique (litige non conforme).
- Mention claire sur chaque annonce et au panier : « Vendu par un particulier » ou « Vendu par un professionnel » (directive Omnibus).
- **Prix barrés** : prix de référence = plus bas prix pratiqué dans les 30 jours précédents (`listing_price_history`), contrôlé automatiquement pour les pros.
- **Avis** : informations sur la vérification (8.10).
- **Classement** : paramètres principaux expliqués, mention des résultats payants (Omnibus).
- **Prix total** : article + frais + livraison affichés avant engagement.
- **Médiation de la consommation** : adhésion à un médiateur **[À VALIDER]**, mention dans les CGV.

### 14.4 Enchères

En France, les ventes aux enchères en ligne entre particuliers via une plateforme relèvent du **courtage aux enchères par voie électronique** (art. L321-3 du Code de commerce) : l'opérateur n'est pas mandataire du vendeur et n'adjuge pas. Le schéma exact (pas d'adjudication par TROVÉLYA, la vente est conclue entre les parties au meilleur enchérisseur) DOIT être validé par un avocat avant P12 **[À VALIDER]**. Aucun développement des enchères ne passe en production sans ce feu vert.

### 14.5 Fiscalité

- **DAC7** : collecte des informations (identité, TIN, date de naissance, adresse, IBAN via prestataire) des vendeurs dépassant **30 ventes ou 2 000 €** par an ; déclaration annuelle avant le 31 janvier à la DGFiP ; information du vendeur ; suspension après deux relances sans réponse. Job `dac7_aggregate` (janvier) + export au format de l'administration **[À VALIDER : format exact]**.
- **TVA** : section 10.8 ; OSS en P18.

### 14.6 Sécurité des produits (GPSR, règlement 2023/988)

- Enregistrement de TROVÉLYA sur le portail Safety Gate, point de contact unique.
- Pros : informations obligatoires (fabricant, personne responsable dans l'UE, identifiant produit, avertissements) avant publication dans les catégories concernées.
- Rapprochement automatique des rappels (Safety Gate, RappelConso) avec les annonces (`product_recalls`) : retrait et information des acheteurs concernés.
- Traitement des signalements de produits dangereux sous 2 jours ouvrés.

### 14.7 Accessibilité (EAA, applicable depuis le 28 juin 2025)

WCAG 2.2 niveau AA pour le web (et l'app en P21), déclaration d'accessibilité publiée, audit automatisé en CI (`axe-core` via Playwright) + audit manuel avant chaque jalon de mise en ligne (skill `wcag-audit-patterns`).

### 14.8 Immobilier (P9)

- **Loi Hoguet** (loi n° 70-9) : vérification de la carte professionnelle des agents et mandataires ; TROVÉLYA ne fait **aucune** activité d'intermédiaire (pas de négociation pour compte d'autrui, pas de maniement de fonds) : elle publie des annonces et met en relation. Ce positionnement DOIT être validé par un avocat **[À VALIDER]**.
- **Mentions obligatoires** des annonces (DPE, coûts d'énergie, honoraires, copropriété, encadrement des loyers) : section 8.20.2.
- **Décence énergétique** : refus des locations de logements classés G (8.20.3).
- **Non-discrimination** dans l'accès au logement : contrôle automatique et modération.
- **Pièces justificatives locataires** : aucune collecte (8.20.4).
- **Meublés de tourisme** : numéro d'enregistrement affiché si la commune l'exige ; réservation intégrée hors périmètre initial.
- Données ouvertes (DVF) : respect de la licence et interdiction de ré-identifier les personnes.

### 14.9 Véhicules (P9)

- Contrôle technique, certificat de cession, non-gage : rappels et check-list (8.21.3) ; aucune démarche administrative n'est faite par TROVÉLYA.
- Pros : informations obligatoires et garantie légale de conformité.
- Paiement protégé : plafond et règles validés avec le prestataire et un avocat **[À VALIDER]**.

### 14.10 Documents légaux à produire avant le lancement public

CGU, CGV (vendeurs pros et particuliers), politique de confidentialité, politique cookies, règles de la communauté, conditions de la Garantie TROVÉLYA, page « Comment fonctionne le classement », page « Comment nous vérifions les avis », mentions légales, déclaration d'accessibilité, procédure de signalement, conditions des enchères (P12), conditions publicitaires (P11), conditions particulières Immobilier, Véhicules et Services (P9). Rédigés par un avocat **[À VALIDER]** ; l'interface les affiche depuis des fichiers Markdown versionnés (`apps/web/content/legal/`), chaque version acceptée étant enregistrée (`consents.policy_version`).

---

## 15. Spécifications fonctionnelles des phases P9 à P21

Chaque phase commence par `brainstorming` puis `writing-plans` ; ces spécifications fixent le **quoi** et les critères, le plan fixe le **comment**.

### 15.1 P9 — Verticales : immobilier, véhicules, services

Règles détaillées : sections 8.19 à 8.23, 14.8, 14.9.

- **Moteur de catégories à modèle transactionnel** : l'interface (fiche, boutons, tunnel), les frais, la messagerie et la modération s'adaptent au `transaction_model` et à la `vertical` de la catégorie. Le gabarit de fiche est choisi par verticale.
- **Formulaires de publication spécialisés** avec validation stricte par sous-catégorie (schémas JSON côté API, miroir Zod côté web), aide IA (lecture d'un DPE photographié, décodage du modèle de véhicule à partir des photos) — l'humain valide.
- **Recherche** : filtres spécialisés, recherche par **carte** et **zone dessinée** (polygone PostGIS) pour l'immobilier, tri par prix au m², alertes instantanées.
- **Mises en relation** : demandes (`leads`), créneaux de visite et d'essai, rappels, agenda W38, statistiques annonceur.
- **Comptes pros vérifiés** : cartes professionnelles, garages, prestataires (`pro_licenses`), vérification manuelle en Tour de contrôle (nouvel onglet « Pros à vérifier »), affichage des mentions obligatoires.
- **Import par flux** pour les pros (formats d'export standard des logiciels d'agence et de concession, XML/CSV) : synchronisation planifiée, rapport d'erreurs, retrait automatique des annonces disparues du flux.
- **Estimation** : chargement et agrégation des données DVF par secteur (IRIS ou cellule H3), « Estimer mon bien », cote véhicule v1.
- **Anti-arnaque** spécifique (8.20.5, 8.21.4) avec file prioritaire en Tour de contrôle.
- **Paiement protégé optionnel** véhicules (8.21.3) en réutilisant commandes, séquestre et code de remise.
- **Offres pros** des verticales (abonnements), options de visibilité pour les particuliers.

**Critères de porte P9** : une agence vérifiée importe 200 annonces par flux en < 10 min ; une annonce de location classée G est refusée ; un message « envoyez un mandat cash avant la visite » est bloqué ; une recherche sur carte avec zone dessinée répond en < 200 ms p95 sur 500 000 biens ; une vente de véhicule avec paiement protégé et code de remise suit tout le parcours avec un grand livre équilibré ; aucun justificatif locataire n'est stocké (test).

### 15.2 P10 — Boutiques et Atelier marchand

**Vitrine (boutique de marque)**
- Une boutique par abonnement Starter (plusieurs en Scale) : nom, logo, couleurs, thème, pages (accueil, collection, produit, à propos, contact, blog, FAQ), menus.
- Éditeur visuel par **sections** (bandeau, grille de produits, collection, texte et image, avis, lives à venir, enchères en cours, newsletter) avec aperçu en direct sur ses propres produits, versions et retour arrière.
- Thèmes : 6 thèmes officiels au lancement de P10 [PARAM] ; marché des templates en P19.
- Domaine propre (achat via registrar revendeur, ou connexion d'un domaine existant), SSL automatique (Vercel domains API ou équivalent), sous-domaine gratuit `nom.trovelya.shop`.
- SEO : sitemap, données structurées, URL propres, redirections après migration.
- Recherche interne à la boutique (même moteur).
- Le client appartient au marchand : export CSV de ses clients et commandes en un clic.

**Catalogue pro et stock unique**
- Produits, variantes (taille, couleur…), SKU, codes-barres, poids, collections manuelles et automatiques, champs personnalisés, import CSV.
- Un produit publié **partout** (boutique, feed, Place, live, enchères) avec **un seul stock** : décrément atomique (`UPDATE inventory_levels SET available = available - n WHERE available >= n`), zéro survente, réservation pendant le paiement.
- Multi-entrepôts, retours, remboursements.

**Migration Shopify en un clic** (arme d'acquisition n°1)
- Connexion OAuth à la boutique Shopify (Admin API GraphQL), import : produits, variantes, images, collections, clients (avec consentement marketing conservé), commandes historiques, avis (applications courantes), pages, redirections SEO (anciennes URL → nouvelles).
- Import asynchrone par lots, reprise sur erreur, rapport détaillé, aucune perte de référencement (redirections 301).
- Test d'acceptation : une boutique de 2 000 produits importée en < 15 minutes, 100 % des produits, 0 image cassée.

**Atelier marchand (web, `/atelier`)**
- Tableau de bord : ventes du jour/semaine/mois, commandes à traiter, messages, lives programmés, recommandations.
- Commandes : traitement par lot, étiquettes, bons de préparation.
- Clients : fiches, segments, export.
- Marketing : codes promo, panier abandonné (e-mail), programme de fidélité relié aux badges, parrainage.
- Analytique : ventes, trafic, conversion, cohortes, valeur client, sources (`own_traffic` vs `marketplace`), recherches menant à la boutique et recherches sans résultat chez lui.
- Équipe : rôles (propriétaire, administrateur, éditeur, support), sièges facturés.
- B2B : listes de prix par client, devis, paiement à 30 jours (via prestataire).
- Abonnement et facturation.
- Publication Google Merchant Center (flux produits) dès P10 ; Meta, TikTok, Pinterest en P19.

**Critères de porte P10** : un marchand migre depuis Shopify, personnalise sa Vitrine, connecte son domaine, vend sur sa Vitrine (commission 0 %) et via le feed (commission selon rang), la commission est correctement attribuée, le stock reste juste sur 1 000 commandes concurrentes simulées.

### 15.3 P11 — TROVÉLYA Ads

**Formats** : produit sponsorisé (recherche, feed, similaires), boutique sponsorisée (bandeau + 3 produits en tête de recherche), vidéo sponsorisée (feed), live boosté (P13), enchère boostée (P12), remontée d'annonce (particuliers, prix fixe), sponsoring d'événement (forfait).

**Enchère publicitaire** (à chaque recherche et rafraîchissement de feed, < 20 ms) :
```
score_pub = enchère × P(clic) × P(achat | clic) × qualité
qualité   = f(score de confiance vendeur, note produit, taux de retour, qualité de fiche, délai de livraison)  ∈ [0,1]
prix payé = (score_pub du suivant / (P(clic) × P(achat) × qualité du gagnant)) + 0,01 €   — second prix
```
- Seuil de qualité [`ads.min_quality = 0,4`] : en dessous, l'annonce est refusée quel que soit le budget.
- Paiement au clic (CPC, dès 0,05 €) ou **à la vente** (3 à 8 % du prix, pas de commission marketplace en plus).
- Pilote automatique : budget + objectif de rentabilité (ROAS) → choix des produits, mots-clés, enchères. Optimisation sur la **marge** si le marchand la renseigne. Enchères conscientes du stock (baisse si stock faible, arrêt si rupture).
- Enchère selon l'intention (requête précise > exploration).
- **Groupe témoin** : 5 % des utilisateurs [`ads.holdout_pct = 5`] ne voient jamais de pub pour mesurer l'effet réellement causé (lift), affiché à l'annonceur.
- Garde-fous : max **1 contenu sponsorisé sur 6** dans le feed, **2** en tête de recherche ; mention « Sponsorisé » ; « Pourquoi cette pub ? » ; pas de pub pour un produit déjà acheté ; plafond de répétition (3 expositions/jour/utilisateur/annonce) ; quota découverte des nouveaux vendeurs intact ; pas de ciblage sensible ni de mineurs.
- Ciblage : intention, contexte, catégorie, distance (rayon autour d'une boutique), panier abandonné, audiences similaires.
- Tableau de bord annonceur : dépenses, ventes, ROAS, ventes causées, mots-clés, part de visibilité, recommandations IA.
- Facturation : budget prépayé ou prélèvement mensuel ; écritures `revenue:ads`.

**Critères de porte P11** : enchère simulée sur 10 000 requêtes respecte charge publicitaire et seuil de qualité ; mesure de lift fonctionnelle ; aucune facturation double (pub à la vente + commission).

### 15.4 P12 — Enchères

Formats : **chronométrée** (1 h à 10 jours), **éclair** (15 à 90 s, en live), **hollandaise** (prix décroissant par paliers jusqu'au premier preneur), **scellée** (offres secrètes révélées à la fin, la plus haute gagne au prix offert), **multi-lots** (N exemplaires, les N meilleures offres gagnent, chacune paie son offre [PARAM : ou le prix de la N-ième]).

Exigences : section 12.2 + règles 9.7. Pages : « Enchères qui finissent », fiche d'enchère (historique horodaté au millième, nombre d'enchérisseurs, réserve atteinte ou non, temps restant synchronisé sur l'horloge serveur), suivi « Mes enchères ». Notifications : surenchéri, se termine dans 1 h / 5 min, gagné, perdu.

Commissions : 10 % (`auction_platform`) ou 5 % (`auction_external`) pour les pros ; frais de protection acheteur pour les ventes entre particuliers.

Authentification par expert (10-30 €) : demande depuis la fiche, partenaires, badge « Authentifié » sur l'objet.

**Critères de porte P12** : feu vert juridique (14.4) ; tests de charge 12.2 ; aucun écart entre l'historique des offres et le gagnant sur 10 000 enchères simulées ; non-paiement < 2 % en bêta.

### 15.5 P13 — Live shopping

Programmation (titre, date, produits, couverture), rappel « Me rappeler », salle d'attente et compte à rebours ; studio de diffusion web (caméra, micro, partage d'écran) ; produits épinglés et achat sans quitter la vidéo ; enchères éclair ; chat modéré (IA + modérateurs) ; co-live (deux vendeurs, audiences fusionnées, partage des revenus) ; replay chapitré et achetable ; multidiffusion RTMP vers TikTok, Instagram, YouTube avec lien retour ; **soirées de ventes** multi-vendeurs éditorialisées ; espace « Lives » de la Tour de contrôle (tuiles de risque, coupure, avertissement). Mesure du coût vidéo par live (porte : coût vidéo < 15 % du revenu live).

### 15.6 P14 — Drops, précommandes, achats groupés, demande inversée

- **Drop** : compte à rebours, salle d'attente, **file d'attente équitable** (ordre aléatoire parmi les présents à l'ouverture, pas premier arrivé), **tirage au sort** pour les produits très demandés, limite par acheteur, défi anti-robots, accès anticipé pour rangs Or+.
- **Précommande participative** : seuil de commandes et date limite ; empreinte bancaire ou paiement capturé à l'atteinte du seuil ; sinon annulation et remboursement automatiques.
- **Achat groupé** : paliers (ex. −10 % à 10 acheteurs, −20 % à 50) ; prix final appliqué à tous à la clôture ; partage incitatif.
- **Demande inversée** : l'acheteur publie un besoin (texte, budget, zone, taille) ; les vendeurs proposent une annonce existante ou une offre ; l'acheteur accepte → commande. Proposée automatiquement en cas de recherche sans résultat.

### 15.7 P15 — Communauté

Profils sociaux et abonnements ; listes d'envies publiques ou privées ; **collections curatées** (« tableaux ») achetables, partageables, commissionnées pour leur auteur (affiliation) ; **cercles** thématiques (discussions, événements, lives réservés, modérateurs bénévoles, règles) ; shopping entre amis (panier partagé, sondage « demander l'avis », cadeau à plusieurs, listes de cadeaux) ; programme créateurs et affiliés ; quêtes, classements par cercle, saisons (récompenses non monétaires ou réductions de frais ; jamais récompenser la dépense pure) ; **score d'impact** (CO₂ et déchets évités par revente, méthode publiée) ; points de fidélité acheteurs.

### 15.8 P16 — IA avancée

| Fonction | Exigence |
|---|---|
| Feed appris v2 | Modèle « deux tours » (embeddings utilisateur/article) pour la présélection, classement multi-objectifs (clic, achat, satisfaction après achat, risque de retour), apprentissage quotidien, mise à jour du profil en quelques secondes ; déploiement uniquement via test A/B gagnant sur la métrique « achats satisfaits par session » |
| Recherche par photo | Embedding image → voisins pgvector (ou index dédié), filtres de prix et distance |
| Recherche conversationnelle | LLM qui traduit la phrase en filtres structurés (schéma JSON validé), puis recherche normale ; jamais d'invention de produits |
| Recherche vocale | Transcription puis recherche texte |
| Mode Chasse | Mission décrite en langage naturel → recherche enregistrée enrichie, alerte dès correspondance |
| Studio photo | Détourage, fond studio, mise en scène, vidéo courte depuis photos (crédits IA) |
| Analyste marchand | Questions en langage naturel sur ses propres données (requêtes SQL générées sur des vues autorisées, en lecture seule, limitées à son `shop_id`) |
| Service client IA | Répond aux acheteurs d'une boutique avec les vraies données de commande ; escalade humaine ; mention « réponse IA » |
| Boutique générée | Phrase → thème, pages, textes, à valider |
| Prévisions | Réassort, tendances, prix optimal suggéré |
| Modération | Contrefaçons par l'image, faux avis, détection d'intention de contournement |

Règle d'or : **l'IA propose, l'humain valide** ; rien n'est publié sans action de l'utilisateur. Chaque appel IA est journalisé (`ai_usage` : modèle, coût, latence), plafonné par compte, et les données envoyées aux fournisseurs restent dans l'UE.

### 15.9 P17 — Vie de l'objet

- **Passeport produit** : identifiant unique (`TRV-PP-…`, ex. certificat `AG-1857-0042` de la maquette renommé au format TRV), créé à la vente neuve par une boutique ou à l'authentification ; QR code ; chronologie (fabrication, ventes, reventes, réparations, authentifications). Préparation au passeport numérique produit européen (règlement écoconception).
- **Royalties de revente** : la marque d'origine définit un pourcentage (ex. 3 %) prélevé à chaque revente sur TROVÉLYA ; TROVÉLYA garde 15 % de la royalty ; écritures dédiées.
- **Histoire de l'objet** : chapitres ajoutés par chaque propriétaire (photo, lieu, réparation, souvenir), visibilité choisie, affichés sur l'annonce de revente.
- **Patrimoine en temps réel** : chaque achat entre dans « Mon patrimoine », valeur recalculée chaque jour à partir des ventes réelles d'objets identiques ou proches, alertes (« vaut 30 % de plus »), **valeur de revente estimée à un an** sur chaque fiche (maquette : 18 500 € → 19 200 €), présentée comme indicative avec méthode expliquée.

### 15.10 P18 — International UE

- Vague 2 (Espagne, Italie, Portugal, Pays-Bas, Allemagne, Autriche, Irlande) puis vague 3 (17 pays restants dont 6 hors euro : Pologne, Tchéquie, Hongrie, Roumanie, Suède, Danemark).
- 24 langues d'interface (`next-intl`, skill `next-intl-add-language`), traduction automatique des annonces (affichée comme telle, original consultable), support dans la langue.
- Multi-devise : prix stocké dans la devise du vendeur, affichage converti pour l'acheteur (taux quotidiens, marge de conversion 1-2 %), paiement dans la devise de l'acheteur quand le prestataire le permet.
- Moyens de paiement locaux : iDEAL, Bancontact, BLIK, Swish, MobilePay, SEPA, paiement fractionné.
- Étiquette UE unique, réseaux de points relais locaux, prix total international affiché sur la fiche, panier multi-vendeurs regroupé par pays.
- TVA par pays et catégorie, OSS, comptes pros dans tous les pays avec vérification VIES.

### 15.11 P19 — Écosystème

API publique (REST + webhooks sortants signés ; GraphQL en option), OAuth 2.1 avec scopes fins, portail développeurs, bac à sable ; applications tierces (permissions minimales, revue avant publication, révocation immédiate, 20 % de commission) ; marché des templates (20 %) ; annuaire de fournisseurs vérifiés et notés, dropshipping, impression à la demande, demandes de devis groupées ; **TROVÉLYA+** (4,99 €/mois : livraison offerte selon conditions, accès anticipé aux drops) ; campagnes Google Shopping et Meta pilotées depuis l'Atelier ; rapports de tendances anonymisés et agrégés (seuil minimal d'agrégation pour empêcher la ré-identification) ; hébergement souverain (OVHcloud/Scaleway) pour l'offre Entreprise.

### 15.12 P20 — Innovations signature

| Innovation | Spécification minimale | Garde-fous |
|---|---|---|
| **Agents négociateurs** | Mission (objet, budget max, distance, prix plancher vendeur, délai de réponse) ; les agents échangent offres et contre-offres via l'API `offers` (`made_by = buyer_agent/seller_agent`) ; conclusion automatique dans les limites ou soumise à validation | Plafond de dépense par mission, historique complet, mention « négocié par agent », reprise en main à tout moment |
| **Bourse des objets** | Page par modèle (identifié via passeport), historique des prix, dernier prix, volume ; ordres d'achat (« j'achète à 80 € en bon état ») et de vente ; appariement automatique → commande avec séquestre | Objets réels uniquement, pas de vente à découvert, pas de produit financier |
| **Scan de la maison** | Vidéo de quelques secondes → objets identifiés, comparés aux ventes récentes, total estimé, annonces pré-remplies | Analyse sur l'appareil autant que possible (P21), vidéo non conservée sans accord, floutage visages et documents |
| **Échanges en chaîne** | Annonces « ouvert à l'échange » + souhaits ; recherche de cycles de 2 à 5 personnes ; soulte d'ajustement ; acceptation de tous puis expéditions simultanées avec séquestre | Vidéo de vérification obligatoire, score de confiance minimum, frais fixes par participant |
| **Membres copropriétaires** | Préparation uniquement : page d'intérêt, éligibilité par rang | Cadre européen du financement participatif et AMF, avocat obligatoire, aucune collecte dans l'application |

### 15.13 P21 — Application mobile Expo

- Skills obligatoires : `expo-overview` en premier, puis `expo-project-structure`, `expo-router`, `expo-data-fetching`, `expo-native-ui`, `expo-design-system`, `vercel-react-native-skills`, `eas-app-stores`, `eas-update`.
- Parité fonctionnelle avec le web, mêmes routes logiques, même `packages/api-client`, mêmes tokens (`packages/design-tokens`), mêmes fichiers de traduction.
- Écrans de la maquette (Welcome, Main avec onglets Pour toi/Abonnements, Menu en squircles, Search, Sell en 30 s, Product, Live, Profile, Messages, Orders, Wallet…) reproduits nativement (barres en Liquid Glass via effets natifs).
- Natif : caméra (vente express, vérification vidéo, scan QR de remise, scan de la maison), notifications push (Expo Notifications), localisation, live natif (SDK LiveKit React Native), Apple Pay / Google Pay natifs, passkeys natives, liens universels.
- Authentification mobile : jetons d'accès 15 min + jeton de rafraîchissement rotatif stocké dans le trousseau (SecureStore).
- Mises à jour OTA via EAS Update (canaux preview/production), publication App Store et Google Play via EAS Submit.
- Attention aux règles des stores : les biens physiques passent par le prestataire de paiement (pas d'achat intégré obligatoire) ; les services numériques (boost, abonnements) peuvent exiger l'achat intégré selon les règles en vigueur **[À VALIDER]**.

---

## 16. Qualité, tests, exploitation

### 16.1 Stratégie de tests

| Niveau | Outil | Exigence |
|---|---|---|
| Unitaires Python | pytest | Règles métier pures (frais, commissions, score, machines à états) : couverture ≥ 95 % des modules `ledger`, `orders`, `payments`, `trust`, `circumvention` |
| Propriétés | hypothesis | Grand livre équilibré, frais jamais négatifs, plafonds respectés, sommes de remboursements bornées |
| Intégration Python | pytest + testcontainers (PostGIS réel) | Chaque route : succès, validation, permissions (tiers → 404), idempotence, concurrence (deux achats simultanés du même article : un seul réussit) |
| Contrat | Schéma OpenAPI | Client généré à jour ; tests du client TS contre une API de test |
| Unitaires web | Vitest + Testing Library | Composants critiques (formulaire d'annonce, panier, récapitulatif de prix) |
| Bout en bout | Playwright | Parcours critiques (16.2) sur staging, à chaque fusion sur `main` |
| Accessibilité | axe-core dans Playwright | 0 violation critique ou sérieuse sur les pages des parcours critiques |
| Performance | Lighthouse CI, k6 | Budgets 6.3 ; API : p95 < 200 ms (lectures), < 400 ms (écritures), recherche p95 < 150 ms |
| Charge | k6 / Locust | Checkout 50 commandes/s ; enchères 12.2 ; WebSocket 10 000 connexions par instance |
| Sécurité | semgrep, gitleaks, pip-audit, pnpm audit, ZAP (DAST staging) | Bloquant sur sévérité haute |

Couverture globale minimale backend : 85 % des lignes ; la couverture n'est pas un objectif en soi, mais une baisse > 1 point bloque la PR.

### 16.2 Parcours critiques (tests e2e obligatoires)

1. Inscription par lien magique → onboarding → zone 5 km.
2. Activation vendeur (prestataire factice) → publication assistée par IA (IA factice) → annonce visible en recherche dans le cercle 1.
3. Recherche avec filtres → élargissement automatique → fiche → favori.
4. Offre → contre-offre → acceptation → paiement → code de remise → saisie par le vendeur → séquestre libéré → avis croisés.
5. Achat avec expédition → étiquette (vidéo obligatoire > 150 €) → livraison simulée → libération automatique 48 h (horloge simulée).
6. Litige « non conforme » → réponse vendeur → décision support → remboursement → écritures correctes.
7. Message contenant un numéro de téléphone → masqué → détection en Tour de contrôle → sanction niveau 2 → exposé des motifs → recours.
8. Signalement DSA d'une annonce sans compte → décision → information du signalant.
9. Export et suppression RGPD.
10. Staff : remboursement > 500 € nécessitant double validation.

### 16.3 CI/CD (GitHub Actions)

- **Sur chaque PR** : installation (cache pnpm + uv), lint (ruff, eslint), types (pyright, tsc), tests unitaires et d'intégration (services Postgres/PostGIS et Redis), génération OpenAPI + vérification de synchronisation, build web, semgrep, gitleaks, audit des dépendances, test d'architecture (import-linter), migrations appliquées sur base vide **et** test de réversibilité (`upgrade` → `downgrade` → `upgrade`).
- **Sur `main`** : déploiement automatique en **staging** (Railway + Vercel), migrations, tests e2e Playwright sur staging.
- **Production** : déclenchement manuel (tag `vX.Y.Z` ou approbation d'environnement GitHub), migrations *expand/contract* (jamais de changement destructeur dans la même version que le code qui en dépend), déploiement progressif, vérification de santé, retour arrière documenté (`docs/runbooks/rollback.md`).
- Turborepo : cache distant activé (skill `turborepo-caching`), seules les applications touchées sont construites.

### 16.4 Observabilité

- Logs JSON structurés (`structlog`) avec `request_id`, `user_id` (pseudonymisé), module, durée ; jamais de PII.
- Traces OpenTelemetry de bout en bout (web → API → base → prestataire).
- Métriques métier exposées : commandes payées/min, taux d'échec de paiement, séquestre total, libérations en retard, litiges ouverts, détections de contournement/heure, latence recherche, file outbox (âge du plus ancien événement non publié), jobs en échec.
- Erreurs : Sentry (web et API), alertes sur nouvelles erreurs.
- **Alertes** (astreinte) : API indisponible (> 1 min), p95 > 1 s (5 min), échec de paiement > 10 % (10 min), outbox en retard > 2 min, écart de rapprochement ≠ 0, échec de sauvegarde, file de webhooks en erreur.
- **SLO** : disponibilité 99,95 % mensuelle (API et web) ; parcours d'achat sans erreur 99,9 %.
- Page de statut publique (après P8).

### 16.5 Sauvegardes et reprise

- PostgreSQL : sauvegarde continue (PITR) 14 jours minimum chez Railway + **sauvegarde logique quotidienne chiffrée** exportée vers un second fournisseur UE (Scaleway Object Storage), conservée 35 jours ; mensuelle conservée 12 mois.
- Médias : stockage objet versionné, réplication dans une seconde région UE.
- **RPO** 5 min, **RTO** 4 h. Exercice de restauration **trimestriel** documenté (`docs/runbooks/restore.md`).

### 16.6 Données de démonstration

Script `apps/api/scripts/seed_demo.py` (idempotent, interdit en production) reprenant l'univers de la maquette : vendeurs (Librairie du Vieux-Lyon, Grenier de Lyon, etc.), annonces (« Les Fleurs du mal, édition originale 1857 » à 18 500 € ; « Les Fleurs du mal, réédition 1868 » à 240 € ; montre, objectif, vinyle, lampe, vase, carte), commandes (`TRV-47790`), détections anti-contournement, litiges, versements (18 500 € à valider) — pour que staging ressemble à la maquette.


---

## 17. Plan de construction chronologique

### 17.0 Règles d'exécution

- Chaque tâche `Px-Tyy` = **une branche, une PR**, des tests écrits d'abord (TDD), un commit conventionnel final (`feat(module): …`). Les tâches d'une même phase sont exécutées **dans l'ordre** sauf mention « parallélisable ».
- Avant chaque phase : relire les sections citées, `brainstorming` → `writing-plans` (le plan détaillé de la phase est enregistré dans `docs/plans/Px-nom.md`).
- Après chaque tâche : `verification-before-completion` (commandes de vérification exécutées et sorties lues), `requesting-code-review`.
- **Point de validation avec Arcel** à la fin de chaque phase : démonstration sur staging + liste des critères cochés. Aucune phase suivante sans son accord.
- Définition de « terminé » (DoD) pour toute tâche : tests verts en CI ; types et lint propres ; migrations réversibles ; OpenAPI et client régénérés ; textes d'interface dans `messages/fr.json` ; accessibilité vérifiée sur les écrans touchés ; journal d'audit pour les actions sensibles ; événements émis ; documentation mise à jour (ADR, glossaire, runbook si besoin) ; démontrable sur staging.

### 17.1 P0 — Fondations

| Tâche | Contenu | Vérification |
|---|---|---|
| P0-T01 | Monorepo : `pnpm-workspace.yaml`, `turbo.json`, `packages/config-*`, `.editorconfig`, `.nvmrc`, `README` de démarrage | `pnpm install && pnpm turbo build` passe |
| P0-T02 | `infra/docker-compose.yml` : Postgres 16 + PostGIS + pgvector (+ h3 si possible), Redis 7, Mailpit, MinIO | `docker compose up` ; extensions présentes (`SELECT * FROM pg_extension`) |
| P0-T03 | `apps/api` : projet uv, FastAPI, structure de modules (5.3), `core/config.py`, `/health` et `/ready` (base + Redis), gestion d'erreurs RFC 9457, middleware `request_id`, logs structlog | `uv run pytest` ; `curl /health` |
| P0-T04 | SQLAlchemy async + Alembic ; migration initiale : extensions, `set_updated_at`, `platform_settings`, `feature_flags`, `outbox_events`, `processed_events`, `idempotency_keys`, `audit_log` (inaltérable + chaînage) | Tests : UPDATE/DELETE sur `audit_log` refusés ; chaîne de hachage vérifiable |
| P0-T05 | `shared/` : `Money` (+ tests de propriétés), `ids` (UUIDv7), `Clock`, `events` (publication outbox dans la transaction), `audit`, service de paramètres et de flags (cache Redis) | Couverture 100 % de `money.py` |
| P0-T06 | Worker arq : relais outbox (au moins une fois, idempotence consommateurs), planificateur cron | Test : événement émis dans une transaction annulée n'est jamais publié |
| P0-T07 | Squelette du grand livre : tables 7.8, service `post_transaction(entries, idempotency_key)`, trigger d'équilibre différé | Tests : transaction déséquilibrée rejetée au COMMIT ; rejouer la clé → aucun doublon |
| P0-T08 | Idempotence HTTP (middleware + table), limites de débit Redis, CSRF | Tests dédiés |
| P0-T09 | Test d'architecture (`import-linter`) | Une violation volontaire fait échouer la CI |
| P0-T10 | `apps/web` : Next.js 15, TypeScript strict, Tailwind 4, `next-intl` (`/fr` par défaut), polices Geist, tokens (`packages/design-tokens`), thème clair/sombre, en-têtes de sécurité et CSP, PWA (manifest, service worker minimal) | Lighthouse ≥ 95 PWA/Best practices sur page vide |
| P0-T11 | `packages/ui` : composants de base accessibles (Button, IconButton, Input, Select, Checkbox, Switch, Dialog, Sheet, Tabs, Toast, Badge, Avatar, Card, Skeleton, Price, Distance, EmptyState), icônes maison, squircles, Liquid Glass | Stories ou page `/_design` ; axe-core 0 violation |
| P0-T12 | `packages/api-client` : génération depuis OpenAPI, script `pnpm api:generate`, vérification CI | CI échoue si désynchronisé |
| P0-T13 | CI GitHub Actions (16.3) | PR de test verte |
| P0-T14 | Déploiements : Railway (api, worker, Postgres, Redis — région UE) staging + production ; Vercel (web, `fra1`) ; domaines `trovelya.com`, `api.`, `admin.`, `staging.` **[À VALIDER : nom de domaine acheté]** | `/health` en ligne sur staging |
| P0-T15 | Observabilité : Sentry, OpenTelemetry, tableau de bord de base, alertes santé | Erreur volontaire visible dans Sentry |
| P0-T16 | Documents : ADR-0001 à 0010, `GLOSSARY.md`, `threat-model.md` v1, `PII.md`, runbooks (déploiement, retour arrière, restauration) | Revue par Arcel |

**Porte P0** : un `git push` sur une PR déclenche toute la CI ; `main` se déploie seul en staging ; base avec extensions, outbox, audit, grand livre équilibré testés ; page web vide, rapide, accessible, traduite, PWA.

### 17.2 P1 — Identité et comptes

| Tâche | Contenu |
|---|---|
| P1-T01 | Tables 7.3 (users, sessions, magic_links, auth_identities, passkeys, roles, permissions, user_roles, approval_requests) + graine des rôles et permissions (3.2) |
| P1-T02 | Connexion par lien magique (e-mail transactionnel, Mailpit en local), sessions opaques, déconnexion, liste et révocation des sessions |
| P1-T03 | Connexion Google et Apple (OIDC, PKCE, `state`, `nonce`, liaison au compte existant par e-mail vérifié) |
| P1-T04 | Passkeys (WebAuthn : `py_webauthn` côté API, `@simplewebauthn/browser` côté web), step-up |
| P1-T05 | Profil (pseudo unique, nom affiché, avatar via médias, bio), profil public `/u/[pseudo]` |
| P1-T06 | Adresses, zones de recherche (géocodage : API Adresse data.gouv.fr pour la France, Nominatim/Photon UE ensuite — via adaptateur), préférences |
| P1-T07 | Onboarding web (intérêts, tailles, zone, notifications) — écran W07 |
| P1-T08 | Consentements et bandeau cookies (CNIL) ; pages légales provisoires |
| P1-T09 | RGPD libre-service : export (job, archive), suppression (anonymisation) |
| P1-T10 | Suivre / bloquer |
| P1-T11 | Garde de permissions (dépendance FastAPI `require_permission("…")`), double validation générique, comptes staff et sessions admin séparées |
| P1-T12 | Écrans web W06, W08 (partiel), W20 ; en-tête et navigation (6.5) ; e2e parcours 1 |

**Porte P1** : parcours 1 vert ; tiers → 404 sur toutes les routes privées ; export RGPD complet ; aucune donnée personnelle dans les logs (test).

### 17.3 P2 — Catalogue et annonces

| Tâche | Contenu |
|---|---|
| P2-T01 | Catégories (ltree), attributs, marques ; graine des **16 univers** et de leur arbre complet de sous-catégories (section 8.19), avec `vertical` et `transaction_model` ; univers Immobilier, Véhicules, Services présents mais masqués par le drapeau `verticals` jusqu'à P9 ; `GET /categories` |
| P2-T02 | Médias : URL présignées, traitement (EXIF retiré, variantes AVIF/WebP 320/640/1080/1600, hachage perceptuel), vidéos (transcodage HLS via service managé ou ffmpeg en job) |
| P2-T03 | Annonces : tables 7.5, création de brouillon, validation des attributs par catégorie, positions publique/réelle, H3, `place_name` |
| P2-T04 | Machine à états 9.1, publication, retrait, renouvellement, expiration (job) |
| P2-T05 | Modération à la publication : liste d'interdits (8.17), détection anti-contournement sur titre/description (version initiale du module `circumvention`), classification d'images (fournisseur UE via adaptateur), passage en `pending_review` |
| P2-T06 | Assistance IA (`POST /listings/assist`) : vision → titre, catégorie, marque, état, attributs, fourchette de prix (comparables pgvector quand disponibles) ; journalisation `ai_listing_suggestions` ; adaptateur factice pour les tests |
| P2-T07 | Score de qualité de fiche (photos, longueur, attributs remplis) |
| P2-T08 | Favoris, suivi de prix, historique des prix |
| P2-T09 | Écran W09 « Vendre en 30 s » (photo → suggestions → validation → publication), W10 mes annonces |
| P2-T10 | Fiche produit W03 (sans achat) : galerie, vendeur, prix, distance, onglets Description et Historique, similaires (pgvector), SEO (données structurées, OG image) |
| P2-T11 | Embeddings texte + image des annonces (job à la publication) |
| P2-T12 | e2e parcours 2 (partiel : jusqu'à l'annonce visible) |

**Porte P2** : une annonce se publie en < 60 s depuis une photo sur mobile web ; fiche produit LCP < 2,5 s ; modération bloque les interdits et masque les coordonnées.

### 17.4 P3 — Recherche, priorité territoriale, feed v1, notifications

| Tâche | Contenu |
|---|---|
| P3-T01 | `search_document` (tsvector pondéré, configuration française + `unaccent`), trigram pour fautes, synonymes (table) |
| P3-T02 | Recherche hybride : plein texte + vecteur, fusion RRF (*reciprocal rank fusion*), filtres, facettes (skill `hybrid-search-implementation`) |
| P3-T03 | Priorité territoriale 8.11 : calcul des cercles, ordre strict, élargissement automatique, bloc « le plus proche », arrondis de distance |
| P3-T04 | Suggestions et autocomplétion (< 50 ms) |
| P3-T05 | Carte `/carte` (MapLibre, agrégats H3, positions décalées) |
| P3-T06 | Catalogue W02 complet (filtres maquette, pastilles, tris, grille/liste, cercles titrés) et accueil W01 |
| P3-T07 | Recherches enregistrées et alertes (job de correspondance à chaque `listing.published`, regroupement quotidien/hebdomadaire) |
| P3-T08 | Module notifications : in-app, e-mail (modèles traduits), Web Push (VAPID) ; préférences ; centre W18 |
| P3-T09 | Événements d'interaction (`POST /events`, partitionnement) |
| P3-T10 | Feed v1 (8.12) : pipeline, trois fils, « Pourquoi je vois ça ? », option non personnalisée, mode « Pas maintenant », quota découverte, diversité |
| P3-T11 | Plateforme A/B (affectation déterministe, exposition journalisée, tableau de résultats simple) |
| P3-T12 | Performance : index, `EXPLAIN ANALYZE` sur 1 M d'annonces générées, p95 < 150 ms (skill `sql-optimization-patterns`) |
| P3-T13 | e2e parcours 3 |

**Porte P3** : recherche p95 < 150 ms sur 1 M d'annonces ; aucun résultat d'un cercle supérieur au-dessus d'un résultat pertinent d'un cercle inférieur (test de propriété) ; positions publiques jamais exactes (test).

### 17.5 P4 — Commande, paiement, séquestre, grand livre

| Tâche | Contenu |
|---|---|
| P4-T01 | Interface `PaymentProvider` + `FakePaymentProvider` complet (succès, échec, 3-D Secure, rétrofacturation) |
| P4-T02 | `StripeConnectProvider` (mode test) : comptes connectés, onboarding hébergé, paiements, transferts, remboursements, versements, webhooks (skills `stripe-best-practices`, `connect-recommend`) **[À VALIDER : prestataire]** |
| P4-T03 | Activation vendeur, `seller_accounts`, informations pros DSA art. 30 (VIES), plafond avant KYC |
| P4-T04 | Calculs : protection (8.1), commission et attribution (8.2), marge de paiement, livraison estimée — fonctions pures + tableaux d'exemples en tests |
| P4-T05 | Offres et contre-offres (8.5, 9.6), réservation, lots |
| P4-T06 | Panier multi-vendeurs, `checkout/quote`, `checkout` (verrous, idempotence, expiration 30 min) |
| P4-T07 | Webhooks paiement → transaction unique : commande `paid`, séquestre, écritures, annonces vendues, outbox |
| P4-T08 | Grand livre complet : plan de comptes, écritures 10.4, invariants 10.5 (tests de propriétés), vue des soldes |
| P4-T09 | Libération du séquestre (service + job), transferts |
| P4-T10 | Solde vendeur, versements standard et instantanés, revue manuelle (9.5) |
| P4-T11 | Remboursements (service, seuils, double validation) |
| P4-T12 | Factures TROVÉLYA (numérotation continue, PDF) |
| P4-T13 | Rapprochement quotidien + alerte |
| P4-T14 | Écrans W12 (panier, paiement avec Payment Element, Apple Pay, Google Pay), W13 (suivi d'achat), W15 (solde) |
| P4-T15 | Tests de concurrence : 2 acheteurs, 1 article → 1 seule commande payée ; e2e parcours 4 (avec prestataire factice) |

**Porte P4** : 10 000 scénarios de paiement simulés → grand livre équilibré, rapprochement à 0 € d'écart ; aucun double débit en rejouant tous les webhooks ; montants affichés = montants facturés au centime.

### 17.6 P5 — Remise, expédition, après-vente

| Tâche | Contenu |
|---|---|
| P5-T01 | Remise en main propre (8.7) : code, QR signé, saisie et scan (caméra web), verrouillage, rendez-vous, lieux publics suggérés |
| P5-T02 | Adaptateur transporteurs (Boxtal ou Sendcloud **[À VALIDER]**) : tarifs, points relais (carte), étiquettes, suivi (webhooks) |
| P5-T03 | Délais d'expédition, annulation automatique (8.6.5) |
| P5-T04 | Vérification vidéo (8.8) : capture in-app web (`MediaRecorder`), checklist guidée, horodatage serveur, analyse IA v1 |
| P5-T05 | Confirmation de réception, libération automatique 48 h (horloge injectée) |
| P5-T06 | Rétractation 14 jours (pros), retours, étiquettes retour |
| P5-T07 | Litiges (8.9, 9.4) : ouverture, preuves, réponse vendeur, propositions, décision support, remboursements |
| P5-T08 | Avis (8.10) : double aveugle, réponse, pages publiques |
| P5-T09 | Écrans W13 (complet), W14, W17 ; bouton « Revendre » |
| P5-T10 | e2e parcours 5 et 6 |

**Porte P5** : bêta fermée possible ; parcours 4, 5, 6 verts sur staging avec le prestataire en mode test ; un litige suit chaque branche de sa machine à états (tests).

### 17.7 P6 — Messagerie et anti-contournement

| Tâche | Contenu |
|---|---|
| P6-T01 | WebSocket (12.1) : authentification, abonnements, Redis pub/sub, reprise par `seq` |
| P6-T02 | Conversations et messages, pièces jointes (images), accusés de lecture, indicateur de saisie |
| P6-T03 | Messages système liés aux commandes et aux offres ; proposition de rendez-vous |
| P6-T04 | Moteur de détection (8.16) : normalisation (chiffres en lettres, séparateurs, homoglyphes), règles regex éditables, mots-clés, validation IBAN, OCR des images, score de confiance |
| P6-T05 | Masquage, rappel pédagogique, conservation chiffrée de l'original |
| P6-T06 | Échelle de sanctions, `visibility_factor`, exposés des motifs, recours |
| P6-T07 | Leviers activables (paramètres) et affichage des avantages « dans l'app » au bon moment |
| P6-T08 | Écrans W16 ; jeu de tests de 500 messages annotés (vrais et faux positifs) : précision ≥ 95 %, rappel ≥ 90 % sur les numéros et e-mails |
| P6-T09 | e2e parcours 7 (côté utilisateur) |

**Porte P6** : messages livrés en < 300 ms p95 ; objectifs de précision/rappel atteints ; aucune coordonnée en clair dans la messagerie sur le jeu de tests.

### 17.8 P7 — Confiance

| Tâche | Contenu |
|---|---|
| P7-T01 | Calcul du score (8.13) : fonctions pures testées sur cas types, job nocturne, historique |
| P7-T02 | Badges (8.14), attribution/retrait automatiques |
| P7-T03 | Rangs (8.15), revue mensuelle, effet sur commissions et visibilité |
| P7-T04 | Comptes liés (empreinte d'appareil, carte via prestataire, IP, adresse) et exclusions |
| P7-T05 | Score de risque transactionnel (règles v1 : compte récent, montant, vélocité, pays, incohérences) → `allow/review/block` |
| P7-T06 | Affichages : niveau public, badges, rang sur profil, fiche et cartes ; page W19 avec conseils |
| P7-T07 | Garantie TROVÉLYA : page explicative, mentions sur fiche et paiement |

**Porte P7** : scores recalculés pour 100 000 utilisateurs simulés en < 10 min ; ventes entre comptes liés exclues (test).

### 17.9 P8 — Tour de contrôle et conformité

| Tâche | Contenu |
|---|---|
| P8-T01 | Application admin (`(admin)` sous `admin.trovelya.com`) : authentification staff, passkey obligatoire, mise en page de la maquette (7 espaces) |
| P8-T02 | Vue d'ensemble : chiffres clés (dont « Revenu du jour »), graphique, pays, incidents, **copilote IA** (3 recommandations argumentées, actions en un clic soumises à validation) |
| P8-T03 | Utilisateurs : recherche, fiche 360°, sanctions, notes internes |
| P8-T04 | Anti-contournement : file des cas avec preuve surlignée, décisions a0 (faux positif) à a4, règles et leviers, canaux |
| P8-T05 | Modération : signalements, annonces en revue, décisions avec exposé des motifs, recours |
| P8-T06 | Litiges : file, assignation, décisions |
| P8-T07 | Finances : revenus par source, séquestre, versements à valider (double validation), remboursements, rapprochement |
| P8-T08 | Journal d'audit : recherche, filtres, vérification de chaîne |
| P8-T09 | Configuration : `platform_settings`, flags, catégories (double validation) |
| P8-T10 | Conformité : formulaire de signalement public W22, rapport de transparence, base de transparence UE, DAC7 (agrégation, export), rappels GPSR |
| P8-T11 | Pages légales définitives (14.10) et centre d'aide W21 |
| P8-T12 | Test d'intrusion externe, audit d'accessibilité, revue `security-review` complète |
| P8-T13 | e2e parcours 7 (côté staff), 8, 9, 10 |

**Porte P8 = lancement public Paris possible** : pentest sans faille haute ouverte ; WCAG AA sur parcours critiques ; avocat a validé CGU/CGV ; prestataire de paiement en production ; runbooks testés ; restauration testée.

### 17.10 P9 — Verticales

| Tâche | Contenu |
|---|---|
| P9-T01 | `transaction_model` et `vertical` pilotent API et web : boutons, tunnel, frais, règles de messagerie (8.23) |
| P9-T02 | Tables `real_estate_details`, `vehicle_details`, `service_details`, schémas de validation par sous-catégorie |
| P9-T03 | Comptes pros vérifiés (`pro_licenses`), onglet « Pros à vérifier » en Tour de contrôle |
| P9-T04 | Publication immobilier : formulaire, mentions obligatoires, contrôles 8.20.3 (DPE G, encadrement, discrimination, doublons, prix anormal) |
| P9-T05 | Recherche immobilière : carte, zone dessinée, filtres, alertes ; gabarit de fiche W35 |
| P9-T06 | Visites et rendez-vous : créneaux, réservations, rappels, agenda W38 |
| P9-T07 | Anti-arnaque immobilier et véhicules, file prioritaire |
| P9-T08 | Estimation DVF (import, agrégats, « Estimer mon bien ») |
| P9-T09 | Véhicules : formulaire, référentiel marques/modèles, contrôles, gabarit W36, essais |
| P9-T10 | Paiement protégé véhicules et check-list de cession |
| P9-T11 | Services : fiches prestataires, devis et rendez-vous, W37 |
| P9-T12 | Import par flux pros |
| P9-T13 | Offres pros et options de visibilité (facturation via le prestataire) |
| P9-T14 | e2e : agence → flux → annonce → visite ; particulier → location refusée (G) ; vente de voiture avec paiement protégé |

### 17.11 P10 à P21

Chaque phase suit le même format : plan détaillé (`docs/plans/`), tâches numérotées, porte. Découpage indicatif :

| Phase | Tâches indicatives (ordre) |
|---|---|
| **P10** Boutiques | T01 plans et abonnements (facturation récurrente via prestataire) · T02 boutiques et membres · T03 catalogue pro (produits, variantes, stock multi-entrepôts, stock unique) · T04 Vitrine : rendu public, thèmes, sections · T05 éditeur visuel · T06 domaines et SSL · T07 import CSV · T08 migration Shopify · T09 redirections SEO · T10 commandes pro, rétractation, factures pour compte · T11 marketing (codes, panier abandonné, fidélité) · T12 analytique marchand · T13 équipe et B2B · T14 Google Merchant Center · T15 Atelier W24 · T16 porte 15.2 |
| **P11** Ads | T01 comptes, campagnes, budgets · T02 formats et créations · T03 estimation P(clic)/P(achat) v1 · T04 enchère au second prix + qualité · T05 insertion feed/recherche avec plafonds · T06 groupe témoin et lift · T07 pilote automatique v1 · T08 remontée d'annonce · T09 facturation · T10 tableau de bord annonceur W25 · T11 transparence (« Pourquoi cette pub ? ») |
| **P12** Enchères | T00 feu vert avocat · T01 modèle et machine à états · T02 moteur à écrivain unique · T03 anti-sniping, auto-enchère, réserve, achat immédiat · T04 empreintes bancaires · T05 formats hollandaise, scellée, multi-lots · T06 collusion · T07 temps réel · T08 écrans W26 · T09 tests de charge · T10 authentification par expert |
| **P13** Live | T01 intégration LiveKit, studio web · T02 programmation, rappels · T03 épinglage et achat dans la vidéo · T04 enchères éclair · T05 chat modéré et transcription · T06 co-live · T07 replay chapitré · T08 multidiffusion · T09 soirées de ventes · T10 espace Lives de la Tour de contrôle · T11 mesure des coûts |
| **P14** Drops… | T01 drops et file équitable · T02 tirage au sort · T03 précommandes participatives · T04 achats groupés · T05 demande inversée + lien avec la recherche sans résultat |
| **P15** Communauté | T01 collections curatées · T02 listes d'envies · T03 affiliation · T04 cercles · T05 shopping entre amis · T06 quêtes et saisons · T07 score d'impact · T08 fidélité acheteurs |
| **P16** IA | T01 entrepôt de caractéristiques et jeux d'entraînement · T02 modèle deux tours · T03 classement multi-objectifs · T04 A/B et déploiement · T05 recherche photo · T06 recherche conversationnelle et vocale · T07 mode Chasse · T08 studio photo · T09 analyste marchand · T10 service client IA · T11 boutique générée · T12 prévisions |
| **P17** Vie de l'objet | T01 passeport et QR · T02 événements de vie · T03 royalties · T04 histoire de l'objet · T05 valorisations quotidiennes · T06 patrimoine et alertes · T07 valeur de revente estimée sur fiche |
| **P18** International | T01 pays, devises, taux · T02 traductions d'interface (vague 2) · T03 traduction des annonces · T04 moyens de paiement locaux · T05 étiquette UE · T06 TVA par pays et OSS · T07 vague 3 et devises hors euro |
| **P19** Écosystème | T01 OAuth 2.1 et API publique · T02 webhooks sortants · T03 portail développeurs · T04 apps tierces · T05 marché des templates · T06 fournisseurs et dropshipping · T07 TROVÉLYA+ · T08 Google/Meta · T09 rapports de tendances · T10 hébergement souverain |
| **P20** Innovations | T01 agents négociateurs · T02 bourse des objets · T03 scan de la maison (web d'abord, natif en P21) · T04 échanges en chaîne · T05 page copropriétaires |
| **P21** Mobile | T01 `apps/mobile` (skills Expo) · T02 authentification mobile · T03 navigation et écrans principaux · T04 vente express caméra · T05 messagerie et notifications push · T06 achat et paiement natifs · T07 live natif · T08 scan QR, vérification vidéo, scan de la maison · T09 accessibilité et performance · T10 EAS Build/Submit/Update · T11 publication stores |

---

## 18. Décisions ouvertes

| # | Décision | Valeur par défaut d'implémentation | Bloque | Responsable |
|---|---|---|---|---|
| D1 | Prestataire de paiement | Stripe Connect derrière `PaymentProvider` | P4 en production | Arcel |
| D2 | Avocat : CGU/CGV, courtage des enchères, statut DSA, médiateur | — | P8 lancement, P12 | Arcel |
| D3 | Expert-comptable : TVA plateforme, OSS, mandat de facturation, facturation électronique, DAC7 | TVA FR 20 % sur services plateforme | P4 production, P18 | Arcel |
| D4 | Dépôt de la marque TROVÉLYA (INPI puis EUIPO) et domaines (`trovelya.com`, `.fr`, `.eu`) | — | P0-T14 | Arcel |
| D5 | Agrégateur transport : Boxtal ou Sendcloud | Boxtal | P5 | Arcel |
| D6 | Fournisseur IA (vision, LLM, embeddings) avec traitement UE | Adaptateur ; fournisseur à choisir | P2-T06 | Arcel |
| D7 | Fournisseur vidéo live | LiveKit Cloud UE | P13 | Arcel |
| D8 | Commission sur les lives/enchères entre particuliers | 0 % + protection acheteur | P12 | Arcel |
| D9 | Versement anticipé à l'expédition pour Or+ | Non | P7 | Arcel |
| D10 | Alcool chez les vendeurs pros | Interdit | P2 | Arcel + avocat |
| D11 | Jalons de mise en ligne (4.4) | Selon tableau | — | Arcel |
| D12 | Achats intégrés stores pour services numériques (P21) | Analyse avant P21 | P21 | Arcel |
| D13 | Moteur de recherche dédié (Typesense/OpenSearch) | PostgreSQL jusqu'aux seuils ADR-0003 | — | Technique |
| D14 | Juriste immobilier : positionnement hors loi Hoguet, mentions obligatoires, DPE, encadrement des loyers, meublés de tourisme | Annonces + mise en relation, aucun fonds | P9 | Arcel |
| D15 | Plafond du paiement protégé pour les véhicules (avec le prestataire) | 50 000 € | P9 | Arcel |
| D16 | Tarifs des offres pros immobilier, auto, services | Section 8.20.6, 8.21.5, 8.22 | P9 | Arcel |
| D17 | Univers mis en avant dans la communication de lancement | Aucune restriction de catalogue | Marketing | Arcel |
| D18 | Ouvrir un univers Emploi (offres d'emploi) | Non | — | Arcel |
| D19 | Réservation et paiement intégrés pour la location saisonnière et les services | Hors périmètre, étude en P19 | P19 | Arcel |
| D20 | Fournisseur de décodage VIN / cote véhicule | Adaptateur ; à choisir | P9 | Arcel |

---

## 19. Correspondance phases ↔ skills installés

| Besoin | Skills à charger |
|---|---|
| Avant toute fonctionnalité | `brainstorming` ou `grill-me`/`grilling`, `writing-plans`, `karpathy-guidelines`, `domain-modeling` |
| Exécution | `executing-plans`, `subagent-driven-development`, `dispatching-parallel-agents`, `using-git-worktrees`, `test-driven-development` |
| Fin de tâche | `verification-before-completion`, `requesting-code-review`, `receiving-code-review`, `finishing-a-development-branch` |
| Bug | `systematic-debugging` |
| Monorepo (P0) | `monorepo-management`, `turborepo-caching`, `modern-python`, `uv-package-manager` |
| API FastAPI | `fastapi-patterns`, `api-design`, `async-python-patterns`, `python-error-handling`, `python-type-safety`, `python-testing-patterns`, `python-background-jobs`, `python-observability` |
| Base de données | `postgresql-table-design`, `postgresql-optimization`, `postgresql-code-review`, `sql-optimization-patterns`, `database-migration` |
| Redis, temps réel, enchères | `redis-patterns`, `async-python-patterns` |
| Recherche et feed | `hybrid-search-implementation`, `recsys-pipeline-architect` |
| Paiements | `connect-recommend`, `stripe-best-practices` |
| Web | `nextjs-app-router-patterns`, `vercel-react-best-practices`, `vercel-composition-patterns`, `frontend-design`, `web-design-guidelines`, `next-intl-add-language` |
| Tests web | `webapp-testing`, `e2e-testing-patterns` |
| Accessibilité | `wcag-audit-patterns` |
| Sécurité | `security-review`, `auth-implementation-patterns`, `stride-analysis-patterns`, `semgrep`, `sharp-edges`, `supply-chain-risk-auditor` |
| RGPD | `gdpr-data-handling` |
| Déploiement | `docker-patterns`, `deployment-patterns`, `deploy-to-vercel` |
| Mobile (P21) | `expo-overview` (toujours en premier), `expo-project-structure`, `expo-router`, `expo-data-fetching`, `expo-native-ui`, `expo-design-system`, `vercel-react-native-skills`, `eas-app-stores`, `eas-update` |
| Prototype jetable | `prototype` |
| Passation entre sessions | `handoff` |
| Besoin non couvert | `find-skills` |

---

## Annexe A — Premier message à donner à Claude Code

> Lis `CLAUDE.md` puis `docs/CAHIER_DES_CHARGES.md` en entier. Nous commençons la **phase P0 — Fondations** (section 17.1), web d'abord. Applique `brainstorming` pour confirmer ta compréhension et me poser tes questions bloquantes, puis `writing-plans` pour produire `docs/plans/P0-fondations.md` avec les tâches P0-T01 à P0-T16, leurs tests et leurs points de validation. N'écris pas de code avant que je valide le plan.

## Annexe B — Récapitulatif des paramètres par défaut

| Clé | Valeur |
|---|---|
| `fees.buyer_protection.fixed_minor` | 70 |
| `fees.buyer_protection.percent_bp` | 500 |
| `fees.buyer_protection.cap_minor` | 15000 |
| `fees.payment_margin_bp` | 40 |
| `commission.marketplace_bp_by_rank` | `{"bronze":800,"silver":700,"gold":600,"platinum":550,"legend":500}` |
| `commission.live_platform_bp` | 1000 |
| `commission.live_external_bp` | 500 |
| `commission.own_traffic_bp` | 0 |
| `commission.preorder_bp` | 500 |
| `commission.cap_minor` | 25000 |
| `attribution.window_days` | 7 |
| `offers.ttl_hours` | 48 |
| `offers.min_ratio_bp` | 5000 |
| `offers.reservation_hours` | 24 |
| `checkout.reservation_minutes` | 30 |
| `escrow.auto_release_hours` | 48 |
| `fulfillment.auto_cancel_days` | 7 |
| `handover.max_attempts` | 5 |
| `handover.deadline_days` | 7 |
| `verification_video.required_above_minor` | 15000 |
| `disputes.seller_response_hours` | 72 |
| `geo.default_radius_m` | 5000 |
| `geo.auto_expand_threshold` | 10 |
| `search.ranking_weights` | `{"relevance":0.45,"proximity":0.20,"trust":0.15,"quality":0.10,"price":0.10}` |
| `feed.discovery_slot_every` | 8 |
| `ads.max_share_feed` | 1/6 |
| `ads.max_top_search` | 2 |
| `ads.min_quality` | 0.4 |
| `ads.holdout_pct` | 5 |
| `trust.window_days` | 90 |
| `payouts.manual_review_above_minor` | 500000 |
| `payouts.instant_fee_bp` | 100 (min 50) |
| `kyc.max_unverified_sales_minor` | 50000 |
| `auctions.anti_snipe_seconds` | 30 |
| `listings.expiry_days` | 120 |
| `retention.verification_video_days` | 365 |
| `geo.default_radius_m_by_vertical` | `{"goods":5000,"services":10000,"vehicles":50000,"real_estate":null}` |
| `real_estate.rent_min_energy_class` | `F` (G refusé) |
| `real_estate.max_individual_rentals` | 3 |
| `real_estate.price_anomaly_pct` | 40 |
| `vehicles.protected_payment_cap_minor` | 5000000 |
| `listings.max_photos_by_vertical` | `{"goods":12,"real_estate":30,"vehicles":30,"services":12}` |

---

*Fin du cahier des charges v1.1 — TROVÉLYA, « La belle trouvaille ».*

