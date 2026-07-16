from src.services import task_service_entrypoint_support as support


def test_build_task_inputs_merges_common_and_extra_fields():
    inputs = support.build_task_inputs(
        prompt="hello",
        images=["a.png"],
        resolution=512,
        duration=5,
        lora_name="foo",
        lora_strength=0.8,
    )

    assert inputs == {
        "prompt": "hello",
        "images": ["a.png"],
        "resolution": 512,
        "duration": 5,
        "lora_name": "foo",
        "lora_strength": 0.8,
    }


def test_resolve_video_billing_args_returns_empty_for_non_video():
    args = support.resolve_video_billing_args(
        is_video=False,
        resolution=512,
        task_type="image",
        duration=5,
    )

    assert args == {"billing_resolution": None, "requested_duration": None}


def test_resolve_video_billing_args_applies_duration_transform():
    args = support.resolve_video_billing_args(
        is_video=True,
        resolution="720p",
        task_type="custom_video",
        duration="5s",
        duration_transform=lambda value: 5 if value == "5s" else 0,
    )

    assert args["billing_resolution"] == "standard"
    assert args["requested_duration"] == 5


def test_resolve_video_billing_args_respects_allowed_task_types():
    args = support.resolve_video_billing_args(
        is_video=True,
        resolution=512,
        task_type="video",
        duration=5,
        allowed_task_types=("custom_video", "video_lora"),
    )

    assert args["billing_resolution"] == "512"
    assert args["requested_duration"] is None


def test_resolve_video_billing_args_can_skip_requested_duration():
    args = support.resolve_video_billing_args(
        is_video=True,
        resolution=512,
        task_type="face_video",
        duration=5,
        include_requested_duration=False,
    )

    assert args["billing_resolution"] == "512"
    assert args["requested_duration"] is None


def test_build_log_prompt_keeps_user_prompt_clean_when_runtime_metadata_is_structured():
    prompt = support.build_log_prompt(
        "base prompt",
        resolution="720p",
        duration="5s",
        lora_name="foo",
        task_type="video_lora",
        lora_task_types=("video_lora", "img2img_lora"),
    )

    assert prompt == "base prompt"


def test_build_cleanup_paths_filters_empty_values():
    assert support.build_cleanup_paths(["a.png", None, "", "b.mp4"]) == ["a.png", "b.mp4"]
    assert support.build_cleanup_paths([None, ""]) is None


def test_build_unexpected_error_log_message_supports_default_and_processing_verbs():
    assert (
        support.build_unexpected_error_log_message("custom video task")
        == "Error in custom video task for user {internal_user_id}: {error}"
    )
    assert (
        support.build_unexpected_error_log_message("face video task", verb="processing")
        == "Error processing face video task for {internal_user_id}: {error}"
    )
