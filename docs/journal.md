# Development Journal

Internal record of design decisions, missteps, and lessons. Operator-facing
release notes live in `CHANGELOG.md`; this file is for the engineers
maintaining the dashboard.

Newest entries first. Each release gets one entry. When something gets
rolled back or redesigned mid-release, capture both the misfire and the
correction so the design history is honest.

---

## v0.9.0 — Multi-namespace support (2026-05-06)

### What shipped

The dashboard authenticates against ONE F5 XC tenant with ONE token but
now watches MULTIPLE namespaces within it. Operator manages the watch
list via a new ops CLI; sync tasks iterate the configured list.

Schema: `tenants.namespaces` ARRAY column (alembic 0011). Sync tasks read
through `Tenant.effective_namespaces` property which falls back to
`[f5xc_namespace]` for unmigrated rows.

### The course correction

v0.9.0 was originally scoped as **multi-tenant** — encrypted token storage,
Tenant CRUD API, per-tenant transaction isolation, cross-tenant isolation
tests. About 5 phases of work landed before the user clarified mid-session:
"this dashboard does not need to support multiple tenants... it just needs
to support multiple namespaces."

The actual need: one F5 XC tenant, multiple namespaces within it. Multi-
tenant scope was wrong-shape — encryption-at-rest of a single env-mounted
token, CRUD for a singleton tenant row, and cross-tenant isolation tests
all add complexity without addressing the real problem.

We rolled back v0.9.0-take-1 to v0.8.0 baseline (keeping the user CLI work
which was independently useful), then rebuilt as v0.9.0-take-2 multi-
namespace in 5 phases over ~3 hours.

Final shape:
- Phase 1: model + alembic 0011 + `effective_namespaces` property
- Phase 2: 4 sync tasks refactored (LBs, pools, certs, policies);
  9 tasks inherit multi-namespace via per-LB iteration
- Phase 3: namespace CLI (list/add/remove/replace) with probe-on-add
- Phase 4: seed.py populates the new column for fresh installs
- Phase 6: CHANGELOG + version bump (Phase 5 — drop legacy column —
  deferred to v0.10.0 for rollback safety)

### Rollback execution notes

Reverted in 10 chunks, opposite-order-of-application: sync_loadbalancers
refactor → PerTenantSync helper → Tenant model → admin_tenants router →
tenant_cli → 12 sync task token refs → alembic 0010 (drop ciphertext col)
→ auth/crypto.py → bootstrap-secrets → docker-compose secret mounts.

Tarball + DB dump captured before any reverts. Each chunk verified
post-apply (syntax, imports, smoke test). Caught one missed reference
(user_cli.py imported `TenantNotFound` from the deleted services/tenants.py)
during post-rollback smoke testing.

### Lessons

1. **Decision drift across long planning sessions can quietly mis-scope
   the work.** v0.9.0-take-1 multi-tenant scope started from inferred
   conversational language, not an explicit requirement. Re-state
   requirements before designing: "We're building X to solve Y. Confirm?"

2. **F5 XC list endpoints are LENIENT about namespace existence.** They
   return 200 + empty list for non-existent namespaces. Use the namespace
   registry endpoint (`/api/web/namespaces/{name}`) for strict existence
   validation — 404s on bogus names. Discovered when the initial probe-on-
   add test silently accepted a namespace that didn't exist.

3. **Alembic `version_num` column is `varchar(32)`.** Long revision IDs
   (>32 chars) cause the upgrade transaction to fail at the version-
   stamp UPDATE, rolling back any DDL the migration applied. Convention:
   `<NNNN>_<short_descriptor>` ≤ 32 chars. Hit this when 0010's full
   name was 34 chars.

4. **`alembic revision --rev-id <slug> -m "<msg>"` appends the message
   slug to the FILENAME** even with `--rev-id` set. Internal rev-id is
   correct; filename is bloated. Rename post-generation. Or pass `-m ""`.

5. **When deleting a Python module, grep for ALL imports.** `from <module>`
   AND `import <module>`. Missing imports surface as `ModuleNotFoundError`
   at runtime, not at delete time. Caught only because we did smoke
   testing after rollback.

6. **Stale-row reaping should scope to currently-active scopes, not
   historical ones.** Removing a namespace from the watch list does NOT
   auto-delete its synced rows. Conservative default avoids destructive
   surprises; operators clean up explicitly when they really mean to.

7. **Don't use shell-env-var-named identifiers as Makefile variables.**
   `USER`, `HOME`, `SHELL` are exported by interactive shells; make picks
   them up. `make user-get` (no arg) silently substituted the OS user
   instead of erroring. Convention: `TARGET_USER`, `TENANT`, `NAMESPACE`,
   `FILE`, etc.

8. **F5 XC certificate_chains list call returns shared-namespace certs
   even when called against a user namespace.** Multi-namespace upserts
   collapse correctly via the unique constraint on (tenant_id, namespace,
   name) — same cert listed from two namespaces hits the same row, just
   gets touched twice. The "count=N" in tenant_done logs reflects upserts,
   not unique rows.

### State at ship

- Stack: 7 services healthy, 0 production violations
- Alembic head: `0011_tenant_namespaces`
- `__version__`: 0.9.0
- Default tenant: `namespaces = {shared, <your-namespace>}`
- Sync tasks refactored: sync_loadbalancers, sync_origin_pools,
  sync_certificates, sync_policies
- New CLI: namespace-{list, add, remove, replace}
- Bonus CLI: user-{list, get, add, rotate-password, set-role,
  deactivate, activate}
- Probe endpoint: `/api/web/namespaces/{name}` (strict 404 validation)
- Backups: `backups/v090-rollback-<ts>/` (pre-rollback) and
  `backups/v090-ga-<ts>/` (post-ship)

### Validated end-to-end

Real namespace test (`xxxxxx`, member of `<your-tenant>` tenant):
probe → add → 4 sync tasks iterated 3 namespaces correctly →
real data populated (3 LBs, 5 pools, 3 certs, 1 firewall from <test-namespace>) →
remove → namespace dropped from watch list. Cleanup of synced rows was
manual via SQL DELETE per design.

