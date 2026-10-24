#!/usr/bin/env bash
# Restore exercise (docs/runbooks/restore.md): dump the database at $DATABASE_URL, restore it
# into a throwaway database on the same server, compare row counts table by table, verify
# the audit chain and the extensions, then drop the throwaway database.
# Needs PostgreSQL 17 client tools (image postgres:17) and the right to CREATE DATABASE.
set -eu
SRC="$DATABASE_URL"
BASE="${SRC%/*}"
DRILL_DB="restore_drill"
q() { psql "$1" -v ON_ERROR_STOP=1 -AtXc "$2"; }
counts() {
  sql=$(q "$1" "select string_agg(format('select %L as t, count(*) as n from public.%I', table_name, table_name), ' union all ' order by table_name) from information_schema.tables where table_schema = 'public' and table_type = 'BASE TABLE'")
  q "$1" "select string_agg(t || '=' || n, ' ' order by t) from ($sql) c"
}
echo "DRILL start $(date -u +%FT%TZ) server=$(q "$SRC" 'show server_version')"
# The exercise is itself an operation: it is written to the audit log (CLAUDE.md).
q "$SRC" "insert into audit_log (actor_type, action, target_type, target_id, reason) values ('system', 'ops.restore_drill', 'database', '${DRILL_TARGET:-staging}', 'restore exercise')" >/dev/null
echo "G3 extensions: $(q "$SRC" "select string_agg(extname, ',' order by extname) from pg_extension")"
echo "G5 audit chain: rows=$(q "$SRC" 'select count(*) from audit_verify_chain()') all_ok=$(q "$SRC" 'select coalesce(bool_and(ok), true) from audit_verify_chain()')"
echo "alembic: $(q "$SRC" "select string_agg(version_num, ',') from alembic_version")"
BEFORE=$(counts "$SRC")
echo "source counts: $BEFORE"
T0=$(date +%s)
pg_dump --format=custom --file=/tmp/drill.dump "$SRC"
echo "dump: $(stat -c %s /tmp/drill.dump) bytes in $(( $(date +%s) - T0 )) s"
q "$SRC" "drop database if exists $DRILL_DB" >/dev/null
q "$SRC" "create database $DRILL_DB" >/dev/null
T1=$(date +%s)
# Triggers are restored after the data (post-data section): audit rows keep their hashes.
pg_restore --no-owner --exit-on-error --dbname="$BASE/$DRILL_DB" /tmp/drill.dump
echo "restore: $(( $(date +%s) - T1 )) s"
AFTER=$(counts "$BASE/$DRILL_DB")
echo "restored counts: $AFTER"
[ "$BEFORE" = "$AFTER" ] && echo "counts: identical" || { echo "counts: DIFFERENT"; exit 1; }
echo "restored audit chain: rows=$(q "$BASE/$DRILL_DB" 'select count(*) from audit_verify_chain()') all_ok=$(q "$BASE/$DRILL_DB" 'select coalesce(bool_and(ok), true) from audit_verify_chain()')"
echo "restored extensions: $(q "$BASE/$DRILL_DB" "select string_agg(extname, ',' order by extname) from pg_extension")"
q "$SRC" "drop database $DRILL_DB" >/dev/null
echo "DRILL OK $(date -u +%FT%TZ)"
