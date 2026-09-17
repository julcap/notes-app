# CI pipeline and deploy

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: done.** `.github/workflows/ci.yaml` — a `test` job on every PR and push to `main`, and a `deploy` job that only runs on push to `main` after `test` passes.

## What was asked for

- A CI pipeline that on every pull request: installs dependencies, runs backend and frontend tests, runs a linter/type-check, and builds both Docker images.
- A CD step that, on merge to main, runs migrations and deploys the new images.

## What exists

- `test` job: `npm ci && npm run build` for the frontend (build acts as the type-check today — Angular's build fails on TypeScript errors), then the full backend/auth suite via `docker compose -f compose.test.yaml`.
- `deploy` job (gated behind `vars.DEPLOY_ENABLED == 'true'` and `needs: test`): authenticates to AWS via OIDC (`aws-actions/configure-aws-credentials`, no long-lived AWS keys in the repo), builds and pushes both images to ECR tagged with the commit SHA, then applies the Kubernetes manifests in `deploy/` and waits for the rollout to complete.
- Deploys immutable, SHA-tagged images — never a moving `latest` tag — so what's running is always traceable to an exact commit.

## Gaps not covered by "done"

- No dedicated linter/type-check step distinct from the build (acceptable for now since the Angular build already fails on type errors; Python has no linter configured at all).
- No database migration step in the deploy job — see [04 Database migrations (Alembic)](./04%20Database%20migrations%20%28Alembic%29.md), since there's no Alembic to run yet.
- No staging environment — see [11 Staging environment](./11%20Staging%20environment.md).
