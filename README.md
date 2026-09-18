# Minutes — Meeting Notes

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
uvicorn app.main:app --reload
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

Browser → Angular served by Nginx → `/api` reverse proxy → FastAPI → PostgreSQL and an upload volume.

- `frontend/src/main.ts`: bootstraps the standalone root component with `app.config.ts` (providers) and `app.routes.ts` (routes).
- `frontend/src/app/auth/`: `auth.service.ts` (session state), `auth.guard.ts`, `auth.interceptor.ts`, `user.model.ts`, `error-text.ts`/`password-policy.ts` (small shared helpers), and `auth-page/` (login/register/forgot/reset/verify/login-2fa — one parametrized page component driven by route `data.mode`, plus an inline 2FA-code step when a login response asks for one).
- `frontend/src/app/account/`: `account.ts`/`.html` — the signed-in Account page (profile, password, 2FA enrollment/disable, delete account).
- `frontend/src/app/shell/`: `nav-rail.ts`/`.html` — the sidebar navigation shared by the notes workspace and the Account page.
- `frontend/src/app/notes/`: `notes-workspace.ts`/`.html` (the meeting-notes UI) and `note.model.ts`.
- `frontend/src/app/error-tracking.ts`: opt-in Angular error capture, runtime public configuration, and payload/breadcrumb allowlisting.
- `frontend/src/styles.css`: shared responsive styling.
- `backend/app/main.py`: FastAPI app wiring (middleware, routers, health check).
- `backend/app/observability.py`: allowlisted JSON logging, request-ID context/middleware, safe unhandled-error stacks, and identifier-free auth audit events.
- `backend/app/error_tracking.py`: opt-in FastAPI Sentry initialization and complete event/breadcrumb allowlisting.
- `backend/app/database.py`: SQLAlchemy engine, session factory, declarative base.
- `backend/app/storage.py`: local and S3-compatible attachment backends, deterministic object keys, and retryable quarantine/restore helpers used by routes, purge, and account deletion.
- `backend/app/storage_migrate.py`: dry-run-by-default, SHA-256-verified local-to-S3 attachment migration CLI with a JSON-lines retry manifest.
- `backend/app/auth/`: accounts, sessions and email — `models.py`/`schemas.py` (data), `security.py` (hashing, rate limiting, origin checks), `tokens.py` (JWTs, cookies, dependencies, MFA challenges), `email.py` (SES/SMTP delivery), `totp.py` (TOTP secrets, QR codes, backup codes), `routes.py` (register/login/reset/verify/account management/2FA), `oauth.py` (Google/Facebook/Amazon).
- `backend/app/notes/`: meeting notes, sharing, and attachments — `models.py`/`schemas.py` (data), `permissions.py` (central owner/edit/view authorization), `sharing.py` (owner-managed collaborators and previous recipients), `attachments.py` (media-type normalization and byte-signature verification), `export.py` plus `assets/` (safe Markdown/PDF rendering and licensed DejaVu/Noto Unicode fonts), and `routes.py` (CRUD, export, 15-second undo, and file upload/download/preview).
- `backend/app/jobs.py` and `backend/app/notifications/`: internal scheduled-job CLI and notification delivery model/service. `purge-deleted`, `reminders`, and `weekly-digest` use PostgreSQL advisory locks; notification runs also persist unique delivery keys.
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

For local opt-in testing, set those variables in `.env`; leaving either DSN empty guarantees that side never initializes its SDK. Production backend configuration uses the optional `sentry-dsn` key in a `minutes-observability` Kubernetes Secret. `FRONTEND_SENTRY_DSN` is a public GitHub environment variable. Do not add a debug crash route or real credentials to source control. A release is code-complete without live ingestion: an operator must separately approve configuration and verify one scrubbed event in the provider before claiming production monitoring is active.

## EKS deployment

Infrastructure prerequisites:

1. An EKS cluster with the AWS Load Balancer Controller and EBS CSI driver, and a `gp3` StorageClass using `WaitForFirstConsumer`.
2. An external PostgreSQL instance (RDS recommended), reachable from the worker nodes. Require TLS using `?sslmode=require` in DATABASE_URL.
3. ECR repositories named `minutes-backend` and `minutes-frontend`; worker nodes need permission to pull them.
4. An ACM certificate and a domain. The default ALB is **internal**; clients need network access to the VPC. Point DNS at the ALB hostname after creation.
5. An AWS IAM role trusted by GitHub OIDC, scoped to this repository's production environment, with ECR push and EKS access. The runner must reach the cluster API; use a self-hosted runner for private-only endpoints.

Create the namespace and provision a Kubernetes Secret named `minutes-secrets` containing the keys `database-url` and `auth-secret`, using your secrets manager or a protected file. Do not commit credentials.

```sh
kubectl apply -f deploy/namespace.yaml
kubectl -n minutes create secret generic minutes-secrets --from-file=database-url=/secure/path/database-url --from-file=auth-secret=/secure/path/auth-secret
```

When backend error tracking is approved, create `minutes-observability` out of band with a `sentry-dsn` key. The manifest treats this Secret and key as optional, so an unconfigured deployment remains disabled rather than failing startup.

The file should contain the complete PostgreSQL connection URL with no trailing newline; URL-encode password characters. For manual deployment, export `BACKEND_IMAGE`, `FRONTEND_IMAGE`, `APP_DOMAIN`, `ACM_CERTIFICATE_ARN`, `AWS_REGION`, `SES_FROM_EMAIL`, and `SES_ROLE_ARN`, then:

```sh
envsubst < deploy/service-account.yaml | kubectl apply -f -
envsubst < deploy/app.yaml | kubectl apply -f -
envsubst < deploy/ingress.yaml | kubectl apply -f -
kubectl -n minutes rollout status deployment/backend
kubectl -n minutes rollout status deployment/frontend
```

The default local-storage backend uses a single replica with `Recreate` updates for its EBS volume; updates briefly interrupt API availability. The `purge-deleted-notes` CronJob runs daily at 03:00 UTC, mounts that same upload volume, forbids overlapping Kubernetes Jobs, takes a PostgreSQL advisory lock, and uses required pod affinity so the ReadWriteOnce EBS volume is mounted from the backend node. After an operator-verified migration, the explicit S3 overlay removes those mounts and affinity and enables two rolling backend replicas. `meeting-reminders` runs every minute and `weekly-digests` runs Monday at 09:00 UTC; both use the backend service account for SES and database locks plus persistent keys for normal-run deduplication. SES has no exactly-once idempotency key, so a process crash after send acceptance but before the delivery-row commit can cause one duplicate retry. The frontend has two replicas. The manifests assume x86-64 EKS nodes, matching the GitHub Actions image build.

Authentication and owner checks protect all notes and attachments. The ALB remains internal by default. Configure the production origin, secure cookies, SES, and OAuth secrets as described in AUTH.md before making the service public.

## GitHub Actions

Push this directory as the repository root. Pull requests and pushes to `main` run the Angular build and PostgreSQL integration tests. To enable deployment after a successful main merge, configure these repository/environment variables:

| Variable | Purpose |
| --- | --- |
| `DEPLOY_ENABLED` | `true` enables deployments |
| `AWS_REGION` | EKS/ECR region |
| `AWS_DEPLOY_ROLE_ARN` | GitHub OIDC deploy role |
| `EKS_CLUSTER` | Existing cluster name |
| `APP_DOMAIN` | Meeting app hostname |
| `ACM_CERTIFICATE_ARN` | ALB TLS certificate |
| `SES_FROM_EMAIL` | SES verified sender |
| `SES_ROLE_ARN` | EKS service account IAM role permitting SES send |
| `FRONTEND_SENTRY_DSN` | Optional public browser DSN; empty disables frontend error tracking |

Create the `production` GitHub environment and configure its access rules. Images are tagged with the commit SHA. The workflow builds and pushes both images, applies manifests, and waits for rollouts. Infrastructure, DNS, and secrets must already exist; the workflow does not provision the Kubernetes cluster.

## Reference

Implementation uses Angular's documented [version compatibility](https://angular.dev/reference/versions) and FastAPI's [file upload interface](https://fastapi.tiangolo.com/tutorial/request-files/).
