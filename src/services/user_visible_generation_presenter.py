from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.domain_config.task_type_registry import resolve_user_task_display_key
from src.lora_catalog import LTX_VIDEO_LORA_CALLBACK_CHOICES
from src.lora_mapping import extract_prompt_lora_context


GENERATION_CONTEXT_KEY = "_generation_context"
GENERATION_CONTEXT_VERSION = 1

_SETTING_PREFIX_PATTERN = re.compile(r"^\[[^\]\n|]+\|[^\]\n]+\]\s*")

_CREDIT_OPERATION_TYPES = {
    "affiliate_credits_redeem",
    "checkin",
    "edit_image",
    "gallery_prompt_unlock_purchase",
    "gallery_prompt_unlock_reward",
    "membership_settlement_reward",
    "recharge",
    "referral_reward_channel",
    "referral_reward_generation",
    "referral_reward_initial",
    "template_submission",
    "welcome_bonus",
}

_PUBLIC_MODEL_IDS = {
    "qwen/YARN_1.0.safetensors": "image_realistic",
    "qwen/adjust_pussy_anus.safetensors": "image_anatomy_detail",
    "qwen/realistic_texture.safetensors": "image_realistic_texture",
    "qwen/flat_chest_hairless.safetensors": "image_flat_chest",
    "qwen/penis.safetensors": "image_futanari",
    "BreastGrow": "video_breast_growth",
    "BreastInsertion": "video_breast_insertion",
    "Cum": "video_cumshot",
    "Cunilingus": "video_cunnilingus",
    "Flatchested": "video_flat_chest",
    "Footjob": "video_footjob",
    "Insertion": "video_insertion",
}
_PUBLIC_MODEL_IDS.update(
    {
        path: f"ltx_{option_id}"
        for option_id, path in LTX_VIDEO_LORA_CALLBACK_CHOICES.items()
        if path
    }
)


@dataclass(frozen=True, slots=True)
class UserVisiblePrompt:
    prompt: str
    prompt_model: dict[str, Any] | None = None


def _normalize_key(value: str | None) -> str:
    return str(value or "").strip().replace("-", "_")


def resolve_credit_ledger_display_key(operation_type: str | None) -> str:
    raw = str(operation_type or "").strip()
    normalized = _normalize_key(raw)
    if normalized.startswith("refund"):
        return "credit_ledger.operation_types.refund"
    if normalized in _CREDIT_OPERATION_TYPES:
        return f"credit_ledger.operation_types.{normalized}"
    task_key = resolve_user_task_display_key(raw)
    if task_key != "task_type.other":
        return task_key
    return "credit_ledger.operation_types.other"


def resolve_public_model_id(lora_name: str | None) -> str | None:
    normalized = str(lora_name or "").strip()
    if not normalized:
        return None
    return _PUBLIC_MODEL_IDS.get(normalized, "additional")


def _normalize_strength(value: Any) -> float | None:
    if value is None:
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized >= 0 else None


def build_generation_context(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    metadata = metadata or {}
    nested_context = metadata.get(GENERATION_CONTEXT_KEY)
    if isinstance(nested_context, dict):
        metadata = nested_context
    lora_name = str(metadata.get("lora_name") or "").strip()
    context: dict[str, Any] = {"version": GENERATION_CONTEXT_VERSION}
    if lora_name:
        context.update(
            {
                "lora_name": lora_name,
                "public_model_id": resolve_public_model_id(lora_name),
            }
        )
    strength = _normalize_strength(metadata.get("lora_strength"))
    if lora_name and strength is not None:
        context["lora_strength"] = strength
    resolution = next(
        (
            str(metadata.get(key)).strip()
            for key in (
                "billing_resolution",
                "resolution_preset",
                "wan22_resolution_preset",
                "resolution",
            )
            if metadata.get(key) is not None and str(metadata.get(key)).strip()
        ),
        None,
    )
    if resolution:
        context["resolution"] = resolution
    duration = next(
        (
            metadata.get(key)
            for key in (
                "requested_duration",
                "duration",
                "wan22_duration_seconds",
                "ltx_duration_seconds",
                "scail2_duration_seconds",
            )
            if metadata.get(key) is not None
        ),
        None,
    )
    if duration is not None:
        try:
            context["duration_seconds"] = int(duration)
        except (TypeError, ValueError):
            pass
    return context if len(context) > 1 else None


def merge_generation_context_into_extra_outputs(
    *,
    extra_outputs: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    context = build_generation_context(metadata)
    if context is None:
        return extra_outputs
    merged = dict(extra_outputs or {})
    merged[GENERATION_CONTEXT_KEY] = context
    return merged


def _structured_generation_context(extra_outputs: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(extra_outputs, dict):
        return {}
    context = extra_outputs.get(GENERATION_CONTEXT_KEY)
    return context if isinstance(context, dict) else {}


def present_user_prompt(
    prompt: str | None,
    *,
    extra_outputs: dict[str, Any] | None = None,
) -> UserVisiblePrompt:
    clean_prompt = str(prompt or "").strip()
    while True:
        stripped = _SETTING_PREFIX_PATTERN.sub("", clean_prompt, count=1).lstrip()
        if stripped == clean_prompt:
            break
        clean_prompt = stripped

    legacy_prompt, legacy_lora_name, legacy_strength = extract_prompt_lora_context(
        clean_prompt
    )
    clean_prompt = legacy_prompt

    context = _structured_generation_context(extra_outputs)
    lora_name = str(context.get("lora_name") or legacy_lora_name or "").strip()
    public_model_id = str(
        context.get("public_model_id") or resolve_public_model_id(lora_name) or ""
    ).strip()
    strength = _normalize_strength(
        context.get("lora_strength")
        if context.get("lora_strength") is not None
        else legacy_strength
    )
    prompt_model = None
    if public_model_id:
        prompt_model = {
            "id": public_model_id,
            "display_key": f"generation_models.{public_model_id}",
            **({"strength": strength} if strength is not None else {}),
        }
    return UserVisiblePrompt(prompt=clean_prompt, prompt_model=prompt_model)


def resolve_prompt_generation_context(
    prompt: str | None,
    *,
    extra_outputs: dict[str, Any] | None = None,
) -> tuple[str, str | None, float | None]:
    presented = present_user_prompt(prompt, extra_outputs=extra_outputs)
    context = _structured_generation_context(extra_outputs)
    legacy_prompt = str(prompt or "").strip()
    while True:
        stripped = _SETTING_PREFIX_PATTERN.sub("", legacy_prompt, count=1).lstrip()
        if stripped == legacy_prompt:
            break
        legacy_prompt = stripped
    _clean, legacy_lora_name, legacy_strength = extract_prompt_lora_context(
        legacy_prompt
    )
    lora_name = str(context.get("lora_name") or legacy_lora_name or "").strip() or None
    strength = _normalize_strength(
        context.get("lora_strength")
        if context.get("lora_strength") is not None
        else legacy_strength
    )
    return presented.prompt, lora_name, strength
