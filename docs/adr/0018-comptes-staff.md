# ADR-0018 — Comptes staff : passkey seule, création et enrôlement par script

**Statut :** Acceptée (décision Q18 d'Arcel, écart E9 du plan P1)
**Date :** 24 octobre 2026

## Contexte

Le cahier (3.1) réserve les comptes staff aux adresses du domaine de l'entreprise, avec une authentification forte. TROVÉLYA n'a pas encore de domaine (acheté à la fin du projet). Au départ, Arcel est le seul membre du staff, avec le rôle `staff_superadmin`. La double validation (3.2, Q17) exige un approbateur distinct du demandeur et détenant la même permission : avec un seul compte staff, aucune action 🔒 ne peut aboutir.

## Décision

1. **Compte staff distinct** du compte client : on ne transforme jamais un compte client en compte staff. Arcel utilise une adresse dédiée (`djoutchouangpepemssie+staff@gmail.com`).
2. **Création par script**, depuis le serveur : `uv run python -m trovelya.scripts.create_staff --email … --role staff_superadmin` (sur Railway : `railway run`). Le script refuse une adresse déjà utilisée par un compte client et refuse un rôle qui n'est pas un rôle staff. Il inscrit la création au journal d'audit (`actor_type = "system"`).
3. **Lien d'enrôlement** affiché dans le terminal, jamais envoyé par e-mail : `{WEB_ORIGIN}/fr/staff/enrolement#token=…`, valable 15 minutes et à usage unique. Le jeton n'est gardé dans Redis que sous forme d'empreinte SHA-256. Il n'est consommé qu'une fois la passkey prouvée, si bien qu'une tentative refusée (mauvais site, annulation) laisse le lien utilisable. La page retire le jeton de la barre d'adresse dès qu'elle l'a lu. Relancer le script pour un compte staff sans passkey donne un nouveau lien ; une fois une passkey enregistrée, il refuse.
4. **Passkey seule** : le lien magique et la connexion Google/Apple sont refusés aux comptes staff (P1-T02c, T03). Une connexion par passkey ouvre une session `admin` de 12 heures. Les routes staff exigent un compte staff, une session `admin` et une preuve forte récente.
5. **Interrupteur `auth.passkeys`** : quand il est éteint, les membres ne peuvent ni ajouter ni gérer de passkey, mais la connexion par passkey et l'enrôlement staff restent ouverts. Un membre ne pouvant pas détenir de passkey tant que l'interrupteur est éteint, seul le staff s'en sert.

## Conséquences

+ Le premier compte staff existe sans domaine, sans e-mail et sans mot de passe.
+ Le jeton d'enrôlement ne transite ni par un e-mail ni par un journal.
− Avec un seul compte staff, aucune action soumise à double validation ne peut aboutir (attribution de rôles staff, suspension, etc.). C'est voulu : les comptes suivants seront créés par le même script, puis les rôles gérés par double validation.
− Si Arcel perd sa passkey staff, il faudra un accès au serveur pour réinitialiser le compte (supprimer la passkey puis relancer le script). La procédure sera décrite dans le runbook avant le lancement.
− À rouvrir quand le domaine existera : restreindre les comptes staff aux adresses de ce domaine.
