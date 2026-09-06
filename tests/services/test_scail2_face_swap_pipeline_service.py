from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.scail2_face_swap_pipeline_service import (
    build_scail2_first_frame_object_key,
    prepare_scail2_face_swap_first_frame,
    process_bot_scail2_face_swap_pipeline,
)


class FakeStorage:
    def __init__(self, *, downloaded_bytes: bytes = b"video"):
        self.downloaded_bytes = downloaded_bytes
        self.downloads = []
        self.uploads = []

    def download_file(self, bucket_name: str, object_name: str, file_path: str):
        self.downloads.append((bucket_name, object_name))
        Path(file_path).write_bytes(self.downloaded_bytes)

    def upload_file(
        self,
        file_path: str,
        object_name: str,
        bucket_name: str | None = None,
    ):
        self.uploads.append(
            (
                Path(file_path).read_bytes(),
                object_name,
                bucket_name,
            )
        )
        return object_name


def _fake_extract(video_path: Path, output_path: Path) -> None:
    assert video_path.read_bytes() == b"video"
    output_path.write_bytes(b"first-frame")


def test_build_scail2_first_frame_object_key_is_deterministic():
    assert build_scail2_first_frame_object_key(123, "root-task") == (
        "123/pipeline_inputs/root-task_scail2_face_swap_first_frame.png"
    )


@pytest.mark.asyncio
async def test_bot_pipeline_fails_closed_without_generation_executor():
    prepare_first_frame = AsyncMock()

    with pytest.raises(RuntimeError, match="generation executor is not configured"):
        await process_bot_scail2_face_swap_pipeline(
            context=SimpleNamespace(),
            chat_id=456,
            user_id=789,
            internal_user_id=123,
            username="tester",
            reference_image_path="/tmp/reference.png",
            motion_video_path="/tmp/motion.mp4",
            prompt="keep scene",
            duration=5,
            message_id=99,
            cleanup=True,
            source_post_id=None,
            normal_priority=7,
            cost=40,
            prepare_first_frame_func=prepare_first_frame,
            process_scail2_stage_func=AsyncMock(),
        )

    prepare_first_frame.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_first_frame_uses_local_bot_video_and_uploads_hidden_object(
    tmp_path,
):
    video_path = tmp_path / "motion.mp4"
    video_path.write_bytes(b"video")
    storage = FakeStorage()

    object_key = await prepare_scail2_face_swap_first_frame(
        internal_user_id=123,
        registry_task_id="root-task",
        motion_video_path=str(video_path),
        storage_service=storage,
        bucket_name="user-data-test",
        extract_first_frame_func=_fake_extract,
    )

    assert object_key == (
        "123/pipeline_inputs/root-task_scail2_face_swap_first_frame.png"
    )
    assert storage.downloads == []
    assert storage.uploads == [
        (
            b"first-frame",
            object_key,
            "user-data-test",
        )
    ]


@pytest.mark.asyncio
async def test_prepare_first_frame_downloads_web_object_before_extraction():
    storage = FakeStorage()

    object_key = await prepare_scail2_face_swap_first_frame(
        internal_user_id=123,
        registry_task_id="root-task",
        motion_video_path="user-data-test/123/input_images/motion.mp4",
        storage_service=storage,
        bucket_name="user-data-test",
        extract_first_frame_func=_fake_extract,
    )

    assert storage.downloads == [
        ("user-data-test", "123/input_images/motion.mp4")
    ]
    assert storage.uploads[0][1] == object_key


@pytest.mark.asyncio
async def test_prepare_first_frame_propagates_download_failure_without_upload():
    class FailingDownloadStorage(FakeStorage):
        def download_file(self, bucket_name: str, object_name: str, file_path: str):
            raise OSError("object download failed")

    storage = FailingDownloadStorage()

    with pytest.raises(OSError, match="object download failed"):
        await prepare_scail2_face_swap_first_frame(
            internal_user_id=123,
            registry_task_id="root-task",
            motion_video_path="123/input_images/missing.mp4",
            storage_service=storage,
            bucket_name="user-data-test",
            extract_first_frame_func=_fake_extract,
        )

    assert storage.uploads == []


@pytest.mark.asyncio
async def test_prepare_first_frame_propagates_ffmpeg_failure_without_upload(tmp_path):
    video_path = tmp_path / "motion.mp4"
    video_path.write_bytes(b"video")
    storage = FakeStorage()

    def fail_extraction(_video_path: Path, _output_path: Path) -> None:
        raise RuntimeError("ffmpeg failed")

    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        await prepare_scail2_face_swap_first_frame(
            internal_user_id=123,
            registry_task_id="root-task",
            motion_video_path=str(video_path),
            storage_service=storage,
            bucket_name="user-data-test",
            extract_first_frame_func=fail_extraction,
        )

    assert storage.uploads == []


@pytest.mark.asyncio
async def test_bot_pipeline_prioritizes_face_swap_and_normally_queues_video_stage():
    prepare_first_frame = AsyncMock(return_value="123/pipeline_inputs/frame.png")
    process_image = AsyncMock(
        return_value=(None, "123/output_images/swapped-frame.png")
    )
    download_output = AsyncMock(return_value="/tmp/swapped-frame.png")
    process_scail2 = AsyncMock(return_value=(b"video", "123/output/video.mp4"))
    runtime_state = SimpleNamespace(registry_task_id="root-bot-task")
    cleanup_first_frame = AsyncMock(return_value=True)

    result = await process_bot_scail2_face_swap_pipeline(
        context=SimpleNamespace(),
        chat_id=456,
        user_id=789,
        internal_user_id=123,
        username="tester",
        reference_image_path="/tmp/reference.png",
        motion_video_path="/tmp/motion.mp4",
        prompt="keep scene",
        duration=5,
        message_id=99,
        cleanup=True,
        source_post_id=None,
        normal_priority=7,
        cost=40,
        prepare_first_frame_func=prepare_first_frame,
        process_generation_task_func=process_image,
        download_output_file_func=download_output,
        process_scail2_stage_func=process_scail2,
        runtime_state=runtime_state,
        cleanup_first_frame_func=cleanup_first_frame,
    )

    assert result == (b"video", "123/output/video.mp4")
    assert process_image.await_args.kwargs["base_priority"] == 100
    assert process_image.await_args.kwargs["cost_override"] == 40
    assert process_image.await_args.kwargs["task_type"] == "face_swap_v2"
    assert process_image.await_args.kwargs["images"] == [
        "123/pipeline_inputs/frame.png",
        "/tmp/reference.png",
        "/tmp/motion.mp4",
    ]
    assert process_image.await_args.kwargs["result_meta"][
        "_scail2_face_swap_continuation"
    ]["normal_priority"] == 7
    stage2 = process_scail2.await_args.kwargs
    assert stage2["reference_preprocessed"] is True
    assert stage2["base_priority"] == 7
    assert stage2["deduct_quota"] is False
    assert stage2["cost_override"] == 0
    assert stage2["user_cancel_allowed"] is False
    assert stage2["history_reference_image_path"] == "/tmp/reference.png"
    cleanup_first_frame.assert_awaited_once_with(
        "123/pipeline_inputs/frame.png"
    )


@pytest.mark.asyncio
async def test_bot_pipeline_refunds_root_once_when_video_stage_has_no_output():
    refund_root = AsyncMock()

    await process_bot_scail2_face_swap_pipeline(
        context=SimpleNamespace(),
        chat_id=456,
        user_id=789,
        internal_user_id=123,
        username="tester",
        reference_image_path="/tmp/reference.png",
        motion_video_path="/tmp/motion.mp4",
        prompt="keep scene",
        duration=5,
        message_id=99,
        cleanup=True,
        source_post_id=None,
        normal_priority=7,
        cost=40,
        prepare_first_frame_func=AsyncMock(return_value="hidden-frame.png"),
        process_generation_task_func=AsyncMock(
            return_value=(None, "swapped-frame.png")
        ),
        download_output_file_func=AsyncMock(
            return_value="/tmp/swapped-frame.png"
        ),
        process_scail2_stage_func=AsyncMock(return_value=(None, None)),
        runtime_state=SimpleNamespace(registry_task_id="root-bot-task"),
        cleanup_first_frame_func=AsyncMock(return_value=True),
        refund_root_func=refund_root,
    )

    refund_root.assert_awaited_once_with(
        internal_user_id=123,
        username="tester",
        cost=40,
        registry_task_id="root-bot-task",
    )
