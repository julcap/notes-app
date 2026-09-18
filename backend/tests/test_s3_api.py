import os
from io import BytesIO

import boto3
import pytest

from app import jobs
from app.database import SessionLocal
from app.notes import routes as note_routes
from app.notes.models import Attachment
from app.storage import S3Storage
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
    bucket = 'minutes-api-integration'
    client.create_bucket(Bucket=bucket)
    return S3Storage(bucket, prefix='api', client=client)


def test_s3_backed_authorized_stream_missing_delete_and_oversize_rollback(client, monkeypatch):
    storage = s3_storage()
    monkeypatch.setattr(note_routes, 'storage', storage)
    meeting = note(client)
    base = f"/api/notes/{meeting['id']}/attachments"

    uploaded = client.post(
        base,
        files={'file': ('s3.txt', b's3 bytes', 'text/plain')},
    )
    assert uploaded.status_code == 201
    attachment_id = uploaded.json()['id']
    with SessionLocal() as session:
        object_key = session.get(Attachment, attachment_id).object_key
    assert object_key == storage.object_key(attachment_id)
    assert storage.read(object_key) == b's3 bytes'

    downloaded = client.get(f'{base}/{attachment_id}')
    assert downloaded.status_code == 200
    assert downloaded.content == b's3 bytes'
    assert downloaded.headers['content-length'] == '8'

    quarantined = storage.quarantine([object_key])
    original_delete = storage.client.delete_object

    def fail_trash_delete(**kwargs):
        if '/.trash/' in kwargs['Key']:
            raise RuntimeError('lost delete result')
        return original_delete(**kwargs)

    monkeypatch.setattr(storage.client, 'delete_object', fail_trash_delete)
    with pytest.raises(RuntimeError, match='lost delete result'):
        storage.restore(quarantined)
    assert storage.exists(object_key)
    assert storage.quarantined() == quarantined
    monkeypatch.setattr(storage.client, 'delete_object', original_delete)
    with SessionLocal() as session:
        jobs.reconcile_quarantine(session, storage)
    assert storage.read(object_key) == b's3 bytes'
    assert storage.quarantined() == []

    orphan_key = storage.object_key('orphan')
    storage.write(orphan_key, BytesIO(b'orphan'))
    orphaned = storage.quarantine([orphan_key])
    monkeypatch.setattr(storage.client, 'delete_object', fail_trash_delete)
    with pytest.raises(RuntimeError, match='lost delete result'):
        storage.restore(orphaned)
    monkeypatch.setattr(storage.client, 'delete_object', original_delete)
    with SessionLocal() as session:
        jobs.reconcile_quarantine(session, storage)
    assert not storage.exists(orphan_key)
    assert storage.quarantined() == []

    storage.delete(object_key)
    assert client.get(f'{base}/{attachment_id}').status_code == 404
    assert client.delete(f'{base}/{attachment_id}').status_code == 204

    monkeypatch.setattr(note_routes, 'MAX_FILE_SIZE', 3)
    oversized = client.post(base, files={'file': ('large.bin', b'four')})
    assert oversized.status_code == 413
    assert storage.client.list_objects_v2(Bucket=storage.bucket).get('Contents', []) == []
