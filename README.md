# Minutes — Meeting Notes

A standalone meeting notes workspace built from `Meeting Notes App.md`: Angular frontend, Python/FastAPI backend, and PostgreSQL. Create, edit, delete, and search notes; record meeting dates and attendees; upload, download, and remove attachments.

## Run locally

Install Docker Desktop, then from this directory:

```sh
# First installation only (keep .env private):
python3 -c "import secrets; print('AUTH_SECRET=' + secrets.token_urlsafe(48))" > .env
chmod 600 .env
docker compose up --build -d
```

Open http://localhost:8080 and create an account. Open the local development inbox at http://localhost:8025 to find the verification email, follow its link, and click **Verify email**. You can then create a note. Production mail uses AWS SES. See [AUTH.md](AUTH.md) for configuration and security details. Notes and uploads survive container restarts in named Docker volumes. `docker compose down` stops the app without deleting data; adding `-v` permanently removes local data.

The app starts empty intentionally. Search filters title, body, and attendees. The API also supports `GET /api/notes?q=keyword`. Attachments have a 20 MB limit and are served as downloads rather than inline executable content. Filenames are metadata; server-generated UUIDs determine disk paths.

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

Tests use a separate disposable PostgreSQL database. The test container upgrades it through Alembic before pytest; fixtures clear rows between tests without recreating schema. Migration coverage includes empty installs, validated adoption of populated current installs, ownerless pre-auth data preservation, drift rejection, repeated upgrades, and concurrent startup. Never point either the migration tests or the full Python suite at production.

## Architecture

Browser → Angular served by Nginx → `/api` reverse proxy → FastAPI → PostgreSQL and an upload volume.

- `frontend/src/main.ts`: bootstraps the standalone root component with `app.config.ts` (providers) and `app.routes.ts` (routes).
- `frontend/src/app/auth/`: `auth.service.ts` (session state), `auth.guard.ts`, `auth.interceptor.ts`, `user.model.ts`, `error-text.ts`/`password-policy.ts` (small shared helpers), and `auth-page/` (login/register/forgot/reset/verify/login-2fa — one parametrized page component driven by route `data.mode`, plus an inline 2FA-code step when a login response asks for one).
- `frontend/src/app/account/`: `account.ts`/`.html` — the signed-in Account page (profile, password, 2FA enrollment/disable, delete account).
- `frontend/src/app/shell/`: `nav-rail.ts`/`.html` — the sidebar navigation shared by the notes workspace and the Account page.
- `frontend/src/app/notes/`: `notes-workspace.ts`/`.html` (the meeting-notes UI) and `note.model.ts`.
- `frontend/src/styles.css`: shared responsive styling.
- `backend/app/main.py`: FastAPI app wiring (middleware, routers, health check).
- `backend/app/database.py`: SQLAlchemy engine, session factory, declarative base.
- `backend/app/storage.py`: shared attachment-storage path/size-limit constants used by both `notes/routes.py` and account deletion.
- `backend/app/auth/`: accounts, sessions and email — `models.py`/`schemas.py` (data), `security.py` (hashing, rate limiting, origin checks), `tokens.py` (JWTs, cookies, dependencies, MFA challenges), `email.py` (SES/SMTP delivery), `totp.py` (TOTP secrets, QR codes, backup codes), `routes.py` (register/login/reset/verify/account management/2FA), `oauth.py` (Google/Facebook/Amazon).
- `backend/app/notes/`: meeting notes and attachments — `models.py`/`schemas.py` (data), `routes.py` (CRUD + file upload/download).
- `backend/app/migrations.py` and `backend/migrations/`: the Alembic upgrade entrypoint and immutable schema revisions. Every schema change must add a revision; `app.init_db` only runs `upgrade head`.
- `compose.yaml`: local application stack; only the frontend is published, on localhost.
- `deploy/`: EKS manifests.
- `.github/workflows/ci.yaml`: PR checks and main-branch deployment.

Notes are plain text. File metadata is in PostgreSQL; file bytes are on a persistent volume. Each account has private notes and attachments. Email verification is required before creating notes. Access JWTs live in browser memory; refresh sessions use HttpOnly cookies. List/search loads all notes, appropriate for a small workspace; add pagination and PostgreSQL full-text indexing when the dataset grows. Concurrent edits currently use last-save-wins. Back up the database and file volume together. A crash between database commit and file deletion can leave unreferenced files; it cannot expose them through the API.

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

The file should contain the complete PostgreSQL connection URL with no trailing newline; URL-encode password characters. For manual deployment, export `BACKEND_IMAGE`, `FRONTEND_IMAGE`, `APP_DOMAIN`, `ACM_CERTIFICATE_ARN`, `AWS_REGION`, `SES_FROM_EMAIL`, and `SES_ROLE_ARN`, then:

```sh
envsubst < deploy/service-account.yaml | kubectl apply -f -
envsubst < deploy/app.yaml | kubectl apply -f -
envsubst < deploy/ingress.yaml | kubectl apply -f -
kubectl -n minutes rollout status deployment/backend
kubectl -n minutes rollout status deployment/frontend
```

The backend uses a single replica with `Recreate` updates for its EBS volume; updates briefly interrupt API availability. Move files to S3 before scaling backend replicas. The frontend has two replicas. The manifests assume x86-64 EKS nodes, matching the GitHub Actions image build.

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

Create the `production` GitHub environment and configure its access rules. Images are tagged with the commit SHA. The workflow builds and pushes both images, applies manifests, and waits for rollouts. Infrastructure, DNS, and secrets must already exist; the workflow does not provision the Kubernetes cluster.

## Reference

Implementation uses Angular's documented [version compatibility](https://angular.dev/reference/versions) and FastAPI's [file upload interface](https://fastapi.tiangolo.com/tutorial/request-files/).
