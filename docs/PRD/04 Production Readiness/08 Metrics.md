# Metrics

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: not done.** No request-level metrics are collected anywhere in the stack.

## Problem

There's currently no way to answer "is the API slow" or "which endpoint is erroring more than usual" without reading raw logs by hand — and until [05 Structured logging](./05%20Structured%20logging.md) exists, not even that.

## Requirements

- Track basic request metrics: latency and error rate per endpoint. Doesn't need to be elaborate, but zero visibility isn't sustainable once real users depend on this.

## Implementation notes

- A Prometheus-style `/metrics` endpoint (via `prometheus-fastapi-instrumentator` or similar) is the standard fit for an app already running on Kubernetes — scraping doesn't require standing up a separate metrics pipeline if the cluster already runs Prometheus, and if it doesn't, that's a cluster-level decision outside this app's scope.
- Middleware-based timing (wrap the existing `private_responses` middleware in `backend/app/main.py`, or add a sibling one) is the least invasive way to capture per-request latency without touching every route.
