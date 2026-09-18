# Error tracking (Sentry)

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: code-complete; local live ingestion verified 2026-09-18.** Backend FastAPI and frontend Angular exception capture are implemented and disabled unless their separate DSNs are explicitly configured. A real scrubbed event was sent through the backend's actual `initialize_error_tracking()` code path (not a synthetic test) using a DSN configured in the local, gitignored `.env`, and Sentry's ingest endpoint returned `200` for it; the frontend container's `/runtime-config.js` was confirmed to serve the same DSN correctly. Production Kubernetes DSN configuration and its own live-ingestion check remain a separate operator action — this verification covered local/dev only.

## What shipped

- `backend/app/error_tracking.py` initializes `sentry-sdk` with the FastAPI integration only when `SENTRY_DSN` is non-empty.
- `frontend/src/app/error-tracking.ts` registers Sentry's Angular `ErrorHandler` only when the public runtime `FRONTEND_SENTRY_DSN` is valid and non-empty.
- The frontend container writes `/runtime-config.js` at startup, so environment, release, and public browser DSN can change without rebuilding the Angular bundle. The backend DSN is never exposed to the frontend.
- Both SDKs disable default PII, tracing, profiling, replay, and log forwarding.
- Backend and frontend `beforeSend`/breadcrumb allowlists reconstruct the complete outgoing event. They retain exception type, scrubbed filename/function/line stack frames, release/environment, and a validated request ID where available. They drop request URLs, query strings, fragments, headers, cookies, bodies, users, email/IP values, raw note IDs/content, exception messages, breadcrumb messages/data, arbitrary contexts, and extras.
- Backend initialization includes the FastAPI SDK integration. Frontend initialization uses the Angular SDK's `createErrorHandler` provider.
- No permanent crash/debug endpoint exists. Tests use thrown exceptions, an in-memory backend transport, and fake frontend initialization callbacks.

## Configuration

- Backend: `SENTRY_DSN`, optionally `SENTRY_ENVIRONMENT` and `SENTRY_RELEASE`.
- Frontend: separate public `FRONTEND_SENTRY_DSN`, optionally the same non-secret environment/release labels.
- Empty DSNs are the default and perform no SDK initialization or telemetry network activity.
- Kubernetes reads the backend DSN from the optional `<namespace>-observability/sentry-dsn` Secret. The frontend DSN is a public GitHub environment variable rendered into container runtime configuration.

## Verification boundary

Automated tests verify disabled behavior, configured exception capture with a stack, full-payload and breadcrumb sentinel redaction, Angular provider/runtime wiring, and absence of a crash endpoint. One real scrubbed-event inspection has now been performed locally (see status line above): the exact `beforeSend` allowlist logic ran unmodified against a live captured exception, confirming the scrubbing pipeline behaves in practice as the unit tests assert in isolation. Production DSNs, provider projects, alert delivery, retention, and access control in the deployed cluster remain operator-controlled and unverified. Code completion, and even a successful local ingestion check, do not mean production monitoring is active.
