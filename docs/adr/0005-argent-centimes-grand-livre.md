# ADR-0005 — Argent : centimes entiers et grand livre en partie double

**Statut :** Acceptée (cahier 5.2), socle en place depuis P0-T07
**Date :** 24 octobre 2026

## Contexte

Les erreurs d'arrondi et les écritures déséquilibrées sont inacceptables sur une place de marché qui manipule des fonds en séquestre.

## Décision

Montants en centimes entiers (`BIGINT`) avec devise ISO 4217 ; jamais de nombres à virgule (règle semgrep `trovelya-money-no-float`, `shared/money.py` couvert à 100 %). Tout mouvement passe par le grand livre en partie double (`modules/ledger`) : contrainte différée d'équilibre par transaction, au moins deux écritures, devise de l'écriture = devise du compte, écritures immuables. Écriture idempotente (`post_transaction` par clé).

## Conséquences

+ L'équilibre est garanti par la base, pas seulement par le code (propriétés hypothesis en CI).
− Le plan de comptes et les écritures métier arrivent en P4.
