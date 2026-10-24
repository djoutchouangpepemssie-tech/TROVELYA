# ADR-0014 — Chaîne du journal d'audit calculée en base

**Statut :** Acceptée (écart E2)
**Date :** 24 octobre 2026

## Contexte

Le cahier (7.2) définit `audit_log.hash = SHA-256(prev_hash ‖ ligne canonique)` sans dire où le calcul est fait. Calculé en Python, deux insertions concurrentes pourraient lire le même `prev_hash` et faire fourcher la chaîne.

## Décision

Un trigger `BEFORE INSERT`, sérialisé par `pg_advisory_xact_lock`, réattribue l'identifiant, lit le dernier hash et calcule `sha256()` sur la ligne canonique (`jsonb_build_object(...)::text`). La table est en ajout seul (UPDATE et DELETE refusés). `audit_verify_chain()` recalcule toute la chaîne ; le worker la vérifie chaque nuit à 03 h 00.

## Conséquences

+ Chaîne inaltérable même sous concurrence (tests G5).
+ Une restauration `pg_restore` conserve les hash : les triggers sont recréés après les données (exercice du 24/10/2026).
− Les insertions d'audit sont sérialisées ; volume attendu faible (actions d'administration).
