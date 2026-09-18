# Export

2026-09-17 · split from `03 Feature Roadmap (Post-MVP).md`

**Status:** Code complete (2026-09-18); deployment pending operator-controlled release.

## Shipped behavior

- `GET /api/notes/{note_id}/export?format=md|pdf` requires authentication, applies the central note-permission check for owners and `view`/`edit` collaborators, and rejects missing or unsupported formats with `422`.
- Both formats include title, meeting date, attendees, note content, and every action item's status, owner, and due date. Downloads use sanitized ASCII filenames and `Cache-Control: no-store`.
- Markdown is returned as UTF-8 `text/markdown`. PDF is rendered directly with ReportLab Platypus, bundled licensed DejaVu Sans, and bundled Noto fallbacks for CJK and emoji; user text is escaped and no markup, URL, attachment, or local-file content is interpreted or fetched.
- The Angular detail view offers separate Markdown and PDF actions through the authenticated HTTP client, uses the server-provided filename, and downloads through a short-lived object URL.
- Automated coverage parses multipage PDF output from a 100,000-character note, verifies Unicode and action-item extraction, exact Markdown fields, filename sanitization, format validation, owner/deleted-note isolation, literal hostile markup, and browser download behavior.

## Problem

There's no way to get a meeting out of the app once it's in.

## Requirements

- Export a single meeting as PDF or markdown, including its action items.
- `GET /api/meetings/{id}/export?format=pdf|md` (route naming: match the existing `/api/notes/{note_id}/...` convention used everywhere else in this codebase rather than introducing `/api/meetings`).

## Backend

- Endpoint: `GET /api/notes/{note_id}/export?format=pdf|md`, checked through the central note-permission helper; owners and `view`/`edit` collaborators may export live notes.
- Markdown export: straightforward template — title, date, attendees, content, then a `- [ ]`/`- [x]` list of action items (from `Note.action_items`, already available via the `action_items` relationship added in [01 - done - Action items](./01%20-%20done%20-%20Action%20items.md)).
- PDF export uses direct ReportLab Platypus rendering with escaped text, DejaVu Sans as the primary font, and bundled Noto fallbacks; it does not invoke a browser or HTML-to-PDF service.
- Response should be a `FileResponse`/streamed download with an appropriate filename (e.g. `{note.title}.md` / `.pdf`) and content-type, following the pattern already used in `download()` for attachments.

## Frontend

- An "Export" action on the detail view (`notes-workspace.html`) offering PDF/markdown, downloading via the same blob-download pattern already used in `downloadFile()`.

## Out of scope

- Batch export (all meetings matching the current search/tag filter) — explicitly deferred in the original roadmap doc as a fast-follow, not required for v1.
