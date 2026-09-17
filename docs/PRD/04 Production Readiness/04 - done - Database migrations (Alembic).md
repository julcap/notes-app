# Database migrations (Alembic)

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: code-complete.** Alembic now owns the schema history. Runtime startup no longer calls `create_all()` or carries an open-ended list of manual `ALTER TABLE` statements.

## Problem

`backend/app/init_db.py` runs `Base.metadata.create_all(connection)` on startup, then a fixed sequence of `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` statements for every schema change made after the first one (owner_id, pending_email, totp columns, etc.), guarded by a Postgres advisory lock so concurrent replica startups don't race. This works, but every future schema change means hand-writing another idempotent `ALTER TABLE` line and hoping nothing conflicts — there's no record of schema history, no ability to roll back a bad schema change independently of a code rollback, and no single source of truth for what the schema actually looked like at any point in time.

## Requirements

- Generate a real initial Alembic migration from the current models.
- Require every future schema change (like `action_items` in the Feature Roadmap, or a future `deleted_at` column) to ship as an Alembic revision instead of a code-only model change plus a manual `ALTER TABLE` line in `init_db.py`.
- Run `alembic upgrade head` as a deploy step, before the new backend code starts serving traffic — likely an init container or a pre-deploy job in `deploy/app.yaml` / the `deploy` job in `.github/workflows/ci.yaml`.
- Remove `Base.metadata.create_all()` and the manual `ALTER TABLE` sequence in `init_db.py` once this is in place — leaving both in place invites drift between what Alembic thinks the schema is and what actually got created.

## Migration path

This can be introduced without a flag day: generate the initial revision against the *current* production schema (via `alembic revision --autogenerate` pointed at a real database), verify it's a no-op against production, then switch new changes over to Alembic from that point forward.

## Implemented

- `20260917_0001` creates the full current schema on an empty database.
- An unversioned current schema is inspected before adoption; unknown tables, columns, missing keys, or missing indexes are rejected instead of blindly stamped.
- The known pre-auth `notes`/`attachments` shape is upgraded in-place. Ownerless notes and their attachments remain intact and inaccessible, while a `NOT VALID` ownership check rejects new ownerless writes.
- The migration environment retains the PostgreSQL advisory transaction lock, so concurrent startup processes serialize safely. Re-running `upgrade head` is a no-op.
- Local Compose and the isolated test service migrate before startup. EKS uses a backend-image init container, so migrations finish before the API serves traffic.
- Tests use a real isolated PostgreSQL server and cover empty, current populated, known legacy, unknown drift, repeated, and concurrent upgrade paths.

No production migration or deployment was performed as part of this code change.
