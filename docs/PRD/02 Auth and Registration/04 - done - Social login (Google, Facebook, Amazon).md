# Social login (Google, Facebook, Amazon)

2026-09-17 · split from `02 Auth & Registration Spec.md`

**Status: done.** Implemented in `backend/app/auth/oauth.py`, using Authlib's OAuth 2.0/OIDC client.

## What it does

All three providers follow the same authorization-code flow:

1. `GET /api/auth/{provider}/login` redirects to the provider's consent screen.
2. Provider redirects back to `GET /api/auth/{provider}/callback` with an authorization code.
3. Backend exchanges the code for the provider's tokens, then fetches the user's profile (email, name, provider user id). For Google this comes from the OIDC `userinfo` claims (with `email_verified`); Facebook and Amazon are treated as unverified-by-provider and go through this app's own email verification.
4. `social_user()` looks up an existing `Identity` row by `(provider, provider_user_id)`:
   - Match found → log them in.
   - No match, but the email matches an existing account that's already verified → link the social login to that account (an advisory lock on the email keyed via `pg_advisory_xact_lock` prevents a race between two simultaneous sign-ins for the same email).
   - No match, and the email doesn't match a verified account → create a new, separate account rather than silently attaching to someone else's unverified email.
5. Backend issues the same access/refresh tokens as the email/password flow.

`GET /api/auth/providers` tells the frontend which providers are actually configured (client ID/secret present), so `auth-page.ts` only shows buttons for providers that will work.

## Provider notes

- Google: OpenID Connect via `accounts.google.com`'s discovery document; Authlib validates state, issuer, audience, and nonce.
- Facebook: Facebook Login (Graph API v23), `token_endpoint_auth_method: client_secret_post`.
- Amazon: Login with Amazon, same auth method.
- Each provider's client ID/secret are read from environment variables (`{PROVIDER}_CLIENT_ID`/`_CLIENT_SECRET`) — a provider is only registered with Authlib if both are present, so an unconfigured provider fails closed rather than half-registering.

## Data model

`social_identities` (`backend/app/auth/models.py`, referred to as `Identity`): `id`, `user_id`, `provider`, `provider_user_id`, unique on `(provider, provider_user_id)`.

## Endpoints

`GET /api/auth/providers`, `GET /api/auth/{provider}/login`, `GET /api/auth/{provider}/callback` for `provider` in `google`, `facebook`, `amazon`.

## Security

- OAuth client secrets live only in backend environment variables (`<namespace>-oauth` Kubernetes Secret in `deploy/app.yaml`), never shipped to the frontend.
- Authlib validates the OAuth `state` parameter on callback.
- `GET /api/auth/{provider}/login` is rate-limited.
- An unhandled failure anywhere in the callback rolls back the transaction and redirects to a generic `social_failed` error rather than leaking exception detail.

## Not yet in production

Facebook additionally requires Meta's app review to serve real users past a small testing allowlist, and all three providers require a live privacy policy before their consent screens can leave test mode — see [15 - done - Legal pages](../04%20Production%20Readiness/15%20-%20done%20-%20Legal%20pages%20%28privacy%20policy%20and%20ToS%29.md).
