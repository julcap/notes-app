# Backend automated tests

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: done.** `backend/tests/test_api.py` (notes/attachments/action items) and `backend/tests/test_auth.py` (the full auth surface), run against a real test Postgres via `docker compose -p minutes-tests -f compose.test.yaml up`.

## What was asked for

- Integration tests for each router, using a real (test) Postgres database via a fixture, not mocked — auth flows especially, since token issuance, hashing, and expiry logic are exactly the kind of thing that's easy to get subtly wrong.
- Auth-specific coverage: registration validation, login with wrong/social-only accounts, password reset token expiry and single-use, 2FA enrollment and challenge flow.
- A minimum bar: every auth endpoint and every meetings CRUD endpoint has at least a happy-path and a failure-path test.

## What exists

- `test_api.py`: CRUD + search + validation, attachment upload/download/cascade/size-limit, action-item CRUD and cross-note/cross-user ownership isolation.
- `test_auth.py`: registration + single-use verification, password policy + duplicate email rejection, per-user note/attachment privacy, refresh rotation + CSRF + logout, password reset (generic response, single-use, session revocation), expired-token handling, rate limits, "remember me" cookie lifetime, social-account merge/unverified-separation/mailbox-proof-before-linking, OAuth state rejection, resend-verification, TOTP login + backup codes, TOTP disable requiring password-or-code, email change flow, password change, account-deletion cascade.
- Both use a real Postgres instance (`compose.test.yaml`'s `test-database` service), not mocks. The service runs Alembic before pytest, and fixtures clear table rows between tests without bypassing migration history.

## Enforcement

Gated in CI — see [10 - done - CI pipeline and deploy](./10%20-%20done%20-%20CI%20pipeline%20and%20deploy.md): `.github/workflows/ci.yaml`'s `test` job runs this suite on every PR and on push to `main`, and `deploy` only runs if `test` passes. A `compose.test.yaml` volume-mount gap that made one metrics test silently error out instead of asserting anything was fixed 2026-09-18 — see [08 - done - Metrics](./08%20-%20done%20-%20Metrics.md#fixed-2026-09-18-test-harness-gap). Full suite: 106/106 passing.

## Not covered by this file

Frontend component/service tests — see [02 - done - Frontend automated tests](./02%20-%20done%20-%20Frontend%20automated%20tests.md), now implemented separately.
