# Health checks

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: done.** `GET /api/health` (`backend/app/main.py`) executes `SELECT 1` against the real database connection, not just a process-liveness check.

## What was asked for

The original doc noted `/api/health` "only checks that the process is up, not that it can reach the database" and asked for a real dependency check. That gap is closed — a database outage now fails the health check rather than the endpoint reporting healthy while every real request 500s.

## Wired into deployment

`deploy/app.yaml`'s backend `readinessProbe` hits `/api/health`, so Kubernetes stops routing traffic to a backend pod that can't reach Postgres, rather than serving errors from it.

## Not covered by this file

Request-level metrics (latency and status counters) are code-complete in [08 - done - Metrics](./08%20-%20done%20-%20Metrics.md). [09 - done - Alerting](./09%20-%20done%20-%20Alerting.md) now provides a tested synthetic `/api/health` failure rule, while live monitoring deployment and confirmed human delivery remain operator-gated.
