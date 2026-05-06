# Contributing

Thanks for your interest. This is a personal project (see "Affiliation" in
README); contributions are welcome but review cadence is best-effort.

## Development setup

### Prerequisites

- Docker Engine 24+ with Compose v2 plugin
- Make
- An F5 Distributed Cloud tenant + API token, or use mock mode

### Getting started

```bash
git clone <your-fork-url>
cd f5xc-dashboard
cp .env.example .env
# Edit .env — at minimum set JWT_SECRET_KEY (random ≥32 chars) and
# either F5XC_MOCK=true or provide F5XC_API_TOKEN

./scripts/bootstrap-secrets.sh
make up
SEED_ADMIN_PASSWORD='change_me_now' make seed
curl -k https://localhost/healthz
```

## Running tests + lint

```bash
make test    # backend pytest
make lint    # ruff
```

Tests run in mock mode and require no F5 XC credentials.

## Project structure

See `README.md` § "Repo layout". Key entry points:

- `backend/app/main.py` — FastAPI factory + startup probe
- `backend/app/workers/celery_app.py` — Celery factory + beat schedule
- `backend/app/f5xc/client.py` — F5 XC HTTP client
- `backend/scripts/seed.py` — initial tenant/user creation
- `backend/scripts/{user,namespace}_cli.py` — ops CLIs
- `backend/alembic/versions/` — schema migrations
- `frontend/src/app/` — Next.js App Router
- `infra/caddy/Caddyfile` — TLS / reverse proxy
- `Makefile` — up/down/seed/test/lint + ops targets

## Code style

- **Python**: ruff (lint + format). Type hints on public APIs.
  Line length 100. `from __future__ import annotations` in use.
- **TypeScript/React**: Tailwind utility classes preferred over custom CSS.
- **SQL**: lowercase keywords, snake_case identifiers.

## Submitting a pull request

1. Open an issue first for non-trivial changes
2. Fork + branch from `main` (`feat/...` or `fix/...`)
3. Run `make test && make lint` before pushing
4. Update `CHANGELOG.md` under `## Unreleased`
5. Use the PR template

## Database migrations

```bash
docker compose exec backend /app/scripts/entrypoint.sh alembic revision \
    --rev-id NNNN_short_descriptor -m "what changed"
```

Gotchas:
- Revision IDs ≤ 32 chars (`alembic_version.version_num` is `varchar(32)`).
  Longer IDs cause the version-stamp UPDATE to fail mid-transaction,
  rolling back any DDL the migration applied.
- `--rev-id` sets the internal ID but alembic still appends the message
  slug to the filename. Rename post-generation.
- Always include both `upgrade()` and `downgrade()`. Test downgrade locally.

## Code of Conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md).
