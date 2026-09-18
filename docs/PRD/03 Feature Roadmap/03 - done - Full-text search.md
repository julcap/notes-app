# Full-text search

2026-09-17 · split from `03 Feature Roadmap (Post-MVP).md`

**Status:** Code complete 2026-09-17. Backend-only — no frontend or contract impact. Production activation follows the normal Alembic migration during deployment.

## Problem

The current search is `ILIKE '%term%'` across title/content/attendees (`backend/app/notes/routes.py::notes`). It's correct but doesn't rank results by relevance, and it gets slow once the table has more than a few thousand rows since it can't use a normal index.

## Requirements

- Move to Postgres's built-in full-text search: a `tsvector` column (generated from title + content + attendees), a GIN index on it, and queries via `tsquery` / `plainto_tsquery`.
- Rank results with `ts_rank` instead of returning them in whatever order the date sort happens to produce.
- Keep the existing `GET /api/notes?q=` API and bare-array response shape — this stays a backend-only change.

## Data model

- Add a generated `search_vector` (`tsvector`) column to `notes`, weighted title A, attendees B, and content C with the explicit immutable `pg_catalog.simple` text-search configuration.
- Add a GIN index on `search_vector`.
- Apply through Alembic revision `20260917_0002`, after the current-schema baseline.

## Backend

- Replace the `ilike`/`or_` clause in `notes()` (`backend/app/notes/routes.py`) with a `plainto_tsquery('simple', q)` match against `search_vector`, ordered by rank, meeting date, update time, and id (falling back to the current date sort when there's no search term).
- Keep escaping/validation as strict as today — `plainto_tsquery` handles user input safely without needing the manual `%`/`_` escaping the ILIKE path uses.

## Tests

- PostgreSQL integration coverage verifies the generated vector and GIN index, weighted ranking, stable ties, uppercase and attendee matches, punctuation and SQL-like input, updated content, query limits, and owner isolation.

## Out of scope

- Pagination of search results — see [04 Pagination](./04%20Pagination.md).
- Fuzzy/typo-tolerant search — not requested, would need `pg_trgm` or similar.
