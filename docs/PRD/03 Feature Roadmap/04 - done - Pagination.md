# Pagination in the UI

2026-09-17 · split from `03 Feature Roadmap (Post-MVP).md`

**Status:** Code complete 2026-09-17; deployment pending.

## Shipped implementation

- `GET /api/notes` returns `{items, total}` and validates `skip >= 0` plus `1 <= limit <= 200`, with a default page size of 50.
- Count and result queries share the owner and PostgreSQL full-text filters. Ranked and unfiltered results both use the note id as a stable final ordering key.
- The notes workspace loads one page at a time, displays the server total, appends with **Load more**, and disables the control when the current result set is complete.
- Search is server-backed, debounced by 300 ms, resets paging, and ignores stale responses after the query changes.
- Create, update, and delete operations reload the first page so list contents and totals remain authoritative.
- Backend coverage exercises validation boundaries, owner/search totals, and disjoint stable pages on PostgreSQL. Angular coverage exercises off-page search, query races, retry, completion state, and CRUD count refreshes.

No production deployment or production data operation was performed as part of this implementation.

## Problem

The API already accepts `skip`/`limit` params conceptually, but the frontend's meeting list (`notes-workspace.ts::load()`) loads everything in one request via a bare `GET /api/notes`. That's invisible today with a handful of meetings and will visibly slow down page load once someone has a few hundred.

## Requirements

- Add "load more" or numbered pages to the note list in `notes-workspace.html`.
- `MeetingService.list()` (currently inlined as `this.http.get<Note[]>('/api/notes')` in `notes-workspace.ts::load()`) needs to pass through `skip`/`limit` and know the total count.

## Backend

- `GET /api/notes` currently returns a bare `Note[]` array (`backend/app/notes/routes.py::notes`). Change the response shape to `{items: Note[], total: number}`, or add an `X-Total-Count` header — pick one and update `NoteOut` usage accordingly (a bare array is simpler to keep for callers that don't need the total, but this app has exactly one caller, so changing the shape is fine).
- Add `skip: int = 0, limit: int = Query(50, le=200)` params to the `notes()` endpoint, applied via `.offset(skip).limit(limit)` on the existing query. Compute `total` via a separate `count()` query (or `func.count()` over the same filtered query before pagination).

## Frontend

- `load()` needs to request a page (not everything) and track `total` alongside `notes`.
- Add pagination controls to `notes-workspace.html`'s note-list section — simplest is a "Load more" button that appends the next page to `this.notes`, matching the existing append-ish pattern in `save()`.
- The client-side `filtered` getter (`notes-workspace.ts`) currently searches only what's already loaded in memory. Once pagination lands, search should go through the backend `q` param instead (already supported server-side) rather than filtering an incomplete local list — otherwise "search" will silently miss meetings not yet paged in.

## Out of scope

- Full-text ranking of paginated results — see [03 Full-text search](./03%20Full-text%20search.md); the two are easy to combine but each is independently shippable.
