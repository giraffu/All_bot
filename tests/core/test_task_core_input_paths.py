from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.task_core_input_preparation import (
    prepare_task_submission_payload,
    process_input_path,
)
from src.core.task_core_video_request import (
    build_video_task_request,
    infer_requested_billing_resolution,
    infer_requested_output_metadata,
)
from src.core.task_core_types import (
    CoreDomainError,
    TaskSubmissionContext,
    VideoTaskRequest,
)


@pytest.mark.asyncio
async def test_process_input_path_keeps_plain_object_key():
    user_logger = MagicMock()

    result = await process_input_path(
        user_logger=user_logger,
        path="123456/input_images/example.png",
        bucket_name="bot-data",
    )

    assert result == "123456/input_images/example.png"
    user_logger.save_input_image.assert_not_called()


@pytest.mark.asyncio
async def test_process_input_path_rejects_missing_absolute_local_file():
    user_logger = MagicMock()
    missing_path = "/tmp/does-not-exist-custom-video.png"

    with pytest.raises(CoreDomainError, match="本地输入文件不存在"):
        await process_input_path(
            user_logger=user_logger,
            path=missing_path,
            bucket_name="bot-data",
        )

    user_logger.save_input_image.assert_not_called()


@pytest.mark.asyncio
async def test_process_input_path_rejects_failed_local_upload(tmp_path):
    user_logger = MagicMock()
    local_file = tmp_path / "custom-video.png"
    local_file.write_bytes(b"fake-image")
    user_logger.save_input_image.return_value = ""

    with pytest.raises(CoreDomainError, match="本地输入文件上传失败"):
        await process_input_path(
            user_logger=user_logger,
            path=str(local_file),
            bucket_name="bot-data",
        )

    user_logger.save_input_image.assert_called_once_with(str(local_file))


def test_infer_requested_output_metadata_keeps_unknown_height_for_tier_based_video():
    assert infer_requested_output_metadata(
        {"resolution": 1024, "duration": 8}
    ) == (1024, None, 8)


def test_infer_requested_output_metadata_parses_explicit_ltx_resolution():
    assert infer_requested_output_metadata(
        {"resolution": "1280x704", "duration": "10s"}
    ) == (1280, 704, 10)


def test_infer_requested_billing_resolution_keeps_requested_tier():
    assert (
        infer_requested_billing_resolution({"resolution": 720}, "custom_video")
        == "standard"
    )


def test_infer_requested_billing_resolution_keeps_ltx_resolution_pair():
    assert (
        infer_requested_billing_resolution(
            {"resolution": "1280x704"}, "ltx_video"
        )
        == "1280x704"
    )


@pytest.mark.parametrize(
    "task_type",
    ["face_video", "face_video_step1", "face_video_step2"],
)
def test_build_video_task_request_allows_face_video_legacy_frame_duration_at_1024p(
    task_type,
):
    request = build_video_task_request(
        task_type,
        {"resolution": 1024, "duration": 121},
    )

    assert request.output_width == 1024
    assert request.output_duration == 121
    assert request.requested_duration == 121
    assert request.billing_resolution == "1024"


def test_build_video_task_request_still_rejects_standard_1024p_10s_combo():
    with pytest.raises(CoreDomainError, match="Cannot select 1024p resolution"):
        build_video_task_request(
            "image_to_video",
            {"resolution": 1024, "duration": 10},
        )


@pytest.mark.parametrize("task_type", ["ltx_video_v2", "ltx_video_v2_flf2v"])
@pytest.mark.parametrize("duration", [10, 15, 20])
def test_build_video_task_request_allows_ltx_v2_1280x704_at_supported_durations(
    task_type,
    duration,
):
    request = build_video_task_request(
        task_type,
        {"resolution": "1280x704", "duration": duration},
    )

    assert request.output_width == 1280
    assert request.output_height == 704
    assert request.output_duration == duration
    assert request.requested_duration == duration


@pytest.mark.asyncio
async def test_prepare_task_submission_payload_uses_default_prompt_and_applies_saved_inputs():
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

    inputs = {"target_image": "body.png", "prompt": "   "}
    result = await prepare_task_submission_payload(
        user_id=9,
        username="tester",
        task_type="face_swap",
        inputs=inputs,
        strategy=strategy,
        base_priority=4,
        is_template=False,
        is_video_task=False,
        video_request=VideoTaskRequest(),
        user_logger_factory=lambda user_id, username: SimpleNamespace(
            user_id=user_id, username=username
        ),
        validate_local_input_paths_func=lambda **_kwargs: None,
        get_user_priority_and_identity_func=fake_get_priority,
        load_prompts_func=lambda: {"face_swap": "默认提示词"},
        process_input_path_func=fake_process_input_path,
        bucket_name="bot-data",
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
async def test_prepare_task_submission_payload_promotes_strategy_inputs_before_history():
    strategy = MagicMock()
    strategy.get_file_paths_to_upload.return_value = [
        "staging/user-uploads/9/body.png",
        "staging/user-uploads/9/face.png",
    ]
    strategy.get_metadata.side_effect = lambda inputs: {
        "saved_inputs": list(inputs["saved_input_images"])
    }
    promote = AsyncMock(
        return_value=[
            "task-inputs/registry-1/0.png",
            "task-inputs/registry-1/1.png",
        ]
    )

    async def fake_get_priority(_user_id: int):
        return 0, "user", "title"

    async def keep_object_key(user_logger, path: str):
        assert user_logger.user_id == 9
        return path

    inputs = {
        "target_image": "staging/user-uploads/9/body.png",
        "face_image": "staging/user-uploads/9/face.png",
        "prompt": "swap",
    }
    result = await prepare_task_submission_payload(
        user_id=9,
        username="tester",
        task_type="face_swap",
        inputs=inputs,
        registry_task_id="registry-1",
        strategy=strategy,
        base_priority=0,
        is_template=False,
        is_video_task=False,
        video_request=VideoTaskRequest(),
        user_logger_factory=lambda user_id, username: SimpleNamespace(
            user_id=user_id, username=username
        ),
        validate_local_input_paths_func=lambda **_kwargs: None,
        get_user_priority_and_identity_func=fake_get_priority,
        load_prompts_func=lambda: {},
        process_input_path_func=keep_object_key,
        promote_staged_inputs_func=promote,
        bucket_name="user-data-prod",
    )

    promote.assert_awaited_once_with(
        input_refs=[
            "staging/user-uploads/9/body.png",
            "staging/user-uploads/9/face.png",
        ],
        task_id="registry-1",
        user_id=9,
    )
    assert result.saved_inputs == [
        "task-inputs/registry-1/0.png",
        "task-inputs/registry-1/1.png",
    ]
    assert result.metadata["saved_inputs"] == result.saved_inputs
    assert inputs["saved_input_images"] == result.saved_inputs


@pytest.mark.asyncio
async def test_prepare_task_submission_payload_caps_priority_at_100():
    strategy = MagicMock()
    strategy.get_file_paths_to_upload.return_value = []
    strategy.get_metadata.return_value = {}

    async def fake_get_priority(_user_id: int):
        return 60, "user", "title"

    async def fake_process_input_path(_user_logger, _path: str):
        return ""

    result = await prepare_task_submission_payload(
        user_id=5,
        username="tester",
        task_type="custom_video",
        inputs={"prompt": "keep me"},
        strategy=strategy,
        base_priority=50,
        is_template=True,
        is_video_task=True,
        video_request=VideoTaskRequest(),
        user_logger_factory=lambda user_id, username: SimpleNamespace(
            user_id=user_id, username=username
        ),
        validate_local_input_paths_func=lambda **_kwargs: None,
        get_user_priority_and_identity_func=fake_get_priority,
        load_prompts_func=lambda: {},
        process_input_path_func=fake_process_input_path,
        bucket_name="bot-data",
    )

    assert result.final_priority == 100
    assert result.prompt == "keep me"
    assert result.allow_contribute is False


def test_task_submission_context_keeps_history_prompt_clean_and_runtime_lora_structured():
    submission_context = SimpleNamespace(
        user_id=9,
        username="tester",
    )
    context = TaskSubmissionContext(
        task_type="img2img_lora",
        is_video_task=False,
        user_logger=submission_context,
        prompt="cinematic portrait",
        saved_inputs=["demo/input.png"],
        metadata={
            "saved_inputs": ["demo/input.png"],
            "lora_name": "qwen/YARN_1.0.safetensors",
            "lora_strength": 0.35,
        },
        allow_contribute=True,
        final_priority=7,
        video_request=VideoTaskRequest(),
    )

    assert context.log_prompt == "cinematic portrait"
