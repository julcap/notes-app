# Error tracking (Sentry)

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: not done.** No error-monitoring SDK is wired into either the backend or the frontend.

## Problem

Unhandled exceptions currently just 500 (backend) or fail silently in the console (frontend) — there's no stack trace capture, no alert, and no way to know how often a given error happens without a user reporting it.

## Requirements

- Wire up an error monitoring service (e.g. Sentry) on both backend and frontend, so unhandled exceptions are captured with a stack trace and enough context to reproduce.

## Implementation notes

- Backend: FastAPI has a documented Sentry ASGI integration; add it in `backend/app/main.py` alongside the existing middleware stack. Scrub auth headers/cookies from captured request context — the refresh-token cookie and `Authorization` header should never reach Sentry.
- Frontend: Sentry's Angular SDK hooks into `ErrorHandler`; register it in `frontend/src/app/app.config.ts` (or wherever providers are configured).
- Depends on nothing else in this folder — can be added independently of [05 Structured logging](./05%20Structured%20logging.md), though the two are natural to roll out together since both need the same "never log secrets" discipline.
