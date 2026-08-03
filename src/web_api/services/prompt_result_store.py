from __future__ import annotations

from typing import Any
import logging

from src.services.redis_client import redis_client

PROMPT_RESULT_TTL_SECONDS = 24 * 60 * 60
PROMPT_RESULT_SCHEMA_VERSION = "allbot.prompt_optimizer.v1"
logger = logging.getLogger(__name__)


def validate_prompt_result(
    *,
    result_kind: str | None,
    result_text: str | None,
    result_meta: dict[str, Any] | None,
    expected_optimizer_metadata: dict[str, Any],
) -> dict[str, Any]:
    if result_kind != "text":
        raise ValueError("prompt optimizer completion must use result_kind=text")
    normalized_text = str(result_text or "").strip()
    if not normalized_text or len(normalized_text) > 2000:
        raise ValueError("prompt optimizer result_text is empty or too long")
    optimizer = (result_meta or {}).get("prompt_optimizer")
    if not isinstance(optimizer, dict):
        raise ValueError("prompt optimizer result metadata is missing")
    if optimizer.get("schema_version") != PROMPT_RESULT_SCHEMA_VERSION:
        raise ValueError("prompt optimizer result schema version mismatch")
    for key in ("profile_ref", "template_ref"):
        if optimizer.get(key) != expected_optimizer_metadata.get(key):
            raise ValueError(f"prompt optimizer {key} mismatch")
    optimized_fields = optimizer.get("optimized_fields")
    primary_field = optimizer.get("primary_field")
    allowed_fields = set(expected_optimizer_metadata.get("allowed_output_fields") or [])
    if (
        not isinstance(optimized_fields, dict)
        or set(optimized_fields) - allowed_fields
        or primary_field not in allowed_fields
        or optimized_fields.get(primary_field) != normalized_text
    ):
        raise ValueError("prompt optimizer output fields violate the profile")
    return {
        "result_kind": "text",
        "result_text": normalized_text,
        "result_meta": {"prompt_optimizer": optimizer},
    }


async def store_prompt_result(
    *,
    task_id: str,
    user_id: int,
    task_type: str,
    result_kind: str | None,
    result_text: str | None,
    result_meta: dict[str, Any] | None,
    expected_optimizer_metadata: dict[str, Any],
) -> None:
    validated = validate_prompt_result(
        result_kind=result_kind,
        result_text=result_text,
        result_meta=result_meta,
        expected_optimizer_metadata=expected_optimizer_metadata,
    )
    await redis_client.set_prompt_result(
        task_id,
        {
            "user_id": user_id,
            "task_id": task_id,
            "task_type": task_type,
            **validated,
        },
        ttl_seconds=PROMPT_RESULT_TTL_SECONDS,
    )


async def store_prompt_failure_result(
    *,
    task_id: str,
    user_id: int,
    partial_result_text: str,
    refund_status: str,
    message: str | None = None,
) -> None:
    partial = str(partial_result_text or "")[:2000]
    await redis_client.set_prompt_result(
        task_id,
        {
            "user_id": user_id,
            "task_id": task_id,
            "task_type": "prompt_optimize",
            "status": "failed",
            "result_kind": "text",
            "partial_result_text": partial,
            "partial_unvalidated": True,
            "refund_status": refund_status,
            "message": message or "prompt optimizer failed",
        },
        ttl_seconds=PROMPT_RESULT_TTL_SECONDS,
    )


async def get_owned_prompt_result(task_id: str, user_id: int) -> dict[str, Any] | None:
    try:
        payload = await redis_client.get_prompt_result(task_id)
    except Exception as exc:
        logger.warning(
            "Prompt result store unavailable task_id=%s error_type=%s",
            task_id,
            type(exc).__name__,
        )
        return None
    if payload is None:
        return None
    if int(payload.get("user_id", -1)) != int(user_id):
        raise PermissionError("prompt result is not owned by this user")
    return payload
