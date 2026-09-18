# Session management UI

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: code-complete.** Active sessions are listed in Account settings with approximate user-agent, trusted peer IP, created time, last-use time, and current-session state. Users can revoke one session or log out everywhere. Alembic revision `20260918_0009` adds nullable metadata so legacy sessions are shown honestly as unknown rather than with invented values. Applying that migration and deploying the code remain normal operator steps.

## Problem

Refresh sessions can last up to 30 days with “remember me” (see [02 - done - Login and sessions](../02%20Auth%20and%20Registration/02%20-%20done%20-%20Login%20and%20sessions.md)). Account settings now makes that lifetime visible and controllable per device.

## Requirements

- An "Active sessions" section in account settings, listing each refresh token's approximate device/browser, IP or location, and last-used time.
- A way to revoke a single session, or "log out everywhere."

## Data model change required

`refresh_tokens` stores bounded `user_agent` and peer `ip_address` values plus timezone-aware `created_at` and `last_used_at` timestamps. Every registration, password login, verification, OAuth, and completed 2FA issuance records metadata; refresh rotation preserves the stable session ID and updates the last-use metadata. The API never returns token hashes. No external IP geolocation service is used.

## Endpoints

- `GET /api/auth/sessions` lists only the authenticated user's unexpired, unrevoked sessions and marks the session represented by the access token.
- `DELETE /api/auth/sessions/{id}` returns 404 for another user's ID and revokes the selected session immediately, including already-issued access tokens.
- `POST /api/auth/logout-all` revokes every refresh session, increments `User.token_version`, clears cookies, and invalidates already-issued access tokens.
- Password changes increment the token version, revoke every other session, and return a replacement access token for the deliberately retained current session. Password reset continues to revoke every session.

## Frontend

The Account page includes loading, retry/error, empty, confirmation, current-session, single-revoke, and log-out-everywhere states. Legacy rows display unknown metadata explicitly.
