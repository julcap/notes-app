# Attachment previews

2026-09-17 · split from `03 Feature Roadmap (Post-MVP).md`

**Status:** Not started.

## Problem

Attachments are currently download-only (`downloadFile()` in `notes-workspace.ts` forces a blob download for every file type), which breaks the flow of reading notes when the attachment is something you'd just want to glance at, like a screenshot or a one-page PDF.

## Requirements

- Inline preview for images and PDFs directly in the meeting detail view, with download remaining available for everything else.
- Content-type needs to be reliably stored per attachment (see Backend below — checked against the current code, and it isn't stored today, so this is a small but real backend change, not the no-op the original roadmap doc assumed).

## Backend

- None required. `GET /api/notes/{note_id}/attachments/{attachment_id}` (`download()`) currently always returns `media_type='application/octet-stream'` with `X-Content-Type-Options: nosniff` to force download. For inline preview, this endpoint needs a way to serve images/PDFs with their real content-type and no forced download — likely a query param (`?inline=1`) or a second endpoint, since the existing one is intentionally locked down to prevent the browser executing arbitrary uploaded content. Keep `nosniff` either way; only relax the content-type/disposition for a small allowlist of safe-to-inline types (`image/png`, `image/jpeg`, `image/gif`, `image/webp`, `application/pdf`).
- Attachment content-type isn't currently stored on the `Attachment` model at all (only `filename`, `size` — see `backend/app/notes/models.py`). Add a `content_type` column, populated at upload time from `UploadFile.content_type` (with a filename-extension fallback), so preview decisions are reliable rather than re-guessed from the extension on every read.

## Frontend

- In the attachments section of `notes-workspace.html`, render an `<img>` or `<embed>`/`<iframe>` inline for image/PDF attachments (fetched via the new inline-serving path), falling back to the existing download row for everything else.
- Keep the download button available even for previewable files.

## Out of scope

- Preview generation/thumbnailing for non-image, non-PDF types (e.g. Office docs) — out of scope per the doc, which limits this to images and PDFs.
