# Staging environment

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: code-complete; live activation pending.** Repository policy, environment-specific manifest rendering, and explicit production promotion are implemented and tested. The live GitHub Environments, required reviewers, credentials, infrastructure, Secrets, and first staging-to-production drill remain operator gates.

## Problem

A tested change still needs an isolated proving ground before it can reach real users. Automatic production deployment from a main-branch push cannot provide that boundary.

## Requirements

- Separate staging and production environments, so a bad deploy is caught before it reaches real users.

## Implemented behavior

- Pull requests and `feat/prd-completion` pushes run tests and non-pushing builds of both images. They have no deployment job.
- A successful `main` push can deploy only to the `staging` GitHub Environment, and only when the repository-level and environment-level enable flags are both set.
- `workflow_dispatch` from `main` is the only production trigger. It accepts an exact 40-character SHA through an environment variable rather than executable script interpolation, rejects any SHA without a successful `Deploy staging` job on `main`, and enters the `production` GitHub Environment so configured required reviewers can approve it.
- Staging builds and pushes SHA tags to immutable ECR repositories, deploys digest references, and records those exact references in an immutable run artifact. Production downloads that artifact from the validated staging run, verifies its SHA/digest fields, and deploys the exact references without rebuilding or resolving tags again.
- `deploy/render.sh` accepts only `staging`/`minutes-staging` or `production`/`minutes-production`, fails closed on missing settings, and renders all namespaced resources, Secret references, Sentry environment/release values, domains, IAM role, and cron schedules for that target.
- Each environment uses distinct `<namespace>-secrets`, `<namespace>-oauth`, and optional `<namespace>-observability` Secret names. GitHub Environment variables independently supply cluster, domain, certificate, database-adjacent access, storage bucket/prefix, email sender/IAM, and cron configuration.
- Per-environment concurrency groups prevent overlapping migrations or rollouts. A one-shot Alembic Job must complete before application manifests are applied and rollout waits begin.
- Policy tests render both targets, parse every Kubernetes document, assert namespace and Secret isolation, verify immutable-image and promotion rules, reject missing values, and prove migration ordering.

## Operator gates

Before claiming either environment is live, an operator must create and isolate its EKS/database/storage/IAM/domain resources, OAuth registrations and exact callbacks, SES sender, GitHub variables and Secrets. The ECR repositories must reject mutable tags. The `production` GitHub Environment must have required reviewers and restrict deployment branches to protected `main`. A staging smoke test and an approved promotion drill must verify the deployed SHA/digests and environment boundaries. None of those cloud or provider changes are performed by this repository commit.
