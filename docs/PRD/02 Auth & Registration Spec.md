# Meeting Notes App — Auth & Registration Spec

2026-09-17 · @Someone · split 2026-09-17 into `02 Auth and Registration/` for one-spec-at-a-time tracking

Adds user registration, email/password authentication, forgot-password recovery, social login via Google/Facebook/Amazon, optional TOTP two-factor authentication, and account management to the meeting notes app.

## Overview & scope

Before this spec, the app had no concept of a user: any visitor could see, create and delete all meetings. This work adds accounts so meetings belong to the person who created them, plus four ways to sign in.

**Out of scope for this spec** (tracked in the Feature Roadmap folder instead): sharing a meeting with other users / team workspaces, roles or permissions beyond "owner" — see [09 Sharing and collaboration](./03%20Feature%20Roadmap/09%20Sharing%20and%20collaboration.md).

## Status: all in-scope items shipped

Every item below is implemented end to end (backend route + data model + frontend UI), verified against the running stack. See each linked file for the specific endpoints and files involved.

1. ✅ [Registration and email verification](./02%20Auth%20and%20Registration/01%20-%20done%20-%20Registration%20and%20email%20verification.md)
2. ✅ [Login and sessions](./02%20Auth%20and%20Registration/02%20-%20done%20-%20Login%20and%20sessions.md)
3. ✅ [Forgot password recovery](./02%20Auth%20and%20Registration/03%20-%20done%20-%20Forgot%20password%20recovery.md)
4. ✅ [Social login (Google, Facebook, Amazon)](./02%20Auth%20and%20Registration/04%20-%20done%20-%20Social%20login%20%28Google%2C%20Facebook%2C%20Amazon%29.md)
5. ✅ [Two-factor authentication (TOTP)](./02%20Auth%20and%20Registration/05%20-%20done%20-%20Two-factor%20authentication%20%28TOTP%29.md)
6. ✅ [Account management](./02%20Auth%20and%20Registration/06%20-%20done%20-%20Account%20management.md)

## What's not covered here

This spec is about *this app having accounts*, not about the app being safe to run at scale with those accounts — rate limiting beyond auth, session-revocation UI, and the legal pages required for the OAuth providers to leave test mode are tracked in `04 Production Readiness/`, not here.
