# Minutes — Meeting Notes

[![CI](https://github.com/julcap/notes-app/actions/workflows/ci.yml/badge.svg)](https://github.com/julcap/notes-app/actions/workflows/ci.yml)

A standalone meeting notes workspace built from `Meeting Notes App.md`: Angular frontend, Python/FastAPI backend, and PostgreSQL. Create, edit, search, and safely undo deleted notes; record meeting dates and attendees; upload, download, and remove attachments.

## Run locally

Install Docker Desktop, then from this directory:

```sh
# First installation only (keep .env private):
python3 -c "import secrets; print('AUTH_SECRET=' + secrets.token_urlsafe(48))" > .env
chmod 600 .env
docker compose up --build -d
```

Open http://localhost:8080 and create an account. Open the local development inbox at http://localhost:8025 to find the verification email, follow its link, and click **Verify email**. You can then create a note. Production mail uses AWS SES. See [AUTH.md](AUTH.md) for configuration and security details. Notes and uploads survive container restarts in named Docker volumes. `docker compose down` stops the app without deleting data; adding `-v` permanently removes local data.

The app starts empty intentionally. Search filters title, body, and attendees. The API also supports `GET /api/notes?q=keyword`. Owners can share a note with verified accounts as view-only or editable; editors can update note content, action items, and attachments, while deletion, scheduling, and sharing remain owner-only. Previous recipients are retained as an owner-specific contact list and are only re-added after explicit confirmation. Each note can be exported as UTF-8 Markdown or a Unicode PDF, including its action items. A note may also have an optional future scheduled time, separate from its historical meeting date. Verified users can explicitly opt in to configurable “meeting starting soon” reminders and Monday 09:00 UTC weekly digests from Account settings; both default off. Deleting a note starts a 15-second undo window; hidden notes and attachment bytes are retained for 30 days before the scheduled purge. Attachments have a 20 MB limit. Downloads remain forced by default; authenticated inline previews are limited to PNG, JPEG, GIF, WebP, and PDF files whose stored media type matches a verified byte signature. Attachment bytes use local storage by default or S3-compatible object storage when explicitly configured; PostgreSQL persists each new object's key while legacy local rows retain id-based lookup.

## Development

Use Node 24, Python 3.13, and PostgreSQL 17. With an accessible PostgreSQL database:

```sh
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/minutes'
export UPLOAD_DIR='./uploads'
export AUTH_SECRET='replace-with-a-random-secret-at-least-32-characters'
export APP_URL='http://localhost:4200'
export COOKIE_SECURE=false
export MAIL_MODE=smtp
export SMTP_HOST=localhost
export SMTP_PORT=1025
python -m app.init_db
uvicorn app.main:app --reload --no-proxy-headers
```

In another terminal:

```sh
cd frontend
npm ci
npm start
```

Run a local SMTP catcher on port 1025 for direct development (Compose Mailpit only publishes its UI by default). Open http://localhost:4200. The Angular development server proxies `/api` to port 8000. FastAPI's API documentation is at http://localhost:8000/docs when running the backend directly.

## Validation

```sh
docker compose -p minutes-tests -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -p minutes-tests -f compose.test.yaml down
cd frontend
npm ci
npm run build
```

Tests use a separate disposable PostgreSQL database. The test container upgrades it through Alembic before pytest; fixtures clear rows between tests without recreating schema. Migration coverage includes empty installs, validated adoption of populated current installs, ownerless pre-auth data preservation, drift rejection, repeated upgrades, and concurrent startup. Purge tests require actual PostgreSQL for advisory-lock coverage and temporary file storage. Never point migration, purge, or full Python tests at production.

## Architecture

Production browser → ALB (`/api` directly to FastAPI, `/` to Angular/Nginx) → PostgreSQL and an attachment store. Local Compose keeps Nginx as the `/api` reverse proxy.

- `frontend/src/main.ts`: bootstraps the standalone root component with `app.config.ts` (providers) and `app.routes.ts` (routes).
- `frontend/src/app/auth/`: `auth.service.ts` (session state), `auth.guard.ts`, `auth.interceptor.ts`, `user.model.ts`, `error-text.ts`/`password-policy.ts` (small shared helpers), and `auth-page/` (login/register/forgot/reset/verify/login-2fa — one parametrized page component driven by route `data.mode`, plus an inline 2FA-code step when a login response asks for one).
- `frontend/src/app/account/`: `account.ts`/`.html` and `session.model.ts` — the signed-in Account page (profile, password, active-session revocation, 2FA enrollment/disable, delete account).
- `frontend/src/app/shell/`: `nav-rail.ts`/`.html` — the sidebar navigation shared by the notes workspace and the Account page.
- `frontend/src/app/notes/`: `notes-workspace.ts`/`.html` (the meeting-notes UI) and `note.model.ts`.
- `frontend/src/app/error-tracking.ts`: opt-in Angular error capture, runtime public configuration, and payload/breadcrumb allowlisting.
- `frontend/src/styles.css`: shared responsive styling.
- `backend/app/main.py`: FastAPI app wiring (middleware, routers, health check, private metrics installation).
- `backend/app/observability.py`: allowlisted JSON logging, request-ID context/middleware, safe unhandled-error stacks, and identifier-free auth audit events.
- `backend/app/error_tracking.py`: opt-in FastAPI Sentry initialization and complete event/breadcrumb allowlisting.
- `backend/app/metrics.py`: opt-in bounded Prometheus counters/histograms and bearer-protected private exposition.
- `backend/app/rate_limits.py`: atomic PostgreSQL API/user/IP counters, upload/export sub-limits, accurate retry timing, and explicit trusted-proxy parsing.
- `monitoring/`: opt-in Prometheus scrape/rule templates, deterministic alert tests, Blackbox Exporter probe configuration, Alertmanager receiver template, and drill runbook.
- `backend/app/database.py`: SQLAlchemy engine, session factory, declarative base.
- `backend/app/storage.py`: local and S3-compatible attachment backends, deterministic object keys, and retryable quarantine/restore helpers used by routes, purge, and account deletion.
- `backend/app/storage_migrate.py`: dry-run-by-default, SHA-256-verified local-to-S3 attachment migration CLI with a JSON-lines retry manifest.
- `backend/app/auth/`: accounts, sessions and email — `models.py`/`schemas.py` (data), `security.py` (hashing, rate limiting, origin checks), `tokens.py` (JWTs, cookies, session metadata/dependencies, MFA challenges), `email.py` (SES/SMTP delivery), `totp.py` (TOTP secrets, QR codes, backup codes), `routes.py` (register/login/reset/verify/account/session management/2FA), `oauth.py` (Google/Facebook/Amazon).
- `backend/app/notes/`: meeting notes, sharing, and attachments — `models.py`/`schemas.py` (data), `permissions.py` (central owner/edit/view authorization), `sharing.py` (owner-managed collaborators and previous recipients), `attachments.py` (media-type normalization and byte-signature verification), `export.py` plus `assets/` (safe Markdown/PDF rendering and licensed DejaVu/Noto Unicode fonts), and `routes.py` (CRUD, export, 15-second undo, and file upload/download/preview).
- `backend/app/jobs.py` and `backend/app/notifications/`: internal scheduled-job CLI and notification delivery model/service. `purge-deleted`, `reminders`, and `weekly-digest` use PostgreSQL advisory locks; `cleanup-rate-limits` deletes at most 1,000 expired buckets per run; notification runs also persist unique delivery keys.
- `backend/app/migrations.py` and `backend/migrations/`: the Alembic upgrade entrypoint and immutable schema revisions. Every schema change must add a revision; `app.init_db` only runs `upgrade head`.
- `compose.yaml`: local application stack; only the frontend is published, on localhost.
- `deploy/`: EKS manifests.
- `.github/workflows/ci.yaml`: PR checks and main-branch deployment.

Notes are Markdown-formatted text rendered through an allowlisted sanitizer. File metadata and object keys are in PostgreSQL; file bytes use local storage by default or an explicitly configured S3-compatible bucket. Notes are private unless their owner creates a `view` or `edit` share, and every note/action-item/attachment/export route checks the same effective-permission helper. Email verification is required before creating notes and before an account can be selected for sharing. Access JWTs live in browser memory; refresh sessions use HttpOnly cookies. List/search is server-backed with PostgreSQL full-text indexing, stable paginated owned-and-shared results, totals, and a 50-note default page size. Soft-deleted notes are hidden immediately. Permanent deletion atomically quarantines bytes before the database commit, restores them on rollback, and lets the scheduled job retry any final local unlink or S3 delete that failed. Concurrent edits currently use last-save-wins. Back up the database and active attachment store together.

## Attachment storage

`STORAGE_BACKEND=local` is the default and uses `UPLOAD_DIR`. S3-compatible mode requires `STORAGE_BACKEND=s3` and `S3_BUCKET`; it accepts optional `S3_ENDPOINT_URL`, `S3_REGION` (falling back to `AWS_REGION`), and `S3_PREFIX`. boto3 uses ambient IAM credentials. Do not add access keys to manifests or source control.

Before changing an installation with existing local files, place attachment writes in maintenance mode and run `python -m app.storage_migrate` from a controlled process with both the old volume and S3 access. The command is dry-run by default; add `--apply` only after reviewing the JSON-lines manifest. It verifies size and SHA-256 before database cutover and preserves every source file. See `docs/PRD/04 Production Readiness/03 - done - Object storage for attachments.md` for the cutover and rollback checklist.

Local deployment remains one backend replica with the ReadWriteOnce PVC. After a successful migration, render the explicit S3 Kustomize overlay to remove backend/purge PVC mounts and enable two backend replicas:

```sh
kubectl kustomize deploy-s3 | envsubst | kubectl apply -f -
```

## Error tracking

Error tracking is disabled unless a DSN is explicitly configured. The backend reads the private `SENTRY_DSN`; the frontend reads the separate public `FRONTEND_SENTRY_DSN` at container startup through `/runtime-config.js`, so rebuilding the Angular bundle is unnecessary and no backend secret enters it. Both sides accept `SENTRY_ENVIRONMENT` and `SENTRY_RELEASE`. Tracing, profiling, replay, log forwarding, and default PII collection remain disabled. Allowlist hooks retain the exception type, scrubbed stack, release/environment, and safe request ID while dropping request URLs, query strings, fragments, headers, cookies, bodies, users, email/IP values, raw note identifiers/content, exception messages, breadcrumb messages, and breadcrumb data.

For local opt-in testing, set those variables in `.env`; leaving either DSN empty guarantees that side never initializes its SDK. Production backend configuration uses the optional `sentry-dsn` key in an environment-specific `<namespace>-observability` Kubernetes Secret. `FRONTEND_SENTRY_DSN` is a public GitHub environment variable. Do not add a debug crash route or real credentials to source control. A release is code-complete without live ingestion: an operator must separately approve configuration and verify one scrubbed event in the provider before claiming production monitoring is active.

## Request metrics

Request metrics are disabled unless `METRICS_ENABLED=true`. When enabled, the backend records `http_requests_total` and `http_request_duration_seconds` with only bounded `method`, FastAPI route template, and `status` labels; extension methods collapse to `OTHER`, unmatched routes collapse to `/unmatched`, and health/scrape traffic is excluded. `GET /metrics` requires a non-empty `METRICS_TOKEN` as a bearer token. The public Nginx frontend returns 404 for `/metrics`, and the ingress routes only to that frontend, so an approved scraper must use the private `backend` ClusterIP service.

Run one Uvicorn worker per pod and sum the same labeled series across backend pods in Prometheus. This repository does not configure Python multiprocess metrics. For production, create or update the optional `<namespace>-observability` Secret with a `metrics-token` key before setting the protected GitHub environment variable `METRICS_ENABLED=true`; leaving the flag false is the secure default. Installing the monitoring services and verifying delivery remain separate operator gates.

## API rate limits

PostgreSQL-backed counters protect every business endpoint under `/api/`: valid access-token users receive 120 requests per minute and unauthenticated or malformed-token requests receive 60 per transport IP. Uploads and exports also have per-user limits of 10 and 20 per minute. Existing tighter 15-minute auth throttles remain separate. Rejections return HTTP 429 with an accurate `Retry-After`; `/api/health` and the private `/metrics` endpoint do not consume business buckets. The scheduled `cleanup-rate-limits` job deletes at most 1,000 expired rows per run and defaults to every five minutes through `RATE_LIMIT_CLEANUP_SCHEDULE`.

Uvicorn proxy-header rewriting is deliberately disabled. The production ingress routes `/api` directly from the ALB to the backend; the Nginx fallback overwrites rather than passes through client-supplied forwarding headers. `X-Forwarded-For` is ignored unless the direct backend peer belongs to the optional `TRUSTED_PROXY_IPS` comma-separated IPv4/IPv6 address or CIDR list. Configure that variable with only the exact ALB source ranges, excluding pod and service CIDRs; leave it empty to trust no proxy. Universal ranges such as `0.0.0.0/0` and `::/0` fail startup because they would let arbitrary clients choose their IP bucket.

## Alerting

`monitoring/` provides disabled-by-default deployment templates for Prometheus, Blackbox Exporter, and Alertmanager. The rules page on a sustained 5xx ratio above 5% only when at least 20 requests occurred in five minutes, a real HTTP `/api/health` probe failure lasting two minutes, and private backend scrape failure lasting two minutes. The health probe and Prometheus `up` signal are deliberately separate: `probe_success` covers the external HTTP path and database-aware health response, while `up` only covers the metrics scrape path.

Alertmanager reads the human webhook URL from an out-of-band secret file, groups and repeats at 30-minute intervals, and sends resolved notifications. No receiver, provider, or monitoring deployment is activated by the application manifests. Follow [the monitoring activation and drill runbook](monitoring/README.md), validate with `promtool` and `amtool`, and complete an approved staging firing/recovery drill before claiming operational readiness. Repository tests prove rule logic and local delivery only; a real human receipt remains an external gate.

## EKS deployment

The repository defines two isolated deployment targets:

| Target | Trigger | GitHub environment | Kubernetes namespace |
| --- | --- | --- | --- |
| staging | successful push to `main`, when repository variable `STAGING_DEPLOY_ENABLED=true` and the environment variable `DEPLOY_ENABLED=true` | `staging` | `minutes-staging` |
| production | explicit `workflow_dispatch` with the exact SHA of a successful staging deployment | `production` | `minutes-production` |

Pull requests and pushes to `feat/prd-completion` run tests and build both container images with `push: false`; they cannot deploy. A main push can deploy only staging. Production has no push trigger: a dispatch must run from `main`, and the workflow rejects malformed SHAs and SHAs without a successful `Deploy staging` job on `main`. A successful staging job records its exact backend/frontend digest references in an immutable, run-scoped artifact retained for 30 days; older staged SHAs must be staged again before promotion. Production downloads that artifact from the validated staging run, verifies its SHA and digest forms, and checks out the exact commit; it never rebuilds or re-resolves tags. Both ECR repositories must reject mutable tags when staging publishes the images.

Create the `staging` and `production` GitHub Environments before enabling deployment. Configure production with required reviewers and restrict deployment branches to protected `main`, so the environment gate must approve every eligible dispatch. Repository code also rejects non-main dispatch refs, but cannot verify the GitHub Environment settings; reviewer/branch-policy configuration and a first live promotion remain operator gates.

Each environment must have independent values and credentials. Do not copy staging references into production or vice versa:

- a separate EKS cluster or access role and the fixed namespace shown above;
- a separate PostgreSQL database URL in `<namespace>-secrets` and a separate auth secret;
- a separate application domain, ACM certificate, and OAuth provider registrations whose callback URLs use that domain, stored in `<namespace>-oauth`;
- a separate S3 bucket or prefix and an IAM policy restricted to that environment's objects when `STORAGE_BACKEND=s3`;
- a separate SES sender and pod IAM role;
- separate purge, rate-limit cleanup, reminder, and digest schedules;
- exact trusted ingress/load-balancer source CIDRs in optional `TRUSTED_PROXY_IPS` when per-client forwarded IP buckets are required;
- an optional `<namespace>-observability` secret for the environment's Sentry DSN and metrics token.

Required environment variables are `DEPLOY_ENABLED`, `AWS_REGION`, `AWS_DEPLOY_ROLE_ARN`, `EKS_CLUSTER`, `APP_DOMAIN`, `ACM_CERTIFICATE_ARN`, `SES_FROM_EMAIL`, `SES_ROLE_ARN`, `STORAGE_BACKEND`, `PURGE_SCHEDULE`, `REMINDER_SCHEDULE`, and `DIGEST_SCHEDULE`. S3 mode additionally requires `S3_BUCKET` and `S3_PREFIX`. `FRONTEND_SENTRY_DSN`, `TRUSTED_PROXY_IPS`, and `RATE_LIMIT_CLEANUP_SCHEDULE` are optional; rate-limit cleanup defaults to every five minutes and `METRICS_ENABLED` defaults to `false`. Empty required values fail before deployment.

The workflow serializes staging deployments separately from production promotions, renders every manifest with `deploy/render.sh`, validates it with kubectl's client-side schema handling, and checks the environment-scoped core and OAuth Secrets. It deploys a one-shot Alembic migration Job and waits for completion before applying the application workloads. Backend and frontend images are always the digest references recorded by the successful staging run; `IMAGE_SHA` is used for the migration Job name and Sentry release only.

For an offline review of the templates, supply non-secret placeholder values and run `deploy/render.sh`. The renderer accepts only `staging`/`minutes-staging` or `production`/`minutes-production`, requires an explicit storage backend, 40-character commit SHAs, and sha256 image references, and fails if required settings are absent. The policy and render assertions require Python with PyYAML plus kubectl/kustomize and run with:

```sh
python3 -m unittest tests/test_deployment_policy.py -v
```

Infrastructure prerequisites remain an EKS cluster with the AWS Load Balancer Controller (plus EBS CSI and `gp3` storage when local attachment storage is selected), reachable PostgreSQL, immutable `minutes-backend` and `minutes-frontend` ECR repositories, environment-scoped GitHub OIDC roles, ACM certificates, DNS, and secrets created out of band. The workflow does not provision clusters, databases, buckets, DNS, OAuth apps, IAM roles, GitHub Environment rules, or Secrets.

## GitHub Actions

The test job runs on pull requests and pushes to `main` or `feat/prd-completion`. It validates deployment policy and both rendered environments, validates monitoring configuration, runs Angular tests/build, and runs the PostgreSQL-backed backend suite. The feature branch also performs non-pushing Docker builds of both images. Main deploys only to staging when explicitly enabled. Production is an explicit promotion of a previously successful staging SHA and is subject to the `production` GitHub Environment approval rules.

Local manifests still default to one backend replica and a ReadWriteOnce volume; S3 mode uses `deploy-s3`, removes the volume coupling, and enables two rolling backend replicas. The scheduled jobs retain PostgreSQL advisory locks and persistent delivery keys. SES has no exactly-once idempotency key, so a process crash after send acceptance but before the delivery-row commit can cause one duplicate retry.

Authentication and owner checks protect all notes and attachments. The ALB remains internal by default. Configure each environment's origin, secure cookies, SES, OAuth registrations, database, and storage boundary before exposing it. Live staging/production resources, GitHub required reviewers, secrets, and a promotion drill are not created or verified by this repository change.

## Reference

Implementation uses Angular's documented [version compatibility](https://angular.dev/reference/versions) and FastAPI's [file upload interface](https://fastapi.tiangolo.com/tutorial/request-files/).
