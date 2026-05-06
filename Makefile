.PHONY: help up down logs restart build rebuild seed reset-admin-password test lint clean

help:
	@echo "F5 XC Dashboard - dev commands"
	@echo "  make up                     - start all services (docker compose up -d)"
	@echo "  make down                   - stop all services"
	@echo "  make logs                   - tail logs"
	@echo "  make restart                - restart services"
	@echo "  make build                  - build images"
	@echo "  make rebuild                - rebuild without cache"
	@echo "  make seed                   - create initial admin user + tenant (no-op if admin exists)"
	@echo "  make reset-admin-password   - force-reset admin password (set ADMIN_PASSWORD env var)"
	@echo "  make test                   - run backend tests"
	@echo "  make lint                   - run backend lint"
	@echo "  make clean                  - remove containers, volumes, build artifacts"

	@echo ""
	@echo "v0.7.2 helpers:"
	@echo "  make backup-db              - pg_dump to ./backups/<ts>.dump"
	@echo "  make restore-db FILE=...    - pg_restore (DESTRUCTIVE)"
	@echo "  make rotate-jwt             - rotate JWT key"
	@echo "  make rotate-token           - rotate F5 XC API token"
	@echo "  make generate-secrets       - bootstrap or rotate Docker secrets"
	@echo "  make audit-tail             - last 50 audit_events"
	@echo "  make logs-tail              - timestamped backend+worker+beat"
	@echo "  make truncate-synced-data   - wipe synced inventory (DESTRUCTIVE)"
	@echo "  make rebuild-frontend       - full frontend rebuild"
	@echo "  make clean-bak              - remove v0.7.2 apply backup files"

	@echo ""
	@echo "v0.9.0 user CLI (ops-only):"
	@echo "  make user-list                         - list users"
	@echo "  make user-get TARGET_USER=<id|username>  - fetch one user"
	@echo "  make user-add                          - create user (interactive)"
	@echo "  make user-rotate-password TARGET_USER=... - rotate password (interactive)"
	@echo "  make user-set-role TARGET_USER=... ROLE=... - change role (admin|viewer)"
	@echo "  make user-deactivate TARGET_USER=...   - soft-delete (is_active=false)"
	@echo "  make user-activate TARGET_USER=...     - reactivate"
	@echo ""
	@echo "v0.9.0 namespace CLI (ops-only):"
	@echo "  make namespace-list                    - list current namespaces"
	@echo "  make namespace-add NAMESPACE=<name>    - add (probes F5 XC)"
	@echo "  make namespace-remove NAMESPACE=<name> - remove (refuses last)"
	@echo "  make namespace-replace NAMESPACES=a,b,c - bulk replace"

up:
	@test -f .env || (echo "Missing .env - copy .env.example first"; exit 1)
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

restart:
	docker compose restart

build:
	docker compose build

rebuild:
	docker compose build --no-cache

seed:
	docker compose exec backend python -m scripts.seed

# Force-reset the admin password. Unlike `make seed` (which is create-only),
# this updates an existing admin user's hashed_password.
# Usage:
#   ADMIN_PASSWORD='new-password' make reset-admin-password
#   ADMIN_USERNAME=other-admin ADMIN_PASSWORD='...' make reset-admin-password
reset-admin-password:
	@test -n "$(ADMIN_PASSWORD)" || (echo "Set ADMIN_PASSWORD, e.g. ADMIN_PASSWORD='xyz' make reset-admin-password"; exit 1)
	docker compose exec \
		-e ADMIN_USERNAME="$(or $(ADMIN_USERNAME),admin)" \
		-e ADMIN_PASSWORD="$(ADMIN_PASSWORD)" \
		backend python -m scripts.reset_admin_password

test:
	docker compose exec backend pytest -v

lint:
	docker compose exec backend ruff check app/

clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/.next frontend/node_modules

# ============================================================
# v0.7.2 hardening — operational helpers
# ============================================================

.PHONY: backup-db restore-db rotate-jwt rotate-token audit-tail logs-tail \
        truncate-synced-data rebuild-frontend clean-bak generate-secrets \
        user-list user-get user-add user-rotate-password user-set-role \
        user-deactivate user-activate \
        namespace-list namespace-add namespace-remove namespace-replace

# ----- secrets ---------------------------------------------------------------

generate-secrets:  ## Generate or rotate Docker secrets in ./secrets/
	@./scripts/bootstrap-secrets.sh

rotate-jwt:  ## Rotate JWT signing key (invalidates all sessions on next request)
	@./scripts/bootstrap-secrets.sh --rotate jwt_secret_key
	@echo
	@echo "JWT key rotated. Restart backend, worker, beat to pick up:"
	@echo "  docker compose up -d --force-recreate backend worker beat"

rotate-token:  ## Rotate F5 XC API token (prompts for new value)
	@./scripts/bootstrap-secrets.sh --rotate f5xc_api_token
	@echo
	@echo "F5 XC token rotated. Restart backend, worker, beat to pick up:"
	@echo "  docker compose up -d --force-recreate backend worker beat"

# ----- database --------------------------------------------------------------

backup-db:  ## pg_dump the dashboard DB to ./backups/<timestamp>.dump
	@mkdir -p backups
	@ts=$$(date -u +%Y%m%dT%H%M%SZ); \
	docker compose exec -T postgres pg_dump -U f5xc -Fc f5xc_dashboard \
		> backups/$$ts.dump && \
	echo "wrote backups/$$ts.dump ($$(du -h backups/$$ts.dump | cut -f1))"

restore-db:  ## Restore from FILE=backups/<...>.dump (DESTRUCTIVE)
	@test -n "$(FILE)" || (echo "Usage: make restore-db FILE=backups/<file>.dump" && exit 2)
	@test -f "$(FILE)" || (echo "no such file: $(FILE)" && exit 2)
	@echo "WARNING: this will OVERWRITE the database. Continue? [y/N]"; \
	read ans; [ "$$ans" = "y" ] || (echo "aborted"; exit 1)
	docker compose exec -T postgres pg_restore \
		-U f5xc -d f5xc_dashboard --clean --if-exists --no-owner < $(FILE)

truncate-synced-data:  ## TRUNCATE all synced F5 XC inventory (forces re-sync)
	@echo "WARNING: this drops all synced inventory. Continue? [y/N]"; \
	read ans; [ "$$ans" = "y" ] || (echo "aborted"; exit 1)
	docker compose exec -T postgres psql -U f5xc -d f5xc_dashboard -c "\
		TRUNCATE load_balancers, origin_pools, sites, certificates, \
		         app_firewalls, service_policies, bot_defense_policies, \
		         api_definitions, api_endpoints, policy_attachments \
		RESTART IDENTITY CASCADE;"

# ----- observability ---------------------------------------------------------

audit-tail:  ## Tail recent audit_events (last 50)
	docker compose exec -T postgres psql -U f5xc -d f5xc_dashboard -c "\
		SELECT created_at::timestamp(0) AS at, event_type, result, \
		       actor_username, host(request_ip) AS ip, target \
		FROM audit_events ORDER BY created_at DESC LIMIT 50;"

logs-tail:  ## Tail backend + worker + beat with timestamps
	docker compose logs -f --timestamps backend worker beat

# ----- frontend --------------------------------------------------------------

rebuild-frontend:  ## Full frontend rebuild (tailwind/package changes)
	docker compose down frontend
	docker compose rm -f frontend
	-docker image rm f5xc-dashboard-frontend 2>/dev/null || true
	docker compose build --no-cache frontend
	docker compose up -d frontend

# ----- cleanup ---------------------------------------------------------------

clean-bak:  ## Remove all *.bak and *.v071.bak files left over from v0.7.2 apply
	@find . -type f \( -name '*.v071.bak' -o -name '*.v071-step7.bak' \
	                  -o -name '*.step8.bak' -o -name '*.step8a.bak' \
	                  -o -name '*.step8b.bak' -o -name '*.step8c-bak' \
	                  -o -name '*.step8a-bak' -o -name '*.v072.bak' \) \
	  -not -path './.git/*' -not -path './node_modules/*' -print
	@echo
	@echo "Above files will be deleted. Continue? [y/N]"; \
	read ans; [ "$$ans" = "y" ] || (echo "aborted"; exit 1)
	@find . -type f \( -name '*.v071.bak' -o -name '*.v071-step7.bak' \
	                  -o -name '*.step8.bak' -o -name '*.step8a.bak' \
	                  -o -name '*.step8b.bak' -o -name '*.step8c-bak' \
	                  -o -name '*.step8a-bak' -o -name '*.v072.bak' \) \
	  -not -path './.git/*' -not -path './node_modules/*' -delete
	@echo "cleaned"


# ============================================================
# v0.9.0 — multi-tenant ops CLI: users (CLI-only by design, no API)
# ============================================================

user-list:  ## List all users (USER_TENANT=<id|name> to filter)
	docker compose exec backend /app/scripts/entrypoint.sh python -m scripts.user_cli list $(if $(USER_TENANT),--tenant "$(USER_TENANT)",)

user-get:  ## Fetch one user (TARGET_USER=<id|username>)
	@test -n "$(TARGET_USER)" || (echo "Usage: TARGET_USER=<id|username> make user-get" && exit 2)
	docker compose exec backend /app/scripts/entrypoint.sh python -m scripts.user_cli get "$(TARGET_USER)"

user-add:  ## Create a user (interactive prompts for password via getpass)
	docker compose exec -it backend /app/scripts/entrypoint.sh python -m scripts.user_cli add

user-rotate-password:  ## Rotate user password (TARGET_USER=<id|username>)
	@test -n "$(TARGET_USER)" || (echo "Usage: TARGET_USER=<id|username> make user-rotate-password" && exit 2)
	docker compose exec -it backend /app/scripts/entrypoint.sh python -m scripts.user_cli rotate-password "$(TARGET_USER)"

user-set-role:  ## Change user role (TARGET_USER=<id|username> ROLE=admin|viewer)
	@test -n "$(TARGET_USER)" || (echo "Usage: TARGET_USER=<id|username> ROLE=admin|viewer make user-set-role" && exit 2)
	@test -n "$(ROLE)" || (echo "Usage: TARGET_USER=<id|username> ROLE=admin|viewer make user-set-role" && exit 2)
	docker compose exec backend /app/scripts/entrypoint.sh python -m scripts.user_cli set-role "$(TARGET_USER)" "$(ROLE)"

user-deactivate:  ## Soft-delete user via is_active=false (TARGET_USER=<id|username>)
	@test -n "$(TARGET_USER)" || (echo "Usage: TARGET_USER=<id|username> make user-deactivate" && exit 2)
	docker compose exec backend /app/scripts/entrypoint.sh python -m scripts.user_cli deactivate "$(TARGET_USER)"

user-activate:  ## Reactivate user (TARGET_USER=<id|username>)
	@test -n "$(TARGET_USER)" || (echo "Usage: TARGET_USER=<id|username> make user-activate" && exit 2)
	docker compose exec backend /app/scripts/entrypoint.sh python -m scripts.user_cli activate "$(TARGET_USER)"


# ============================================================
# v0.9.0 — multi-namespace ops CLI (CLI-only by design, no API)
# ============================================================

namespace-list:  ## List current namespaces watched by the tenant
	docker compose exec backend /app/scripts/entrypoint.sh python -m scripts.namespace_cli list

namespace-add:  ## Add a namespace (probes F5 XC). Usage: NAMESPACE=foo make namespace-add
	@test -n "$(NAMESPACE)" || (echo "Usage: NAMESPACE=<name> make namespace-add" && exit 2)
	docker compose exec backend /app/scripts/entrypoint.sh python -m scripts.namespace_cli add "$(NAMESPACE)"

namespace-remove:  ## Remove a namespace. Usage: NAMESPACE=foo make namespace-remove
	@test -n "$(NAMESPACE)" || (echo "Usage: NAMESPACE=<name> make namespace-remove" && exit 2)
	docker compose exec backend /app/scripts/entrypoint.sh python -m scripts.namespace_cli remove "$(NAMESPACE)"

namespace-replace:  ## Bulk-replace namespace list. Usage: NAMESPACES="a,b,c" make namespace-replace
	@test -n "$(NAMESPACES)" || (echo 'Usage: NAMESPACES="a,b,c" make namespace-replace' && exit 2)
	docker compose exec -it backend /app/scripts/entrypoint.sh python -m scripts.namespace_cli replace "$(NAMESPACES)"
