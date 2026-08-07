import io
from types import SimpleNamespace

import pytest

from src.services.storage_r2_promotion import (
    StagedInputPromotionError,
    promote_staged_user_inputs,
)


class FakeClient:
    def __init__(self):
        self.objects = {
            ("user-data-prod", "staging/user-uploads/42/upload-1.png"): b"input-bytes!",
        }
        self.copies = []

    def stat_object(self, bucket, key):
        if (bucket, key) not in self.objects:
            raise RuntimeError("not found")
        return SimpleNamespace(size=len(self.objects[(bucket, key)]))

    def get_object(self, bucket, key):
        return io.BytesIO(self.objects[(bucket, key)])

    def copy_object(self, bucket, key, source):
        self.copies.append((bucket, key, source.bucket_name, source.object_name))
        self.objects[(bucket, key)] = self.objects[(source.bucket_name, source.object_name)]


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
        )
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
    client.objects[("user-data-prod", "task-inputs/registry-1/0.png")] = b"other-bytes!"

    with pytest.raises(StagedInputPromotionError, match="different content"):
        await promote_staged_user_inputs(
            input_refs=["staging/user-uploads/42/upload-1.png"],
            task_id="registry-1",
            user_id=42,
            bucket="user-data-prod",
            client=client,
        )
