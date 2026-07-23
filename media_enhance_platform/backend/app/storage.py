from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import BinaryIO

import boto3

from .config import get_settings


class Storage:
    async def put_file(self, key: str, path: Path, content_type: str) -> None:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        raise NotImplementedError

    async def open_bytes(self, key: str) -> bytes:
        raise NotImplementedError


class LocalStorage(Storage):
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("invalid object key")
        return path

    async def put_file(self, key: str, path: Path, content_type: str) -> None:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, path, destination)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)

    async def open_bytes(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)


class S3Storage(Storage):
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )

    async def ensure_bucket(self) -> None:
        def ensure() -> None:
            try:
                self.client.head_bucket(Bucket=self.bucket)
            except Exception:
                self.client.create_bucket(Bucket=self.bucket)

        await asyncio.to_thread(ensure)

    async def put_file(self, key: str, path: Path, content_type: str) -> None:
        await asyncio.to_thread(
            self.client.upload_file,
            str(path),
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(
            self.client.delete_object, Bucket=self.bucket, Key=key
        )

    async def open_bytes(self, key: str) -> bytes:
        response = await asyncio.to_thread(
            self.client.get_object, Bucket=self.bucket, Key=key
        )
        return await asyncio.to_thread(response["Body"].read)


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        settings = get_settings()
        _storage = (
            S3Storage()
            if settings.storage_backend == "s3"
            else LocalStorage(settings.local_storage_path)
        )
    return _storage
