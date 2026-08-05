from types import SimpleNamespace

import pytest

from src.core.task_core_output_materialization import materialize_successful_task_output


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


async def _async_value(value):
    return value
