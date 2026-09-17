# Export

2026-09-17 · split from `03 Feature Roadmap (Post-MVP).md`

**Status:** Not started.

## Problem

There's no way to get a meeting out of the app once it's in.

## Requirements

- Export a single meeting as PDF or markdown, including its action items.
- `GET /api/meetings/{id}/export?format=pdf|md` (route naming: match the existing `/api/notes/{note_id}/...` convention used everywhere else in this codebase rather than introducing `/api/meetings`).

## Backend

- New endpoint: `GET /api/notes/{note_id}/export?format=pdf|md`, owner-checked via the existing `get_note()` helper in `backend/app/notes/routes.py`.
- Markdown export: straightforward template — title, date, attendees, content, then a `- [ ]`/`- [x]` list of action items (from `Note.action_items`, already available via the `action_items` relationship added in [01 - done - Action items](./01%20-%20done%20-%20Action%20items.md)).
- PDF export: needs a rendering step server-side (e.g. render the same markdown/HTML template and convert with a library such as WeasyPrint, or render via a headless browser) — pick whichever has the lightest footprint to add to the backend's dependencies, since this app currently has no PDF-generation dependency at all.
- Response should be a `FileResponse`/streamed download with an appropriate filename (e.g. `{note.title}.md` / `.pdf`) and content-type, following the pattern already used in `download()` for attachments.

## Frontend

- An "Export" action on the detail view (`notes-workspace.html`) offering PDF/markdown, downloading via the same blob-download pattern already used in `downloadFile()`.

## Out of scope

- Batch export (all meetings matching the current search/tag filter) — explicitly deferred in the original roadmap doc as a fast-follow, not required for v1.
