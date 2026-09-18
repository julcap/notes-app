# Metrics

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: code-complete.** Bounded Prometheus request metrics are implemented and disabled by default. No live scraper or monitoring backend is implied by repository completion.

## What shipped

- `backend/app/metrics.py` records `http_requests_total` and `http_request_duration_seconds` for completed HTTP requests.
- The only labels are bounded method, FastAPI route template, and status. Standard HTTP methods retain their names while extension methods collapse to `OTHER`; dynamic path values, query strings, headers, users, note IDs, and request or response bodies never become labels. Requests that do not match a route use the fixed `/unmatched` label.
- `GET /metrics` returns 404 unless `METRICS_ENABLED=true`. When enabled, every scrape requires an `Authorization` header using the Bearer scheme and configured token; an unset, missing, or incorrect token is denied with 401 and compared using `secrets.compare_digest`.
- `/api/health` and `/metrics` are excluded from request metrics so health probes and scrape traffic do not distort business latency or error-rate calculations.
- The public frontend Nginx server explicitly returns 404 for `/metrics`. The application ingress routes only to that frontend, while an approved in-cluster scraper can call the private `backend` ClusterIP service on port 8000.
- Focused tests cover success, unmatched 404, unhandled 500, histogram and counter exposition, disabled and bearer-token access, sensitive-value/cardinality bounds, health/scrape exclusions, deployment non-exposure, and concurrent increments.

## Operations

Metrics use an in-process Prometheus registry. Run one Uvicorn worker per pod, as the checked-in container does, and sum the same labeled series across backend pods in Prometheus. There is no undocumented Python multiprocess collector or shared counter directory.

To enable a deployment, an operator must first store a non-empty `metrics-token` key in the optional `<namespace>-observability` Kubernetes Secret, configure an internal scraper to send that bearer token to `http://backend.<namespace>.svc.cluster.local:8000/metrics`, and then set the protected GitHub environment variable `METRICS_ENABLED=true`. Local Compose accepts the same variables from an uncommitted `.env` file. Keep metrics disabled if no private scraper is configured.

## Not covered by this file

Installing or operating Prometheus, creating dashboards, and delivering alerts to a human remain environment/operator work. Tested thresholds and receiver templates are code-complete in [09 - done - Alerting](./09%20-%20done%20-%20Alerting.md), but live activation and confirmed receipt remain operator-gated.

## Fixed 2026-09-18: test harness gap

`backend/tests/test_metrics.py::test_public_frontend_denies_metrics_and_backend_configuration_is_private` was silently failing in every run, local and CI, with a `FileNotFoundError` rather than actually asserting anything: it computes the repo root as `Path(__file__).resolve().parents[2]`, which resolves to `/` inside the test container since `compose.test.yaml`'s `tests` service builds only from `./backend`, and `frontend/nginx.conf` was never mounted there. Fixed by adding explicit read-only volume mounts in `compose.test.yaml` for the specific repo-root files that test reads (`frontend/nginx.conf`, `deploy/ingress.yaml`, `deploy/app.yaml`, `compose.yaml`, `.github/workflows/ci.yaml`), at the container-root paths the existing path logic already expects — no change to the test itself or the backend build context. The full backend suite now passes 106/106; this test's nginx/ingress/bearer-token assertions actually run instead of erroring out before reaching them.
