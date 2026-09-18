import base64
import binascii
import os
import tempfile
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

import boto3
from botocore.exceptions import ClientError


STORAGE = Path(os.getenv('UPLOAD_DIR', '/data/uploads'))
MAX_FILE_SIZE = 20 * 1024 * 1024
FILE_CLEANUP_LOCK_ID = 538_719_443


class StorageError(RuntimeError):
    pass


class ObjectNotFound(StorageError):
    pass


class FileTooLarge(StorageError):
    pass


@dataclass(frozen=True)
class QuarantinedObject:
    key: str
    quarantine_key: str


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root

    def object_key(self, attachment_id: str) -> str:
        return attachment_id

    def _path(self, key: str) -> Path:
        candidate = PurePosixPath(key)
        if candidate.is_absolute() or '..' in candidate.parts or not candidate.parts:
            raise StorageError('Invalid object key')
        return self.root.joinpath(*candidate.parts)

    def write(self, key: str, source: BinaryIO, *, max_size: int | None = None) -> int:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f'.{target.name}.{uuid.uuid4().hex}.upload')
        size = 0
        try:
            with temporary.open('wb') as output:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if max_size is not None and size > max_size:
                        raise FileTooLarge
                    output.write(chunk)
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return size

    def read(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as error:
            raise ObjectNotFound(key) from error

    def iter_chunks(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        try:
            source = self._path(key).open('rb')
        except FileNotFoundError as error:
            raise ObjectNotFound(key) from error
        with source:
            while chunk := source.read(chunk_size):
                yield chunk

    def size(self, key: str) -> int:
        try:
            return self._path(key).stat().st_size
        except FileNotFoundError as error:
            raise ObjectNotFound(key) from error

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def quarantine(self, keys: Iterable[str]) -> list[QuarantinedObject]:
        quarantined = []
        try:
            for key in keys:
                source = self._path(key)
                if not source.is_file():
                    continue
                quarantine_key = f'.trash/{key}'
                destination = self._path(quarantine_key)
                destination.parent.mkdir(parents=True, exist_ok=True)
                source.replace(destination)
                quarantined.append(QuarantinedObject(key, quarantine_key))
        except OSError:
            self.restore(quarantined)
            raise
        return quarantined

    def restore(self, quarantined: Iterable[QuarantinedObject]) -> None:
        for item in reversed(list(quarantined)):
            source = self._path(item.quarantine_key)
            if source.is_file():
                destination = self._path(item.key)
                destination.parent.mkdir(parents=True, exist_ok=True)
                source.replace(destination)

    def discard(self, quarantined: Iterable[QuarantinedObject]) -> None:
        for item in quarantined:
            try:
                self._path(item.quarantine_key).unlink(missing_ok=True)
            except OSError:
                pass

    def quarantined(self) -> list[QuarantinedObject]:
        trash = self.root / '.trash'
        if not trash.is_dir():
            return []
        return [
            QuarantinedObject(path.relative_to(trash).as_posix(), path.relative_to(self.root).as_posix())
            for path in trash.rglob('*')
            if path.is_file()
        ]


class S3Storage:
    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        region: str | None = None,
        prefix: str = '',
        client=None,
    ):
        self.bucket = bucket
        self.prefix = prefix.strip('/')
        self.client = client or boto3.client('s3', endpoint_url=endpoint_url, region_name=region)

    def object_key(self, attachment_id: str) -> str:
        parts = [part for part in (self.prefix, 'attachments', attachment_id) if part]
        return '/'.join(parts)

    def _trash_key(self, key: str) -> str:
        encoded = base64.urlsafe_b64encode(key.encode()).decode().rstrip('=')
        return '/'.join(part for part in (self.prefix, '.trash', encoded) if part)

    def _original_key(self, quarantine_key: str) -> str:
        encoded = quarantine_key.rsplit('/', 1)[-1]
        padding = '=' * (-len(encoded) % 4)
        try:
            return base64.urlsafe_b64decode(encoded + padding).decode()
        except (binascii.Error, UnicodeDecodeError) as error:
            raise StorageError('Invalid quarantined object key') from error

    def _is_missing(self, error: ClientError) -> bool:
        return str(error.response.get('Error', {}).get('Code')) in {'404', 'NoSuchKey', 'NotFound'}

    def write(self, key: str, source: BinaryIO, *, max_size: int | None = None) -> int:
        size = 0
        with tempfile.SpooledTemporaryFile(max_size=MAX_FILE_SIZE) as body:
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                if max_size is not None and size > max_size:
                    raise FileTooLarge
                body.write(chunk)
            body.seek(0)
            self.client.upload_fileobj(body, self.bucket, key)
        return size

    def read(self, key: str) -> bytes:
        try:
            body = self.client.get_object(Bucket=self.bucket, Key=key)['Body']
        except ClientError as error:
            if self._is_missing(error):
                raise ObjectNotFound(key) from error
            raise
        try:
            return body.read()
        finally:
            body.close()

    def iter_chunks(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        try:
            body = self.client.get_object(Bucket=self.bucket, Key=key)['Body']
        except ClientError as error:
            if self._is_missing(error):
                raise ObjectNotFound(key) from error
            raise
        try:
            while chunk := body.read(chunk_size):
                yield chunk
        finally:
            body.close()

    def size(self, key: str) -> int:
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)['ContentLength']
        except ClientError as error:
            if self._is_missing(error):
                raise ObjectNotFound(key) from error
            raise

    def exists(self, key: str) -> bool:
        try:
            self.size(key)
            return True
        except ObjectNotFound:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def quarantine(self, keys: Iterable[str]) -> list[QuarantinedObject]:
        quarantined = []
        try:
            for key in keys:
                if not self.exists(key):
                    continue
                quarantine_key = self._trash_key(key)
                self.client.copy_object(
                    Bucket=self.bucket,
                    Key=quarantine_key,
                    CopySource={'Bucket': self.bucket, 'Key': key},
                )
                quarantined.append(QuarantinedObject(key, quarantine_key))
                self.delete(key)
        except Exception:
            self.restore(quarantined)
            raise
        return quarantined

    def restore(self, quarantined: Iterable[QuarantinedObject]) -> None:
        for item in reversed(list(quarantined)):
            if not self.exists(item.quarantine_key):
                continue
            self.client.copy_object(
                Bucket=self.bucket,
                Key=item.key,
                CopySource={'Bucket': self.bucket, 'Key': item.quarantine_key},
            )
            self.delete(item.quarantine_key)

    def discard(self, quarantined: Iterable[QuarantinedObject]) -> None:
        for item in quarantined:
            try:
                self.delete(item.quarantine_key)
            except Exception:
                pass

    def quarantined(self) -> list[QuarantinedObject]:
        trash_prefix = '/'.join(part for part in (self.prefix, '.trash') if part) + '/'
        paginator = self.client.get_paginator('list_objects_v2')
        items = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=trash_prefix):
            for entry in page.get('Contents', []):
                quarantine_key = entry['Key']
                items.append(QuarantinedObject(self._original_key(quarantine_key), quarantine_key))
        return items


def storage_from_env():
    backend = os.getenv('STORAGE_BACKEND', 'local').lower()
    if backend == 'local':
        return LocalStorage(STORAGE)
    if backend == 's3':
        bucket = os.getenv('S3_BUCKET')
        if not bucket:
            raise RuntimeError('S3_BUCKET is required when STORAGE_BACKEND=s3')
        return S3Storage(
            bucket,
            endpoint_url=os.getenv('S3_ENDPOINT_URL'),
            region=os.getenv('S3_REGION') or os.getenv('AWS_REGION'),
            prefix=os.getenv('S3_PREFIX', ''),
        )
    raise RuntimeError('STORAGE_BACKEND must be local or s3')


storage = storage_from_env()


QuarantinedFile = tuple[Path, Path]


def quarantine_files(ids: Iterable[str], root: Path = STORAGE) -> list[QuarantinedFile]:
    backend = LocalStorage(root)
    return [
        (backend._path(item.key), backend._path(item.quarantine_key))
        for item in backend.quarantine(ids)
    ]


def restore_quarantined(quarantined: Iterable[QuarantinedFile]) -> None:
    for source, destination in reversed(list(quarantined)):
        if destination.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            destination.replace(source)


def discard_quarantined(quarantined: Iterable[QuarantinedFile]) -> None:
    for _, destination in quarantined:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
