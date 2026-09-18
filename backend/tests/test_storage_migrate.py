import json
import os
from io import BytesIO

import boto3
import pytest

from app.database import SessionLocal
from app.notes.models import Attachment
from app.storage import STORAGE, LocalStorage, S3Storage
from app.storage_migrate import migrate_attachments
from test_api import note


def s3_storage():
    endpoint = os.getenv('S3_TEST_ENDPOINT')
    if not endpoint:
        pytest.skip('S3_TEST_ENDPOINT is not configured')
    client = boto3.client(
        's3',
        endpoint_url=endpoint,
        region_name='us-east-1',
        aws_access_key_id='test',
        aws_secret_access_key='test',
    )
    bucket = 'minutes-migration-integration'
    try:
        client.create_bucket(Bucket=bucket)
    except client.exceptions.BucketAlreadyOwnedByYou:
        pass
    return S3Storage(bucket, prefix='migration', client=client)


def test_storage_migration_dry_run_apply_and_rerun_preserve_source(client, tmp_path):
    meeting = note(client)
    uploaded = client.post(
        f"/api/notes/{meeting['id']}/attachments",
        files={'file': ('migration.txt', b'migrate safely', 'text/plain')},
    ).json()
    source = LocalStorage(STORAGE)
    target = s3_storage()
    target_key = target.object_key(uploaded['id'])
    target.delete(target_key)
    manifest = tmp_path / 'manifest.jsonl'

    dry_run = migrate_attachments(SessionLocal, source, target, apply=False, manifest=manifest)
    assert dry_run == {'planned': 1, 'migrated': 0, 'skipped': 0, 'failed': 0}
    assert not target.exists(target_key)
    with SessionLocal() as session:
        assert session.get(Attachment, uploaded['id']).object_key == uploaded['id']

    applied = migrate_attachments(SessionLocal, source, target, apply=True, manifest=manifest)
    assert applied == {'planned': 0, 'migrated': 1, 'skipped': 0, 'failed': 0}
    assert target.read(target_key) == b'migrate safely'
    assert source.read(uploaded['id']) == b'migrate safely'
    with SessionLocal() as session:
        assert session.get(Attachment, uploaded['id']).object_key == target_key

    rerun = migrate_attachments(SessionLocal, source, target, apply=True, manifest=manifest)
    assert rerun == {'planned': 0, 'migrated': 0, 'skipped': 1, 'failed': 0}
    records = [json.loads(line) for line in manifest.read_text().splitlines()]
    assert [record['status'] for record in records] == ['planned', 'migrated', 'skipped']
    assert all(record['attachment_id'] == uploaded['id'] for record in records)


def test_storage_migration_resumes_uploaded_objects_and_repairs_corruption(client, tmp_path):
    meeting = note(client)
    first = client.post(
        f"/api/notes/{meeting['id']}/attachments",
        files={'file': ('corrupt.txt', b'authoritative one', 'text/plain')},
    ).json()
    second = client.post(
        f"/api/notes/{meeting['id']}/attachments",
        files={'file': ('interrupted.txt', b'authoritative two', 'text/plain')},
    ).json()
    source = LocalStorage(STORAGE)
    target = s3_storage()
    first_key = target.object_key(first['id'])
    second_key = target.object_key(second['id'])
    target.write(first_key, BytesIO(b'corrupt'))
    target.write(second_key, BytesIO(b'authoritative two'))

    report = migrate_attachments(
        SessionLocal,
        source,
        target,
        apply=True,
        manifest=tmp_path / 'resume.jsonl',
    )

    assert report == {'planned': 0, 'migrated': 2, 'skipped': 0, 'failed': 0}
    assert target.read(first_key) == b'authoritative one'
    assert target.read(second_key) == b'authoritative two'
    target.write(first_key, BytesIO(b'corrupt again'))

    repaired = migrate_attachments(
        SessionLocal,
        source,
        target,
        apply=True,
        manifest=tmp_path / 'repair.jsonl',
    )
    assert repaired == {'planned': 0, 'migrated': 1, 'skipped': 1, 'failed': 0}
    assert target.read(first_key) == b'authoritative one'
