from types import SimpleNamespace

import pytest

from scripts.backfill_history_r2_objects import (
    build_history_r2_candidate,
    process_history_r2_candidate,
    summarize_results,
)


def test_build_history_r2_candidate_prefers_history_namespace_keys():
    candidate = build_history_r2_candidate(
        history_id=1,
        user_id=11,
        username="A A",
        task_id="task-1",
        history_type="custom_video",
        output_file="123/output_images/task-1.mp4",
    )

    assert candidate.media_type == "video"
    assert candidate.media_r2_key == "history/task-1/original.mp4"
    assert candidate.thumbnail_r2_key == "history/task-1/thumb.jpg"
    assert candidate.thumbnail_source_object == "123/output_images/task-1_thumb.jpg"


def test_build_history_r2_candidate_falls_back_to_legacy_keys_without_task_id():
    candidate = build_history_r2_candidate(
        history_id=2,
        user_id=22,
        username="legacy-user",
        task_id=None,
        history_type="txt2img",
        output_file="123/output_images/legacy.png",
    )

    assert candidate.media_type == "image"
    assert candidate.media_r2_key == "legacy.png"
    assert candidate.thumbnail_r2_key == "legacy_thumb.webp"


@pytest.mark.asyncio
async def test_process_history_r2_candidate_plans_upload_and_thumbnail_generation():
    candidate = build_history_r2_candidate(
        history_id=3,
        user_id=33,
        username="A A",
        task_id="task-3",
        history_type="doggy_style",
        output_file="123/output_images/task-3.mp4",
    )

    async def fake_async_object_exists(bucket_name, object_name):
        if object_name == "123/output_images/task-3.mp4":
            return True
        if object_name == "123/output_images/task-3_thumb.jpg":
            return False
        raise AssertionError(f"unexpected object probe: {bucket_name}/{object_name}")

    async def fake_async_r2_object_exists(_object_name):
        return False

    async def fake_async_copy_to_r2(_bucket_name, _object_name, _r2_key):
        raise AssertionError("dry-run should not upload")

    async def fake_generate_and_upload_thumbnail(_output_file, _media_type, _r2_key):
        raise AssertionError("dry-run should not generate thumbnail")

    result = await process_history_r2_candidate(
        candidate,
        apply_changes=False,
        media_only=False,
        async_object_exists_func=fake_async_object_exists,
        async_r2_object_exists_func=fake_async_r2_object_exists,
        async_copy_to_r2_func=fake_async_copy_to_r2,
        generate_and_upload_thumbnail_func=fake_generate_and_upload_thumbnail,
    )

    assert result.media_status == "would_upload"
    assert result.thumbnail_status == "would_generate"


@pytest.mark.asyncio
async def test_process_history_r2_candidate_applies_copy_and_copy_thumbnail():
    candidate = build_history_r2_candidate(
        history_id=4,
        user_id=44,
        username="fav-user",
        task_id="task-4",
        history_type="txt2img",
        output_file="123/output_images/task-4.png",
    )
    copied = []

    async def fake_async_object_exists(_bucket_name, object_name):
        return object_name in {
            "123/output_images/task-4.png",
            "123/output_images/task-4_thumb.webp",
        }

    async def fake_async_r2_object_exists(_object_name):
        return False

    async def fake_async_copy_to_r2(bucket_name, object_name, r2_key):
        copied.append((bucket_name, object_name, r2_key))
        return True

    async def fake_generate_and_upload_thumbnail(_output_file, _media_type, _r2_key):
        raise AssertionError("existing thumbnail should be copied instead of generated")

    result = await process_history_r2_candidate(
        candidate,
        apply_changes=True,
        media_only=False,
        async_object_exists_func=fake_async_object_exists,
        async_r2_object_exists_func=fake_async_r2_object_exists,
        async_copy_to_r2_func=fake_async_copy_to_r2,
        generate_and_upload_thumbnail_func=fake_generate_and_upload_thumbnail,
    )

    assert result.media_status == "uploaded"
    assert result.thumbnail_status == "copied"
    assert copied == [
        ("bot-data", "123/output_images/task-4.png", "history/task-4/original.png"),
        ("bot-data", "123/output_images/task-4_thumb.webp", "history/task-4/thumb.webp"),
    ]


def test_summarize_results_counts_dry_run_statuses():
    candidate = build_history_r2_candidate(
        history_id=5,
        user_id=55,
        username="A A",
        task_id="task-5",
        history_type="custom_video",
        output_file="123/output_images/task-5.mp4",
    )
    summary = summarize_results(
        [
            SimpleNamespace(
                candidate=candidate,
                media_status="would_upload",
                thumbnail_status="would_generate",
            ),
            SimpleNamespace(
                candidate=candidate,
                media_status="exists",
                thumbnail_status="exists",
            ),
        ],
        apply_changes=False,
    )

    assert summary.mode == "dry-run"
    assert summary.scanned == 2
    assert summary.media_would_upload == 1
    assert summary.thumbnail_would_generate == 1
    assert summary.media_exists == 1
    assert summary.thumbnail_exists == 1
    assert summary.thumbnail_skipped == 0


@pytest.mark.asyncio
async def test_process_history_r2_candidate_media_only_skips_thumbnail_work():
    candidate = build_history_r2_candidate(
        history_id=6,
        user_id=66,
        username="A A",
        task_id="task-6",
        history_type="custom_video",
        output_file="123/output_images/task-6.mp4",
    )

    async def fake_async_object_exists(_bucket_name, object_name):
        return object_name == "123/output_images/task-6.mp4"

    async def fake_async_r2_object_exists(_object_name):
        return False

    async def fake_async_copy_to_r2(_bucket_name, _object_name, _r2_key):
        return True

    async def fake_generate_and_upload_thumbnail(_output_file, _media_type, _r2_key):
        raise AssertionError("media-only should skip thumbnail generation")

    result = await process_history_r2_candidate(
        candidate,
        apply_changes=True,
        media_only=True,
        async_object_exists_func=fake_async_object_exists,
        async_r2_object_exists_func=fake_async_r2_object_exists,
        async_copy_to_r2_func=fake_async_copy_to_r2,
        generate_and_upload_thumbnail_func=fake_generate_and_upload_thumbnail,
    )

    assert result.media_status == "uploaded"
    assert result.thumbnail_status == "skipped"
