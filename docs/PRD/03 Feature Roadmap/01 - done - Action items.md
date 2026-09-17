# Action items

2026-09-17 · split from `03 Feature Roadmap (Post-MVP).md`

**Status: done**, shipped 2026-09-17 (commit "Add action items to meeting notes"). This was the other half of the original roadmap doc's "richer notes" section — the markdown-formatting half is tracked separately in [02 Rich text notes formatting](./02%20Rich%20text%20notes%20formatting.md).

## Problem

`content` was a single plain-text blob, so nothing in a meeting's notes was ever trackable — every action item lived and died as a sentence someone had to re-read to remember.

## What shipped

- A new concept, separate from free-text notes: an action item has text, an owner name, an optional due date, and a done/not-done state.
- Action items belong to a meeting, shown as a checklist under the notes in the detail view.
- Checking one off is a lightweight `PATCH`, not a full meeting update.

## Data model

`action_items` (`backend/app/notes/models.py`): `id`, `note_id` (FK, cascade delete with the note), `text`, `owner_name`, `due_date` (nullable), `done` (boolean, default false), `created_at`. Exposed on `Note.action_items` (`NoteOut.action_items`).

## Endpoints

`POST /api/notes/{note_id}/action-items`, `PATCH /api/action-items/{id}` (partial update — a bare `{"done": true}` is enough to toggle), `DELETE /api/action-items/{id}`. All ownership-checked through the parent note via `get_action_item()`.

## Frontend

Checklist section in `notes-workspace.html`'s detail view: checkbox to toggle done, remove button, and a small inline form to add new items (text/owner/due date). See `notes-workspace.ts`'s `addActionItem`/`toggleActionItem`/`removeActionItem`.

## Tests

`backend/tests/test_api.py::test_action_items_crud_and_ownership` — creation, validation, partial-update semantics, cross-user/cross-note ownership isolation, cascade delete with the parent note.

## Known frontend authorization regression

The imported baseline's interceptor only attaches bearer tokens to `/api/notes...`. The UI's `PATCH` and `DELETE /api/action-items/{id}` calls are therefore not covered by that authorization path. Frontend automated tests intentionally do not claim this done-labelled leaf passes end to end; the sharing/authorization implementation owns the fix and integration coverage.

## Deferred (not part of this pass)

A simple "my open action items" view across all meetings — noted in the original roadmap doc as a natural fast-follow once this concept exists, not required for v1.
