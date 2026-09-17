# Legal pages (privacy policy & ToS)

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: not done.** No privacy policy or terms-of-service page exists in the frontend.

## Problem

Google, Facebook, and Amazon all require a live privacy policy (and typically terms of service) before their OAuth consent screens can leave test mode. Facebook additionally requires a completed app review to serve real users past a small testing allowlist. Social login (see [04 - done - Social login](../02%20Auth%20and%20Registration/04%20-%20done%20-%20Social%20login%20%28Google%2C%20Facebook%2C%20Amazon%29.md)) is fully implemented but effectively unusable by anyone outside a developer allowlist until this exists.

## Requirements

- A privacy policy covering what's collected (email, meeting content, attachments) and how it's used.
- Terms of service.
- Both linked from registration and account settings.

## Why this isn't optional scope

This is a hard blocker on social login actually working for anyone beyond a handful of test accounts — it needs to exist before the Google/Facebook/Amazon OAuth apps are submitted for production review, not as a nice-to-have after launch.

## Implementation notes

Static content pages — no backend work needed, just new routes/components in `frontend/src/app/` (e.g. `/privacy`, `/terms`) linked from `auth-page.html`'s registration form and `account.html`.
