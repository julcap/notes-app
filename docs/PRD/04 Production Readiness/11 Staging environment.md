# Staging environment

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: not done.** `.github/workflows/ci.yaml`'s `deploy` job targets a single `production` GitHub environment; there is no staging counterpart.

## Problem

Every merge to `main` that passes tests deploys straight to production (see [10 - done - CI pipeline and deploy](./10%20-%20done%20-%20CI%20pipeline%20and%20deploy.md)). A bad deploy — one that passes tests but breaks in ways tests don't catch — reaches real users with nothing in between.

## Requirements

- Separate staging and production environments, so a bad deploy is caught before it reaches real users.

## Implementation notes

- The existing `deploy` job's structure (build → push to ECR → apply `deploy/` manifests → wait for rollout) generalizes to a second environment reasonably easily: a second GitHub environment (`staging`) with its own `vars`/secrets (separate `EKS_CLUSTER`, `APP_DOMAIN`, database, and OAuth app registrations — see [12 - done - Secrets management](./12%20-%20done%20-%20Secrets%20management.md)'s point about no environment touching another's data), deployed automatically on every merge to `main`, with production requiring a manual promotion step (GitHub Environments' required-reviewers feature is a natural fit, since the pipeline already deploys via environment-scoped jobs).
- This needs its own EKS namespace or cluster, its own database, and — per [04 - done - Social login](../02%20Auth%20and%20Registration/04%20-%20done%20-%20Social%20login%20%28Google%2C%20Facebook%2C%20Amazon%29.md) — its own OAuth app registrations with staging's callback URLs, since providers require exact redirect URL matches per app.
