# Object storage for attachments

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: not done**, though partially mitigated. Attachments live on a Kubernetes `PersistentVolumeClaim` (`deploy/app.yaml`'s `uploads` PVC, `gp3`, 10Gi) mounted at `/data/uploads`, not ephemeral container storage — so a redeploy no longer loses files the way plain container-filesystem storage would. The underlying architectural limit the original doc flagged is still present: the backend runs `replicas: 1` specifically because local-disk storage can't be shared across instances, which caps this service's horizontal scalability.

## Problem

Attachments are stored as files under `STORAGE` (`backend/app/storage.py`, `UPLOAD_DIR` env var) keyed by attachment id, referenced from the `attachments` table only by that id. Scaling the backend beyond one replica would require each replica to see the same files, which a `ReadWriteOnce` PVC does not provide.

## Requirements

- Move to object storage (AWS S3, or an S3-compatible service) before this app needs to scale the backend beyond one replica.
- Store the object key in the `Attachment` model instead of relying on the id-as-filename convention on local disk.
- Uploads and downloads either proxy through the backend or use presigned URLs (presigned is better for larger files — avoids routing file bytes through the API server).
- Needs a one-time migration script to move existing files from the PVC into the bucket if there's data to carry over at cutover time.

## Backend changes

- `backend/app/notes/routes.py`'s `upload()`, `download()`, and `delete_attachment()` all touch `STORAGE` directly today — these become S3 `put_object`/presigned-URL generation/`delete_object` calls instead.
- `backend/app/storage.py` becomes an S3 client wrapper rather than a `Path`.
- AWS credentials via the same IAM-role pattern already used for SES (`SES_ROLE_ARN` in `deploy/app.yaml`) rather than static keys.

## Out of scope

- Multi-region replication or lifecycle policies — not asked for, just moving off local disk.
