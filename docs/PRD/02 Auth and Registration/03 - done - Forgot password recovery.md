# Forgot password / account recovery

2026-09-17 · split from `02 Auth & Registration Spec.md`

**Status: done.** Implemented in `backend/app/auth/routes.py` (`forgot`, `reset`) and `backend/app/auth/email.py`.

## What it does

1. User enters their email on a "forgot password" screen.
2. Backend always returns a generic "if that email exists, we've sent a link" response, whether or not the account exists — avoids leaking which emails are registered.
3. If the account exists and uses `auth_provider = 'local'`, a single-use, time-limited reset token is generated, its hash stored, and a reset link containing the raw token is emailed.
4. If the account exists but was created via a social provider, the email instead tells them to log in with that provider — there's no password to reset.
5. User submits a new password from the emailed link.
6. Backend validates the token (not expired, not already used), applies the same password policy as registration, updates the password hash, invalidates the token, and bumps `User.token_version` to invalidate every existing refresh token for that user (forces re-login everywhere).

## Email provider

AWS SES in production (`MAIL_MODE=ses` in `deploy/app.yaml`), used for password reset, email verification, and email-change confirmation.

## Data model

Reuses the `email_tokens` table from [01 - done - Registration and email verification](./01%20-%20done%20-%20Registration%20and%20email%20verification.md), keyed by `purpose`.

## Endpoints

`POST /api/auth/forgot-password`, `POST /api/auth/reset-password`.

## Security

- `POST /api/auth/forgot-password` is rate-limited.
- Identical response shape regardless of account existence.
- Reset tokens stored as hashes, single-use, time-limited (expires in 1 hour).
- Successful reset revokes every outstanding session for that user.
