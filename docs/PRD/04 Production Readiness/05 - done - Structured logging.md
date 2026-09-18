# Structured logging

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: code-complete.** The backend now emits allowlisted JSON logs, propagates safe request IDs, records redacted request/error details, and maintains an identifier-free auth-event trail. Live log aggregation remains deployment-owned; this change adds no PII transport or logging infrastructure.

## Problem

If something breaks in production, the only way to find out right now is a user reporting it, or reading raw container stdout by hand.

## Requirements

- Replace ad hoc logging with structured (JSON) logs, including a request id per request so a single request's logs can be traced end to end.
- Log auth events specifically (login success/failure, password reset requested, 2FA enabled/disabled) — these double as a lightweight audit trail.
- Never log passwords, tokens, or TOTP secrets, even at debug level.

## Implementation notes

- `backend/app/observability.py` uses a stdlib JSON formatter and a `ContextVar` request ID. Incoming `X-Request-ID` values must be 1–64 safe ASCII characters; invalid values are replaced with a generated UUID and the accepted value is echoed on the response.
- Request records include only method, matched route template, status, duration, and request ID. Raw paths, query strings, bodies, headers, cookies, IP addresses, emails, note identifiers, and content are never included. Third-party records are reduced to safe logger/level metadata instead of formatting their messages.
- Unhandled errors retain only the exception class and a source-location stack without the exception value. Login password/OAuth/2FA outcomes, password-reset requests, and 2FA enable/disable outcomes are explicit auth events without user identifiers.
- Focused tests parse emitted JSON, exercise concurrent context isolation and request-ID replacement, assert safe 500/error records, cover all required auth paths, and seed email/password/token/TOTP/query sentinels across application and access-log channels. The complete backend suite runs against isolated PostgreSQL.
- JSON is written to stdout for the deployment's existing collection layer. No external collector, provider, production configuration, or deployment is activated by this repository change.
