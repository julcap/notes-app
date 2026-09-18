# Secrets management

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: done**, for the "not committed to the repo" core ask. `deploy/app.yaml` reads credentials from environment-scoped Kubernetes Secrets (`minutes-staging-*` or `minutes-production-*`) via `secretKeyRef`/`envFrom`, never hardcoded in a manifest or committed file. CI deploy credentials use short-lived, GitHub Environment-scoped AWS OIDC federation (`aws-actions/configure-aws-credentials` with `role-to-assume`), not long-lived access keys.

## What was asked for

- Move production secrets (database credentials, JWT signing key, OAuth client secrets, AWS SES/S3 credentials) into a proper secrets manager or, at minimum, environment variables injected at deploy time — never committed to the repo.
- Rotate the JWT signing key and database password away from whatever was used during development before any real user data exists.
- Different secrets per environment (local/staging/production) — no environment should be able to accidentally touch another's database or send email as another's identity.

## What's actually done vs. what's an operational follow-up

- **Done (structural):** no secret value lives in the repo; the manifests only reference Kubernetes Secret names, which are populated out-of-band.
- **Not verifiable from code, and not this doc's job to verify:** whether the `AUTH_SECRET`/database passwords that will populate `minutes-staging-secrets` and `minutes-production-secrets` are rotated, distinct values. That is an operational action worth confirming directly against each cluster.
- **Done (repository boundary):** [staging isolation](./11%20-%20done%20-%20Staging%20environment.md) renders different namespaces and Secret names and obtains all environment settings through separate GitHub Environments. Live Secret values, IAM boundaries, databases, storage prefixes, and sender identities still must be created and verified independently by an operator.
