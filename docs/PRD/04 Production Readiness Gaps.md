# Meeting Notes App — Production Readiness Gaps

2026-09-17 · @Someone · split 2026-09-17 into `04 Production Readiness/` for one-spec-at-a-time tracking

Infrastructure and operational gaps that make the app unsafe to run in production, independent of any new product features. Companion to the Feature Roadmap doc, which covers product depth instead.

## Overview

"Production ready" here means safe to run with real users and real data, independent of which features exist. An app with every feature in the roadmap doc but none of these fixed is still not production ready — these are about not losing data, not leaking secrets, and knowing when something breaks, not about what the app does.

Unlike the feature roadmap, most of these aren't optional or sequenced by user value — they're closer to blocking issues that happen to not be visible yet because nothing has gone wrong. A rough grouping, unchanged from the original doc:

- **Would cause data loss or an outage:** object storage, database migrations
- **Would go unnoticed until a user complains:** structured logging, error tracking, metrics, alerting
- **Would block or slow down shipping safely:** frontend tests, staging environment
- **Would block launch entirely:** app-wide rate limiting, legal pages (blocks social login leaving test mode)
- **Would erode trust once discovered:** session management UI

The import audit corrected the baseline to 4 of 15 completed items: backend tests, health checks, CI/deploy code, and secrets management. Frontend automated tests are now the fifth code-complete item. Remaining entries still distinguish repository implementation from any later live provider or production activation gate.

## Items, in the original doc's section order

1. ✅ [Backend automated tests](./04%20Production%20Readiness/01%20-%20done%20-%20Backend%20automated%20tests.md)
2. ✅ [Frontend automated tests](./04%20Production%20Readiness/02%20-%20done%20-%20Frontend%20automated%20tests.md) — code-complete; Karma/Jasmine runs in real ChromeHeadless and blocks CI
3. ⬜ [Object storage for attachments](./04%20Production%20Readiness/03%20Object%20storage%20for%20attachments.md) — partially mitigated by a Kubernetes PVC, but still local-disk, still caps the backend to one replica
4. ⬜ [Database migrations (Alembic)](./04%20Production%20Readiness/04%20Database%20migrations%20%28Alembic%29.md) — corrects an inaccurate claim in the original doc; there's no Alembic in the repo at all, scaffolded or otherwise
5. ⬜ [Structured logging](./04%20Production%20Readiness/05%20Structured%20logging.md)
6. ⬜ [Error tracking (Sentry)](./04%20Production%20Readiness/06%20Error%20tracking%20%28Sentry%29.md)
7. ✅ [Health checks](./04%20Production%20Readiness/07%20-%20done%20-%20Health%20checks.md)
8. ⬜ [Metrics](./04%20Production%20Readiness/08%20Metrics.md)
9. ⬜ [Alerting](./04%20Production%20Readiness/09%20Alerting.md)
10. ✅ [CI pipeline and deploy](./04%20Production%20Readiness/10%20-%20done%20-%20CI%20pipeline%20and%20deploy.md)
11. ⬜ [Staging environment](./04%20Production%20Readiness/11%20Staging%20environment.md)
12. ✅ [Secrets management](./04%20Production%20Readiness/12%20-%20done%20-%20Secrets%20management.md)
13. ⬜ [App-wide rate limiting](./04%20Production%20Readiness/13%20App-wide%20rate%20limiting.md) — the auth-specific slice of this already shipped with the Auth spec
14. ⬜ [Session management UI](./04%20Production%20Readiness/14%20Session%20management%20UI.md)
15. ⬜ [Legal pages (privacy policy & ToS)](./04%20Production%20Readiness/15%20Legal%20pages%20%28privacy%20policy%20and%20ToS%29.md)

## Working with this folder

- Each file is self-contained: problem, requirements, and implementation notes referencing the actual current code — no need to read the others to start one.
- When a spec ships: rename its file to insert `- done -` between the number and title, flip its status line and this index's marker.
- Several items here are prerequisites for others (metrics before alerting, Sentry/logging before either is very useful, staging before secrets-per-environment is meaningful) — each file's own "not covered by this file" / dependency notes say which.
