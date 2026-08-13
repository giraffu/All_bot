from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from src.prompt_optimizer.config_snapshot import snapshot_content_hash
from src.prompt_optimizer.registry import (
    build_output_json_schema,
    get_profile_by_ref,
    get_template_by_ref,
    render_prompt_messages,
)


class PromptOptimizationExecutionError(RuntimeError):
    pass


_MINIMAX_H3_PROFILE_PREFIX = "minimax_h3_"
_MINIMAX_H3_FORBIDDEN_TRIGGERS = ("hmmotion", "hmbreasts", "hmpenis", "hmpussy")


def _validate_profile_output(
    profile,
    result_text: str,
    *,
    context: dict[str, Any],
    trusted_context: dict[str, Any],
) -> None:
    if not profile.id.startswith(_MINIMAX_H3_PROFILE_PREFIX):
        return
    lowered = result_text.casefold()
    if any(trigger in lowered for trigger in _MINIMAX_H3_FORBIDDEN_TRIGGERS):
        raise PromptOptimizationExecutionError("invalid_minimax_h3_trigger")
    if not re.match(
        r"^(handjob|insertion|missionary|cowgirl|blowjob|doggy)\b",
        result_text,
        flags=re.IGNORECASE,
    ):
        raise PromptOptimizationExecutionError("invalid_minimax_h3_class_header")
    if "\n\n" in result_text:
        raise PromptOptimizationExecutionError("invalid_minimax_h3_paragraph_count")
    if re.search(r"\bareolas\b", lowered):
        raise PromptOptimizationExecutionError("invalid_minimax_h3_areolas")
    if "breasts" not in set(trusted_context.get("addon_ids") or []) and re.search(
        r"\b(nipples|areoles)\b", lowered
    ):
        raise PromptOptimizationExecutionError("invalid_minimax_h3_breast_vocabulary")
    if re.search(r"\[Shot 1\]\s+At\b", result_text, flags=re.IGNORECASE):
        raise PromptOptimizationExecutionError("invalid_minimax_h3_first_timestamp")
    if len(re.findall(r"\[Shot\s+\d+\]", result_text, flags=re.IGNORECASE)) > 2:
        raise PromptOptimizationExecutionError("invalid_minimax_h3_shot_count")
    duration = int(context.get("duration_seconds") or 0)
    timestamps = []
    for minutes, seconds, milliseconds in re.findall(
        r"(?<!\d)(\d{2}):(\d{2})\.(\d{3})(?!\d)", result_text
    ):
        if int(seconds) >= 60:
            raise PromptOptimizationExecutionError("invalid_minimax_h3_timestamp")
        timestamps.append(int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000)
    if any(value >= duration for value in timestamps) or any(
        current <= previous for previous, current in zip(timestamps, timestamps[1:])
    ):
        raise PromptOptimizationExecutionError("invalid_minimax_h3_timestamp")
    word_count = len(re.findall(r"\b[\w'-]+\b", result_text, flags=re.UNICODE))
    if not 200 <= word_count <= 270:
        raise PromptOptimizationExecutionError("invalid_minimax_h3_word_count")


async def execute_prompt_optimization(
    payload: dict[str, Any],
    *,
    provider,
    load_media: Callable[[str], Awaitable[bytes]],
    preprocess_media: Callable[[bytes], str],
    on_text_delta: Callable[[str, str], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    profile = get_profile_by_ref(str(payload.get("profile_ref") or ""))
    template = get_template_by_ref(str(payload.get("template_ref") or ""))
    if payload.get("template_hash") != template.content_hash:
        raise PromptOptimizationExecutionError("template_hash_mismatch")
    if template.ref not in profile.allowed_template_refs:
        raise PromptOptimizationExecutionError("template_profile_incompatible")
    media = payload.get("media")
    if not isinstance(media, list):
        raise PromptOptimizationExecutionError("invalid_media")
    roles = tuple(item.get("role") for item in media if isinstance(item, dict))
    if roles != profile.required_media_roles:
        raise PromptOptimizationExecutionError("invalid_media_roles")
    snapshot = payload.get("prompt_config_snapshot")
    if snapshot is not None:
        if not isinstance(snapshot, dict) or snapshot.get("profile_ref") != profile.ref:
            raise PromptOptimizationExecutionError("prompt_config_profile_mismatch")
        if snapshot.get("snapshot_hash") != snapshot_content_hash(snapshot):
            raise PromptOptimizationExecutionError("prompt_config_hash_mismatch")
        system_prompt = str(snapshot.get("system_message") or "").strip()
        user_prompt = str(snapshot.get("user_message") or "").strip()
        if not system_prompt or not user_prompt:
            raise PromptOptimizationExecutionError("invalid_prompt_config_snapshot")
    else:
        system_prompt, user_prompt = render_prompt_messages(
            profile=profile,
            template=template,
            prompt=str(payload.get("prompt") or ""),
            context=payload.get("context") or {},
        )
    image_data_urls = [
        preprocess_media(await load_media(str(item["object_key"]))) for item in media
    ]
    raw = await provider.optimize(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        image_data_urls=image_data_urls,
        json_schema=build_output_json_schema(profile),
        output_fields=profile.output_fields,
        on_text_delta=on_text_delta,
    )
    if set(raw) != {"optimized_fields", "warnings"}:
        raise PromptOptimizationExecutionError("unknown_output_fields")
    optimized_fields = raw.get("optimized_fields")
    warnings = raw.get("warnings")
    if not isinstance(optimized_fields, dict) or set(optimized_fields) != set(
        profile.output_fields
    ):
        raise PromptOptimizationExecutionError("invalid_optimized_fields")
    if not isinstance(warnings, list) or not all(
        isinstance(item, str) for item in warnings
    ):
        raise PromptOptimizationExecutionError("invalid_warnings")
    for value in optimized_fields.values():
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > profile.max_output_characters
        ):
            raise PromptOptimizationExecutionError("invalid_output_text")
    result_text = optimized_fields[profile.primary_field].strip()
    _validate_profile_output(
        profile,
        result_text,
        context=payload.get("context") or {},
        trusted_context=payload.get("trusted_context") or {},
    )
    return {
        "result_kind": "text",
        "result_text": result_text,
        "result_meta": {
            "prompt_optimizer": {
                "schema_version": "allbot.prompt_optimizer.v1",
                "profile_ref": profile.ref,
                "template_ref": template.ref,
                "primary_field": profile.primary_field,
                "optimized_fields": {
                    key: value.strip() for key, value in optimized_fields.items()
                },
                "warnings": warnings,
            }
        },
    }
