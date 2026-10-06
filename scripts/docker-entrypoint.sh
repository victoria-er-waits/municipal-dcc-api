#!/bin/sh
# Container entrypoint. Persistent disks (Render disks, Fly volumes, docker -v) usually mount root-owned,
# so as root: create/chown the disk directories, then drop to the unprivileged 'app' user and exec CMD.
#
#   DATABASE_PATH     accounts / API-key hashes / usage / Stripe ids  (e.g. /var/data/accounts.sqlite3)
#   OPERATOR_DB_PATH  paid (Surrey) rate DB copied onto the disk once (e.g. /var/data/dcc-operator.sqlite3).
#                     Absent file = public Victoria-only build DB; paid-only cities answer 404 "not in this build".
set -e

ACCOUNTS_DIR="$(dirname "${DATABASE_PATH:-/var/data/accounts.sqlite3}")"

if [ -n "${ADMIN_UNLOCK_TOKEN:-}" ]; then
  echo "WARNING: ADMIN_UNLOCK_TOKEN is set -> POST /v1/admin/unlock is ENABLED. Leave it empty in production." >&2
fi

if [ "$(id -u)" = "0" ]; then
  mkdir -p "$ACCOUNTS_DIR"
  chown -R app:app "$ACCOUNTS_DIR" 2>/dev/null || echo "warning: could not chown $ACCOUNTS_DIR" >&2
  if [ -n "${OPERATOR_DB_PATH:-}" ]; then
    OPERATOR_DIR="$(dirname "$OPERATOR_DB_PATH")"
    mkdir -p "$OPERATOR_DIR"
    # SQLite needs a writable directory for its journal; the file itself is chowned to app.
    chown app:app "$OPERATOR_DIR" 2>/dev/null || echo "warning: could not chown $OPERATOR_DIR" >&2
    if [ -f "$OPERATOR_DB_PATH" ]; then
      chown app:app "$OPERATOR_DB_PATH" 2>/dev/null || echo "warning: could not chown $OPERATOR_DB_PATH" >&2
      chmod 0640 "$OPERATOR_DB_PATH" 2>/dev/null || true
      echo "Operator rate DB: $OPERATOR_DB_PATH (paid municipalities served from it)" >&2
    else
      echo "Operator rate DB not found at $OPERATOR_DB_PATH -> public build DB only (paid-only cities 404)." >&2
    fi
  else
    echo "OPERATOR_DB_PATH unset -> public build DB only (Victoria)." >&2
  fi
  if command -v setpriv >/dev/null 2>&1; then
    exec setpriv --reuid=app --regid=app --init-groups "$@"
  fi
  echo "warning: setpriv not found; running as root" >&2
fi

exec "$@"
