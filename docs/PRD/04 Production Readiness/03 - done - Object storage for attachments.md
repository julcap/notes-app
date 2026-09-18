# Object storage for attachments

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: code-complete; live bucket, IAM, migration, and cutover remain operator-gated.** The backend now supports local storage by default and S3-compatible storage through the same authorization-preserving API. Repository completion does not mean production bytes have been migrated.

## Implemented design

- `backend/app/storage.py` provides local and S3-compatible backends selected by `STORAGE_BACKEND=local|s3`.
- S3 configuration uses `S3_BUCKET`, optional `S3_ENDPOINT_URL`, `S3_REGION` or `AWS_REGION`, and optional `S3_PREFIX`. Credentials come from the ambient boto3/IAM chain; no static access keys are accepted by application configuration.
- Alembic revision `20260918_0007` adds nullable `attachments.object_key`. Existing rows keep `NULL` and continue resolving to their attachment id on local storage; new uploads persist their actual key.
- Uploads, authorized downloads/previews, attachment deletion, 30-day purge, and account hard deletion all use the abstraction. Downloads remain backend-proxied with `Content-Length`, forced-download/default preview behavior, `no-store`, and `nosniff`, so authorization changes take effect immediately.
- Local and S3 deletion use a retryable quarantine. A database rollback restores bytes; a failed final object deletion stays in quarantine for the next purge reconciliation.
- Local mode retains the one-replica ReadWriteOnce PVC deployment. `deploy-s3/storage-s3-patch.yaml` is an explicit operator-applied strategic-merge patch that removes the PVC dependency and raises the backend to two replicas only in S3 mode.

## Migration and cutover

`python -m app.storage_migrate` is dry-run by default. It reads existing local files, copies each to the deterministic configured S3 key, downloads it again, verifies byte length and SHA-256, then updates `attachments.object_key` only after verification. It never uses ETag as a checksum and never removes the source file.

```sh
# Run in a controlled pod/process that has both the old PVC and S3 IAM access.
export STORAGE_BACKEND=s3
export S3_BUCKET=minutes-production-attachments
export S3_PREFIX=production
export AWS_REGION=us-east-1
python -m app.storage_migrate --manifest /data/storage-migration.jsonl
python -m app.storage_migrate --apply --manifest /data/storage-migration.jsonl
```

The JSON-lines manifest records planned, migrated, skipped, and failed rows without file contents or credentials. Re-running is safe: verified rows are skipped, an upload interrupted before database cutover is adopted after verification, and a corrupt target is replaced and re-verified from the preserved local source.

During the production cutover, stop attachment writes, back up the database and PVC, run dry-run and apply, require zero failures, apply the S3 deployment patch, verify authenticated upload/download/preview/delete/purge behavior, then resume writes. Keep the PVC/source bytes until rollback and retention policy approval.

## Verification

- Local temporary-file roundtrip and oversized-write rollback.
- Actual PostgreSQL migration and API regression coverage, including legacy id-based objects, streaming headers, missing objects, authorization/revocation, upload rollback, purge, and account deletion retries.
- Isolated HTTP S3-compatible service coverage for put/get/head/stream, deterministic prefixes, quarantine restore, failed-final-delete retry, and oversize rollback.
- Migration coverage for dry-run, apply, preserved sources, rerun, interrupted cutover, target corruption repair, size, and SHA-256 verification.

MinIO's public binary endpoint returned HTTP 410 in this implementation environment, so no MinIO-specific or live-cloud claim is made. The isolated HTTP S3-compatible tests used a local Moto service; bucket/IAM/provider compatibility still requires the operator gate below.

## Remaining live gate

Provisioning the bucket, granting least-privilege IAM to the backend service account and migration job, selecting the production prefix/region, approving the maintenance window, running the real migration, applying `deploy-s3/storage-s3-patch.yaml`, and validating rollback are intentionally not performed by this repository change. Multi-region replication and lifecycle policies remain out of scope.
