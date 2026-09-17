# Authentication and registration

The app now supports local registration/login, email verification, recovery, private notes and attachments, silent session refresh, remember-me, logout, and Google/Facebook/Amazon authorization-code adapters. Access tokens are 15-minute JWTs held only in Angular service memory. Refresh credentials are opaque random tokens stored as SHA-256 hashes, rotated on every use. Without remember-me the cookie is session-only and the server session expires after 24 hours; remember-me uses a persistent cookie with a fixed 30-day expiry.

## Try locally

The running app is at http://localhost:8080. Register with any valid test email, then open http://localhost:8025 to read the verification message. Mailpit captures mail locally; nothing is sent to the public email address. Open the link and press **Verify email**. Forgot-password links arrive in the same local inbox. Mailpit is development-only, bound to localhost, and is not deployed to Kubernetes.

For a new checkout, create a private `.env` containing a cryptographically random `AUTH_SECRET` (32+ characters) before `docker compose up --build -d`. `.env.example` lists optional provider credentials. The existing installation already has a generated secret; do not overwrite it unless intentionally revoking all sessions.

Verification and reset links expire after one hour, are single-use, and carry tokens in a URL fragment so proxy access logs and Referer headers do not include them. The frontend removes the fragment after reading it and submits the token in a POST. If a link expires, sign in and use **Resend email**, or request a new password reset. Password reset revokes every refresh session and outstanding email token; access tokens are also rejected immediately via the user's token version.

## Production configuration

| Setting | Required value |
| --- | --- |
| `AUTH_SECRET` | Strong random secret shared across backend workers; keep in `minutes-secrets` under `auth-secret` |
| `APP_URL` | Exact HTTPS frontend origin, without trailing slash |
| `COOKIE_SECURE` | `true` (default); false only permitted for localhost HTTP development |
| `MAIL_MODE` | `ses` (default) |
| `AWS_REGION` | Region containing the SES verified identity |
| `SES_FROM_EMAIL` | Verified sender address/domain |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google OAuth web application credentials |
| `FACEBOOK_CLIENT_ID`, `FACEBOOK_CLIENT_SECRET` | Meta app credentials |
| `AMAZON_CLIENT_ID`, `AMAZON_CLIENT_SECRET` | Login with Amazon Security Profile credentials |

Create `minutes-oauth` as a Kubernetes Secret with the provider variable names as keys. The backend imports it via `envFrom`; secrets never go into the Angular bundle. Provider buttons are unavailable until both ID and secret are configured. Restart the backend after changing them.

`deploy/service-account.yaml` uses an IRSA role (`SES_ROLE_ARN`) trusted by `system:serviceaccount:minutes:minutes-backend`. Grant this role `ses:SendEmail` scoped to your verified identity. Do not provide static AWS keys to the frontend. The cluster must support IAM roles for service accounts and allow outbound HTTPS to SES and the provider APIs. SES sandbox accounts require verified recipients; request production access for arbitrary recipients. Delivery failures are logged without message bodies, tokens, or recipient addresses; users can retry through resend/recovery. Delivery currently runs as an in-process background task, not a durable queue, so a crash can lose an email; a fresh resend issues a new link.

Register these exact callback URLs in provider consoles (substitute your production domain; use localhost:8080 for Docker development):

- `https://YOUR_DOMAIN/api/auth/google/callback`
- `https://YOUR_DOMAIN/api/auth/facebook/callback`
- `https://YOUR_DOMAIN/api/auth/amazon/callback`

Google uses OIDC with Authlib validation of issuer, audience, signature, nonce, and state, plus PKCE. Facebook uses Graph API v23.0 with `email public_profile` scopes; review Meta's production approval requirements. Amazon uses the `profile` scope. Missing email, rejected consent, invalid state, and provider errors return a safe sign-in error. No OAuth access/refresh credential is put in a frontend URL.

## Spec resolutions

- The overview said email verification was out of scope, but the detailed registration rules and final decisions require it. It is implemented and enforced by the backend.
- Global uniqueness of `users.email` conflicts with separate accounts for an unverified email match. Local emails have a partial unique index; social identities have a unique `(provider, provider_user_id)` constraint in a separate table. This supports automatic links to multiple providers without overwriting the original password or provider identity.
- A matching email is merged only when both the existing account and the incoming mailbox are verified. Google provides a verified-email claim. Facebook/Amazon profile email alone is not treated as proof: these accounts receive an email verification link, and then automatically merge into the verified matching account. No manual provider-linking UI is added. This also means those new social accounts must verify before creating notes.
- Password reset and verification share `email_tokens`, distinguished by a purpose column; their raw tokens are never stored there. Refresh tokens are opaque random credentials rather than JWTs because their database lookup is required for rotation and revocation anyway.
- Existing local pre-auth notes are preserved with null owners, remain inaccessible through the API, and are never assigned to a registrant automatically. Fresh databases require `owner_id`; upgraded databases enforce ownership for new/updated rows through a NOT VALID check constraint. An administrator can explicitly assign old notes to a known account with SQL if wanted.

## Security and operational behavior

Passwords use bcrypt with cost 12. Policy is minimum 10 characters, one ASCII letter, one digit, maximum 72 UTF-8 bytes (bcrypt's input limit). Both the UI and backend validate the policy and confirmation. HTTP cookies are HttpOnly (refresh only), Secure in production, and SameSite=Lax. Refresh/logout require an exact Origin, a custom request header, and a double-submit CSRF value bound to the stored session. There is no cross-origin CORS allowance. Keep frontend and API on the same origin.

PostgreSQL rate-limit counters are shared across workers. Limits per 15 minutes are 5 registrations, 15 login attempts, 5 recovery requests, 5 resends, 15 verification/reset submissions, and 30 OAuth starts per observed client IP. Behind the supplied Nginx proxy this conservatively groups clients by proxy address. Configure a trusted-proxy topology and edge rate limits before serving a larger public audience; the backend deliberately does not trust arbitrary forwarded headers. Expired rate buckets reset on use; schedule periodic cleanup of expired rate/session/email-token rows for a long-running service.

Every note endpoint and every attachment upload/download/delete checks the authenticated owner; other users get 404. Attachment downloads use the Angular HTTP client with the bearer header, not unauthenticated links. Auth and note API responses use no-store. Logout revokes the current session immediately; password reset revokes all sessions. Refresh rotation is single-flight within one tab; two tabs refreshing simultaneously can cause one to return to sign-in. There are no roles, sharing, 2FA, or manual account-linking controls.

## Verification

Run `docker compose -p minutes-tests -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests`. Tests use a separate PostgreSQL instance and mocked email delivery, covering local auth, isolation for every note/file operation, reset/verification reuse and expiry, CSRF, refresh rotation, logout/recovery revocation, remember-me, rate limits, and provider linking/state rejection. Live SES delivery and consent flows need your account configuration and remain untested against external providers.

References: [SES send_email](https://docs.aws.amazon.com/boto3/latest/reference/services/ses/client/send_email.html), [Authlib web OAuth clients](https://docs.authlib.org/en/stable/oauth2/client/web/index.html), [Login with Amazon documentation](https://www.developer.amazon.com/docs/loginwithamazon/documentation-overview).
