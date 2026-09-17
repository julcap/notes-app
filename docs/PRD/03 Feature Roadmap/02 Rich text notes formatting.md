# Rich text notes: formatting

2026-09-17 · split from `03 Feature Roadmap (Post-MVP).md`

**Status: not started.** The other half of the original "richer notes" section, [01 - done - Action items](./01%20-%20done%20-%20Action%20items.md), has already shipped. This spec covers what's left: markdown formatting for the free-text `content` field.

## Problem

`content` is a single plain-text blob rendered as raw text. There's no way to bold a decision, list out options, or check off a quick note inline without it just being a sentence someone re-reads later.

## Requirements

- Support markdown formatting in notes (bold, lists, headings, checkboxes) rather than a flat textarea.
- Render it properly in the detail view instead of showing raw text.
- Frontend: swap the plain `<textarea>` for a lightweight markdown editor (e.g. a simple toolbar over a textarea, or an existing Angular-friendly editor component) with a live preview toggle.

## Data model

None — `content` stays a `Text` column; this is a frontend rendering/editing change only.

## Backend

No change. The API already accepts and returns `content` as a string; markdown is just a convention for what's inside it.

## Frontend

- Add a markdown rendering pipeline for the read-only detail view (`.note-body` in `notes-workspace.html`). Sanitize before rendering — this is user-authored HTML-adjacent content, so an XSS-safe markdown renderer (or explicit sanitization pass) is required, not optional.
- Add a toolbar (bold / list / heading / checkbox) over the existing textarea in edit mode, plus a preview toggle so the user can check formatting before saving.
- No new dependencies unless one is chosen for markdown parsing/sanitizing — pick something small and well-maintained (e.g. `marked` + `dompurify`, or an Angular-native equivalent) rather than a full WYSIWYG editor.

## Out of scope

- A full WYSIWYG editor — a toolbar-over-textarea is enough for v1.
- Collaborative/simultaneous editing — not needed until [09 Sharing and collaboration](./09%20Sharing%20and%20collaboration.md) exists.
