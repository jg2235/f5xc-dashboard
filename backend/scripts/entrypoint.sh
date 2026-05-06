#!/usr/bin/env bash
# Substitutes the postgres password from /run/secrets/postgres_password into
# DATABASE_URL's __PG_PWD__ placeholder. Idempotent and a no-op when the
# secret file is missing (dev mode without docker secrets).
set -euo pipefail

PWD_FILE="/run/secrets/postgres_password"

if [ -f "$PWD_FILE" ] && [ -n "${DATABASE_URL:-}" ]; then
  # Strip newline only (intentional — passwords don't contain CR/LF).
  PWD_VAL="$(tr -d '\n\r' < "$PWD_FILE")"
  if [ -z "$PWD_VAL" ]; then
    echo "entrypoint: ERROR: $PWD_FILE is empty" >&2
    exit 1
  fi
  # Bash parameter substitution; embedded shell metacharacters in the
  # password are inert (we don't eval).
  export DATABASE_URL="${DATABASE_URL//__PG_PWD__/$PWD_VAL}"
  unset PWD_VAL
fi

exec "$@"
