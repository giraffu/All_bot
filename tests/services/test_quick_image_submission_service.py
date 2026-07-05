from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.constants import (
    MODE_I2I_DRAW,
    MODE_IMG2IMG_LORA,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    MODE_RANDOM_FACESWAP,
)
from src.services.qqcc_config_service import (
    SCENE_PRESET_VERSION,
    normalize_qqcc_config,
)
from src.services.quick_image_submission_service import (
    DEFAULT_I2I_DRAW_UNDRESS_PROMPT,
    QuickImageSubmissionKind,
    QuickImageSubmissionRejectReason,
    build_quick_image_submission_plan,
    run_quick_image_submission_plan,
)


def test_qqcc_free_edit_v2_scene_builds_draw_chain_plan_without_prompts_ini():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "soft_light",
                    "name": "柔光写真",
                    "prompt": "soft light prompt",
                }
            ],
        }
    )

    plan = build_quick_image_submission_plan(
        fsm_data={
            "mode": MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
            "scene_id": "soft_light",
        },
        qqcc_config=config,
        image_path="/tmp/input.png",
    )

    assert plan.kind == QuickImageSubmissionKind.DRAW_CHAIN
    assert plan.mode == MODE_PORNMASTER_FLUX2_SINGLE_EDIT
    assert plan.task_type == MODE_PORNMASTER_FLUX2_SINGLE_EDIT
    assert plan.total_cost == 2
    assert plan.images == ["/tmp/input.png"]
    assert [scene["prompt"] for scene in plan.draw_chain] == ["soft light prompt"]


@pytest.mark.asyncio
async def test_run_qqcc_draw_chain_plan_submits_intermediate_hidden_then_final_visible():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "soft_light",
                    "name": "柔光写真",
                    "prompt": "soft light prompt",
                    "postprocess_draw_scene_id": "polish",
                },
                {
                    "id": "polish",
                    "name": "精修",
                    "prompt": "polish prompt",
                },
            ],
        }
    )
    plan = build_quick_image_submission_plan(
        fsm_data={
            "mode": MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
            "scene_id": "soft_light",
        },
        qqcc_config=config,
        image_path="/tmp/input.png",
    )
    process_calls = []

    async def fake_process_generation_task(**kwargs):
        process_calls.append(kwargs)
        return b"image-bytes", f"output-{len(process_calls)}.png"

    await run_quick_image_submission_plan(
        plan=plan,
        context=SimpleNamespace(),
        chat_id=456,
        user_id=123,
        username="tester",
        status_msg_id=77,
        process_generation_task_func=fake_process_generation_task,
        download_output_file_to_fsm_temp_func=AsyncMock(
            return_value="/tmp/intermediate.png"
        ),
    )

    assert process_calls[0]["prompt"] == "soft light prompt"
    assert process_calls[0]["send_result"] is False
    assert process_calls[0]["allow_contribute"] is False
    assert process_calls[1]["prompt"] == "polish prompt"
    assert process_calls[1]["images"] == ["/tmp/intermediate.png"]
    assert process_calls[1]["send_result"] is True
    assert process_calls[1]["allow_contribute"] is True


def test_qqcc_free_edit_lora_scene_keeps_lora_payload():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "realistic",
                    "name": "逼真质感",
                    "prompt": "realistic prompt",
                    "engine": "free_edit",
                    "lora_name": "qwen/YARN_1.0.safetensors",
                }
            ],
        }
    )

    plan = build_quick_image_submission_plan(
        fsm_data={"mode": MODE_IMG2IMG_LORA, "scene_id": "realistic"},
        qqcc_config=config,
        image_path="/tmp/input.png",
    )

    assert plan.kind == QuickImageSubmissionKind.DRAW_CHAIN
    assert plan.mode == MODE_IMG2IMG_LORA
    assert plan.draw_chain[0]["lora_name"] == "qwen/YARN_1.0.safetensors"


@pytest.mark.asyncio
async def test_run_lora_single_image_plan_adds_default_strength():
    plan = build_quick_image_submission_plan(
        fsm_data={
            "mode": MODE_IMG2IMG_LORA,
            "lora_name": "qwen/YARN_1.0.safetensors",
        },
        qqcc_config=None,
        image_path="/tmp/input.png",
        prompts_config={MODE_IMG2IMG_LORA: "lora prompt"},
    )
    process_task = AsyncMock(return_value=(None, None))

    await run_quick_image_submission_plan(
        plan=plan,
        context=SimpleNamespace(),
        chat_id=456,
        user_id=123,
        username="tester",
        status_msg_id=None,
        process_generation_task_func=process_task,
    )

    kwargs = process_task.await_args.kwargs
    assert kwargs["task_type"] == MODE_IMG2IMG_LORA
    assert kwargs["lora_name"] == "qwen/YARN_1.0.safetensors"
    assert kwargs["lora_strength"] == 0.3


def test_random_faceswap_filters_templates_and_builds_swap_images():
    plan = build_quick_image_submission_plan(
        fsm_data={"mode": MODE_RANDOM_FACESWAP, "cost": 1},
        qqcc_config=None,
        image_path="/tmp/face.png",
        prompts_config={"face_swap": "swap prompt"},
        template_files=[
            "quick_face/readme.txt",
            "quick_face/a.png",
            "quick_face/b.webp",
        ],
        random_choice_func=lambda files: files[-1],
        reply_markup="markup",
    )

    assert plan.kind == QuickImageSubmissionKind.RANDOM_FACESWAP
    assert plan.task_type == "face_swap"
    assert plan.prompt == "swap prompt"
    assert plan.images == ["template:quick_face/b.webp", "/tmp/face.png"]
    assert plan.cleanup is False
    assert plan.preserve_input_for_again is True
    assert plan.reply_markup == "markup"


def test_random_faceswap_returns_no_template_reject_for_empty_template_set():
    result = build_quick_image_submission_plan(
        fsm_data={"mode": MODE_RANDOM_FACESWAP, "cost": 1},
        qqcc_config=None,
        image_path="/tmp/face.png",
        prompts_config={"face_swap": "swap prompt"},
        template_files=["quick_face/readme.txt"],
    )

    assert result.reason == QuickImageSubmissionRejectReason.NO_TEMPLATE


def test_i2i_draw_compatibility_plan_uses_prompt_fallback():
    plan = build_quick_image_submission_plan(
        fsm_data={"mode": MODE_I2I_DRAW, "cost": 3},
        qqcc_config=None,
        image_path="/tmp/input.png",
        prompts_config={},
    )

    assert plan.kind == QuickImageSubmissionKind.SINGLE_IMAGE
    assert plan.task_type == MODE_I2I_DRAW
    assert plan.prompt == DEFAULT_I2I_DRAW_UNDRESS_PROMPT
    assert plan.images == ["/tmp/input.png"]


@pytest.mark.parametrize(
    ("config_override", "fsm_data", "reason"),
    [
        (
            {"main_buttons": {"ai_draw": False}},
            {"mode": MODE_PORNMASTER_FLUX2_SINGLE_EDIT, "scene_id": "soft_light"},
            QuickImageSubmissionRejectReason.FEATURE_DISABLED,
        ),
        (
            {"draw_scenes": []},
            {"mode": MODE_PORNMASTER_FLUX2_SINGLE_EDIT, "scene_id": "missing"},
            QuickImageSubmissionRejectReason.FEATURE_DISABLED,
        ),
        (
            {},
            {"mode": "unknown_mode", "cost": 2},
            QuickImageSubmissionRejectReason.UNSUPPORTED_MODE,
        ),
    ],
)
def test_invalid_or_disabled_submission_returns_reject(
    config_override,
    fsm_data,
    reason,
):
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "soft_light",
                    "name": "柔光写真",
                    "prompt": "soft light prompt",
                }
            ],
            **config_override,
        }
    )

    result = build_quick_image_submission_plan(
        fsm_data=fsm_data,
        qqcc_config=config if fsm_data["mode"] != "unknown_mode" else None,
        image_path="/tmp/input.png",
    )

    assert result.reason == reason
