from unittest.mock import MagicMock

import pytest

from src.core.task_core import (
    CoreDomainError,
    _prepare_task_submission_payload,
    _infer_requested_billing_resolution,
    _infer_requested_output_metadata,
    _process_input_path,
)
from src.core.task_core_types import VideoTaskRequest


@pytest.mark.asyncio
async def test_process_input_path_keeps_plain_object_key():
    user_logger = MagicMock()

    result = await _process_input_path(
        user_logger, "123456/input_images/example.png"
    )

    assert result == "123456/input_images/example.png"
    user_logger.save_input_image.assert_not_called()


@pytest.mark.asyncio
async def test_process_input_path_rejects_missing_absolute_local_file():
    user_logger = MagicMock()
    missing_path = "/tmp/does-not-exist-custom-video.png"

    with pytest.raises(CoreDomainError, match="本地输入文件不存在"):
        await _process_input_path(user_logger, missing_path)

    user_logger.save_input_image.assert_not_called()


@pytest.mark.asyncio
async def test_process_input_path_rejects_failed_local_upload(tmp_path):
    user_logger = MagicMock()
    local_file = tmp_path / "custom-video.png"
    local_file.write_bytes(b"fake-image")
    user_logger.save_input_image.return_value = ""

    with pytest.raises(CoreDomainError, match="本地输入文件上传失败"):
        await _process_input_path(user_logger, str(local_file))

    user_logger.save_input_image.assert_called_once_with(str(local_file))


def test_infer_requested_output_metadata_keeps_unknown_height_for_tier_based_video():
    assert _infer_requested_output_metadata(
        {"resolution": 1024, "duration": 8}
    ) == (1024, None, 8)


def test_infer_requested_output_metadata_parses_explicit_ltx_resolution():
    assert _infer_requested_output_metadata(
        {"resolution": "1280x704", "duration": "10s"}
    ) == (1280, 704, 10)


def test_infer_requested_billing_resolution_keeps_requested_tier():
    assert _infer_requested_billing_resolution({"resolution": 720}, "custom_video") == "720"


def test_infer_requested_billing_resolution_keeps_ltx_resolution_pair():
    assert (
        _infer_requested_billing_resolution(
            {"resolution": "1280x704"}, "ltx_video"
        )
        == "1280x704"
    )


@pytest.mark.asyncio
async def test_prepare_task_submission_payload_uses_default_prompt_and_applies_saved_inputs(
    monkeypatch,
):
    strategy = MagicMock()
    strategy.get_file_paths_to_upload.return_value = ["local/a.png", ""]
    strategy.get_metadata.return_value = {"style": "demo"}

    processed_paths = []

    async def fake_get_priority(user_id: int):
        assert user_id == 9
        return 3, "user", "title"

    async def fake_process_input_path(user_logger, path: str):
        processed_paths.append((user_logger.user_id, user_logger.username, path))
        return f"processed:{path}" if path else ""

    monkeypatch.setattr(
        "src.core.task_core.get_user_priority_and_identity",
        fake_get_priority,
    )
    monkeypatch.setattr(
        "src.core.task_core._process_input_path",
        fake_process_input_path,
    )
    monkeypatch.setattr(
        "src.core.task_core.load_prompts",
        lambda: {"face_swap": "默认提示词"},
    )

    inputs = {"target_image": "body.png", "prompt": "   "}
    result = await _prepare_task_submission_payload(
        user_id=9,
        username="tester",
        task_type="face_swap",
        inputs=inputs,
        strategy=strategy,
        base_priority=4,
        is_template=False,
        is_video_task=False,
        video_request=VideoTaskRequest(),
    )

    assert result.prompt == "默认提示词"
    assert result.saved_inputs == ["processed:local/a.png"]
    assert result.metadata == {"style": "demo"}
    assert result.final_priority == 7
    assert result.allow_contribute is True
    assert inputs["prompt"] == "默认提示词"
    assert inputs["saved_input_images"] == ["processed:local/a.png"]
    assert processed_paths == [(9, "tester", "local/a.png"), (9, "tester", "")]


@pytest.mark.asyncio
async def test_prepare_task_submission_payload_caps_priority_at_100(monkeypatch):
    strategy = MagicMock()
    strategy.get_file_paths_to_upload.return_value = []
    strategy.get_metadata.return_value = {}

    async def fake_get_priority(_user_id: int):
        return 60, "user", "title"

    async def fake_process_input_path(_user_logger, _path: str):
        return ""

    monkeypatch.setattr(
        "src.core.task_core.get_user_priority_and_identity",
        fake_get_priority,
    )
    monkeypatch.setattr(
        "src.core.task_core._process_input_path",
        fake_process_input_path,
    )
    monkeypatch.setattr("src.core.task_core.load_prompts", lambda: {})

    result = await _prepare_task_submission_payload(
        user_id=5,
        username="tester",
        task_type="custom_video",
        inputs={"prompt": "keep me"},
        strategy=strategy,
        base_priority=50,
        is_template=True,
        is_video_task=True,
        video_request=VideoTaskRequest(),
    )

    assert result.final_priority == 100
    assert result.prompt == "keep me"
    assert result.allow_contribute is False
