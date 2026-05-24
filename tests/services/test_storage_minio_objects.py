from types import SimpleNamespace

import pytest
from minio.error import S3Error

from src.services import storage_minio_objects


class _Logger:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, *args):
        self.errors.append(args)

    def warning(self, *args):
        self.warnings.append(args)


class _Response:
    def __init__(self, data: bytes):
        self._data = data
        self.closed = False
        self.released = False

    def read(self):
        return self._data

    def close(self):
        self.closed = True

    def release_conn(self):
        self.released = True


def test_upload_file_accepts_bucket_alias():
    calls = []
    logger = _Logger()
    service = SimpleNamespace(
        client=SimpleNamespace(
            fput_object=lambda bucket, object_name, file_path: calls.append(
                (bucket, object_name, file_path)
            )
        )
    )

    result = storage_minio_objects.upload_file(
        service,
        file_path="/tmp/demo.png",
        object_name="demo.png",
        bucket="templates",
        logger=logger,
    )

    assert result is True
    assert calls == [("templates", "demo.png", "/tmp/demo.png")]
    assert logger.errors == []


def test_get_file_bytes_closes_response():
    response = _Response(b"abc")
    logger = _Logger()
    service = SimpleNamespace(
        client=SimpleNamespace(get_object=lambda bucket, object_name: response)
    )

    result = storage_minio_objects.get_file_bytes(
        service,
        object_name="demo.png",
        bucket="bucket-a",
        logger=logger,
    )

    assert result == b"abc"
    assert response.closed is True
    assert response.released is True


def test_list_objects_filters_directories():
    logger = _Logger()
    service = SimpleNamespace(
        client=SimpleNamespace(
            list_objects=lambda *args, **kwargs: [
                SimpleNamespace(object_name="a/file.png", is_dir=False),
                SimpleNamespace(object_name="a/folder", is_dir=True),
            ]
        )
    )

    result = storage_minio_objects.list_objects(
        service,
        prefix="a/",
        bucket="bucket-a",
        logger=logger,
    )

    assert result == ["a/file.png"]


def test_object_exists_returns_false_for_missing_object():
    logger = _Logger()

    def _raise(*_args, **_kwargs):
        raise S3Error(
            code="NoSuchKey",
            message="missing",
            resource="bucket/object",
            request_id="req",
            host_id="host",
            response=None,
        )

    service = SimpleNamespace(client=SimpleNamespace(stat_object=_raise))

    result = storage_minio_objects.object_exists(
        service,
        bucket_name="bucket-a",
        object_name="missing.png",
        logger=logger,
    )

    assert result is False
    assert logger.warnings == []


@pytest.mark.asyncio
async def test_async_object_exists_delegates_to_thread(monkeypatch):
    logger = _Logger()
    service = SimpleNamespace(client=object())

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(storage_minio_objects.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(
        storage_minio_objects,
        "object_exists",
        lambda _service, *, bucket_name, object_name, logger: (
            bucket_name,
            object_name,
            logger is not None,
        ),
    )

    result = await storage_minio_objects.async_object_exists(
        service,
        bucket_name="bucket-a",
        object_name="demo.png",
        logger=logger,
    )

    assert result == ("bucket-a", "demo.png", True)
