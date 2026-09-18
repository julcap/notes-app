# Login and sessions

2026-09-17 · split from `02 Auth & Registration Spec.md`

**Status: done.** Implemented in `backend/app/auth/routes.py` (`login`, `refresh`, `logout`, `me`) and `frontend/src/app/auth/`.

## What it does

1. User submits email and password.
2. Backend looks up the user by email, verifies the password hash (a dummy-hash comparison runs even on a missing user, so response timing doesn't reveal whether the email exists).
3. If the account was created via a social provider (no password set), a clear error tells them which provider to use instead.
4. If the account has TOTP enabled, tokens aren't issued yet — a short-lived "2FA required" challenge is returned instead; see [05 - done - Two-factor authentication (TOTP)](./05%20-%20done%20-%20Two-factor%20authentication%20%28TOTP%29.md).
5. On success, the backend issues an access token (short-lived) and a refresh token (long-lived, longer with "remember me"), the refresh token stored as an httpOnly cookie.
6. `authInterceptor` (`frontend/src/app/auth/auth.interceptor.ts`) attaches the access token to outgoing requests and, on a 401, attempts a silent refresh before retrying once.
7. `authGuard` (`frontend/src/app/auth/auth.guard.ts`) redirects to login when there's no valid session, applied to all meeting routes.

## Data model

`refresh_tokens` (`backend/app/auth/models.py`): `id`, `user_id`, `token_hash`, `csrf_hash`, `remember`, `expires_at`, `revoked_at` — stored as hashes so a database leak doesn't expose usable tokens. `User.token_version` lets a password change or account event invalidate all outstanding tokens at once without deleting rows individually.

## Endpoints

`POST /api/auth/login`, `POST /api/auth/refresh`, `POST /api/auth/logout`, `GET /api/auth/me`.

## Security

- `POST /api/auth/login` is rate-limited.
- Refresh token cookie is httpOnly, Secure (`COOKIE_SECURE=true` in production, see `deploy/app.yaml`), and carries a separate CSRF token (`csrf_hash`) checked on refresh/logout.
- Refresh performs rotation (old token revoked, new one issued) rather than reusing the same token indefinitely.
- All auth endpoints are served over HTTPS in production (`APP_URL=https://${APP_DOMAIN}` in the deploy manifest).

## Not built

- A UI for viewing/revoking individual sessions — see [14 - done - Session management UI](../04%20Production%20Readiness/14%20-%20done%20-%20Session%20management%20UI.md) in the Production Readiness folder; the `refresh_tokens` table would need device/IP/last-used metadata added to support it.
