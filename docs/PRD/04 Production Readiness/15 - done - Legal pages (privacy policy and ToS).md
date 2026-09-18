# Legal pages (privacy policy & ToS)

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: code-complete.** Public `/privacy` and `/terms` Angular pages describe the application's implemented data behavior, are reachable without authentication, and are linked from registration and Account settings. The pages remain visibly marked as publication drafts because operator/contact fields and independent legal approval are not repository facts. OAuth production review has not been claimed or performed.

## Problem

Google, Facebook, and Amazon require a live privacy policy, and commonly terms of service, before their OAuth consent screens can leave test mode. Static pages alone do not complete provider review: the final operator identity, contact details, legal text, hosted deployment, and each provider's approval remain external publication gates.

## Shipped behavior

- `frontend/src/app/legal/legal-page.ts` and `legal-page.html` provide a shared, semantic public layout for distinct privacy and terms content.
- `frontend/src/app/app.routes.ts` registers `/privacy` and `/terms` without `authGuard`; the wildcard remains after both routes.
- Registration explicitly links both documents beside account creation. Account settings has a separate Legal and privacy section with the same links.
- The privacy draft covers account/profile and social-provider claims, note/action-item/scheduling content, attachment bytes and metadata, sharing recipients and permissions, session IP/user-agent/device metadata, notification preferences and message content, security counters, structured logs, metrics, optional scrubbed Sentry events, email/object-storage providers, and the current Google Fonts request.
- Retention text matches implemented behavior: 15-second server-enforced meeting undo, scheduled permanent purge after 30 days, immediate live account hard deletion, and an explicit operational-backup caveat without inventing a backup schedule.
- The terms draft covers account security, user-content responsibility, view/edit collaboration, acceptable use, export/deletion behavior, and external dependencies. It does not invent an operator, address, jurisdiction, SLA, certification, warranty, or liability promise.
- Both pages disclose that operator identity/contact details, legal review, OAuth production approval, and live publication remain pending.

## Accessibility and verification

- Each document has one `main` landmark and one `h1`, ordered section headings, semantic lists, a keyboard-focusable legal navigation with `aria-current`, and responsive styles.
- Jasmine coverage checks public unguarded routes, registration/account links, semantic landmarks, required data-lifecycle wording, and unresolved-publication disclosures.
- The Angular production build and complete ChromeHeadless test suite are the acceptance gates for repository completion.

## External publication gates

Before presenting these drafts as final or submitting OAuth applications, an authorized operator must supply and approve the operator name, service/contact address, privacy/legal contact, effective publication details, governing-law/venue language if required, backup-retention representation, and the complete lawyer-reviewed text. The approved pages must then be deployed at public stable URLs and separately submitted to Google, Facebook, and Amazon. None of those actions is performed by this repository-only feature.
