import os
from io import BytesIO

import boto3
import pytest

from app.storage import FileTooLarge, S3Storage, LocalStorage


def test_local_storage_roundtrip_and_oversize_rollback(tmp_path):
    storage = LocalStorage(tmp_path)

    assert storage.write('attachments/one', BytesIO(b'hello'), max_size=5) == 5
    assert storage.read('attachments/one') == b'hello'
    assert storage.size('attachments/one') == 5

    with pytest.raises(FileTooLarge):
        storage.write('attachments/large', BytesIO(b'too large'), max_size=5)
    assert not storage.exists('attachments/large')


def test_s3_compatible_http_roundtrip_quarantine_and_oversize_rollback(monkeypatch):
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
    bucket = 'minutes-storage-integration'
    client.create_bucket(Bucket=bucket)
    storage = S3Storage(bucket, prefix='tests', client=client)
    key = storage.object_key('one')

    assert key == 'tests/attachments/one'
    assert storage.write(key, BytesIO(b'hello'), max_size=5) == 5
    assert storage.read(key) == b'hello'
    assert b''.join(storage.iter_chunks(key, 2)) == b'hello'
    assert storage.size(key) == 5

    quarantined = storage.quarantine([key])
    assert not storage.exists(key)
    assert storage.quarantined() == quarantined
    storage.restore(quarantined)
    assert storage.read(key) == b'hello'

    quarantined = storage.quarantine([key])
    original_delete = client.delete_object

    def fail_trash_delete(**kwargs):
        if '/.trash/' in kwargs['Key']:
            raise RuntimeError('temporary object deletion failure')
        return original_delete(**kwargs)

    monkeypatch.setattr(client, 'delete_object', fail_trash_delete)
    storage.discard(quarantined)
    assert storage.quarantined() == quarantined
    monkeypatch.setattr(client, 'delete_object', original_delete)
    storage.discard(storage.quarantined())
    assert storage.quarantined() == []

    with pytest.raises(FileTooLarge):
        storage.write(storage.object_key('large'), BytesIO(b'too large'), max_size=5)
    assert not storage.exists(storage.object_key('large'))

    legacy_key = 'legacy-prefix/attachments/legacy'
    client.put_object(Bucket=bucket, Key=legacy_key, Body=b'legacy')
    current = S3Storage(bucket, prefix='current-prefix', client=client)
    quarantined = current.quarantine([legacy_key])
    assert current.quarantined() == quarantined
    assert quarantined[0].key == legacy_key
    current.restore(current.quarantined())
    assert current.read(legacy_key) == b'legacy'
