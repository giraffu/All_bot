from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from src.prompt_optimizer.registry import (
    build_output_json_schema,
    get_profile_by_ref,
    get_template_by_ref,
    render_prompt_messages,
)


class PromptOptimizationExecutionError(RuntimeError):
    pass


async def execute_prompt_optimization(
    payload: dict[str, Any],
    *,
    provider,
    load_media: Callable[[str], Awaitable[bytes]],
    preprocess_media: Callable[[bytes], str],
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
    )
    if set(raw) != {"optimized_fields", "warnings"}:
        raise PromptOptimizationExecutionError("unknown_output_fields")
    optimized_fields = raw.get("optimized_fields")
    warnings = raw.get("warnings")
    if not isinstance(optimized_fields, dict) or set(optimized_fields) != set(
        profile.output_fields
    ):
        raise PromptOptimizationExecutionError("invalid_optimized_fields")
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise PromptOptimizationExecutionError("invalid_warnings")
    for value in optimized_fields.values():
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise PromptOptimizationExecutionError("invalid_output_text")
    result_text = optimized_fields[profile.primary_field].strip()
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

