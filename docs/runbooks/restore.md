# Runbook — restaurer la base de données

## Quand

- Perte ou corruption de données (erreur humaine, migration ratée, incident Railway).
- Exercice : au moins une fois par trimestre, et après tout changement de l'image PostgreSQL.

## Sauvegardes

- **Volume Railway** (`pg-data`, environnement concerné) : sauvegardes du volume dans Railway → service `pg` → *Backups* (à planifier dans Railway ; vérifier qu'au moins une sauvegarde quotidienne existe en production).
- **Sauvegarde logique** : `pg_dump --format=custom`, celle utilisée par l'exercice ci-dessous. Elle est portable d'un serveur à l'autre tant que la cible a les mêmes extensions (notre image, ADR-0011).

## Restaurer une sauvegarde logique

1. Geler les écritures : mettre l'API et le worker à 0 réplique (Railway → service → *Settings* → *Replicas*), ou couper le trafic.
2. Restaurer dans une **nouvelle** base, jamais par-dessus l'existante :
   ```bash
   createdb -h <hôte> -U <utilisateur> restored
   pg_restore --no-owner --exit-on-error --dbname=postgresql://…/restored sauvegarde.dump
   ```
   `pg_restore` recrée les triggers **après** les données : les lignes du journal d'audit gardent leurs hash d'origine, sans option particulière.
3. Vérifier : `select coalesce(bool_and(ok), true) from audit_verify_chain();` → `t`, nombre de lignes des tables principales, `select version_num from alembic_version`.
4. Basculer : faire pointer `DATABASE_URL` de l'API et du worker vers la base restaurée (ou renommer les bases pendant l'arrêt), puis remettre les répliques.
5. Consigner l'incident et la restauration dans le journal d'audit et dans un post-mortem.

## Exercice : script `infra/postgres/restore-drill.sh`

Le script sauvegarde la base de `$DATABASE_URL`, la restaure dans une base jetable `restore_drill` du même serveur, compare le nombre de lignes table par table, vérifie la chaîne d'audit et les extensions, supprime la base jetable, et inscrit l'exercice dans le journal d'audit (`ops.restore_drill`).

Le lancer sur Railway (aucun port de la base n'est exposé, l'exercice tourne donc dans le réseau privé) :

1. Dans l'environnement voulu, créer un service `ops-drill` à partir de l'image `postgres:17`.
2. Variables : `DATABASE_URL=${{pg.DATABASE_URL}}`, `DRILL_TARGET=<environnement>`, et `DRILL_SH` = contenu du script.
3. Commande de démarrage : `sh -c 'printf "%s" "$DRILL_SH" | bash; echo "exit=$?"; sleep infinity'`, redémarrage `NEVER`.
4. Lire les journaux du service, puis supprimer le service.

En local : `docker exec -e DATABASE_URL=… <conteneur postgres> bash /restore-drill.sh`.

## Exercice réel du 24 octobre 2026 (staging)

Serveur : service `pg` de staging, PostgreSQL 17.11, Railway europe-west4. Sortie du service `ops-drill` (déploiement `279d7442`) :

```
DRILL start 2026-10-24T12:33:11Z server=17.11 (Debian 17.11-1.pgdg13+2)
G3 extensions: btree_gist,citext,fuzzystrmatch,h3,h3_postgis,ltree,pg_trgm,plpgsql,postgis,postgis_raster,postgis_tiger_geocoder,postgis_topology,unaccent,vector
G5 audit chain: rows=1 all_ok=t
alembic: 0002
source counts: alembic_version=1 audit_log=1 feature_flags=0 idempotency_keys=0 ledger_accounts=0 ledger_entries=0 ledger_transactions=0 outbox_events=0 platform_settings=0 processed_events=0 spatial_ref_sys=8500
dump: 38679 bytes in 0 s
restore: 1 s
restored counts: alembic_version=1 audit_log=1 feature_flags=0 idempotency_keys=0 ledger_accounts=0 ledger_entries=0 ledger_transactions=0 outbox_events=0 platform_settings=0 processed_events=0 spatial_ref_sys=8500
counts: identical
restored audit chain: rows=1 all_ok=t
restored extensions: btree_gist,citext,fuzzystrmatch,h3,h3_postgis,ltree,pg_trgm,plpgsql,postgis,postgis_raster,postgis_tiger_geocoder,postgis_topology,unaccent,vector
DRILL OK 2026-10-24T12:33:14Z
exit=0
```

Constats :

- Restauration complète en **1 seconde** (base quasi vide) ; à remesurer quand la base grossira.
- Les 9 extensions du projet sont présentes. Les extensions `fuzzystrmatch`, `postgis_tiger_geocoder` et `postgis_topology` viennent des scripts d'initialisation de l'image PostGIS sur Railway ; elles sont inutilisées mais sans risque.
- Le test local montre aussi que l'option `--disable-triggers` est inutile : la chaîne d'audit reste valide sans elle.
