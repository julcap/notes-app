# Frontend automated tests

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: code-complete.** Angular 20 Karma/Jasmine tests run in real ChromeHeadless locally and in CI. This repository status does not assert any unrelated live provider or production activation.

## Problem

The backend has solid coverage (see [01 - done - Backend automated tests](./01%20-%20done%20-%20Backend%20automated%20tests.md)), but every frontend component, service, and guard is currently verified by hand only.

## Requirements

- Component tests for `notes-workspace`, `auth-page`, and `account`.
- Service tests for the HTTP-calling logic in `auth.service.ts` and the inlined note-fetching logic in `notes-workspace.ts` (error handling, retry-on-401 behavior of `auth.interceptor.ts`).
- At minimum: the login/registration form validation in `auth-page.ts` and the meeting create/edit form validation in `notes-workspace.ts` need coverage — these are exactly the flows most likely to have an edge case someone didn't think of.

## Tooling decision

The project uses Angular 20's stable `@angular/build:karma` builder with Jasmine and real ChromeHeadless. Jest and Angular's experimental Vitest path were intentionally not introduced.

## CI enforcement

The test job installs the locked frontend dependencies, runs `npm run test:ci`, and only then runs the production build and backend suite. A frontend test failure therefore blocks the workflow.

## Implemented coverage

- Real component coverage for `notes-workspace`, `auth-page`, and `account`.
- HTTP coverage for `AuthService` and notes load/save errors.
- Guard and interceptor coverage, including one retry after a 401 and refresh deduplication across concurrent requests.
- Login and registration form validation, verified-email creation gating, meeting create/edit validation, and account confirmation flows.

## Known baseline gap

The imported action-item UI still sends `PATCH` and `DELETE /api/action-items/{id}` outside the interceptor's current `/api/notes` authorization scope. This suite does not claim that done-labelled flow passes end to end; its fix and integration coverage are tracked with the later sharing/authorization feature.
