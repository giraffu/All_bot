from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.services import storage_r2_transfer


class _FakeResponse:
    def __init__(self, content_type="image/png"):
        self.headers = {"Content-Type": content_type}
        self.closed = False
        self.released = False

    def close(self):
        self.closed = True

    def release_conn(self):
        self.released = True


def test_sync_upload_to_r2_marks_cache_and_closes_response():
    response = _FakeResponse()
    service = SimpleNamespace(
        client=SimpleNamespace(get_object=MagicMock(return_value=response)),
        r2_client=SimpleNamespace(upload_fileobj=MagicMock()),
        r2_bucket="gallery-r2",
        mark_r2_object_exists=MagicMock(),
        invalidate_r2_exists_cache=MagicMock(),
    )
    logger = MagicMock()

    ok = storage_r2_transfer.sync_upload_to_r2(
        service,
        bucket_name="bot-data",
        object_name="history/task-1/original.png",
        r2_object_name="history/task-1/original.png",
        logger=logger,
    )

    assert ok is True
    service.r2_client.upload_fileobj.assert_called_once()
    service.mark_r2_object_exists.assert_called_once_with("history/task-1/original.png")
    assert response.closed is True
    assert response.released is True


@pytest.mark.asyncio
async def test_async_copy_to_r2_returns_false_without_client():
    service = SimpleNamespace(r2_client=None)

    ok = await storage_r2_transfer.async_copy_to_r2(
        service,
        bucket_name="bot-data",
        object_name="history/task-1/original.png",
        logger=MagicMock(),
    )

    assert ok is False


def test_get_r2_public_url_normalizes_slashes():
    assert (
        storage_r2_transfer.get_r2_public_url(
            object_name="/history/task-1/original.png",
            public_domain="https://cdn.example.com/",
        )
        == "https://cdn.example.com/history/task-1/original.png"
    )
