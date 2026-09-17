# Coding standards

Tool-agnostic conventions for this repo. Any AI coding agent working here should follow these. Claude Code also reads `CLAUDE.md` for a few Claude-specific operational notes on top of this.

## Structure: split by concern, not by size

Organize code into small, single-responsibility files grouped into feature/domain packages — don't chase a line-count target, chase "this file answers one question."

**Backend (FastAPI)** — one package per domain (`backend/app/auth/`, `backend/app/notes/`), each split the same way:
- `models.py` — SQLAlchemy models only
- `schemas.py` — Pydantic request/response shapes
- `security.py` / equivalent — hashing, validation, rate limiting: pure defensive helpers
- `tokens.py` / session logic — anything issuing or checking a session/credential
- `email.py` (or other external-integration files) — side-effecting calls to third parties
- `routes.py` — HTTP endpoints, kept thin; business logic lives in the files above, not inline in route handlers
- a shared `router.py` when more than one routes file needs the same `APIRouter` instance (e.g. local auth routes + OAuth routes both register onto `auth/router.py`)
- `__init__.py` re-exports only what other packages actually import — not everything defined inside

**Frontend (Angular)** — standard `src/app/` layout, feature folders mirroring backend domains:
- `app.config.ts` (providers) + `app.routes.ts` (routes) instead of inline bootstrap config in `main.ts`
- `main.ts` is bootstrap only — no components, no routes, no providers defined inline
- one concern per file: a service, a guard, and an interceptor never share a file even if small
- models/interfaces live in dedicated `*.model.ts` files, imported by whatever needs them — not redeclared per-component
- a route guard specific to one component's own state (e.g. an unsaved-changes check) is co-located next to that component; a cross-cutting guard (e.g. auth) gets its own top-level file

**Both sides**: keep `main.py`/`main.ts` as thin wiring only. If a "main" file has business logic in it, something hasn't been split out yet.

## Don't over-split

DRY beats "one file per route." A single parametrized component/handler serving several near-identical variants (e.g. one Angular component driving login/register/forgot-password/reset/verify off a route `data` param) is preferred over duplicating near-identical files just to get a 1:1 file-to-route mapping. Split when responsibilities actually differ; don't split when it would just copy-paste the same shape six times.

## Naming

- Drop a type suffix when the surrounding convention already implies it (Angular: component classes/files skip `Component` — `App`, `AuthPage`, `notes-workspace.ts`, matching the current Angular style guide). Keep suffixes that carry real information (`AuthService`, `auth.guard.ts`, `auth.interceptor.ts`).
- kebab-case filenames, PascalCase classes/components, camelCase functions and variables, snake_case for Python.
- When an existing file/module already established a naming convention, match it instead of defaulting to a generic one — consistency with the surrounding code wins over a "more standard" alternative.

## Comments and docs

- No docstrings, no comment blocks explaining what code does — names should do that.
- A comment is only for the non-obvious WHY: a security rationale, a workaround for a specific constraint, a subtle invariant. Example already in this codebase: `# Shared PostgreSQL counters work across workers. Never trust arbitrary X-Forwarded-For.`
- Keep `README.md`'s architecture/file-map section in sync whenever files move or get restructured.

## Refactors must be behavior-preserving

- When splitting or reorganizing existing working code, change structure only — no drive-by logic fixes, no "while I'm here" improvements, unless that's explicitly the task.
- Update tests' internal wiring (import paths, monkeypatch targets) to match a new file layout rather than adding re-exports or compatibility shims just to avoid touching test files.
- After any structural refactor: re-run the existing automated test suite, then also do a live smoke test against the running stack (register/verify/CRUD, whatever the change touches) — passing tests alone is necessary but not sufficient. Clean up any test data created during manual verification afterward.

## Security posture (don't relax incidentally)

This project treats auth as a first-class concern: bcrypt password hashing, CSRF double-submit tokens, httpOnly+Secure+SameSite refresh cookies, per-endpoint rate limiting, OAuth `state`/PKCE validation, no secrets ever in the frontend bundle. Any refactor touching `auth/` must preserve every one of these properties exactly — verify with the test suite (`compose.test.yaml`) plus a manual check, not just a read-through.

## Git

Don't commit or push unless explicitly asked — including after a large multi-file refactor. Leave changes in the working tree for review.
