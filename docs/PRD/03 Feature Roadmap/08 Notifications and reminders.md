# Notifications & reminders

2026-09-17 · split from `03 Feature Roadmap (Post-MVP).md`

**Status:** Not started. **Depends on:** the AWS SES email integration from the Auth & Registration Spec (`PRD/02 Auth & Registration Spec.md`) — this is why it's sequenced last among the non-collaboration items.

## Problem

Nothing in the app currently reaches out to a user — everything requires them to open it and check. The backend also has no mechanism for anything to happen outside of a direct API request; that's the actual prerequisite this spec is gated on, not just email.

## Requirements — scheduler (shared prerequisite)

- A background job scheduler — something like Celery, APScheduler, or a simple cron-triggered endpoint. Pick the lightest option that fits a single self-managed EKS cluster (a cron-triggered internal endpoint, hit by a Kubernetes CronJob, is probably the least infrastructure for this app's scale — avoid standing up a message broker like Redis/RabbitMQ just for this unless a second use case needs it).
- [05 Soft delete and undo](./05%20Soft%20delete%20and%20undo.md)'s 30-day purge job can reuse this same scheduler once it exists.

## Requirements — reminders

- "Meeting starting soon" reminder email, sent a configurable amount of time before `meeting_date` (default 10 minutes).
- Only meaningful once meetings can be scheduled in the future with intent — today a meeting is really a record of something that already happened (`meeting_date` is a date, not a datetime, and the UI/workflow treats notes as retrospective). This may need a "scheduled time" concept to exist first, separate from the historical `meeting_date` field, before a reminder is meaningful.

## Requirements — digests

- Optional weekly email: open action items, meetings from the past week.
- Opt-in/opt-out from account settings (extends the account settings surface in `frontend/src/app/account/`).

## Data model

- A per-user preference for digest opt-in/opt-out (e.g. a `digest_enabled` column on `users`, following the same idempotent `ALTER TABLE ADD COLUMN IF NOT EXISTS` pattern in `backend/app/init_db.py`).
- Reminders need a way to track "already sent" per meeting to avoid duplicate sends if the scheduler runs more than once around the send window.

## Out of scope until dependencies land

- Reminders specifically are blocked on deciding what "a meeting with a future, reminder-worthy time" even means in this app's model — don't build the email-sending mechanics before that's settled, or they'll have nothing meaningful to trigger on.
