#!/bin/sh
# Container entrypoint. Persistent disks (Render disks, Fly volumes, docker -v) usually mount root-owned,
# so as root: create/chown the accounts-DB directory, then drop to the unprivileged 'app' user and exec CMD.
set -e

DB_DIR="$(dirname "${DATABASE_PATH:-/data/accounts.sqlite3}")"

if [ -n "${ADMIN_UNLOCK_TOKEN:-}" ]; then
  echo "WARNING: ADMIN_UNLOCK_TOKEN is set -> POST /v1/admin/unlock is ENABLED. Leave it empty in production." >&2
fi

if [ "$(id -u)" = "0" ]; then
  mkdir -p "$DB_DIR"
  chown -R app:app "$DB_DIR" 2>/dev/null || echo "warning: could not chown $DB_DIR" >&2
  if command -v setpriv >/dev/null 2>&1; then
    exec setpriv --reuid=app --regid=app --init-groups "$@"
  fi
  echo "warning: setpriv not found; running as root" >&2
fi

exec "$@"
