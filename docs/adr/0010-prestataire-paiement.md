# ADR-0010 — Prestataire de paiement derrière une interface

**Statut :** Proposée — choix final à valider par Arcel
**Date :** 24 octobre 2026

## Contexte

L'application ne détient jamais les fonds et ne stocke jamais de numéro de carte ; le séquestre et les versements sont confiés à un prestataire marketplace.

## Décision

Valeur par défaut d'implémentation : **Stripe Connect** (comptes Express/Custom via Accounts v2, *separate charges and transfers*), derrière une interface `PaymentProvider` qui permet Mangopay ou Adyen. Choix final avant P4.

## Conséquences

+ L'abstraction protège le choix final.
− Rien n'est construit en P0.
