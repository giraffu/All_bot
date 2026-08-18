from types import SimpleNamespace

import pytest

from src.core.task_core_output_materialization import materialize_successful_task_output


@pytest.mark.asyncio
async def test_complete_durable_asset_metadata_skips_web_media_download_and_probe():
    calls = []

    async def unexpected_download(_task_id):
        calls.append("download")
        raise AssertionError("durable asset must not be downloaded")

    async def unexpected_probe(*_args):
        calls.append("probe")
        raise AssertionError("trusted worker metadata must avoid a storage probe")

    result = await materialize_successful_task_output(
        backend_task_id="backend-1",
        registry_task_id="registry-1",
        user_logger=SimpleNamespace(
            save_output_image=lambda *_args: (_ for _ in ()).throw(
                AssertionError("durable asset must not be copied")
            )
        ),
        is_video=False,
        result_path="task-results/backend-1/primary.png",
        result_asset={
            "object_key": "task-results/backend-1/primary.png",
            "sha256": "a" * 64,
            "byte_size": 123,
            "content_type": "image/png",
            "width": 512,
            "height": 768,
        },
        output_width=None,
        output_height=None,
        output_duration=None,
        extra_outputs={},
        download_result_func=unexpected_download,
        download_video_result_func=unexpected_download,
        extract_media_metadata_from_bytes_best_effort_func=lambda *_args: (
            None,
            None,
            None,
        ),
        extract_media_metadata_from_storage_best_effort_func=unexpected_probe,
    )

    assert result.output_file == "task-results/backend-1/primary.png"
    assert result.media_bytes is None
    assert (result.width, result.height, result.duration) == (512, 768, None)
    assert calls == []


@pytest.mark.asyncio
async def test_durable_worker_result_is_not_uploaded_again_under_user_namespace():
    saved = []
    user_logger = SimpleNamespace(
        save_output_image=lambda *args: saved.append(args) or "duplicate.png"
    )

    result = await materialize_successful_task_output(
        backend_task_id="backend-1",
        registry_task_id="registry-1",
        user_logger=user_logger,
        is_video=False,
        result_path="task-results/backend-1/primary.png",
        output_width=None,
        output_height=None,
        output_duration=None,
        extra_outputs={},
        download_result_func=lambda _task_id: _async_value(b"image"),
        download_video_result_func=lambda _task_id: _async_value(None),
        extract_media_metadata_from_bytes_best_effort_func=(
            lambda *_args: (512, 512, None)
        ),
        extract_media_metadata_from_storage_best_effort_func=(
            lambda *_args: _async_value((None, None, None))
        ),
    )

    assert result.output_file == "task-results/backend-1/primary.png"
    assert result.media_bytes == b"image"
    assert saved == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result_path",
    [
        "user-data-prod/task-results/backend-1/primary.png",
        "https://objects.example/user-data-prod/task-results/backend-1/primary.png?sig=x",
    ],
)
async def test_durable_worker_result_reference_is_canonicalized_before_history_persistence(
    monkeypatch, result_path
):
    from src import media_paths

    monkeypatch.setattr(media_paths, "MINIO_BUCKET", "user-data-prod")
    monkeypatch.setattr(media_paths, "MINIO_RESULT_BUCKET", "worker-results-prod")
    saved = []
    user_logger = SimpleNamespace(
        save_output_image=lambda *args: saved.append(args) or "duplicate.png"
    )

    result = await materialize_successful_task_output(
        backend_task_id="backend-1",
        registry_task_id="registry-1",
        user_logger=user_logger,
        is_video=False,
        result_path=result_path,
        output_width=None,
        output_height=None,
        output_duration=None,
        extra_outputs={},
        download_result_func=lambda _task_id: _async_value(b"image"),
        download_video_result_func=lambda _task_id: _async_value(None),
        extract_media_metadata_from_bytes_best_effort_func=lambda *_args: (512, 512, None),
        extract_media_metadata_from_storage_best_effort_func=lambda *_args: _async_value((None, None, None)),
    )

    assert result.output_file == "task-results/backend-1/primary.png"
    assert saved == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_video", "media_bytes", "expected_extension"),
    [
        (False, b"image", "png"),
        (True, b"video", "mp4"),
    ],
)
async def test_bot_fallback_persists_media_under_backend_task_id(
    is_video, media_bytes, expected_extension
):
    saved = []

    def save_output_image(data, task_id, extension):
        saved.append((data, task_id, extension))
        return f"task-results/{task_id}/primary.{extension}"

    result = await materialize_successful_task_output(
        backend_task_id="backend-1",
        registry_task_id="registry-1",
        user_logger=SimpleNamespace(save_output_image=save_output_image),
        is_video=is_video,
        result_path=None,
        output_width=None,
        output_height=None,
        output_duration=None,
        extra_outputs={},
        download_result_func=lambda _task_id: _async_value(
            None if is_video else media_bytes
        ),
        download_video_result_func=lambda _task_id: _async_value(
            media_bytes if is_video else None
        ),
        extract_media_metadata_from_bytes_best_effort_func=(
            lambda *_args: (512, 512, None)
        ),
        extract_media_metadata_from_storage_best_effort_func=(
            lambda *_args: _async_value((None, None, None))
        ),
    )

    assert result.output_file == (
        f"task-results/backend-1/primary.{expected_extension}"
    )
    assert saved == [(media_bytes, "backend-1", expected_extension)]


async def _async_value(value):
    return value
