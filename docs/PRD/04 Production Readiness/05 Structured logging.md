# Structured logging

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: not done.** The only logging call in the backend is a single `logging.getLogger(__name__).error(...)` in `backend/app/auth/email.py` for send failures — no structured format, no request id, no auth-event trail.

## Problem

If something breaks in production, the only way to find out right now is a user reporting it, or reading raw container stdout by hand.

## Requirements

- Replace ad hoc logging with structured (JSON) logs, including a request id per request so a single request's logs can be traced end to end.
- Log auth events specifically (login success/failure, password reset requested, 2FA enabled/disabled) — these double as a lightweight audit trail.
- Never log passwords, tokens, or TOTP secrets, even at debug level.

## Implementation notes

- A request-id middleware (similar in shape to the existing `private_responses` middleware in `backend/app/main.py`) can generate/propagate an id and bind it into a per-request logging context.
- Auth events are a natural fit as explicit log calls at the relevant points in `backend/app/auth/routes.py` (`login`, `login_2fa`, `reset`, `enable_2fa`/`disable_2fa`) rather than inferred from generic request logs.
- Given the app runs on EKS, JSON-formatted stdout logs are the natural fit for whatever log aggregation the cluster already ships to (CloudWatch, or a cluster-level Fluent Bit/Loki setup) — no new logging infrastructure needed, just a formatter change.
