from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import quick_image_submission_service as quick_image_service
from src.constants import (
    MODE_FACE_SWAP_V2,
    MODE_I2I_DRAW,
    MODE_IMG2IMG_LORA,
    MODE_PORNMASTER_FLUX2_EDIT_BF16,
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
    quick_image_plan_requires_continuation,
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
                    "negative_prompt": "bad hands",
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
    assert plan.display_mode_name == "柔光写真"
    assert plan.result_meta == {
        "_qqcc_regenerate": {
            "kind": "quick_image",
            "mode": MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
            "scene_id": "soft_light",
            "scene_kind": "draw",
            "display_mode_name": "柔光写真",
        }
    }
    assert [scene["prompt"] for scene in plan.draw_chain] == ["soft light prompt"]
    assert [scene["negative_prompt"] for scene in plan.draw_chain] == ["bad hands"]


def test_qqcc_free_edit_v3_scene_builds_bf16_plan_with_six_credit_cost():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "bf16_portrait",
                    "name": "自由P图 v3",
                    "prompt": "high precision portrait",
                    "engine": "free_edit_v3",
                }
            ],
        }
    )

    plan = build_quick_image_submission_plan(
        fsm_data={
            "mode": MODE_PORNMASTER_FLUX2_EDIT_BF16,
            "scene_id": "bf16_portrait",
        },
        qqcc_config=config,
        image_path="/tmp/input.png",
    )

    assert plan.task_type == MODE_PORNMASTER_FLUX2_EDIT_BF16
    assert plan.total_cost == 6
    assert plan.images == ["/tmp/input.png"]


@pytest.mark.asyncio
async def test_run_qqcc_single_step_draw_chain_stays_cancellable_with_normal_priority():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "soft_light",
                    "name": "柔光写真",
                    "prompt": "soft light prompt",
                    "negative_prompt": "bad hands",
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
    process_calls = []

    async def fake_process_generation_task(**kwargs):
        process_calls.append(kwargs)
        return b"image-bytes", "output.png"

    await run_quick_image_submission_plan(
        plan=plan,
        context=SimpleNamespace(
            bot_data={
                "bot_client_type": "bot:qqcc-private:7",
                "private_qqcc_bot_id": 7,
            }
        ),
        chat_id=456,
        user_id=123,
        username="tester",
        status_msg_id=77,
        process_generation_task_func=fake_process_generation_task,
    )

    assert len(process_calls) == 1
    assert process_calls[0]["send_result"] is True
    assert process_calls[0]["allow_cancel"] is True
    assert process_calls[0]["user_cancel_allowed"] is True
    assert process_calls[0]["base_priority"] == 0


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
                    "negative_prompt": "bad hands",
                    "postprocess_draw_scene_id": "polish",
                },
                {
                    "id": "polish",
                    "name": "精修",
                    "prompt": "polish prompt",
                    "negative_prompt": "bad anatomy",
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
    assert process_calls[0]["negative_prompt"] == "bad hands"
    assert process_calls[0]["send_result"] is False
    assert process_calls[0]["allow_contribute"] is False
    assert process_calls[0]["allow_cancel"] is True
    assert process_calls[0]["user_cancel_allowed"] is True
    assert process_calls[0]["base_priority"] == 0
    assert process_calls[1]["prompt"] == "polish prompt"
    assert process_calls[1]["negative_prompt"] == "bad anatomy"
    assert process_calls[1]["images"] == ["/tmp/intermediate.png"]
    assert process_calls[1]["send_result"] is True
    assert process_calls[1]["allow_contribute"] is False
    assert process_calls[1]["allow_cancel"] is False
    assert process_calls[1]["user_cancel_allowed"] is False
    assert process_calls[1]["base_priority"] == 100
    assert process_calls[1]["display_mode_name_override"] == "柔光写真"
    assert process_calls[1]["result_meta"] == plan.result_meta


@pytest.mark.asyncio
async def test_private_qqcc_draw_chain_uses_durable_continuation_before_dispatch(
    monkeypatch,
):
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "first",
                    "name": "第一步",
                    "prompt": "first prompt",
                    "postprocess_draw_scene_id": "second",
                },
                {
                    "id": "second",
                    "name": "第二步",
                    "prompt": "second prompt",
                },
            ],
        }
    )
    plan = build_quick_image_submission_plan(
        fsm_data={
            "mode": MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
            "scene_id": "first",
        },
        qqcc_config=config,
        image_path="/tmp/input.png",
    )
    process_task = AsyncMock()
    create_checkpoint = AsyncMock(
        return_value=SimpleNamespace(chain_id="chain-image-1")
    )
    resume_checkpoint = AsyncMock()
    persist_input = AsyncMock(return_value="inputs/original.png")
    monkeypatch.setattr(
        quick_image_service,
        "create_private_qqcc_continuation",
        create_checkpoint,
    )
    monkeypatch.setattr(
        quick_image_service,
        "resume_private_qqcc_continuation",
        resume_checkpoint,
    )
    monkeypatch.setattr(
        quick_image_service,
        "persist_private_qqcc_continuation_input",
        persist_input,
    )

    assert quick_image_plan_requires_continuation(plan) is True
    context = SimpleNamespace(
        bot_data={
            "bot_client_type": "bot:qqcc-private:7",
            "private_qqcc_bot_id": 7,
        }
    )
    await run_quick_image_submission_plan(
        plan=plan,
        context=context,
        chat_id=456,
        user_id=123,
        username="tester",
        status_msg_id=77,
        process_generation_task_func=process_task,
    )

    process_task.assert_not_awaited()
    stages = create_checkpoint.await_args.kwargs["stages"]
    assert create_checkpoint.await_args.kwargs["original_input_ref"] == (
        "inputs/original.png"
    )
    assert create_checkpoint.await_args.kwargs["original_input_durable"] is True
    assert len(stages) == 2
    assert stages[0]["task_kwargs"]["send_result"] is False
    assert stages[0]["task_kwargs"]["user_cancel_allowed"] is True
    assert stages[1]["task_kwargs"]["send_result"] is True
    assert stages[1]["task_kwargs"]["user_cancel_allowed"] is False
    resume_checkpoint.assert_awaited_once()
    resume_kwargs = resume_checkpoint.await_args.kwargs
    assert resume_kwargs["chain_id"] == "chain-image-1"
    assert resume_kwargs["context"] is context
    assert resume_kwargs["store"] is None
    assert callable(resume_kwargs["execute_stage_func"])


def test_private_qqcc_original_face_swap_step_requires_continuation():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "face_restore",
                    "name": "保留原脸",
                    "prompt": "draw prompt",
                    "original_face_swap_enabled": True,
                }
            ],
        }
    )
    plan = build_quick_image_submission_plan(
        fsm_data={
            "mode": MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
            "scene_id": "face_restore",
        },
        qqcc_config=config,
        image_path="/tmp/input.png",
    )

    assert quick_image_plan_requires_continuation(plan) is True


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


def test_qqcc_filter_scene_builds_draw_chain_plan_with_filter_scene_kind():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "filter_scenes": [
                {
                    "id": "real_skin",
                    "name": "真实质感",
                    "prompt": "real skin prompt",
                    "negative_prompt": "plastic skin",
                }
            ],
        }
    )

    plan = build_quick_image_submission_plan(
        fsm_data={
            "mode": MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
            "scene_id": "real_skin",
            "scene_kind": "filter",
        },
        qqcc_config=config,
        image_path="/tmp/input.png",
    )

    assert plan.kind == QuickImageSubmissionKind.DRAW_CHAIN
    assert plan.total_cost == 2
    assert plan.display_mode_name == "真实质感"
    assert plan.draw_chain[0]["prompt"] == "real skin prompt"
    assert plan.draw_chain[0]["negative_prompt"] == "plastic skin"
    assert plan.result_meta == {
        "_qqcc_regenerate": {
            "kind": "quick_image",
            "mode": MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
            "scene_id": "real_skin",
            "scene_kind": "filter",
            "display_mode_name": "真实质感",
        }
    }


@pytest.mark.asyncio
async def test_run_qqcc_draw_scene_can_postprocess_with_filter_template():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "filter_scenes": [
                {
                    "id": "real_skin",
                    "name": "真实质感",
                    "prompt": "real skin prompt",
                    "negative_prompt": "plastic skin",
                }
            ],
            "draw_scenes": [
                {
                    "id": "soft_light",
                    "name": "柔光写真",
                    "prompt": "soft light prompt",
                    "negative_prompt": "bad hands",
                    "postprocess_filter_scene_id": "real_skin",
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

    assert [scene["id"] for scene in plan.draw_chain] == ["soft_light", "real_skin"]
    assert plan.total_cost == 4
    assert plan.display_mode_name == "柔光写真"
    assert plan.result_meta["_qqcc_regenerate"]["scene_kind"] == "draw"
    assert process_calls[0]["prompt"] == "soft light prompt"
    assert process_calls[0]["send_result"] is False
    assert process_calls[1]["prompt"] == "real skin prompt"
    assert process_calls[1]["negative_prompt"] == "plastic skin"
    assert process_calls[1]["send_result"] is True
    assert process_calls[1]["display_mode_name_override"] == "柔光写真"


@pytest.mark.asyncio
async def test_run_qqcc_draw_chain_inserts_original_face_swap_after_enabled_step():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "soft_light",
                    "name": "柔光写真",
                    "prompt": "soft light prompt",
                    "negative_prompt": "bad hands",
                    "original_face_swap_enabled": True,
                    "postprocess_draw_scene_id": "polish",
                },
                {
                    "id": "polish",
                    "name": "精修",
                    "prompt": "polish prompt",
                    "negative_prompt": "bad anatomy",
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
    downloaded = []

    async def fake_process_generation_task(**kwargs):
        process_calls.append(kwargs)
        return b"image-bytes", f"output-{len(process_calls)}.png"

    async def fake_download_output_file_to_fsm_temp(**kwargs):
        downloaded.append(kwargs)
        return f"/tmp/download-{len(downloaded)}.png"

    assert plan.total_cost == 6

    await run_quick_image_submission_plan(
        plan=plan,
        context=SimpleNamespace(),
        chat_id=456,
        user_id=123,
        username="tester",
        status_msg_id=77,
        process_generation_task_func=fake_process_generation_task,
        download_output_file_to_fsm_temp_func=fake_download_output_file_to_fsm_temp,
    )

    assert [call["task_type"] for call in process_calls] == [
        MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
        MODE_FACE_SWAP_V2,
        MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    ]
    assert [call["allow_cancel"] for call in process_calls] == [
        True,
        False,
        False,
    ]
    assert [call["user_cancel_allowed"] for call in process_calls] == [
        True,
        False,
        False,
    ]
    assert [call["base_priority"] for call in process_calls] == [0, 100, 100]
    assert [call["show_queue_status"] for call in process_calls] == [
        True,
        False,
        False,
    ]
    assert process_calls[0]["send_result"] is False
    assert process_calls[0]["negative_prompt"] == "bad hands"
    assert process_calls[1]["images"] == ["/tmp/download-1.png", "/tmp/input.png"]
    assert "negative_prompt" not in process_calls[1]
    assert process_calls[1]["cost_override"] == 2
    assert process_calls[1]["send_result"] is False
    assert process_calls[2]["images"] == ["/tmp/download-2.png"]
    assert process_calls[2]["prompt"] == "polish prompt"
    assert process_calls[2]["negative_prompt"] == "bad anatomy"
    assert process_calls[2]["send_result"] is True


@pytest.mark.asyncio
async def test_run_qqcc_draw_chain_visible_final_face_swap_keeps_draw_result_semantics():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "draw_scenes": [
                {
                    "id": "soft_light",
                    "name": "柔光写真",
                    "prompt": "soft light prompt",
                    "original_face_swap_enabled": True,
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
    process_calls = []

    async def fake_process_generation_task(**kwargs):
        process_calls.append(kwargs)
        return b"image-bytes", f"output-{len(process_calls)}.png"

    assert plan.total_cost == 4

    await run_quick_image_submission_plan(
        plan=plan,
        context=SimpleNamespace(),
        chat_id=456,
        user_id=123,
        username="tester",
        status_msg_id=77,
        process_generation_task_func=fake_process_generation_task,
        download_output_file_to_fsm_temp_func=AsyncMock(
            return_value="/tmp/generated.png"
        ),
    )

    assert [call["task_type"] for call in process_calls] == [
        MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
        MODE_FACE_SWAP_V2,
    ]
    assert process_calls[0]["send_result"] is False
    assert process_calls[0]["allow_cancel"] is True
    assert process_calls[0]["user_cancel_allowed"] is True
    assert process_calls[0]["base_priority"] == 0
    assert process_calls[0]["show_queue_status"] is True
    assert process_calls[1]["send_result"] is True
    assert process_calls[1]["allow_cancel"] is False
    assert process_calls[1]["user_cancel_allowed"] is False
    assert process_calls[1]["base_priority"] == 100
    assert process_calls[1]["show_queue_status"] is False
    assert process_calls[1]["result_task_type"] == MODE_PORNMASTER_FLUX2_SINGLE_EDIT
    assert process_calls[1]["result_prompt"] == "soft light prompt"
    assert process_calls[1]["result_input_image_indices"] == [1]
    assert process_calls[1]["allow_contribute"] is False
    assert process_calls[1]["display_mode_name_override"] == "柔光写真"
    assert process_calls[1]["result_meta"] == plan.result_meta


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
    assert kwargs["allow_contribute"] is True
    assert "allow_cancel" not in kwargs
    assert "user_cancel_allowed" not in kwargs
    assert "base_priority" not in kwargs


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
    assert plan.allow_contribute is True
    assert plan.display_mode_name is None
    assert plan.result_meta is None


@pytest.mark.asyncio
async def test_qqcc_random_faceswap_result_cannot_be_contributed():
    plan = build_quick_image_submission_plan(
        fsm_data={"mode": MODE_RANDOM_FACESWAP, "cost": 1},
        qqcc_config=normalize_qqcc_config(None),
        image_path="/tmp/face.png",
        prompts_config={"face_swap": "swap prompt"},
        template_files=["quick_face/a.png"],
        reply_markup="markup",
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

    assert plan.allow_contribute is False
    assert plan.display_mode_name == "快速换脸"
    assert plan.result_meta == {
        "_qqcc_regenerate": {
            "kind": "quick_image",
            "mode": MODE_RANDOM_FACESWAP,
            "display_mode_name": "快速换脸",
        }
    }
    assert process_task.await_args.kwargs["allow_contribute"] is False
    assert "allow_cancel" not in process_task.await_args.kwargs
    assert "user_cancel_allowed" not in process_task.await_args.kwargs
    assert "base_priority" not in process_task.await_args.kwargs
    assert process_task.await_args.kwargs["display_mode_name_override"] == "快速换脸"
    assert process_task.await_args.kwargs["result_meta"] == plan.result_meta


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
            {
                "main_buttons": {"ai_filter": False},
                "filter_scenes": [
                    {
                        "id": "real_skin",
                        "name": "真实质感",
                        "prompt": "real skin prompt",
                    }
                ],
            },
            {
                "mode": MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
                "scene_id": "real_skin",
                "scene_kind": "filter",
            },
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
