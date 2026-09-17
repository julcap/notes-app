# Two-factor authentication (TOTP)

2026-09-17 · split from `02 Auth & Registration Spec.md`

**Status: done.** Implemented in `backend/app/auth/totp.py`, `backend/app/auth/routes.py` (`enable_2fa`, `confirm_2fa`, `disable_2fa`, `login_2fa`), and the 2FA section of `frontend/src/app/account/account.ts`.

## What it does

- Opt-in, managed from the account page; available to local accounts and as an extra layer on social accounts too.
- Enrollment: backend generates a TOTP secret, the frontend shows a QR code (`otpauth://` URI, rendered as SVG server-side) to scan into an authenticator app; the user confirms by entering one valid 6-digit code before it actually turns on.
- A set of one-time backup codes (10, format `xxxx-xxxx`) is generated at enrollment and shown once, for use if the authenticator device is lost.
- Once enabled, login becomes two steps: after the password (or social provider) succeeds, the user is prompted for a 6-digit code or a backup code (`verify_totp_or_backup_code()`) before tokens are issued.
- Disabling 2FA requires re-entering the current password or a valid code as confirmation.

## Data model

`User.totp_secret` (encrypted, nullable), `User.totp_enabled` (default false). `backup_codes` (`backend/app/auth/models.py`): `id`, `user_id`, `code_hash` (hashed like a password), `used_at`, `created_at`.

## Endpoints

`POST /api/auth/2fa/enable`, `POST /api/auth/2fa/confirm`, `POST /api/auth/2fa/disable`, `POST /api/auth/login/2fa`.

## Security

- TOTP secret encrypted at rest with a key derived from `AUTH_SECRET` with domain separation (`backend/app/auth/totp.py`) — it must be decryptable to check codes, unlike a password, so hashing wasn't an option.
- Backup codes hashed the same way as passwords; each is single-use.
- `POST /api/auth/login/2fa` is rate-limited separately, so a stolen password can't be paired with brute-forcing a 6-digit code.
- Valid-code window is a single step (±30s) either side, per `pyotp.verify(valid_window=1)` — tight enough to resist replay while tolerating normal clock drift.
