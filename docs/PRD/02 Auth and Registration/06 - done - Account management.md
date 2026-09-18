# Account management

2026-09-17 · split from `02 Auth & Registration Spec.md`

**Status: done.** Implemented in `backend/app/auth/routes.py` (`update_profile`, `change_password`, `delete_account`) and `frontend/src/app/account/`.

## What it does

A dedicated "Account" page where a logged-in user can view, update, and delete their own account.

**View:** email, display name, how they sign in (local, or which social provider is linked), and when the account was created — reuses `GET /api/auth/me`.

**Update**

- Change display name — no extra verification needed.
- Change email — requires verifying the new address before it takes effect; the old email keeps working until the new one is confirmed. Held in `User.pending_email` until the confirmation link is used.
- Change password (local accounts only) — requires entering the current password.
- Social-only accounts see the password field as not applicable, since there's no local credential to change.

**Delete account**

- A confirmation step before the delete goes through: local accounts re-enter their password, social-only accounts type "delete account".
- Hard delete — cascades to that user's meetings and attachments via the existing `owner_id` relationship, no soft-delete or retention period.
- All of that user's refresh tokens are revoked immediately.

## Endpoints

`PUT /api/auth/me`, `POST /api/auth/change-password`, `DELETE /api/auth/me`.

## Security

- Email change reuses the `email_tokens` verification pattern from [01 - done - Registration and email verification](./01%20-%20done%20-%20Registration%20and%20email%20verification.md).
- Password change and account deletion both re-check the current credential rather than trusting the authenticated session alone.
- Account deletion is unrecoverable — no soft-delete window, unlike the (not yet built) soft-delete planned for meetings themselves in the Feature Roadmap folder.

## Explicitly out of scope

Sharing a meeting with other users, and roles/permissions beyond "owner" — tracked separately as [09 - done - Sharing and collaboration](../03%20Feature%20Roadmap/09%20-%20done%20-%20Sharing%20and%20collaboration.md) in the Feature Roadmap folder.
