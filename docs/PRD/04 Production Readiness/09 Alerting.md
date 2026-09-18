# Alerting

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: not done.**

## Problem

Even though [07 - done - Health checks](./07%20-%20done%20-%20Health%20checks.md), [08 - done - Metrics](./08%20-%20done%20-%20Metrics.md), and [06 - done - Error tracking (Sentry)](./06%20-%20done%20-%20Error%20tracking%20%28Sentry%29.md) now exist in code, none of them notify anyone — collecting signals nobody looks at is only half the job.

## Requirements

- At minimum, an alert when the error rate spikes or the health check fails, sent somewhere a human will actually see it (email, Slack, etc.).

## Dependency note

This is the last piece of the observability chain, not the first — it uses [08 - done - Metrics](./08%20-%20done%20-%20Metrics.md) for error-rate data and needs [07 - done - Health checks](./07%20-%20done%20-%20Health%20checks.md)'s signal wired to something that can page (readiness-probe failures alone don't notify a human today, they just stop Kubernetes routing traffic). Sentry's own alerting (from [06 - done - Error tracking (Sentry)](./06%20-%20done%20-%20Error%20tracking%20%28Sentry%29.md)) can cover the error-spike case without needing a separate alerting service, but only if Sentry is actually configured and monitored.
