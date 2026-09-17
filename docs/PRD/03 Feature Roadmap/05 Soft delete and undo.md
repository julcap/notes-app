# Soft delete / undo

2026-09-17 · split from `03 Feature Roadmap (Post-MVP).md`

**Status:** Not started.

## Problem

Deleting a meeting today (`DELETE /api/notes/{note_id}` in `backend/app/notes/routes.py::delete_note`) is instant and permanent — one misclick and it's gone, attachments included.

## Requirements

- Add a `deleted_at` column to `notes`; "delete" sets it instead of removing the row.
- List/get/search queries filter out soft-deleted rows.
- Show a brief "Meeting deleted — Undo" toast (10–15 seconds) that clears `deleted_at` if pressed.
- A scheduled job permanently purges rows soft-deleted more than ~30 days ago.

## Data model

- Add `deleted_at: Mapped[datetime | None]` (nullable, default `NULL`) to `Note` (`backend/app/notes/models.py`), applied via the idempotent-migration pattern in `backend/app/init_db.py`.

## Backend

- `notes()`, `get_note()`, and any future search endpoint must filter `Note.deleted_at.is_(None)`.
- `delete_note()` becomes an update (`note.deleted_at = now()`) instead of `session.delete(note)` — and must stop eagerly unlinking attachment files from disk, since undo needs them back.
- New endpoint: `POST /api/notes/{note_id}/undelete` (or similar) that clears `deleted_at`, scoped to the owner and only within the undo window the frontend still has a toast for (no need to expose "undelete anything ever soft-deleted" — that's what the purge job is for).
- Purge job: a scheduled task (see [08 Notifications and reminders](./08%20Notifications%20and%20reminders.md) for the scheduler this would share) that hard-deletes notes where `deleted_at < now() - interval '30 days'`, including their attachment files on disk — this is the one place actual `session.delete` + `STORAGE` file cleanup still needs to happen.

## Frontend

- `remove()` in `notes-workspace.ts` currently deletes then filters the note out of `this.notes` immediately. Change to: call delete, remove from the visible list, show a dismissible "Meeting deleted — Undo" toast for 10–15s that calls the undelete endpoint and re-inserts the note if pressed.
- The `confirmDelete` confirmation dialog (`notes-workspace.html`) can likely be softened or removed now that delete is reversible — worth reconsidering the UX rather than keeping both a confirm dialog and an undo toast.

## Out of scope

- A "trash" view of soft-deleted meetings — the doc only asks for an undo toast, not a recovery UI beyond the toast window.
