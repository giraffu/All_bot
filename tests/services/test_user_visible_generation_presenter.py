import json
from pathlib import Path
from types import SimpleNamespace

from src.services.user_visible_generation_presenter import (
    GENERATION_CONTEXT_KEY,
    build_generation_context,
    merge_generation_context_into_extra_outputs,
    present_user_prompt,
    resolve_credit_ledger_display_key,
    resolve_user_task_display_key,
)
from src.domain_config.task_type_registry import TASK_TYPE_REGISTRY


def test_task_display_keys_cover_registry_aliases_and_hide_unknown_values():
    assert resolve_user_task_display_key("pornmaster_flux2_edit_bf16") == (
        "task_type.pornmaster_flux2_edit_bf16"
    )
    assert resolve_user_task_display_key("faceswap_step1") == "task_type.faceswap_step1"
    assert resolve_user_task_display_key("t2i-pornmaster-turbo") == "task_type.txt2img"
    assert resolve_user_task_display_key("not-a-real-worker-model") == "task_type.other"


def test_credit_ledger_display_keys_normalize_operations_refunds_and_tasks():
    assert resolve_credit_ledger_display_key("checkin") == (
        "credit_ledger.operation_types.checkin"
    )
    assert resolve_credit_ledger_display_key("refund_async_failed_cancelled") == (
        "credit_ledger.operation_types.refund"
    )
    assert resolve_credit_ledger_display_key("ltx_video_flf2v") == (
        "task_type.ltx_video_flf2v"
    )
    assert resolve_credit_ledger_display_key("unknown_internal_stage") == (
        "credit_ledger.operation_types.other"
    )


def test_prompt_presenter_cleans_legacy_prefixes_and_exposes_public_model_only():
    presented = present_user_prompt(
        "[720p|5s] [模型: qwen/YARN_1.0.safetensors] "
        "[强度: 0.30] cinematic portrait"
    )

    assert presented.prompt == "cinematic portrait"
    assert presented.prompt_model == {
        "id": "image_realistic",
        "display_key": "generation_models.image_realistic",
        "strength": 0.3,
    }
    assert "safetensors" not in str(presented.prompt_model)


def test_prompt_presenter_prefers_structured_context_and_never_exposes_unknown_model():
    extra_outputs = {
        GENERATION_CONTEXT_KEY: {
            "version": 1,
            "lora_name": "private/path/secret-model.safetensors",
            "lora_strength": 0.75,
            "public_model_id": "additional",
        }
    }

    presented = present_user_prompt("clean prompt", extra_outputs=extra_outputs)

    assert presented.prompt == "clean prompt"
    assert presented.prompt_model == {
        "id": "additional",
        "display_key": "generation_models.additional",
        "strength": 0.75,
    }
    assert "secret-model" not in str(presented.prompt_model)


def test_generation_context_merges_internal_runtime_metadata_without_changing_prompt():
    context = build_generation_context(
        {
            "lora_name": "BreastGrow",
            "lora_strength": 0.8,
            "resolution_preset": "standard",
            "duration": 8,
        }
    )
    assert context == {
        "version": 1,
        "lora_name": "BreastGrow",
        "lora_strength": 0.8,
        "public_model_id": "video_breast_growth",
        "resolution": "standard",
        "duration_seconds": 8,
    }

    merged = merge_generation_context_into_extra_outputs(
        extra_outputs={"last_frame": "frame.png"},
        metadata={
            "lora_name": "BreastGrow",
            "lora_strength": 0.8,
            "resolution_preset": "standard",
            "duration": 8,
        },
    )
    assert merged["last_frame"] == "frame.png"
    assert merged[GENERATION_CONTEXT_KEY] == context


def test_prompt_presenter_accepts_history_like_object_context():
    history = SimpleNamespace(
        prompt="[模型: 真实质感] old prompt",
        extra_outputs=None,
    )
    presented = present_user_prompt(
        history.prompt,
        extra_outputs=history.extra_outputs,
    )
    assert presented.prompt == "old prompt"
    assert presented.prompt_model["id"] == "image_realistic_texture"


def test_all_registry_task_types_have_zh_and_en_user_labels():
    project_root = Path(__file__).resolve().parents[2]
    for lang in ("zh", "en"):
        locale = json.loads(
            (project_root / "shared" / "locales" / f"{lang}.json").read_text()
        )
        missing = sorted(set(TASK_TYPE_REGISTRY) - set(locale["task_type"]))
        assert missing == []
