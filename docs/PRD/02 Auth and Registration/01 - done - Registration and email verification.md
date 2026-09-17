# Registration and email verification

2026-09-17 · split from `02 Auth & Registration Spec.md`

**Status: done.** Implemented in `backend/app/auth/routes.py` (`register`, `verify`, `resend`) and `frontend/src/app/auth/auth-page/`.

## Problem

Before this, the app had no concept of a user — any visitor could see, create, and delete all meetings.

## What it does

1. User submits email, password, password confirmation, and optional display name.
2. Backend validates: email format, email not already registered, password meets policy (min 10 characters, at least one letter and one number, max 72 UTF-8 bytes — bcrypt's own limit).
3. Password is hashed with bcrypt (never stored in plain text).
4. A `User` row is created with `auth_provider = 'local'`.
5. On success, the backend issues an access token and refresh token; the frontend redirects to the meeting list.
6. A verification email is sent with a single-use link. Local accounts must verify their email before they can create meetings — existing meeting-creation endpoints reject the request with a clear error until verified.

## Data model

`users` (`backend/app/auth/models.py`): `id`, `email` (unique among local accounts via a partial unique index), `password_hash` (nullable — null for social-only accounts), `email_verified`, `pending_email`, `display_name`, `auth_provider`, `token_version`, `created_at`, `updated_at`.

`email_tokens`: `id`, `user_id`, `purpose` (shared with password reset and email-change confirmation), `token_hash` (raw token only ever in the email), `expires_at`, `used_at`.

## Endpoints

`POST /api/auth/register`, `POST /api/auth/verify-email`, `POST /api/auth/resend-verification`.

## Security

- Passwords hashed with bcrypt, never logged or stored in plain text.
- Verification tokens stored as hashes, single-use, time-limited.
- `POST /api/auth/register` is rate-limited (`limit()` in `backend/app/auth/security.py`) to slow down spam/abuse.
- Requests require matching `Origin`/`X-Requested-With` headers (`same_origin` dependency) as basic CSRF-adjacent hardening on state-changing auth endpoints.
