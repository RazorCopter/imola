#!/usr/bin/env bash
# Istanza PostgreSQL portatile per lo sviluppo su macchine senza WSL2 o Docker.
# I binari ufficiali stanno in PG_BIN, i dati in PG_DATA, la porta e 5433 per non
# collidere con un eventuale PostgreSQL di sistema.
set -euo pipefail

PG_BIN="${PG_BIN:-/c/dev/pg-download/extract/pgsql/bin}"
PG_DATA="${PG_DATA:-C:/dev/pgdata}"
PG_PORT="${PG_PORT:-5433}"
LOG="${PG_DATA}/server.log"

case "${1:-}" in
  start)
    "${PG_BIN}/pg_ctl.exe" -D "${PG_DATA}" -l "${LOG}" \
      -o "-p ${PG_PORT} -c listen_addresses=127.0.0.1" start &
    for _ in $(seq 1 30); do
      if "${PG_BIN}/pg_isready.exe" -h 127.0.0.1 -p "${PG_PORT}" >/dev/null 2>&1; then
        echo "PostgreSQL in ascolto su 127.0.0.1:${PG_PORT}"
        exit 0
      fi
      sleep 1
    done
    echo "Avvio non riuscito, ultime righe del log:" >&2
    tail -20 "${LOG}" >&2
    exit 1
    ;;
  stop)
    "${PG_BIN}/pg_ctl.exe" -D "${PG_DATA}" -m fast stop
    ;;
  status)
    "${PG_BIN}/pg_isready.exe" -h 127.0.0.1 -p "${PG_PORT}"
    ;;
  psql)
    shift
    PGPASSWORD=supplier_ledger "${PG_BIN}/psql.exe" -h 127.0.0.1 -p "${PG_PORT}" \
      -U supplier_ledger -d supplier_ledger "$@"
    ;;
  *)
    echo "Uso: $0 {start|stop|status|psql}" >&2
    exit 2
    ;;
esac
