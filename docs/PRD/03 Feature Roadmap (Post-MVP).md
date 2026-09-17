# Meeting Notes App — Feature Roadmap (Post-MVP)

2026-09-17 · @Someone · split 2026-09-17 into `03 Feature Roadmap/` for one-spec-at-a-time work

Product features the app is currently missing to feel complete and be something users are happy to keep using. Companion to the Auth & Registration Spec; this doc is about product depth, not infrastructure (see the Production Readiness Gaps doc for that).

## Overview

The core app (accounts, meetings, attachments, search) works. This roadmap covers what's missing for it to feel like a product people actually want to keep using, as opposed to a working demo. It's the product-depth counterpart to the Production Readiness Gaps doc, which covers infrastructure and operational risk instead.

Each item below is its own spec file in `03 Feature Roadmap/`, sized to be picked up and shipped independently rather than as one large roadmap effort. This index tracks status; the linked file has the actual requirements, data model, and endpoint details. A shipped spec's filename carries `- done -` between its number and title, so status is visible from the file listing alone, not just this index.

## Items, in suggested order

Roughly cheapest-and-most-impactful first, action items excepted since it's already shipped. Not a commitment, just a starting point for triage — pick whichever is actually most valuable next.

1. ✅ [Action items](./03%20Feature%20Roadmap/01%20-%20done%20-%20Action%20items.md) — shipped 2026-09-17. New `action_items` table, checklist UI under notes, lightweight PATCH to toggle done. (The other half of the original "richer notes" section — see item 2.)
2. ✅ [Rich text notes: formatting](./03%20Feature%20Roadmap/02%20-%20done%20-%20Rich%20text%20notes%20formatting.md) — safe markdown toolbar, preview, and read rendering shipped 2026-09-17.
3. ⬜ [Full-text search](./03%20Feature%20Roadmap/03%20Full-text%20search.md) — Postgres `tsvector`/GIN, backend-only.
4. ⬜ [Pagination](./03%20Feature%20Roadmap/04%20Pagination.md) — `skip`/`limit` through to the UI, small API shape change.
5. ⬜ [Soft delete & undo](./03%20Feature%20Roadmap/05%20Soft%20delete%20and%20undo.md) — `deleted_at`, undo toast, scheduled purge.
6. ⬜ [Attachment previews](./03%20Feature%20Roadmap/06%20Attachment%20previews.md) — inline preview for images/PDFs.
7. ⬜ [Export](./03%20Feature%20Roadmap/07%20Export.md) — single meeting as PDF or markdown.
8. ⬜ [Notifications & reminders](./03%20Feature%20Roadmap/08%20Notifications%20and%20reminders.md) — needs the email infra from the auth spec, and a scheduler this app doesn't have yet.
9. ⬜ [Sharing & collaboration](./03%20Feature%20Roadmap/09%20Sharing%20and%20collaboration.md) — the biggest lift, reshapes authorization across every note endpoint, so it's last.

## Working with this folder

- Each file is self-contained: problem, requirements, data model, backend, frontend, and explicit out-of-scope notes — no need to read the others to start one.
- When a spec ships: rename its file to insert `- done -` between the number and title (matching item 1), flip its status line and this index's marker, and note the shipping date + what landed.
- If a spec's scope turns out to be wrong once you're in the code (as happened with attachment previews' "no backend change needed" assumption — content-type isn't actually stored today), fix it in that spec file rather than here.
