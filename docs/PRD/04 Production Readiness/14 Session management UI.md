# Session management UI

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: not done.**

## Problem

Refresh tokens are long-lived (30 days, longer with "remember me" — see [02 - done - Login and sessions](../02%20Auth%20and%20Registration/02%20-%20done%20-%20Login%20and%20sessions.md)), but there's no way for a user to see or act on that. If a device is lost or a password is suspected compromised, the only recourse today is changing the password, which revokes every session at once — there's no way to revoke just one.

## Requirements

- An "Active sessions" section in account settings, listing each refresh token's approximate device/browser, IP or location, and last-used time.
- A way to revoke a single session, or "log out everywhere."

## Data model change required

`refresh_tokens` (`backend/app/auth/models.py`) currently stores only `token_hash`, `csrf_hash`, `remember`, `expires_at`, `revoked_at` — no device, IP, or last-used metadata. This needs new columns (e.g. `user_agent`, `ip_address` or a coarser location, `last_used_at`) populated at token issuance (`login`, `refresh`) and updated on each refresh.

## Endpoints

New: `GET /api/auth/sessions` (list, excluding revoked/expired), `DELETE /api/auth/sessions/{id}` (revoke one), and either reuse or extend the existing `POST /api/auth/logout` semantics for "log out everywhere" (bumping `User.token_version` already does this in bulk for password resets — the same mechanism applies here).

## Frontend

A new section in `frontend/src/app/account/account.ts`/`account.html`, alongside the existing 2FA and danger-zone sections.
