import asyncio
import threading
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from src.services.storage import StorageService


@pytest.fixture
def storage_service():
    service = StorageService()
    service._init_r2_runtime_state()
    service.r2_client = MagicMock()
    service.r2_bucket = "unit-test-bucket"
    yield service
    service._init_r2_runtime_state()


def test_r2_not_found_is_cacheable_negative_result(storage_service):
    storage_service.r2_client.head_object.side_effect = ClientError(
        {
            "Error": {"Code": "404", "Message": "Not Found"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        },
        "HeadObject",
    )

    exists, cacheable = storage_service._r2_object_exists_with_cache_hint("missing-key")

    assert exists is False
    assert cacheable is True


def test_r2_exists_cache_trim_handles_three_value_entries(storage_service):
    storage_service._r2_exists_cache_max_entries = 2
    storage_service._r2_exists_cache["expired-key"] = (True, 1.0, 1.0)

    storage_service._set_r2_exists_cache("fresh-key-1", True)
    storage_service._set_r2_exists_cache("fresh-key-2", True)

    assert "expired-key" not in storage_service._r2_exists_cache
    assert storage_service._get_r2_exists_cache("fresh-key-1") is True
    assert storage_service._get_r2_exists_cache("fresh-key-2") is True


@pytest.mark.asyncio
async def test_async_r2_object_exists_does_not_cache_transient_failures(storage_service):
    storage_service.r2_client.head_object.side_effect = [
        ClientError(
            {
                "Error": {"Code": "500", "Message": "Temporary failure"},
                "ResponseMetadata": {"HTTPStatusCode": 500},
            },
            "HeadObject",
        ),
        {},
    ]

    first = await storage_service.async_r2_object_exists("flaky-key")
    second = await storage_service.async_r2_object_exists("flaky-key")

    assert first is False
    assert second is True
    assert storage_service.r2_client.head_object.call_count == 2
    assert storage_service._get_r2_exists_cache("flaky-key") is True


@pytest.mark.asyncio
async def test_async_r2_object_exists_shields_shared_probe_from_cancellation(
    storage_service,
):
    started = threading.Event()
    release = threading.Event()
    call_count = 0

    def slow_head(_object_name: str):
        nonlocal call_count
        call_count += 1
        started.set()
        release.wait(timeout=2)
        return True, True

    storage_service._r2_object_exists_with_cache_hint = slow_head

    first_waiter = asyncio.create_task(storage_service.async_r2_object_exists("shared-key"))

    await asyncio.to_thread(started.wait, 1)
    first_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_waiter

    second_waiter = asyncio.create_task(storage_service.async_r2_object_exists("shared-key"))
    release.set()

    assert await second_waiter is True
    assert call_count == 1
    assert storage_service._get_r2_exists_cache("shared-key") is True


@pytest.mark.asyncio
async def test_async_r2_object_exists_does_not_override_newer_positive_cache(
    storage_service,
):
    started = threading.Event()
    release = threading.Event()

    def stale_negative_probe(_object_name: str):
        started.set()
        release.wait(timeout=2)
        return False, True

    storage_service._r2_object_exists_with_cache_hint = stale_negative_probe

    probe_task = asyncio.create_task(storage_service.async_r2_object_exists("race-key"))
    await asyncio.to_thread(started.wait, 1)

    storage_service.mark_r2_object_exists("race-key")
    release.set()

    assert await probe_task is True
    assert storage_service._get_r2_exists_cache("race-key") is True
