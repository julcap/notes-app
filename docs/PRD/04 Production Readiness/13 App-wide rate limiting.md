# App-wide rate limiting

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: partially done.** Auth-specific rate limiting already shipped as part of the Auth spec (`limit()` in `backend/app/auth/security.py`, backed by a Postgres counter table so it works across replicas — applied to register, login, `login/2fa`, forgot-password, and each OAuth provider's login redirect; see the individual files in `02 Auth and Registration/`). What's covered here is everything else: the meetings, search, and attachment endpoints have no rate limiting at all.

## Problem

Nothing currently protects `/api/notes/*` from abuse — scraping, storage exhaustion via repeated uploads, or an accidental infinite-retry loop in a client.

## Requirements

- Apply a general rate limit per user (or per IP for unauthenticated requests) across the whole API, in addition to the tighter, auth-specific limits already in place.

## Implementation notes

- The existing `limit()` helper (Postgres-backed, works across workers/replicas without needing Redis) generalizes directly — it just isn't called from `backend/app/notes/routes.py` yet. The simplest version is a dependency applied to the whole notes router rather than auth's per-endpoint calls with tighter, hand-picked thresholds.
- A reverse proxy or API gateway layer (nginx rate limiting, or a library like `slowapi` for FastAPI) is worth considering instead of extending the hand-rolled Postgres approach, if the per-request database round-trip `limit()` currently does becomes a concern at higher request volume than the auth endpoints see.
