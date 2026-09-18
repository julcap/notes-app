import argparse
import hashlib
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from sqlalchemy import select, text

from .database import SessionLocal
from .notes.models import Attachment
from .storage import FILE_CLEANUP_LOCK_ID, STORAGE, LocalStorage, S3Storage, storage_from_env


MIGRATION_LOCK_ID = FILE_CLEANUP_LOCK_ID + 1


def checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def append_manifest(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as output:
        output.write(json.dumps(record, sort_keys=True) + '\n')


def migrate_attachments(session_factory, source, target, *, apply: bool, manifest: Path) -> dict:
    report = {'planned': 0, 'migrated': 0, 'skipped': 0, 'failed': 0}
    with session_factory() as session:
        attachments = session.scalars(select(Attachment).order_by(Attachment.id)).all()
        for attachment in attachments:
            source_key = attachment.object_key if attachment.object_key and source.exists(attachment.object_key) else attachment.id
            target_key = target.object_key(attachment.id)
            record = {
                'attachment_id': attachment.id,
                'source_key': source_key,
                'target_key': target_key,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            try:
                content = source.read(source_key)
                expected_size = len(content)
                expected_checksum = checksum(content)
                record.update(size=expected_size, sha256=expected_checksum)
                target_valid = False
                if target.exists(target_key):
                    target_content = target.read(target_key)
                    target_valid = (
                        len(target_content) == expected_size
                        and checksum(target_content) == expected_checksum
                    )
                if attachment.object_key == target_key and target_valid:
                    record['status'] = 'skipped'
                    report['skipped'] += 1
                elif not apply:
                    record['status'] = 'planned'
                    report['planned'] += 1
                else:
                    session.execute(
                        text('SELECT pg_advisory_xact_lock(:lock_id)'),
                        {'lock_id': MIGRATION_LOCK_ID},
                    )
                    if not target_valid:
                        target.write(target_key, BytesIO(content), max_size=expected_size)
                    migrated = target.read(target_key)
                    if len(migrated) != expected_size or checksum(migrated) != expected_checksum:
                        target.delete(target_key)
                        raise RuntimeError('Target verification failed')
                    attachment.object_key = target_key
                    session.commit()
                    record['status'] = 'migrated'
                    report['migrated'] += 1
            except Exception as error:
                session.rollback()
                record['status'] = 'failed'
                record['error'] = type(error).__name__
                report['failed'] += 1
            append_manifest(manifest, record)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m app.storage_migrate')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--manifest', type=Path, default=Path('storage-migration-manifest.jsonl'))
    args = parser.parse_args(argv)
    target = storage_from_env()
    if not isinstance(target, S3Storage):
        parser.error('STORAGE_BACKEND=s3 and S3_BUCKET are required')
    report = migrate_attachments(
        SessionLocal,
        LocalStorage(STORAGE),
        target,
        apply=args.apply,
        manifest=args.manifest,
    )
    print(json.dumps({'apply': args.apply, **report}, sort_keys=True))
    return 1 if report['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
