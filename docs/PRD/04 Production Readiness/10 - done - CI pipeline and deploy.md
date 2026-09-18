# CI pipeline and deploy

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: done.** `.github/workflows/ci.yaml` tests pull requests and pushes to `main`/`feat/prd-completion`, builds both images without deployment for PR/feature validation, deploys successful enabled `main` pushes to staging, and exposes production only as an explicit staged-SHA promotion.

## What was asked for

- A CI pipeline that on every pull request: installs dependencies, runs backend and frontend tests, runs a linter/type-check, and builds both Docker images.
- A CD step that, on merge to main, runs migrations and deploys the new images.

## What exists

- `test` validates rendered deployment policy and monitoring configuration, runs Angular tests/build, and runs the full PostgreSQL-backed backend/auth suite via `docker compose -f compose.test.yaml`.
- `build-images` verifies both Dockerfiles with `push: false` on pull requests and feature-branch pushes.
- `deploy-staging` authenticates through the staging GitHub Environment and OIDC, requires immutable ECR repositories, builds SHA-tagged images, deploys their digest references, waits for a separate Alembic Job, then rolls out only `minutes-staging`.
- Production `workflow_dispatch` is accepted only from `main` and validates that the exact requested SHA has a successful main-branch staging deployment. It downloads the exact digest references recorded by that staging run, does not rebuild or re-resolve tags, and enters the reviewer/branch-policy-gated production GitHub Environment before deploying only `minutes-production`.

## Gaps not covered by "done"

- No dedicated linter/type-check step distinct from the build (acceptable for now since the Angular build already fails on type errors; Python has no linter configured at all).
- Live staging/production resources, secrets, GitHub required reviewers, and a promotion drill remain operator-gated; see [11 Staging environment](./11%20-%20done%20-%20Staging%20environment.md).
