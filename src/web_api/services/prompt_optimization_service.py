from __future__ import annotations

import os
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from config import MINIO_BUCKET
from src.media_paths import normalize_owned_user_upload_key
from src.core.task_application import TaskApplication
from src.core.task_core_types import (
    CoreDomainError,
    SubmissionReconciliationPending,
    TaskSubmissionCommand,
    TaskSubmissionPolicy,
    TaskSubmissionSideEffectPlan,
)
from src.domain_config.minimax_h3 import MINIMAX_H3_TASK_TYPES
from src.prompt_optimizer.registry import (
    PROMPT_OPTIMIZATION_COST,
    PROMPT_OPTIMIZE_TASK_TYPE,
    PromptOptimizerRegistryError,
    build_prompt_variables,
    get_prompt_optimizer_capability,
    resolve_prompt_optimization,
)
from src.services.storage import storage
from src.services.task_text_stream_store import build_text_stream_contract
from src.services.task_web_submission_intent import WebSubmissionIntentJournal
from src.task_application_runtime import get_task_application

PROMPT_MEDIA_MAX_BYTES = 20 * 1024 * 1024
PROMPT_RESULT_TTL_SECONDS = 24 * 60 * 60
_PROMPT_TASK_NAMESPACE = uuid.UUID("b649f362-7c39-439e-81af-6a3e187d72d8")
_ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def normalize_owned_prompt_media_key(value: str, user_id: int) -> str:
    try:
        return normalize_owned_user_upload_key(
            value,
            user_id=user_id,
            allowed_extensions=_ALLOWED_EXTENSIONS,
        )
    except ValueError as exc:
        if str(exc) == "object key extension is not allowed":
            raise CoreDomainError("优化素材仅支持 PNG/JPEG/WebP。") from exc
        raise CoreDomainError("优化素材必须属于当前用户。") from exc


def normalize_prompt_media_object_key(value: str) -> str:
    raw = str(value or "").strip().lstrip("/")
    return raw.removeprefix(f"{MINIO_BUCKET}/")


async def validate_prompt_media_objects(
    media: list[dict[str, str]],
    *,
    user_id: int,
    object_size: Callable[
        [str, str], Awaitable[int | None]
    ] = storage.async_object_size,
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in media:
        object_key = normalize_owned_prompt_media_key(item["object_key"], user_id)
        size = await object_size(MINIO_BUCKET, object_key)
        if size is None:
            raise CoreDomainError("优化素材不存在或暂不可读取。")
        if size > PROMPT_MEDIA_MAX_BYTES:
            raise CoreDomainError("单个优化素材不能超过 20 MB。")
        normalized.append({"role": item["role"], "object_key": object_key})
    return normalized


def build_prompt_capability_payload(target_task_type: str) -> dict[str, Any]:
    try:
        return get_prompt_optimizer_capability(target_task_type)
    except PromptOptimizerRegistryError as exc:
        raise CoreDomainError(str(exc)) from exc


async def submit_prompt_optimization(
    *,
    request,
    current_user,
    get_balance: Callable[[int], Awaitable[int]],
    object_size: Callable[
        [str, str], Awaitable[int | None]
    ] = storage.async_object_size,
    task_application: TaskApplication | None = None,
    load_config_func=None,
) -> dict[str, Any]:
    requested_media = [item.model_dump() for item in request.media]
    requested_h3_refs = (
        [item.model_dump(exclude_none=True) for item in request.reference_refs]
        if request.reference_refs is not None
        else None
    )
    is_minimax_h3 = request.target_task_type in MINIMAX_H3_TASK_TYPES
    resolved_references = None
    resolved_h3_references = None
    if request.lora_items:
        raise CoreDomainError("当前提示词优化任务不接受附加模型。")
    character_ids = [str(value or "").strip() for value in request.character_ids]
    if request.target_task_type == "ltx_t2v_ic":
        if requested_h3_refs is not None:
            raise CoreDomainError("当前提示词优化任务不接受 H3 人物视图引用。")
        if request.character_refs is not None and character_ids:
            raise CoreDomainError("新旧角色引用不能同时提交。")
        if request.environment_ref is not None and requested_media:
            raise CoreDomainError("新旧环境引用不能同时提交。")
        from src.database.core import AsyncSessionLocal
        from src.web_api.services.reference_asset_service import (
            normalize_reference_inputs,
            resolve_reference_set,
        )

        legacy_background = (
            requested_media[0]["object_key"]
            if [item["role"] for item in requested_media] == ["scene_background"]
            else None
        )
        reference_inputs = {
            "character_refs": [item.model_dump() for item in request.character_refs]
            if request.character_refs is not None
            else None,
            "environment_ref": request.environment_ref.model_dump(exclude_none=True)
            if request.environment_ref
            else None,
            "character_ids": character_ids if request.character_refs is None else None,
            "background_object_key": legacy_background
            if request.environment_ref is None
            else None,
        }
        character_refs, environment_ref = normalize_reference_inputs(reference_inputs)
        async with AsyncSessionLocal() as character_db:
            resolved_references = await resolve_reference_set(
                db=character_db,
                user_id=current_user.id,
                character_refs=character_refs,
                environment_ref=environment_ref,
                object_size=object_size,
            )
        media = [
            {
                "role": f"reference_character_{index}",
                "object_key": normalize_prompt_media_object_key(object_key),
            }
            for index, object_key in enumerate(
                resolved_references.character_sheets, start=1
            )
        ] + [
            {
                "role": "scene_background",
                "object_key": normalize_prompt_media_object_key(
                    resolved_references.environment_object_key
                ),
            }
        ]
    elif request.target_task_type == "minimax_h3_ref2v" and requested_h3_refs is not None:
        if requested_media:
            raise CoreDomainError("H3 新旧参考图格式不能同时提交。")
        uses_character_assets = any(
            item.get("source") == "private_character_view"
            for item in requested_h3_refs
        )
        if uses_character_assets and os.getenv(
            "CHARACTER_ASSETS_ENABLED", "false"
        ).strip().lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            raise CoreDomainError("人物身份素材功能当前未开放。")
        from src.database.core import AsyncSessionLocal
        from src.web_api.services.reference_asset_service import (
            build_h3_character_reference_binding,
            resolve_h3_reference_refs,
        )

        explicit_enabled = os.getenv(
            "CHARACTER_EXPLICIT_VIEWS_ENABLED", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
        async with AsyncSessionLocal() as character_db:
            resolved_h3_references = await resolve_h3_reference_refs(
                db=character_db,
                user_id=current_user.id,
                reference_refs=requested_h3_refs,
                object_size=object_size,
                explicit_views_enabled=explicit_enabled,
            )
        media = [
            {
                "role": f"reference_image_{index}",
                "object_key": object_key,
            }
            for index, object_key in enumerate(
                resolved_h3_references.images, start=1
            )
        ]
    else:
        if requested_h3_refs is not None:
            raise CoreDomainError("人物库参考图仅支持 H3 参考图生视频优化。")
        if character_ids or request.character_refs is not None or request.environment_ref is not None:
            raise CoreDomainError("当前提示词优化任务不接受角色或环境引用。")
        media = await validate_prompt_media_objects(
            requested_media,
            user_id=current_user.id,
            object_size=object_size,
        )
    try:
        resolved = resolve_prompt_optimization(
            target_task_type=request.target_task_type,
            template_id=request.template.id,
            template_version=request.template.version,
            context=request.context,
            media=media,
        )
    except PromptOptimizerRegistryError as exc:
        raise CoreDomainError(str(exc)) from exc

    idempotency_scope = f"{current_user.id}:{request.client_request_id}"
    task_id = str(uuid.uuid5(_PROMPT_TASK_NAMESPACE, idempotency_scope))
    optimizer_meta = {
        "schema_version": "allbot.prompt_optimizer.v1",
        "profile_ref": resolved.profile.ref,
        "template_ref": resolved.template.ref,
        "template_hash": resolved.template.content_hash,
        "target_task_type": request.target_task_type,
        "primary_field": resolved.profile.primary_field,
        "allowed_output_fields": list(resolved.profile.output_fields),
        "max_output_characters": resolved.profile.max_output_characters,
        "result_ttl_seconds": PROMPT_RESULT_TTL_SECONDS,
    }
    inputs = {
        "profile_ref": resolved.profile.ref,
        "template_ref": resolved.template.ref,
        "template_hash": resolved.template.content_hash,
        "target_task_type": request.target_task_type,
        "prompt": request.prompt,
        "context": dict(resolved.normalized_context),
        "media": [dict(item) for item in resolved.normalized_media],
        "trusted_context": (
            {
                "character_descriptions": list(
                    resolved_references.character_descriptions
                ),
                "environment_description": resolved_references.environment_description,
            }
            if request.target_task_type == "ltx_t2v_ic"
            else (
                {
                    "reference_descriptions": list(
                        resolved_h3_references.descriptions
                    )
                }
                if resolved_h3_references is not None
                else {}
            )
        ),
        "text_stream_contract": build_text_stream_contract(
            resolved.profile.output_fields,
            resolved.profile.max_output_characters,
        ),
    }
    from src.database.core import AsyncSessionLocal
    from src.web_api.services.prompt_optimizer_config_service import (
        get_config,
        render_config_snapshot,
    )

    scene_key = "minimax_h3" if is_minimax_h3 else request.target_task_type
    trusted_context = inputs["trusted_context"]
    variables = build_prompt_variables(
        profile=resolved.profile,
        prompt=request.prompt,
        context=resolved.normalized_context,
    )
    if resolved_h3_references is not None:
        bindings = "\n".join(
            f"<Picture {index}>: {description}"
            for index, description in enumerate(
                resolved_h3_references.descriptions, start=1
            )
        )
        character_binding = build_h3_character_reference_binding(
            requested_h3_refs or []
        )
        variables["media_frame_instructions"] = "\n".join(
            part
            for part in (
                variables["media_frame_instructions"],
                bindings,
                character_binding,
            )
            if part
        )
    variables.update(
        {
            "character_descriptions": "\n".join(
                f"Character {index}: {value}"
                for index, value in enumerate(
                    trusted_context.get("character_descriptions", []), start=1
                )
                if value
            ),
            "environment_description": trusted_context.get(
                "environment_description", ""
            ),
            "addon_summary": (
                "Fixed 10Eros-Max Beta2, LightX2V 8-step, and NaughtyTimes v2 "
                "stack; no user-selectable add-ons."
            ),
            "addon_rules": trusted_context.get(
                "addon_rules",
                "Do not output model names, LoRA names, strengths, or trigger tokens.",
            ),
            "breasts_vocabulary_rule": (
                "nipples and areoles require textual or visual evidence; areolas is forbidden."
            ),
        }
    )
    if load_config_func is None:
        async with AsyncSessionLocal() as config_db:
            config = await get_config(config_db, scene_key)
    else:
        config = await load_config_func(scene_key)
    inputs["prompt_config_snapshot"] = render_config_snapshot(
        config=config,
        profile_ref=resolved.profile.ref,
        variables=variables,
    )
    submission_journal = WebSubmissionIntentJournal(
        internal_user_id=current_user.id,
        username=current_user.username,
        task_id=task_id,
    )
    try:
        application = task_application or get_task_application()
        result = await application.submit(
            TaskSubmissionCommand(
                internal_user_id=current_user.id,
                username=current_user.username,
                task_type=PROMPT_OPTIMIZE_TASK_TYPE,
                inputs=inputs,
                task_id=task_id,
                registry_metadata={
                    "record_history": False,
                    "_prompt_optimizer": optimizer_meta,
                },
            ),
            TaskSubmissionPolicy(
                client_type="web",
                cost_override=PROMPT_OPTIMIZATION_COST,
                check_lock=True,
                user_cancel_allowed=True,
                side_effect_plan=TaskSubmissionSideEffectPlan(
                    attach_web_monitor=True
                ),
                concurrency_idempotency_key=f"prompt-optimize:{idempotency_scope}",
                debit_idempotency_key=(
                    f"prompt-optimize-debit:{idempotency_scope}"
                ),
                refund_idempotency_key=(
                    submission_journal.refund_idempotency_key
                ),
                allow_contribute_override=False,
            ),
            submission_journal,
        )
    except SubmissionReconciliationPending as exc:
        result = {"task_id": exc.registry_task_id, "cost": exc.cost}
    return {
        "task_id": result["task_id"],
        "status": "pending",
        "cost": result["cost"],
        "balance_remaining": await get_balance(current_user.id),
    }
