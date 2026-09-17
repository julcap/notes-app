# Verification

Running record of what's actually been checked, and against what. Everything below is dated 2026-09-17.

## Auth & registration feature

- PostgreSQL integration suite: **16 passed**, 3 dependency deprecation warnings.
- Coverage: existing note/file operations, required authentication, ownership isolation, bcrypt policy, duplicate local registration, verification gating/reuse/expiry/resend, generic recovery response, password reset, immediate session revocation, CSRF rejection, refresh rotation, logout, remember-me cookie lifetime, rate limiting, social identity merging/separation, and invalid OAuth state.
- Final Angular production build: passed, 379.50 kB initial bundle (estimated transfer 99.68 kB).
- Updated Docker services built and started successfully. Existing pre-auth local notes preserved without assigning them to a new account.
- Browser checked: protected-route redirect, login page, registration fields, disabled empty submission, recovery navigation, and registration visual layout.
- Signed-in flow verified end-to-end against the running dev stack: registered a local account via `/api/auth/register` (`email_verified: false`); confirmed `/api/notes` creation is rejected with 403 until verified; retrieved the verification email from Mailpit's REST API and consumed the token via `/api/auth/verify-email` (`email_verified` flips to `true`); note creation then succeeds (201); reusing the consumed verification token correctly returns 400; ran `/api/auth/forgot-password` → `/api/auth/reset-password` using the reset email from Mailpit; confirmed the old password is rejected and the new one logs in; confirmed the pre-reset refresh-token cookie is revoked (401 on `/api/auth/refresh`), matching the "reset revokes all sessions" behavior. Test account and its data were deleted afterward.
- In-browser UI walkthrough of the same signed-in flow (clicking through register → Mailpit → verify → create note) was attempted but not completed due to Claude-in-Chrome tab-group instability (tool repeatedly lost track of the active tab); the flow was instead verified directly against the same API the UI calls, exercising identical code paths.
- Local inbox service: Mailpit at http://localhost:8025. Production mail adapter: AWS SES.
- Setup decisions and operational limitations are documented in AUTH.md.

## Backend package refactor (`auth.py`/`main.py` → `auth/`, `notes/` packages)

- Same PostgreSQL integration suite re-run after the split: **16 passed**, same 3 deprecation warnings — no behavior change from the reorganization.
- Byte-compiled every backend `.py` file (`python -m py_compile`) to catch import/syntax errors from the move.
- Rebuilt and restarted the full dev stack; `/api/health` returned 200 and backend logs showed a clean startup with no import errors.
- Live smoke test against the running stack: register → fetch verification token from Mailpit → verify → create a note via the exact `/api/notes` route path (no trailing slash) → list notes — all succeeded with the refactored routers, matching pre-refactor behavior. Test account and note deleted afterward.
- Test suite internals were updated to match the new module layout (`conftest.py`'s `monkeypatch` target moved from `auth.send_email` to `auth.email.send_email`, matching where that function actually lives now) rather than adding compatibility re-exports.

## Frontend restructuring (flat `src/*.ts` → `src/app/` feature folders)

- `npm run build` (production) succeeded: 379.56 kB initial bundle, 99.69 kB estimated transfer — effectively unchanged from the pre-refactor 379.50 kB/99.68 kB (the difference is source reformatting noise, not new code).
- Rebuilt the frontend Docker image and restarted the stack; `/`, `/login`, and `/api/health` all returned 200, and the served page's hashed stylesheet/script filenames matched the fresh build output (confirming the running container wasn't serving a stale bundle).
- Full-stack API round-trip re-checked after the restructuring (register + `/api/auth/me`) to confirm the backend was unaffected; test account deleted afterward.
- Did not complete an in-browser click-through of the restructured pages — Claude-in-Chrome hit the same tab-group instability as during the auth-feature verification. Relied on the build passing plus the API-level check instead.

## SCSS conversion (`styles.css` → `styles.scss`)

- Confirmed no component had inline `styles`/`styleUrls` or template `<style>` blocks to migrate — all global styles were already consolidated in one file, so the change was a pure rename plus `angular.json` update (`styles: ["src/styles.scss"]`, added `inlineStyleLanguage: "scss"`).
- `npm run build` succeeded with an identical bundle: same 379.56 kB / 99.69 kB, same `styles-ELI6AKEF.css` output hash as the prior build, confirming the SCSS compile produced byte-identical CSS output.
- Rebuilt the dev stack; confirmed the served page references that same fresh stylesheet hash.

## Known unverified items

- Live AWS SES delivery, live OAuth consent/token exchange with real Google/Facebook/Amazon provider accounts, and live EKS/GitHub Actions deployment remain unverified until real credentials/infrastructure are configured (local testing uses Mailpit for email and an unconfigured-provider/forged-state path for OAuth error handling).
- No in-browser (as opposed to API-level) verification exists yet for the post-refactor auth or notes UI, due to repeated Claude-in-Chrome tool instability in this environment across multiple attempts.
