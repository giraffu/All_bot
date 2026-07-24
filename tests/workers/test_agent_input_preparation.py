import logging
import time

import pytest

from workers.comfy_agent.agent_input_preparation import (
    prepare_task_inputs,
    process_single_input_asset,
)


async def _noop_upload(**_kwargs):
    return None


def _never_normalize(_param_key, _object_name):
    return False


def _identity_normalize(path):
    return path


@pytest.mark.asyncio
async def test_prepare_task_inputs_downloads_character_sheet_reference():
    calls = []

    async def process(**kwargs):
        calls.append((kwargs["param_key"], kwargs["img_filename"]))

    await prepare_task_inputs(
        params={"character_sheet": "bucket/private-character.png"},
        downloaded_input_paths=[],
        process_single_input_asset_func=process,
    )

    assert calls == [("character_sheet", "bucket/private-character.png")]


@pytest.mark.asyncio
async def test_process_single_input_asset_times_out_download(tmp_path):
    def slow_download(_object_name, _local_path):
        time.sleep(0.2)

    with pytest.raises(RuntimeError, match="Failed to prepare video input"):
        await process_single_input_asset(
            params={},
            downloaded_input_paths=[],
            img_filename="uploads/demo.mp4",
            param_key="video",
            comfy_input_dir=str(tmp_path),
            download_input_func=slow_download,
            should_normalize_image_input_func=_never_normalize,
            normalize_input_image_func=_identity_normalize,
            upload_prepared_input_func=_noop_upload,
            logger=logging.getLogger("test"),
            download_timeout_seconds=0.01,
            download_retry_attempts=1,
            download_retry_delay_seconds=0,
        )


@pytest.mark.asyncio
async def test_process_single_input_asset_cleans_partial_download_on_failure(tmp_path):
    def failing_download(_object_name, local_path):
        (tmp_path / "uploads_demo.mp4.abc.part.minio").write_bytes(b"partial")
        raise OSError("broken stream")

    with pytest.raises(RuntimeError, match="Failed to prepare video input"):
        await process_single_input_asset(
            params={},
            downloaded_input_paths=[],
            img_filename="uploads/demo.mp4",
            param_key="video",
            comfy_input_dir=str(tmp_path),
            download_input_func=failing_download,
            should_normalize_image_input_func=_never_normalize,
            normalize_input_image_func=_identity_normalize,
            upload_prepared_input_func=_noop_upload,
            logger=logging.getLogger("test"),
            download_timeout_seconds=1,
            download_retry_attempts=1,
            download_retry_delay_seconds=0,
        )

    assert not list(tmp_path.glob("*.part.minio"))
