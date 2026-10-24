# ADR-0007 — Tâches asynchrones avec arq et outbox transactionnelle

**Statut :** Acceptée (cahier 5.2), en place depuis P0-T06
**Date :** 24 octobre 2026

## Contexte

Un événement de domaine ne doit être ni perdu ni émis pour une transaction annulée.

## Décision

Les événements sont écrits dans `outbox_events` dans la même transaction que la donnée (`shared/events.emit_event`). Le worker `arq` (`workers/main.py`) les publie chaque seconde dans le flux Redis `trv:events`, par lots verrouillés `FOR UPDATE SKIP LOCKED`, au moins une fois ; les consommateurs sont idempotents (`consume_once`, table `processed_events`). L'âge du plus ancien événement non publié est exporté (`trovelya_outbox_oldest_unpublished_seconds`).

## Conséquences

+ Aucun événement fantôme ni perdu (tests G4).
− Livraison « au moins une fois » : tout consommateur doit rester idempotent.
