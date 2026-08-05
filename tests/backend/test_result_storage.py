import hashlib
import io
from types import SimpleNamespace

import pytest

from app.result_storage import ResultPromotionError, promote_completion_assets


class FakeMinio:
    def __init__(self, objects):
        self.objects = dict(objects)
        self.copy_calls = []

    def stat_object(self, bucket, key):
        value = self.objects.get((bucket, key))
        if value is None:
            raise RuntimeError("not found")
        return SimpleNamespace(
            size=value["size"],
            metadata={"x-amz-meta-sha256": value["sha256"]},
            content_type=value.get("content_type", "application/octet-stream"),
        )

    def get_object(self, bucket, key):
        return io.BytesIO(self.objects[(bucket, key)]["data"])

    def copy_object(self, bucket, destination, source):
        self.copy_calls.append((bucket, destination, source.bucket_name, source.object_name))
        source_value = self.objects[(source.bucket_name, source.object_name)]
        self.objects[(bucket, destination)] = dict(source_value)


@pytest.mark.asyncio
async def test_promotes_staging_assets_before_returning_durable_completion():
    primary_key = "staging/worker-results/backend-1/primary.png"
    extra_key = "staging/worker-results/backend-1/extras/last_frame-0.png"
    primary_data = b"primary"
    extra_data = b"extra"
    primary_sha = hashlib.sha256(primary_data).hexdigest()
    extra_sha = hashlib.sha256(extra_data).hexdigest()
    client = FakeMinio(
        {
            ("user-data-prod", primary_key): {
                "size": 7,
                "sha256": primary_sha,
                "data": primary_data,
                "content_type": "image/png",
            },
            ("user-data-prod", extra_key): {
                "size": 5,
                "sha256": extra_sha,
                "data": extra_data,
                "content_type": "image/png",
            },
        }
    )

    promoted = await promote_completion_assets(
        task_id="backend-1",
        result_path=primary_key,
        extra_outputs={"last_frame": {"path": extra_key, "media_type": "image"}},
        result_asset={
            "staging_key": primary_key,
            "sha256": primary_sha,
            "byte_size": 7,
            "content_type": "image/png",
        },
        extra_output_assets={
            "last_frame": {
                "staging_key": extra_key,
                "sha256": extra_sha,
                "byte_size": 5,
                "content_type": "image/png",
                "media_type": "image",
                "ordinal": 0,
            }
        },
        minio_client=client,
        bucket="user-data-prod",
    )

    assert promoted.result_path == "task-results/backend-1/primary.png"
    assert promoted.extra_outputs == {
        "last_frame": {
            "path": "task-results/backend-1/extras/last_frame-0.png",
            "media_type": "image",
        }
    }
    assert len(client.copy_calls) == 2


@pytest.mark.asyncio
async def test_duplicate_promotion_is_idempotent_when_durable_sha_matches():
    staging = "staging/worker-results/backend-1/primary.png"
    durable = "task-results/backend-1/primary.png"
    durable_data = b"primary"
    durable_sha = hashlib.sha256(durable_data).hexdigest()
    client = FakeMinio(
        {
            ("user-data-prod", durable): {
                "size": 7,
                "sha256": durable_sha,
                "data": durable_data,
            },
        }
    )

    promoted = await promote_completion_assets(
        task_id="backend-1",
        result_path=staging,
        extra_outputs={},
        result_asset={
            "staging_key": staging,
            "sha256": durable_sha,
            "byte_size": 7,
            "content_type": "image/png",
        },
        extra_output_assets={},
        minio_client=client,
        bucket="user-data-prod",
    )

    assert promoted.result_path == durable
    assert client.copy_calls == []


@pytest.mark.asyncio
async def test_promotion_rejects_object_whose_bytes_do_not_match_sha_metadata():
    staging = "staging/worker-results/backend-1/primary.png"
    declared_sha = hashlib.sha256(b"expected").hexdigest()
    client = FakeMinio(
        {
            ("user-data-prod", staging): {
                "size": 8,
                "sha256": declared_sha,
                "data": b"tampered",
            }
        }
    )

    with pytest.raises(ResultPromotionError, match="SHA-256"):
        await promote_completion_assets(
            task_id="backend-1",
            result_path=staging,
            extra_outputs={},
            result_asset={
                "staging_key": staging,
                "sha256": declared_sha,
                "byte_size": 8,
                "content_type": "image/png",
            },
            extra_output_assets={},
            minio_client=client,
            bucket="user-data-prod",
        )


@pytest.mark.asyncio
async def test_promotion_fails_closed_on_bad_sha_or_wrong_staging_prefix():
    client = FakeMinio({})
    for staging_key in (
        "staging/worker-results/other-task/primary.png",
        "history/backend-1/original.png",
    ):
        with pytest.raises(ResultPromotionError):
            await promote_completion_assets(
                task_id="backend-1",
                result_path=staging_key,
                extra_outputs={},
                result_asset={
                    "staging_key": staging_key,
                    "sha256": "not-a-sha",
                    "byte_size": 7,
                    "content_type": "image/png",
                },
                extra_output_assets={},
                minio_client=client,
                bucket="user-data-prod",
            )


@pytest.mark.asyncio
async def test_legacy_worker_completion_remains_compatible_without_asset_contract():
    promoted = await promote_completion_assets(
        task_id="backend-1",
        result_path="legacy-flat.png",
        extra_outputs={"last_frame": {"path": "legacy-last.png"}},
        result_asset=None,
        extra_output_assets=None,
        minio_client=None,
        bucket="user-data-prod",
    )

    assert promoted.result_path == "legacy-flat.png"
    assert promoted.extra_outputs["last_frame"]["path"] == "legacy-last.png"
