# Meeting Notes App

2026-09-17 · @Someone

## Overview

The Meeting Notes App is a small, real tool (not a tutorial project) built to learn Angular by using it, and to serve as the guinea pig workload for the Build Kubernetes Cluster project. It stores meeting notes, supports search, and supports file upload. Since shipping the first version, it has grown accounts and authentication so notes belong to the person who created them — see [AUTH-SPEC.md](AUTH-SPEC.md) for that feature's spec and [AUTH.md](AUTH.md) for how it's actually built and configured.

## Core features

- Create, edit, and delete meeting notes
- Search across notes (title, body, and attendees)
- File upload attached to a note, with download and removal
- Email/password registration and login, required email verification, forgot-password recovery, and Google/Facebook/Amazon social login
- Notes and attachments are private to the account that created them
- A backend that persists notes, files, and accounts

## Tech stack

Frontend: Angular 20, standalone components (no NgModules), organized as feature folders under `src/app/`. Backend: FastAPI (Python) with SQLAlchemy, split into per-domain packages (`auth/`, `notes/`). Database: PostgreSQL. Local transactional email via Mailpit; production via AWS SES. File uploads live on a persistent volume, not in the database. See [README.md](README.md) for exact run/build/test commands.

## Architecture and deployment

Frontend and backend are each containerized separately (`compose.yaml` for local development) and deploy to the EKS cluster built in the Build Kubernetes Cluster project via the manifests in `deploy/`, shipped through the GitHub Actions pipeline (`.github/workflows/ci.yaml`) on every merge to main once the repository's `DEPLOY_ENABLED` variable is turned on. Exposed behind a real load balancer and domain per the README's "EKS deployment" section. Live deployment to that cluster hasn't been exercised yet — see [VERIFICATION.md](VERIFICATION.md).

Code is organized by domain and concern rather than by one large file per layer: backend `app/auth/` and `app/notes/` packages each split into `models.py`/`schemas.py`/`security.py`/`routes.py` (etc.), and the Angular frontend mirrors that with `src/app/auth/` and `src/app/notes/` feature folders. The coding standards behind this structure are written down in [AGENT.md](AGENT.md) and [CLAUDE.md](CLAUDE.md).

## Portfolio goal

The app doubles as a portfolio piece to show future clients. It needs to look and work like something a client would actually use, not a toy, since it will be shown alongside the Kubernetes and CI/CD setup as proof of end to end delivery.

## Decisions (were open questions, now resolved)

- [x] Backend language and framework: **FastAPI (Python) with SQLAlchemy**, not left undecided.
- [x] Standalone project vs. an Angular section of tools.julcap: **standalone**, not embedded via iframe.
- [x] Database for notes and file metadata: **PostgreSQL**.
- [x] File storage — database, volume, or object storage: **a persistent Docker/EBS volume** in both local dev and the current EKS manifests. Noted limitation: the backend runs a single replica with `Recreate` updates because of this volume; moving attachments to S3 is called out as the prerequisite for scaling backend replicas.
- [x] Whether accounts/authentication are in scope: **yes**, added as a full feature after the initial notes-only version shipped (email/password, verification, recovery, and Google/Facebook/Amazon social login) — see AUTH-SPEC.md.

## Open questions

- Live EKS deployment and the GitHub Actions `deploy` job have not been exercised end-to-end (cluster/DNS/ACM/OIDC prerequisites are documented but unconfirmed in practice).
- Live AWS SES delivery and live OAuth consent flows with real Google/Facebook/Amazon accounts are unverified — local testing uses Mailpit and, for OAuth, a forged/unconfigured-provider test path (see VERIFICATION.md).
- Attachment storage is still volume-based; migrating to S3 before running more than one backend replica is a known follow-up, not yet scheduled.
