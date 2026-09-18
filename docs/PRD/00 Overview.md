# Meeting Notes App — PRD Overview

2026-09-17 · master index, added when the PRD folder was split into one-spec-per-file documents

This folder is organized roughly chronologically: the original brief, then the specs that followed it in the order they were written. Each numbered doc below is itself an index into a same-named subfolder of small, independently shippable spec files. A spec's filename carries `- done -` between its number and title once it's shipped, so status is visible from a file listing alone.

## 1. [Initial Draft](./01%20Initial%20Draft.md)

The original project brief — why this app exists, the original tech-stack open questions, all since resolved. Historical; not split further, kept whole as the starting point everything else built on.

## 2. [Auth & Registration Spec](./02%20Auth%20%26%20Registration%20Spec.md) — 6/6 done

Every in-scope item shipped: registration & email verification, login & sessions, forgot password, social login (Google/Facebook/Amazon), TOTP two-factor auth, account management. Sharing/roles were explicitly out of scope here and are tracked in item 3 instead.

→ `02 Auth and Registration/`

## 3. [Feature Roadmap (Post-MVP)](./03%20Feature%20Roadmap%20(Post-MVP).md) — 8/9 code-complete

Product depth: what's missing for this to feel like a product, not a demo. Action items, rich text formatting, search, pagination, soft delete, attachment previews, export, and notifications are code-complete; sharing/collaboration remains.

→ `03 Feature Roadmap/`

## 4. [Production Readiness Gaps](./04%20Production%20Readiness%20Gaps.md) — 9/15 code-complete

CI/CD, secrets management, health checks, backend/frontend tests, database migrations, S3-compatible attachment storage, structured logging, and opt-in backend/frontend error tracking are code-complete. Metrics, alerting, a staging environment, app-wide rate limiting, session management UI, and the legal pages required for social login to leave test mode remain. S3 cutover, production log aggregation, and live scrubbed Sentry ingestion are separate operator gates; code completion does not imply those provider or production activation gates have been cleared.

→ `04 Production Readiness/`

## Reading order for someone new to this project

1. Skim `01 Initial Draft.md` for why the app exists.
2. Treat `02 Auth & Registration Spec.md` as already-shipped reference material — read a linked file only if you need to know exactly how something like TOTP or social-account merging works.
3. Pick up work from `03 Feature Roadmap (Post-MVP).md` or `04 Production Readiness Gaps.md` depending on whether you're adding product depth or hardening what exists — both indexes list their items with status, so you can jump straight to an unclaimed one.
