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
async def test_prepare_task_inputs_downloads_ordered_character_panels():
    calls = []
    params = {
        "character_sheets": [
            "bucket/wang-panel.png",
            "bucket/man-panel.png",
        ]
    }

    async def process(**kwargs):
        calls.append((kwargs["param_key"], kwargs["img_filename"]))
        kwargs["params"][kwargs["param_key"]] = f"local-{kwargs['param_key']}.png"

    await prepare_task_inputs(
        params=params,
        downloaded_input_paths=[],
        process_single_input_asset_func=process,
    )

    assert calls == [
        ("character_sheet_1", "bucket/wang-panel.png"),
        ("character_sheet_2", "bucket/man-panel.png"),
    ]
    assert params["character_sheets"] == [
        "local-character_sheet_1.png",
        "local-character_sheet_2.png",
    ]


@pytest.mark.asyncio
async def test_prepare_task_inputs_preserves_five_ordered_images():
    calls = []
    params = {"images": [f"bucket/reference-{index}.png" for index in range(1, 6)]}

    async def process(**kwargs):
        calls.append((kwargs["param_key"], kwargs["img_filename"]))

    await prepare_task_inputs(
        params=params,
        downloaded_input_paths=[],
        process_single_input_asset_func=process,
    )

    assert calls == [
        ("image", "bucket/reference-1.png"),
        ("image2", "bucket/reference-2.png"),
        ("image3", "bucket/reference-3.png"),
        ("image4", "bucket/reference-4.png"),
        ("image5", "bucket/reference-5.png"),
    ]


@pytest.mark.asyncio
async def test_prepare_task_inputs_downloads_ltx_character_background():
    calls = []
    params = {"background_image": "web_uploads/user/scene.jpeg"}

    async def process(**kwargs):
        calls.append((kwargs["param_key"], kwargs["img_filename"]))
        kwargs["params"][kwargs["param_key"]] = "local-background.png"

    await prepare_task_inputs(
        params=params,
        downloaded_input_paths=[],
        process_single_input_asset_func=process,
    )

    assert calls == [
        ("background_image", "web_uploads/user/scene.jpeg"),
    ]
    assert params["background_image"] == "local-background.png"


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


@pytest.mark.asyncio
async def test_process_single_input_asset_records_the_exact_comfy_input_artifact(
    tmp_path,
):
    uploaded_input_artifacts = []

    def download(_object_name, local_path):
        with open(local_path, "wb") as handle:
            handle.write(b"image")

    async def upload(**_kwargs):
        assert _kwargs["upload_name"] == "task-1_uploads_demo.png"
        return {
            "name": "task-1_uploads_demo.png",
            "subfolder": "",
            "type": "input",
        }

    await process_single_input_asset(
        params={},
        downloaded_input_paths=[],
        uploaded_input_artifacts=uploaded_input_artifacts,
        comfy_filename_prefix="task-1",
        img_filename="uploads/demo.png",
        param_key="image",
        comfy_input_dir=str(tmp_path),
        download_input_func=download,
        should_normalize_image_input_func=_never_normalize,
        normalize_input_image_func=_identity_normalize,
        upload_prepared_input_func=upload,
        logger=logging.getLogger("test"),
    )

    assert len(uploaded_input_artifacts) == 1
    artifact = uploaded_input_artifacts[0]
    assert artifact.kind == "input"
    assert artifact.filename == "task-1_uploads_demo.png"
    assert artifact.subfolder == ""
