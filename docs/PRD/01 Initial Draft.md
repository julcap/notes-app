# Meeting Notes App

2026-09-17 · @Someone

**Status: historical.** This is the original project brief. Every open question below has since been settled in practice — standalone project (not embedded in tools.julcap), FastAPI/SQLAlchemy/PostgreSQL backend, attachments on disk (tracked as a gap, not a final answer — see `04 Production Readiness Gaps.md`). Accounts, arguably the biggest gap this doc left open, are covered in `02 Auth & Registration Spec.md`; everything after that is `03 Feature Roadmap (Post-MVP).md` and `04 Production Readiness Gaps.md`. Kept as-is rather than rewritten, since it's the starting point the rest of the PRD folder built on.

## Overview

The Meeting Notes App is a small, real tool (not a tutorial project) built to learn Angular by using it, and to serve as the guinea pig workload for the Build Kubernetes Cluster project. It stores meeting notes, supports search, and supports file upload.

## Core features

- Create, edit, and delete meeting notes
- Search across notes
- File upload attached to a note
- A backend that persists notes and files

## Tech stack

Frontend: Angular. Backend: not yet chosen, see open questions below. Possibly integrated as a section of tools.julcap (the existing React site), potentially embedded via iframe as a separate project.

## Architecture and deployment

Frontend and backend each containerized separately, deployed to the EKS cluster built in the Build Kubernetes Cluster project. Deployed via Kubernetes manifests or a Helm chart, exposed behind a real load balancer and domain, and shipped through a GitHub Actions pipeline on every merge to main.

## Portfolio goal

The app doubles as a portfolio piece to show future clients. It needs to look and work like something a client would actually use, not a toy, since it will be shown alongside the Kubernetes and CI/CD setup as proof of end to end delivery.

## Open questions

- Backend language and framework: not yet decided
- Whether to build it as a standalone project or as an Angular section of tools.julcap, possibly via iframe
- Database choice for storing notes and file metadata
- File storage: in the database, on a volume, or in object storage
