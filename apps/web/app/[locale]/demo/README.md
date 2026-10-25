# Démonstration provisoire de la maquette

Ces pages reproduisent à l'identique les écrans web de la maquette (design et produits) pour
visualiser le produit avant que les vraies fonctionnalités n'existent. **Tout y est fictif** :
produits, prix, vendeurs, lives et chiffres. Aucune donnée n'est lue ni écrite côté API.

- Adresse : `/fr/demo` (accueil), puis `catalogue`, `annonce`, `live`, `atelier`.
- Jamais en production (`VERCEL_ENV=production` répond 404), jamais indexée (`noindex`).
- Un bandeau « Démonstration · données fictives » reste visible sur chaque écran.

## Retirer la démonstration

1. Supprimer ce dossier `apps/web/app/[locale]/demo/` et `apps/web/public/demo/`.
2. Supprimer `apps/web/components/SiteChrome.tsx` et son usage dans `app/[locale]/layout.tsx`
   (remettre `SiteHeader`, `SiteFooter` et `BottomTabs` directement).
3. Retirer le bloc « Temporary mock-up demo » de `apps/web/eslint.config.js`.
4. Supprimer `tests/e2e/demo.spec.ts`.
