# ADR-0016 — Export RGPD chiffré, stocké en base jusqu'au stockage de fichiers

**Statut :** Acceptée (décision Q16 d'Arcel, écart E8 du plan P1)
**Date :** 24 octobre 2026

## Contexte

Le RGPD (articles 15 et 20) donne à chacun le droit d'obtenir ses données dans un format lisible. Le cahier (14.1) prévoit un export en libre-service, livré « sous 30 jours, en pratique moins de 24 h », et le modèle (7.3) range le fichier produit dans le stockage de médias (`data_requests.result_media_id`). Ce stockage n'arrive qu'en P2. Chaque phase ajoute de nouvelles données personnelles : l'export doit les suivre sans qu'on réécrive le module identité.

## Décision

1. **Registre d'exportateurs** (`core/gdpr.py`) : chaque module enregistre une fonction `(session, user_id) -> dict` sous son nom. L'export contient une clé par exportateur. Identity enregistre `identity` ; chaque phase ajoute le sien.
2. **Ce qui est exporté** : toutes les tables reliées à la personne. Un test vérifie, par introspection des clés étrangères vers `users`, qu'aucune n'est oubliée. Sont exclus les secrets (empreintes de jetons, clés publiques et identifiants de passkeys) et les données d'autres personnes : on exporte les comptes que la personne suit ou bloque, jamais qui la bloque ; ses abonnés sont comptés, pas nommés.
3. **Production asynchrone** : `POST /v1/me/data-export` crée la demande (`data_requests`, une seule en cours par personne) et une tâche du worker construit une archive ZIP (`export.json` et `LISEZMOI.txt`). La personne reçoit un e-mail quand elle est prête.
4. **Stockage** : l'archive est chiffrée (AES-256-GCM, clé dérivée de `FIELD_ENCRYPTION_KEY` pour le seul usage « export RGPD », données associées liées à la demande) et rangée dans `data_exports`. `result_media_id` reste nul en P1.
5. **Durée** : 7 jours (`retention.data_export_days`), puis purge quotidienne.
6. **Accès** : demande et téléchargement exigent une connexion forte récente (step-up, 13.2). Le téléchargement d'une autre personne ou d'un export expiré répond 404. Demande, production et téléchargement sont inscrits au journal d'audit.

## Conséquences

+ Le droit d'accès est en libre-service dès P1, sans stockage de fichiers.
+ Une nouvelle table personnelle oubliée dans l'export fait échouer un test.
− Les archives occupent la base pendant 7 jours. Le volume reste faible en P1 (quelques kilo-octets par compte) ; à revoir quand les médias entreront dans l'export (P2), en passant au stockage objet.
− Les photos et documents ne sont pas dans l'export avant P2.
