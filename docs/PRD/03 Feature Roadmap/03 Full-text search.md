# Full-text search

2026-09-17 · split from `03 Feature Roadmap (Post-MVP).md`

**Status:** Not started. Backend-only — no frontend or contract impact.

## Problem

The current search is `ILIKE '%term%'` across title/content/attendees (`backend/app/notes/routes.py::notes`). It's correct but doesn't rank results by relevance, and it gets slow once the table has more than a few thousand rows since it can't use a normal index.

## Requirements

- Move to Postgres's built-in full-text search: a `tsvector` column (generated from title + content + attendees), a GIN index on it, and queries via `tsquery` / `plainto_tsquery`.
- Rank results with `ts_rank` instead of returning them in whatever order the date sort happens to produce.
- Same API shape (`?search=` / the existing `q` query param) — this must stay a backend-only change.

## Data model

- Add a generated `search_vector` (`tsvector`) column to `notes`, built from `title`, `content`, `attendees` (e.g. via a Postgres `GENERATED ALWAYS AS` expression, or a trigger if weighting per-field matters).
- Add a GIN index on `search_vector`.
- Apply via the same idempotent-migration pattern already used in `backend/app/init_db.py` (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`).

## Backend

- Replace the `ilike`/`or_` clause in `notes()` (`backend/app/notes/routes.py`) with a `tsquery` match against `search_vector`, ordered by `ts_rank(search_vector, query)` (falling back to the current date sort when there's no search term).
- Keep escaping/validation as strict as today — `plainto_tsquery` handles user input safely without needing the manual `%`/`_` escaping the ILIKE path uses.

## Tests

- Extend `backend/tests/test_api.py::test_crud_search_and_validation` (or add a new test) to check: ranking order when multiple notes match with different relevance, and that the existing exact-match assertions (`LAUNCH`, `Alex`) still pass under the new query.

## Out of scope

- Pagination of search results — see [04 Pagination](./04%20Pagination.md).
- Fuzzy/typo-tolerant search — not requested, would need `pg_trgm` or similar.
