# Notifications & reminders

2026-09-17 · split from `03 Feature Roadmap (Post-MVP).md`

**Status:** Code-complete 2026-09-18. Production activation remains operator-controlled: apply Alembic revision `20260918_0005`, deploy the CronJobs, and verify SES plus job monitoring before calling the feature live.

## Shipped behavior

- Notes have an optional timezone-aware `scheduled_at`, separate from the historical `meeting_date`. The API rejects naive datetimes and PostgreSQL stores instants as `TIMESTAMPTZ`; the Angular `datetime-local` control converts the browser's local time to UTC.
- `GET` and `PUT /api/auth/notification-preferences` manage explicit opt-ins for reminders and weekly digests plus a validated 1–1440 minute reminder lead (default 10 minutes). Both email features default off.
- `python -m app.jobs reminders` sends verified owners one “meeting starting soon” email while a live note is within its lead window and still before its scheduled instant. Clearing `scheduled_at` cancels reminder intent; deleted and unverified-owner notes are ignored.
- `python -m app.jobs weekly-digest` sends opted-in verified owners their previous seven calendar days of meetings and current open action items. Empty digests are skipped. Digest content is owner-only; it is never sent to note collaborators.
- Kubernetes runs reminders every minute and weekly digests Monday at 09:00 UTC. The existing purge command uses the same lightweight internal CLI/CronJob pattern; no public scheduler endpoint or message broker was added.

## Delivery safety

PostgreSQL session-level advisory locks prevent overlapping runs, and persistent unique delivery keys cover each owner/note/scheduled instant and each owner/week. Each recipient is committed independently, so a failed `send_email` call remains eligible for retry without rolling back successful deliveries to other recipients. Repeated and concurrent normal runs therefore do not duplicate mail.

SES does not expose an exactly-once idempotency key for `SendEmail`. A process crash after SES accepts a message but before PostgreSQL commits the delivery row can still cause one retry and duplicate message. This unavoidable crash window must be considered when operating or replacing the sender.

## Verification

Coverage includes timezone/DST conversion, naive datetime and lead validation, opt-in defaults, deleted/cancelled/unverified notes, schedule edits, repeated and concurrent jobs, failed-send retry, digest week boundaries and empty skips, account settings UI, and a real local SMTP protocol exchange compatible with Mailpit.
