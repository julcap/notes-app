# Sharing & collaboration

2026-09-17 · split from `03 Feature Roadmap (Post-MVP).md`

**Status:** Not started. Largest change in the original roadmap doc — touches the data model, every meeting endpoint's authorization check, and several UI surfaces. Reasonable to defer until the smaller items in this folder are done.

## Problem

Today a meeting belongs to exactly one user and nobody else can see it (`Note.owner_id`, checked via `get_note()` in `backend/app/notes/routes.py`). That's fine for a personal notes app, but it's the ceiling on how useful this can be for an actual team.

## Requirements

**Sharing a meeting**

- Share a meeting with specific other users (by email), or with everyone the owner has previously shared with.
- A `meeting_shares` table: `meeting_id`, `user_id`, `permission` (`view` or `edit`), `shared_at`.
- Existing endpoints (`read_note`/`get_note`, `update_note`) need to check shares in addition to `owner_id`.

**Permissions beyond owner**

- `view`: can read the meeting and its attachments, can't edit.
- `edit`: can update content, tags, and action items, but can't delete the meeting or manage who it's shared with.
- Only the owner can delete a meeting or change sharing.

## Data model

- New `MeetingShare` model/table: `note_id` (FK, cascade delete with the note), `user_id` (FK to `users`), `permission` (enum/string `view`|`edit`), `shared_at`. Unique constraint on `(note_id, user_id)`.

## Backend

- `get_note()` (`backend/app/notes/routes.py`) is the single choke point every note endpoint routes through — its ownership check (`note.owner_id != user.id`) needs to become "owner OR has a share row with sufficient permission for this action," parameterized by whether the caller needs read or write access.
- `update_note`, action-item create/patch/delete, and attachment upload/delete need the `edit` check; `read_note`, attachment download, and the note list need at least `view`.
- `delete_note` and any future sharing-management endpoints stay owner-only — do not let `edit` permission escalate to those.
- New endpoints: list/add/update/remove shares on a note (e.g. `GET/POST /api/notes/{note_id}/shares`, `DELETE /api/notes/{note_id}/shares/{user_id}`), owner-only.
- `notes()` (the list endpoint) needs to union owned notes with shared-with-me notes, and the frontend needs a way to tell them apart (see Frontend below).

## Frontend

- A "Share" button on the detail view, listing current collaborators and their permission level.
- The meeting list needs a way to distinguish "meetings I own" from "meetings shared with me" (e.g. a badge or filter in `notes-workspace.html`'s note-list section).
- Edit/delete UI affordances (edit button, delete button, attachment upload/remove) need to respect the current user's effective permission on the selected note, not just assume owner.

## Sequencing note

Land this after [02](./02%20-%20done%20-%20Rich%20text%20notes%20formatting.md)–[08](./08%20Notifications%20and%20reminders.md): every other spec in this folder assumes single-owner semantics, and retrofitting shared-access checks into a handful of already-shipped features is more work than building them against single ownership first and adding the permission check as one focused pass at the end.
