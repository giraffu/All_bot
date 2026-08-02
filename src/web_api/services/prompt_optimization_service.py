from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from config import MINIO_BUCKET
from src.core.task_core import process_and_submit_task
from src.core.task_core_types import CoreDomainError, TaskSubmissionSideEffectPlan
from src.prompt_optimizer.registry import (
    PROMPT_OPTIMIZATION_COST,
    PROMPT_OPTIMIZE_TASK_TYPE,
    PromptOptimizerRegistryError,
    get_prompt_optimizer_capability,
    resolve_prompt_optimization,
)
from src.services.storage import storage

PROMPT_MEDIA_MAX_BYTES = 20 * 1024 * 1024
PROMPT_RESULT_TTL_SECONDS = 24 * 60 * 60
_PROMPT_TASK_NAMESPACE = uuid.UUID("b649f362-7c39-439e-81af-6a3e187d72d8")
_ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def normalize_owned_prompt_media_key(value: str, user_id: int) -> str:
    raw = str(value or "").strip().lstrip("/")
    bucket_prefix = f"{MINIO_BUCKET}/"
    object_key = raw[len(bucket_prefix) :] if raw.startswith(bucket_prefix) else raw
    extension = object_key.rsplit(".", 1)[-1].lower() if "." in object_key else ""
    if not object_key.startswith(f"web_uploads/{user_id}/"):
        raise CoreDomainError("优化素材必须属于当前用户。")
    if extension not in _ALLOWED_EXTENSIONS:
        raise CoreDomainError("优化素材仅支持 PNG/JPEG/WebP。")
    return object_key


async def validate_prompt_media_objects(
    media: list[dict[str, str]],
    *,
    user_id: int,
    object_size: Callable[[str, str], Awaitable[int | None]] = storage.async_object_size,
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
    object_size: Callable[[str, str], Awaitable[int | None]] = storage.async_object_size,
    submit_task_func=process_and_submit_task,
) -> dict[str, Any]:
    media = await validate_prompt_media_objects(
        [item.model_dump() for item in request.media],
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
    }
    result = await submit_task_func(
        user_id=current_user.id,
        username=current_user.username,
        task_type=PROMPT_OPTIMIZE_TASK_TYPE,
        inputs=inputs,
        task_id=task_id,
        client_type="web",
        cost_override=PROMPT_OPTIMIZATION_COST,
        check_lock=True,
        user_cancel_allowed=True,
        submission_side_effect_plan=TaskSubmissionSideEffectPlan(
            attach_web_monitor=True
        ),
        submission_concurrency_idempotency_key=f"prompt-optimize:{idempotency_scope}",
        submission_idempotency_key=f"prompt-optimize-debit:{idempotency_scope}",
        submission_refund_idempotency_key=f"prompt-optimize-refund:{idempotency_scope}",
        registry_metadata={
            "record_history": False,
            "_prompt_optimizer": optimizer_meta,
        },
        allow_contribute_override=False,
    )
    return {
        "task_id": result["task_id"],
        "status": "pending",
        "cost": result["cost"],
        "balance_remaining": await get_balance(current_user.id),
    }
