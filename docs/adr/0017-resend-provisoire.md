# ADR-0017 — E-mails transactionnels par Resend, écart temporaire à la résidence UE

**Statut :** Acceptée, provisoire (décision Q6 d'Arcel, 24 octobre 2026)
**Date :** 24 octobre 2026

## Contexte

Le cahier (5.1) prévoit Brevo ou Postmark UE pour les e-mails transactionnels ; `CLAUDE.md` impose des données hébergées dans l'UE. TROVÉLYA n'a pas encore de domaine (acheté à la fin du projet). Sans domaine authentifié (SPF, DKIM, DMARC), Gmail et Yahoo rejettent ou classent en indésirables les e-mails de Brevo. Arcel n'a pas de compte Brevo et préfère Resend. Avant le lancement public, il est le seul utilisateur.

Resend peut envoyer depuis l'Irlande, mais conserve les données du compte (journaux, métadonnées des e-mails) aux États-Unis, sous clauses contractuelles types. Sans domaine, son adresse de test `onboarding@resend.dev` ne livre qu'à l'adresse du compte Resend.

## Décision

1. Les e-mails passent par une interface `EmailSender` (`shared/email.py`) : `ResendEmailSender` (API HTTPS), `SmtpEmailSender` (Mailpit en local et en CI), `FakeEmailSender` (tests). Le choix se fait par `EMAIL_PROVIDER` ; aucun code métier ne connaît le fournisseur.
2. Staging utilise Resend (`EMAIL_PROVIDER=resend`, `EMAIL_FROM=TROVÉLYA <onboarding@resend.dev>`). Seul Arcel reçoit des e-mails, à l'adresse de son compte Resend.
3. Un e-mail n'est mis en file qu'après la validation de la transaction qui le demande (`core/email.py`). Le message est chiffré (AES-256-GCM, clé dérivée de `FIELD_ENCRYPTION_KEY`) dans la file Redis du worker. Le worker l'envoie, avec 5 essais espacés. Les erreurs ne citent jamais l'adresse.
4. **Écart temporaire** à la règle « données dans l'UE » : les adresses et le contenu des e-mails envoyés transitent par Resend et ses métadonnées sont stockées aux États-Unis. **Avant le lancement public**, bascule vers un fournisseur hébergé dans l'UE (Brevo, Postmark UE ou équivalent) par simple configuration, une fois le domaine acheté et authentifié.

## Conséquences

+ La connexion par lien magique est testable de bout en bout sur staging dès maintenant.
+ Changer de fournisseur ne touche aucun code métier : un nouvel adaptateur et une variable.
− Tant que l'écart dure, aucune autre personne qu'Arcel ne doit recevoir d'e-mail de TROVÉLYA. C'est garanti par Resend lui-même (adresse de test).
− Point à rouvrir avant le lancement : choix du fournisseur UE et inscription au registre des sous-traitants.
