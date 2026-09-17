# Secrets management

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: done**, for the "not committed to the repo" core ask. `deploy/app.yaml` reads all credentials from Kubernetes Secrets (`minutes-secrets`: `database-url`, `auth-secret`; `minutes-oauth`, optional) via `secretKeyRef`/`envFrom`, never hardcoded in a manifest or committed file. CI deploy credentials use short-lived AWS OIDC federation (`aws-actions/configure-aws-credentials` with `role-to-assume`), not long-lived access keys.

## What was asked for

- Move production secrets (database credentials, JWT signing key, OAuth client secrets, AWS SES/S3 credentials) into a proper secrets manager or, at minimum, environment variables injected at deploy time — never committed to the repo.
- Rotate the JWT signing key and database password away from whatever was used during development before any real user data exists.
- Different secrets per environment (local/staging/production) — no environment should be able to accidentally touch another's database or send email as another's identity.

## What's actually done vs. what's an operational follow-up

- **Done (structural):** no secret value lives in the repo; the manifests only reference Kubernetes Secret names, which are populated out-of-band.
- **Not verifiable from code, and not this doc's job to verify:** whether the `AUTH_SECRET`/database password currently populating `minutes-secrets` are actually rotated dev→prod values, distinct from whatever was used locally. That's a one-time operational action (rotate the values in the cluster), not a code change — worth confirming directly against the cluster rather than tracking as a spec.
- **Not done:** per-environment separation, since there is currently only one environment (`production`) — see [11 Staging environment](./11%20Staging%20environment.md). Until staging exists, "different secrets per environment" is moot; once it does, its secrets must be genuinely separate Kubernetes Secret objects/values, not the same ones reused.
