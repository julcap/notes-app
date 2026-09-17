# Database migrations (Alembic)

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: not done.** Correction to the original doc: it claimed "the Alembic scaffold exists in the repo but nothing actually uses it" — there is no Alembic anywhere in this repo today, scaffolded or otherwise. Schema changes ship as code-only model changes plus hand-written idempotent SQL.

## Problem

`backend/app/init_db.py` runs `Base.metadata.create_all(connection)` on startup, then a fixed sequence of `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` statements for every schema change made after the first one (owner_id, pending_email, totp columns, etc.), guarded by a Postgres advisory lock so concurrent replica startups don't race. This works, but every future schema change means hand-writing another idempotent `ALTER TABLE` line and hoping nothing conflicts — there's no record of schema history, no ability to roll back a bad schema change independently of a code rollback, and no single source of truth for what the schema actually looked like at any point in time.

## Requirements

- Generate a real initial Alembic migration from the current models.
- Require every future schema change (like `action_items` in the Feature Roadmap, or a future `deleted_at` column) to ship as an Alembic revision instead of a code-only model change plus a manual `ALTER TABLE` line in `init_db.py`.
- Run `alembic upgrade head` as a deploy step, before the new backend code starts serving traffic — likely an init container or a pre-deploy job in `deploy/app.yaml` / the `deploy` job in `.github/workflows/ci.yaml`.
- Remove `Base.metadata.create_all()` and the manual `ALTER TABLE` sequence in `init_db.py` once this is in place — leaving both in place invites drift between what Alembic thinks the schema is and what actually got created.

## Migration path

This can be introduced without a flag day: generate the initial revision against the *current* production schema (via `alembic revision --autogenerate` pointed at a real database), verify it's a no-op against production, then switch new changes over to Alembic from that point forward.
