# Soft delete / undo

2026-09-17 · split from `03 Feature Roadmap (Post-MVP).md`

**Status:** Code complete — shipped on `feat/prd-completion` 2026-09-17; deployment and production migration remain operator-controlled.

## Problem

Deleting a meeting was instant and permanent, including its attachments. A mistaken click had no recovery window.

## Shipped behavior

- Alembic revision `20260917_0003` adds nullable, timezone-aware `notes.deleted_at` with a purge index.
- `DELETE /api/notes/{note_id}` soft-deletes an owned, active note without deleting attachment bytes.
- Lists, full-text search, direct note reads, attachment routes, nested action-item routes, and top-level action-item mutation routes hide deleted parents.
- `POST /api/notes/{note_id}/undelete` restores only the owner’s note and enforces a 15-second server-side window. Missing or unauthorized notes return `404`; expired undo returns `409`.
- The frontend removes the destructive confirmation, updates the paginated total, and shows a dismissible **Meeting deleted — Undo** toast for 15 seconds. Undo restores the note and reloads the authoritative page and total.
- `python -m app.jobs purge-deleted` permanently removes notes deleted more than 30 days ago. Attachment bytes first move atomically into a same-filesystem `.trash` quarantine; database rollback restores them, and failed final unlinks remain discoverable for the next scheduled cleanup.
- `deploy/app.yaml` schedules the purge daily at 03:00 UTC with `concurrencyPolicy: Forbid`. A PostgreSQL advisory lock also prevents overlapping runs across schedulers.
- Account deletion remains an immediate hard delete, including already soft-deleted notes and attachment bytes.

## Verification

Coverage uses an actual isolated PostgreSQL server and temporary upload storage. It includes the exact 15-second undo boundary, expiry, cross-user denial, repeated deletion, deleted-parent mutation exclusion, attachment survival through undo, old-only purge, quarantine cleanup retry, database rollback restoration, concurrent purge exclusion, immediate account deletion, UI toast expiry/undo, delayed DELETE responses, and paginated total reconciliation.

## Operations

The schema migration and CronJob manifest are code-complete but were not applied to staging or production by this feature task. Apply Alembic through the approved deployment path, ensure the CronJob mounts the same upload volume as the backend, and monitor failed Jobs before calling the feature production-ready.

## Out of scope

- A trash view or recovery after the 15-second undo window.
- Production migration, deployment, or execution of the purge job.
