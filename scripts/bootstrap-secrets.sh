#!/usr/bin/env bash
# scripts/bootstrap-secrets.sh
#
# Idempotent: creates ./secrets/ with restrictive perms, generates random
# values for any secret file that does not yet exist, prompts only for
# the F5 XC API token (which we cannot generate). Safe to re-run.
#
# Files created:
#   secrets/jwt_secret_key       — 48-byte urlsafe base64
#   secrets/postgres_password    — 24-byte urlsafe base64
#   secrets/f5xc_api_token       — prompted (with --token flag for non-interactive)
#
# Usage:
#   ./scripts/bootstrap-secrets.sh                          # interactive
#   ./scripts/bootstrap-secrets.sh --token "<F5XC_TOKEN>"   # CI / non-interactive
#   ./scripts/bootstrap-secrets.sh --rotate jwt             # force regenerate one secret
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS_DIR="${ROOT}/secrets"

f5xc_token=""
rotate=""
while [ $# -gt 0 ]; do
	case "$1" in
		--token) f5xc_token="$2"; shift 2 ;;
		--rotate) rotate="$2"; shift 2 ;;
		-h|--help)
			grep '^#' "$0" | sed 's/^# \{0,1\}//'
			exit 0
			;;
		*) echo "unknown arg: $1" >&2; exit 2 ;;
	esac
done

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

# .gitignore inside the secrets/ dir — guarantees nothing is ever committed
# even if the top-level .gitignore is wrong.
if [ ! -f "$SECRETS_DIR/.gitignore" ]; then
	{
		echo '*'
		echo '!.gitignore'
	} > "$SECRETS_DIR/.gitignore"
fi

write_random() {
	local name="$1" bytes="$2" path="$SECRETS_DIR/$1"
	if [ -f "$path" ] && [ "$rotate" != "$name" ]; then
		return
	fi
	python3 -c "import secrets; print(secrets.token_urlsafe($bytes))" > "$path"
	chmod 600 "$path"
	echo "  generated $name ($bytes bytes)"
}

write_random jwt_secret_key 48
write_random postgres_password 24

# F5 XC API token — must be supplied (prompt or flag).
if [ -f "$SECRETS_DIR/f5xc_api_token" ] && [ "$rotate" != "f5xc_api_token" ]; then
	echo "  f5xc_api_token already present (use --rotate f5xc_api_token to replace)"
else
	if [ -z "$f5xc_token" ]; then
		printf "F5 XC API token: "
		# -s suppresses echo; -r treats backslashes literally
		read -rs f5xc_token
		echo
	fi
	if [ -z "$f5xc_token" ]; then
		echo "ERROR: empty F5 XC API token" >&2
		exit 1
	fi
	printf '%s\n' "$f5xc_token" > "$SECRETS_DIR/f5xc_api_token"
	chmod 600 "$SECRETS_DIR/f5xc_api_token"
	echo "  wrote f5xc_api_token"
fi

echo
echo "Secrets directory ready at $SECRETS_DIR"
ls -la "$SECRETS_DIR"
