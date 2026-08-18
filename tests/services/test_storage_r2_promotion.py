import io
import threading
import time
from types import SimpleNamespace

import pytest

from src.services import storage_r2_promotion as promotion
from src.services.storage_r2_promotion import (
    StagedInputPromotionError,
    promote_staged_user_inputs,
)


class FakeClient:
    def __init__(self):
        self.objects = {
            ("user-data-prod", "staging/user-uploads/42/upload-1.png"): {
                "data": b"input-bytes!",
                "metadata": {},
            },
        }
        self.copies = []
        self.get_calls = []

    def stat_object(self, bucket, key):
        if (bucket, key) not in self.objects:
            raise RuntimeError("not found")
        value = self.objects[(bucket, key)]
        return SimpleNamespace(
            size=len(value["data"]),
            metadata=value.get("metadata") or {},
            checksum_sha256=value.get("native_checksum"),
        )

    def get_object(self, bucket, key):
        self.get_calls.append((bucket, key))
        return io.BytesIO(self.objects[(bucket, key)]["data"])

    def copy_object(self, bucket, key, source, **kwargs):
        self.copies.append(
            (bucket, key, source.bucket_name, source.object_name, kwargs)
        )
        source_value = self.objects[(source.bucket_name, source.object_name)]
        self.objects[(bucket, key)] = {
            **source_value,
            "metadata": kwargs.get("metadata") or source_value.get("metadata") or {},
        }


@pytest.mark.asyncio
async def test_promotes_only_current_users_staged_inputs_and_preserves_other_refs():
    client = FakeClient()
    promoted = await promote_staged_user_inputs(
        input_refs=[
            "https://user-data-prod.objects.example/staging/user-uploads/42/upload-1.png?sig=hidden",
            "existing/durable.png",
        ],
        task_id="registry-1",
        user_id=42,
        bucket="user-data-prod",
        client=client,
    )

    assert promoted == [
        "task-inputs/registry-1/0.png",
        "existing/durable.png",
    ]
    assert client.copies == [
        (
            "user-data-prod",
            "task-inputs/registry-1/0.png",
            "user-data-prod",
            "staging/user-uploads/42/upload-1.png",
            {
                "metadata": {
                    "sha256": "1d5cb02923dbb6ee9c021d871afebdc4722f8933251db20fa4d2c3dba2013bd4"
                },
                "metadata_directive": "REPLACE",
            },
        )
    ]
    assert client.get_calls == [
        ("user-data-prod", "staging/user-uploads/42/upload-1.png")
    ]


@pytest.mark.asyncio
async def test_rejects_cross_user_staging_reference():
    with pytest.raises(StagedInputPromotionError):
        await promote_staged_user_inputs(
            input_refs=["staging/user-uploads/99/upload-1.png"],
            task_id="registry-1",
            user_id=42,
            bucket="user-data-prod",
            client=FakeClient(),
        )


@pytest.mark.asyncio
async def test_existing_durable_input_must_match_full_sha_not_only_size():
    client = FakeClient()
    client.objects[("user-data-prod", "task-inputs/registry-1/0.png")] = {
        "data": b"other-bytes!",
        "metadata": {},
    }

    with pytest.raises(StagedInputPromotionError, match="different content"):
        await promote_staged_user_inputs(
            input_refs=["staging/user-uploads/42/upload-1.png"],
            task_id="registry-1",
            user_id=42,
            bucket="user-data-prod",
            client=client,
        )


@pytest.mark.asyncio
async def test_durable_head_failure_is_not_treated_as_missing(monkeypatch):
    client = FakeClient()
    original_stat = client.stat_object

    def failing_stat(bucket, key):
        if key.startswith("task-inputs/"):
            raise RuntimeError("connection reset")
        return original_stat(bucket, key)

    monkeypatch.setattr(client, "stat_object", failing_stat)

    with pytest.raises(StagedInputPromotionError, match="status is unavailable"):
        await promote_staged_user_inputs(
            input_refs=["staging/user-uploads/42/upload-1.png"],
            task_id="registry-1",
            user_id=42,
            bucket="user-data-prod",
            client=client,
        )

    assert client.copies == []


@pytest.mark.asyncio
async def test_native_input_checksum_avoids_application_level_source_read():
    client = FakeClient()
    source = client.objects[
        ("user-data-prod", "staging/user-uploads/42/upload-1.png")
    ]
    source["native_checksum"] = (
        "1d5cb02923dbb6ee9c021d871afebdc4722f8933251db20fa4d2c3dba2013bd4"
    )

    await promote_staged_user_inputs(
        input_refs=["staging/user-uploads/42/upload-1.png"],
        task_id="registry-1",
        user_id=42,
        bucket="user-data-prod",
        client=client,
    )

    assert client.get_calls == []


@pytest.mark.asyncio
async def test_multi_input_promotion_uses_bounded_concurrency_and_preserves_order(
    monkeypatch,
):
    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_promote_one(*, source_key, **_kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.03)
        with lock:
            active -= 1

    monkeypatch.setattr(promotion, "_promote_one", fake_promote_one)
    refs = [f"staging/user-uploads/42/input-{index}.png" for index in range(6)]

    promoted = await promote_staged_user_inputs(
        input_refs=refs,
        task_id="registry-1",
        user_id=42,
        bucket="user-data-prod",
        client=object(),
    )

    assert promoted == [
        f"task-inputs/registry-1/{index}.png" for index in range(6)
    ]
    assert max_active == 3
