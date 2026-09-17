# Meeting Notes App — Auth & Registration Spec

2026-09-17 · @Someone

Adds user registration, email/password authentication, forgot-password recovery, and social login via Google, Facebook and Amazon to the meeting notes app.

## 1. Overview & scope

Today the app has no concept of a user: any visitor can see, create and delete all meetings. This feature adds accounts so meetings belong to the person who created them, and adds four ways to sign in: email/password, Google, Facebook and Amazon.

**In scope**

- Email/password registration and login
- Forgot password (reset via emailed link)
- Social login: Google, Facebook, Amazon (OAuth 2.0 / OpenID Connect)
- Associating meetings with the user who owns them
- Session handling (JWT access + refresh tokens)

**Out of scope for this pass**

- Sharing a meeting with other users / team workspaces
- Roles or permissions beyond "owner"
- Two-factor authentication
- Email verification on registration (recommended as a fast-follow, noted in Open Questions)

## 2. Registration & email/password login

**Registration**

1. User submits email, password, password confirmation, and optional display name
2. Backend validates: email format, email not already registered, password meets policy (min 10 characters, at least one letter and one number)
3. Password is hashed with bcrypt (never stored in plain text) before saving
4. A `User` row is created with `auth_provider = 'local'`
5. On success, the backend issues an access token and refresh token, and the frontend redirects to the meeting list

**Email verification**

- On registration, a verification email is sent with a single-use link
- Local accounts must verify their email before they can create meetings (existing endpoints reject the request with a clear error until verified)
- Verification uses the same token pattern as password reset: single-use, time-limited, stored as a hash

**Login**

1. User submits email and password
2. Backend looks up the user by email, verifies the password hash
3. If the account was created via a social provider (no password set), return a clear error telling them which provider to use instead
4. On success, issue access token (short-lived, \~15 min) and refresh token (long-lived, \~30 days, stored as an httpOnly cookie)

**Frontend validation** mirrors the backend rules so the user gets instant feedback, but the backend is the source of truth and re-validates everything.

## 3. Forgot password / account recovery

1. User enters their email on a "Forgot password" page
2. Backend always returns a generic "if that email exists, we've sent a link" response, whether or not the account exists (avoids leaking which emails are registered)
3. If the account exists and uses `auth_provider = 'local'`, generate a single-use, time-limited reset token (expires in 1 hour), store its hash, and email a reset link containing the raw token
4. If the account exists but was created via a social provider, send an email instead telling them to log in with that provider (no password to reset)
5. User clicks the link, lands on a "Set new password" page, submits a new password
6. Backend validates the token (not expired, not already used), applies the same password policy as registration, updates the password hash, invalidates the token, and invalidates any existing refresh tokens for that user (forces re-login everywhere)

**Email provider: AWS SES.** The backend isn't currently wired up to send transactional email — this is a new dependency this feature introduces, used for both password reset and email verification.

## 4. Social login (Google, Facebook, Amazon)

All three follow the same OAuth 2.0 / OpenID Connect authorization-code flow:

1. Frontend redirects the user to the provider's consent screen (or opens a popup) using a provider-specific client ID registered in that provider's developer console
2. Provider redirects back to a backend callback URL (e.g. `/api/auth/google/callback`) with an authorization code
3. Backend exchanges the code for the provider's tokens, then fetches the user's profile (email, name, provider user id)
4. Backend looks up a user by `(auth_provider, provider_user_id)`:
   - Match found → log them in
   - No match, but the email matches an existing account and that email is already verified → automatically merge: link the social login to that existing account, no manual confirmation step
   - No match, and the email either doesn't match an existing account or matches one that isn't verified yet → treat as a new, separate account (never silently attach to an unverified email)
   - No match at all → create a new `User` row with `auth_provider` set accordingly
5. Backend issues the same access/refresh tokens as the email/password flow, so the rest of the app doesn't need to know how someone signed in

**Provider notes**

- Google: use Google Identity Services; needs a Google Cloud project and OAuth consent screen configured
- Facebook: use Facebook Login; needs a Meta for Developers app, and the app must pass Meta's review to use it in production for more than a handful of test users
- Amazon: use Login with Amazon; needs a Security Profile registered in Amazon's developer console
- Each provider needs its client ID and client secret stored as backend environment variables, never in frontend code
- Redirect/callback URLs must be registered exactly (including protocol and port) in each provider's console for both local development and production

## 5. Data model changes

**New `users` table**

| Column | Type | Notes |
| --- | --- | --- |
| id | integer, PK |  |
| email | string, unique |  |
| password\_hash | string, nullable | null for social-only accounts |
| email\_verified | boolean | default false; local accounts must verify before creating meetings |
| display\_name | string |  |
| auth\_provider | enum: local, google, facebook, amazon |  |
| provider\_user\_id | string, nullable | provider's id for the user; unique together with auth\_provider |
| created\_at | datetime |  |
| updated\_at | datetime |  |

**New `password_reset_tokens` table**

| Column | Type | Notes |
| --- | --- | --- |
| id | integer, PK |  |
| user\_id | FK → users.id |  |
| token\_hash | string | the raw token is only ever in the email, never stored |
| expires\_at | datetime |  |
| used\_at | datetime, nullable |  |

**New `refresh_tokens` table** (so tokens can be revoked, e.g. on password reset or logout)

| Column | Type | Notes |
| --- | --- | --- |
| id | integer, PK |  |
| user\_id | FK → users.id |  |
| token\_hash | string |  |
| expires\_at | datetime |  |
| revoked\_at | datetime, nullable |  |

**Existing `meetings` table**

- Add `owner_id` (FK → users.id, not nullable going forward)
- Not applicable — no existing production data needs migrating, so `owner_id` can be required from the start

## 6. New API endpoints

| Method | Path | Description |
| --- | --- | --- |
| POST | /api/auth/register | Create a local account |
| POST | /api/auth/login | Email/password login, returns tokens |
| POST | /api/auth/refresh | Exchange refresh token for a new access token |
| POST | /api/auth/logout | Revoke the current refresh token |
| POST | /api/auth/forgot-password | Request a reset email |
| POST | /api/auth/reset-password | Submit new password with a reset token |
| GET | /api/auth/google/login | Redirect to Google's consent screen |
| GET | /api/auth/google/callback | Handle Google's redirect back |
| GET | /api/auth/facebook/login | Redirect to Facebook's consent screen |
| GET | /api/auth/facebook/callback | Handle Facebook's redirect back |
| GET | /api/auth/amazon/login | Redirect to Amazon's consent screen |
| GET | /api/auth/amazon/callback | Handle Amazon's redirect back |
| GET | /api/auth/me | Return the logged-in user's profile |
| POST | /api/auth/resend-verification | Resend the verification email |
| POST | /api/auth/verify-email | Confirm the email using the token from the verification link |

**Existing meeting endpoints** all become protected: every request must carry a valid access token, and `list_meetings` / `get_meeting` / `update_meeting` / `delete_meeting` all filter or check against the current user's `owner_id`.

## 7. Frontend changes (Angular)

**New components**

- `login` — email/password form + "Remember me" checkbox + "Sign in with Google/Facebook/Amazon" buttons
- `register` — registration form
- `forgot-password` — request-reset form
- `reset-password` — new-password form (reached via the emailed link's token in the URL)
- `verify-email` — confirms the token from the verification link, with a "resend email" option if it's expired

**New service:** `auth.service.ts` — wraps the `/api/auth/*` endpoints, stores the access token in memory (not localStorage, to reduce XSS exposure), and exposes the current user as an observable

**Route changes**

- Add an `authGuard` (`CanActivateFn`) that redirects to `/login` if there's no valid session, applied to all existing meeting routes
- Add public routes for `/login`, `/register`, `/forgot-password`, `/reset-password`

**HTTP changes**

- An `authInterceptor` attaches the access token to outgoing requests and, on a 401, attempts a silent refresh via `/api/auth/refresh` before retrying once

**Header/nav**

- Show the logged-in user's name and a "Log out" action once authenticated

## 8. Security considerations

- Passwords hashed with bcrypt (or argon2), never stored or logged in plain text
- Reset and refresh tokens stored as hashes, not raw values, so a database leak doesn't expose usable tokens
- Forgot-password responses are identical whether or not the email exists, to avoid confirming which emails are registered
- Rate limit `/api/auth/login`, `/api/auth/register` and `/api/auth/forgot-password` to slow down brute-force and spam attempts
- CSRF protection on any cookie-based flow (the refresh token cookie should be httpOnly, Secure, and SameSite=Lax or Strict)
- OAuth client secrets live only in backend environment variables, never shipped to the frontend
- Validate the OAuth `state` parameter on callback to prevent CSRF on the social login flow
- All auth endpoints served over HTTPS in production

## 9. Open questions

- [x] Require email verification before letting a new local account create meetings, or allow immediate use? **Decided: yes** — email verification is required for local accounts before they can create meetings.
- [x] What happens to meetings created before this feature ships — assign to a default account, or allow nullable `owner_id` for legacy rows? **Decided: N/A** — not applicable.
- [x] Should a user be able to link multiple social providers to one account after signing up? **Decided: no** manual linking for now. A social login auto-merges into an existing account only when the email matches AND that email is already verified; otherwise it creates a new, separate account.
- [x] Which transactional email provider to use for reset links (SendGrid, Postmark, AWS SES, other)? **Decided: AWS SES.**
- [x] Do we need "remember me" vs. a fixed session length, or is the 30-day refresh token enough? **Decided: yes** — add a "remember me" option.

**Out of scope, tracked separately:** two-factor authentication, sharing meetings between users, roles/permissions.
