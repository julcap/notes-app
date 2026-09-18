# App-wide rate limiting

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: done.** The complete `/api/` business surface now has PostgreSQL-backed shared limits. Health and private metrics remain outside those buckets so probes cannot be starved.

## Shipped behavior

- Every non-health `/api/` request consumes one shared one-minute bucket: 120 requests for a valid access-token user, or 60 requests for the transport client IP when no valid session can be established. Multiple browser sessions and backend workers therefore share the same user bucket.
- Attachment uploads consume an additional 10-per-user-per-minute bucket. Note exports consume an additional 20-per-user-per-minute bucket.
- Existing auth endpoint limits remain separate and tighter, retaining their 15-minute IP buckets and thresholds.
- Atomic PostgreSQL transactions lock each shared bucket, take the database clock after any lock wait, and then increment or reset it across replicas. A rejected response is HTTP 429 with `Retry-After` equal to the remaining bucket lifetime, rounded up to a whole second.
- Expired rows are removed in bounded batches of 1,000 by `python -m app.jobs cleanup-rate-limits`. The deployment runs that command every five minutes by default, independently configurable through `RATE_LIMIT_CLEANUP_SCHEDULE`.
- An Alembic-managed expiry index keeps bounded cleanup from scanning and sorting the full counter table.

## Client IP trust boundary

Uvicorn proxy-header rewriting is disabled. Production ingress sends `/api` directly from the ALB to the backend, while the Nginx fallback overwrites inbound forwarding headers with its transport peer. The app only evaluates `X-Forwarded-For` when the direct backend peer belongs to an explicitly configured `TRUSTED_PROXY_IPS` IPv4/IPv6 address or CIDR list. It walks the chain from the trusted edge toward the client and selects the first untrusted address; malformed or entirely trusted chains fall back to the direct peer. Leaving the variable empty trusts no proxy and cannot be bypassed with a forged forwarding header.

Set `TRUSTED_PROXY_IPS` to the exact ALB source ranges for each environment after those ranges are known, excluding pod and service CIDRs. Overly broad ranges weaken the IP identity boundary; universal IPv4 or IPv6 ranges fail startup.

## Verification

PostgreSQL integration coverage exercises independent users and IPs, shared counters across sessions, simultaneous increments, window expiry and exact `Retry-After`, upload/export sub-limits, malformed bearer fallback, forged forwarding headers, bounded cleanup, and health-check bypass. Existing auth throttle coverage remains in the full backend suite.
