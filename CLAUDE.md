# CLAUDE.md

Coding standards for this repo live in [`AGENT.md`](AGENT.md) — read that first; it applies here too. This file only adds notes specific to working in this repo with Claude Code.

## Project

Portfolio project: Angular 20 (standalone components) frontend, FastAPI/SQLAlchemy/PostgreSQL backend, deployed to a self-managed EKS cluster via GitHub Actions. It's also how the owner is learning Angular, so prefer idiomatic, current framework patterns over clever shortcuts.

## Commands

```sh
# Run the full local stack (frontend on :8080, Mailpit inbox on :8025)
docker compose up --build -d

# Backend/auth test suite (isolated Postgres + mocked email)
docker compose -p minutes-tests -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -p minutes-tests -f compose.test.yaml down

# Frontend build (needs Node 20.19+/22.12+; if the host Node is too old, build inside a container)
cd frontend && npm run build
# or: docker run --rm -v "$PWD":/app -w /app node:24-alpine sh -c "npm ci && npm run build"
```

## Verifying changes

- After any backend change: run the test suite above.
- After any change touching `auth/`: also do a live check against the running stack — register, grab the verification link from Mailpit (`http://localhost:8025/api/v1/messages`), verify, confirm note creation is gated correctly before/after. Delete any test accounts/notes created this way afterward (`docker compose exec database psql -U minutes -d minutes -c "..."`).
- After any frontend structural change: confirm `npm run build` succeeds and the bundle size hasn't meaningfully regressed, then rebuild the frontend container and hit it with curl or a browser.
- Prefer this over static review alone — this project's own history includes a case where email delivery worked in tests but the interactive flow had never actually been exercised end-to-end.

## Working notes

- The owner often has PhpStorm open on this repo at the same time and it auto-formats/auto-commits on save. A "file changed on disk" notice for a file you just wrote is almost always that, not a conflict — take the on-disk version as current rather than re-imposing your own formatting.
- Browser automation (Claude in Chrome) has been flaky in this environment (tab-group tracking loses the active tab mid-session). If it fails 2–3 times in a row, fall back to curl-based verification against the running stack instead of retrying the browser repeatedly.
- Don't commit or push unless explicitly asked, even after a large refactor — see `AGENT.md`.
