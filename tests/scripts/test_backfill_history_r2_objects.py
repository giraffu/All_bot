import asyncio
from types import SimpleNamespace

import pytest

import scripts.backfill_history_r2_objects as backfill_module
from src.media_paths import MINIO_BUCKET
from scripts.backfill_history_r2_objects import (
    build_history_r2_candidate,
    build_input_file_candidates,
    collect_cloud_prod_lag_fix_history_ids,
    collect_web_visible_history_ids,
    process_history_r2_candidate,
    process_history_r2_candidates,
    select_hotset_batch,
    summarize_results,
)


async def fail_generate_thumbnail_from_r2_media(_media_r2_key, _media_type, _r2_key):
    raise AssertionError("test case should not generate thumbnails from R2 media")


class _ScalarResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _SequentialSession:
    def __init__(self, result_sets):
        self._result_sets = list(result_sets)

    async def execute(self, _stmt):
        if not self._result_sets:
            return _ScalarResult([])
        return _ScalarResult(self._result_sets.pop(0))


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


def test_build_history_r2_candidate_uses_flat_compatibility_keys_without_task_id():
    candidate = build_history_r2_candidate(
        history_id=2,
        user_id=22,
        username="compat-user",
        task_id=None,
        history_type="txt2img",
        output_file="123/output_images/compat.png",
    )

    assert candidate.media_type == "image"
    assert candidate.media_r2_key == "compat.png"
    assert candidate.thumbnail_r2_key == "compat_thumb.webp"


def test_build_input_file_candidates_skips_external_urls_and_dedupes():
    candidates = build_input_file_candidates(
        "bot-data/uploads/input.png|https://example.com/image.png|bot-data/uploads/input.png"
    )

    assert len(candidates) == 2
    assert candidates[0].file_path == "bot-data/uploads/input.png"
    assert candidates[0].source_bucket == MINIO_BUCKET
    assert candidates[0].source_object == "uploads/input.png"
    assert candidates[0].r2_key == "uploads/input.png"
    assert candidates[1].skip_reason == "external"


@pytest.mark.asyncio
async def test_collect_cloud_prod_lag_fix_history_ids_dedupes_in_priority_order():
    session = _SequentialSession(
        [
            [10, 9, 8],
            [9, 7],
            [6, 5],
            [10, 4],
            [3],
            [2],
            [1],
        ]
    )

    history_ids, source_counts = await collect_cloud_prod_lag_fix_history_ids(
        session,
        wave="first",
        total_limit=5,
    )

    assert history_ids == [10, 9, 8, 7, 6]
    assert source_counts["gallery_latest"] == {"raw": 3, "added": 3}
    assert source_counts["gallery_likes_top"] == {"raw": 2, "added": 1}
    assert source_counts["gallery_applied_top"] == {"raw": 2, "added": 1}
    assert source_counts["recent_history"] == {"raw": 0, "added": 0}


@pytest.mark.asyncio
async def test_collect_web_visible_history_ids_dedupes_visible_sources():
    session = _SequentialSession(
        [
            [10, 9, 8],
            [9, 7],
            [6, 5],
            [10, 4],
            [3],
        ]
    )

    history_ids, source_counts = await collect_web_visible_history_ids(
        session,
        recent_limit=8,
        total_limit=5,
    )

    assert history_ids == [10, 9, 8, 7, 6]
    assert source_counts["per_user_recent_visible_history"] == {"raw": 3, "added": 3}
    assert source_counts["all_gallery_posts"] == {"raw": 2, "added": 1}
    assert source_counts["history_favorites"] == {"raw": 2, "added": 1}
    assert source_counts["gallery_like_apply_interactions"] == {"raw": 0, "added": 0}


@pytest.mark.asyncio
async def test_collect_web_visible_history_ids_can_skip_recent_history():
    session = _SequentialSession(
        [
            [9, 7],
            [6, 5],
            [10, 4],
            [3],
        ]
    )

    history_ids, source_counts = await collect_web_visible_history_ids(
        session,
        recent_limit=8,
        include_per_user_recent=False,
        total_limit=5,
    )

    assert history_ids == [9, 7, 6, 5, 10]
    assert source_counts["per_user_recent_visible_history"] == {"raw": 0, "added": 0}
    assert source_counts["all_gallery_posts"] == {"raw": 2, "added": 2}
    assert source_counts["history_favorites"] == {"raw": 2, "added": 2}
    assert source_counts["gallery_like_apply_interactions"] == {"raw": 2, "added": 1}


def test_select_hotset_batch_skips_processed_history_ids():
    batch, skipped = select_hotset_batch(
        [10, 9, 8, 7, 6],
        batch_size=2,
        processed_history_ids={10, 9},
    )

    assert batch == [8, 7]
    assert skipped == 2


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
        generate_missing_thumbnails=True,
        async_object_exists_func=fake_async_object_exists,
        async_r2_object_exists_func=fake_async_r2_object_exists,
        async_copy_to_r2_func=fake_async_copy_to_r2,
        generate_and_upload_thumbnail_func=fake_generate_and_upload_thumbnail,
        generate_and_upload_thumbnail_from_r2_media_func=(
            fail_generate_thumbnail_from_r2_media
        ),
    )

    assert result.media_status == "would_upload"
    assert result.thumbnail_status == "would_generate"


@pytest.mark.asyncio
async def test_process_history_r2_candidate_times_out_source_probe(monkeypatch):
    monkeypatch.setattr(backfill_module, "HOTSET_EXISTS_TIMEOUT_SECONDS", 0.01)
    candidate = build_history_r2_candidate(
        history_id=3,
        user_id=33,
        username="A A",
        task_id="task-3",
        history_type="doggy_style",
        output_file="123/output_images/task-3.png",
    )

    async def slow_async_object_exists(_bucket_name, _object_name):
        await asyncio.sleep(0.05)
        return True

    async def fake_async_r2_object_exists(_object_name):
        return False

    async def fake_async_copy_to_r2(_bucket_name, _object_name, _r2_key):
        raise AssertionError("timed out source probe should not copy")

    result = await backfill_module.process_history_r2_candidate(
        candidate,
        apply_changes=True,
        media_only=False,
        generate_missing_thumbnails=False,
        async_object_exists_func=slow_async_object_exists,
        async_r2_object_exists_func=fake_async_r2_object_exists,
        async_copy_to_r2_func=fake_async_copy_to_r2,
        generate_and_upload_thumbnail_func=fail_generate_thumbnail_from_r2_media,
        generate_and_upload_thumbnail_from_r2_media_func=(
            fail_generate_thumbnail_from_r2_media
        ),
    )

    assert result.media_status == "source_missing"
    assert result.thumbnail_status == "source_missing"


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
        generate_missing_thumbnails=True,
        async_object_exists_func=fake_async_object_exists,
        async_r2_object_exists_func=fake_async_r2_object_exists,
        async_copy_to_r2_func=fake_async_copy_to_r2,
        generate_and_upload_thumbnail_func=fake_generate_and_upload_thumbnail,
        generate_and_upload_thumbnail_from_r2_media_func=(
            fail_generate_thumbnail_from_r2_media
        ),
    )

    assert result.media_status == "uploaded"
    assert result.thumbnail_status == "copied"
    assert copied == [
        (MINIO_BUCKET, "123/output_images/task-4.png", "history/task-4/original.png"),
        (
            MINIO_BUCKET,
            "123/output_images/task-4_thumb.webp",
            "history/task-4/thumb.webp",
        ),
    ]


@pytest.mark.asyncio
async def test_process_history_r2_candidate_does_not_overwrite_existing_r2_objects():
    candidate = build_history_r2_candidate(
        history_id=40,
        user_id=440,
        username="warm-user",
        task_id="task-warm",
        history_type="txt2img",
        output_file="123/output_images/task-warm.png",
    )

    async def fake_async_object_exists(_bucket_name, _object_name):
        return True

    async def fake_async_r2_object_exists(_object_name):
        return True

    async def fake_async_copy_to_r2(_bucket_name, _object_name, _r2_key):
        raise AssertionError("existing R2 objects must not be overwritten")

    async def fake_generate_and_upload_thumbnail(_output_file, _media_type, _r2_key):
        raise AssertionError("existing R2 thumbnails must not be regenerated")

    result = await process_history_r2_candidate(
        candidate,
        apply_changes=True,
        media_only=False,
        generate_missing_thumbnails=True,
        async_object_exists_func=fake_async_object_exists,
        async_r2_object_exists_func=fake_async_r2_object_exists,
        async_copy_to_r2_func=fake_async_copy_to_r2,
        generate_and_upload_thumbnail_func=fake_generate_and_upload_thumbnail,
        generate_and_upload_thumbnail_from_r2_media_func=(
            fail_generate_thumbnail_from_r2_media
        ),
    )

    assert result.media_status == "exists"
    assert result.thumbnail_status == "exists"


@pytest.mark.asyncio
async def test_process_history_r2_candidate_includes_input_file_copy_plan():
    candidate = build_history_r2_candidate(
        history_id=41,
        user_id=441,
        username="input-user",
        task_id="task-input",
        history_type="txt2img",
        output_file="123/output_images/task-input.png",
        input_file="bot-data/web_uploads/441/input.png|https://example.com/ref.png",
    )

    async def fake_async_object_exists(_bucket_name, object_name):
        return object_name in {
            "123/output_images/task-input.png",
            "123/output_images/task-input_thumb.webp",
            "web_uploads/441/input.png",
        }

    async def fake_async_r2_object_exists(object_name):
        return object_name in {
            "history/task-input/original.png",
            "history/task-input/thumb.webp",
        }

    async def fake_async_copy_to_r2(_bucket_name, _object_name, _r2_key):
        raise AssertionError("dry-run should not upload inputs")

    async def fake_generate_and_upload_thumbnail(_output_file, _media_type, _r2_key):
        raise AssertionError("existing thumbnail should not be generated")

    result = await process_history_r2_candidate(
        candidate,
        apply_changes=False,
        media_only=False,
        include_input_files=True,
        generate_missing_thumbnails=True,
        async_object_exists_func=fake_async_object_exists,
        async_r2_object_exists_func=fake_async_r2_object_exists,
        async_copy_to_r2_func=fake_async_copy_to_r2,
        generate_and_upload_thumbnail_func=fake_generate_and_upload_thumbnail,
        generate_and_upload_thumbnail_from_r2_media_func=(
            fail_generate_thumbnail_from_r2_media
        ),
    )

    assert result.media_status == "exists"
    assert result.thumbnail_status == "exists"
    assert [input_result.status for input_result in result.input_results] == [
        "would_upload",
        "skipped_external",
    ]
    summary = summarize_results([result], apply_changes=False)
    assert summary.input_would_upload == 1
    assert summary.input_skipped_external == 1


@pytest.mark.asyncio
async def test_process_history_r2_candidates_passes_include_input_files():
    candidate = build_history_r2_candidate(
        history_id=42,
        user_id=442,
        username="batch-input-user",
        task_id="task-batch-input",
        history_type="txt2img",
        output_file="123/output_images/task-batch-input.png",
        input_file="bot-data/web_uploads/442/input.png",
    )

    async def fake_async_object_exists(_bucket_name, object_name):
        return object_name in {
            "123/output_images/task-batch-input.png",
            "123/output_images/task-batch-input_thumb.webp",
            "web_uploads/442/input.png",
        }

    async def fake_async_r2_object_exists(object_name):
        return object_name in {
            "history/task-batch-input/original.png",
            "history/task-batch-input/thumb.webp",
        }

    async def fake_async_copy_to_r2(_bucket_name, _object_name, _r2_key):
        raise AssertionError("dry-run should not upload inputs")

    async def fake_generate_and_upload_thumbnail(_output_file, _media_type, _r2_key):
        raise AssertionError("existing thumbnail should not be generated")

    results = await process_history_r2_candidates(
        [candidate],
        concurrency=1,
        apply_changes=False,
        media_only=False,
        include_input_files=True,
        generate_missing_thumbnails=True,
        async_object_exists_func=fake_async_object_exists,
        async_r2_object_exists_func=fake_async_r2_object_exists,
        async_copy_to_r2_func=fake_async_copy_to_r2,
        generate_and_upload_thumbnail_func=fake_generate_and_upload_thumbnail,
        generate_and_upload_thumbnail_from_r2_media_func=(
            fail_generate_thumbnail_from_r2_media
        ),
    )

    assert [input_result.status for input_result in results[0].input_results] == [
        "would_upload"
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
        generate_missing_thumbnails=True,
        async_object_exists_func=fake_async_object_exists,
        async_r2_object_exists_func=fake_async_r2_object_exists,
        async_copy_to_r2_func=fake_async_copy_to_r2,
        generate_and_upload_thumbnail_func=fake_generate_and_upload_thumbnail,
        generate_and_upload_thumbnail_from_r2_media_func=(
            fail_generate_thumbnail_from_r2_media
        ),
    )

    assert result.media_status == "uploaded"
    assert result.thumbnail_status == "skipped"
