from __future__ import annotations

import json
from typing import Any


BOT_TASK_RECOVERY_METADATA_KEY = "_bot_task_recovery"
BOT_TASK_RECOVERY_VERSION = 1
_MAX_RECOVERY_CONTRACT_BYTES = 64 * 1024


def _clean_optional_text(value: Any, *, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:max_length]


def _json_object(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None
    if len(encoded.encode("utf-8")) > _MAX_RECOVERY_CONTRACT_BYTES:
        return None
    decoded = json.loads(encoded)
    return decoded if isinstance(decoded, dict) else None


def build_bot_task_recovery_contract(
    *,
    send_result: bool,
    delete_status: bool,
    allow_contribute: bool,
    record_history: bool = True,
    result_task_type: Any = None,
    result_prompt: Any = None,
    result_input_image_indices: Any = None,
    result_meta: Any = None,
    completion_caption: Any = None,
    language_code: Any = None,
    show_queue_status: bool = True,
) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "version": BOT_TASK_RECOVERY_VERSION,
        "send_result": bool(send_result),
        # A hidden result in the QQCC surface is an intermediate step.  Until a
        # durable orchestration checkpoint exists, recovery must never present
        # it as a completed user-visible result.
        "requires_continuation": not bool(send_result),
        "delete_status": bool(delete_status),
        "allow_contribute": bool(allow_contribute),
    }
    if not record_history:
        contract["record_history"] = False
    if not show_queue_status:
        contract["show_queue_status"] = False
    optional_text = {
        "result_task_type": _clean_optional_text(result_task_type, max_length=128),
        "result_prompt": _clean_optional_text(result_prompt, max_length=16_000),
        "completion_caption": _clean_optional_text(
            completion_caption,
            max_length=2_048,
        ),
        "language_code": _clean_optional_text(language_code, max_length=16),
    }
    contract.update({key: value for key, value in optional_text.items() if value})

    if isinstance(result_input_image_indices, list):
        indices = [
            value
            for value in result_input_image_indices[:32]
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        ]
        if indices:
            contract["result_input_image_indices"] = indices

    serialized_result_meta = _json_object(result_meta)
    if serialized_result_meta is not None:
        contract["result_meta"] = serialized_result_meta

    return {BOT_TASK_RECOVERY_METADATA_KEY: contract}


def normalize_bot_task_recovery_contract(
    metadata: Any,
) -> dict[str, Any] | None:
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get(BOT_TASK_RECOVERY_METADATA_KEY)
    if not isinstance(raw, dict):
        return None
    if raw.get("version") != BOT_TASK_RECOVERY_VERSION:
        return None
    if not isinstance(raw.get("send_result"), bool):
        return None

    contract = build_bot_task_recovery_contract(
        send_result=raw["send_result"],
        delete_status=raw.get("delete_status") is True,
        allow_contribute=raw.get("allow_contribute") is True,
        record_history=raw.get("record_history") is not False,
        result_task_type=raw.get("result_task_type"),
        result_prompt=raw.get("result_prompt"),
        result_input_image_indices=raw.get("result_input_image_indices"),
        result_meta=raw.get("result_meta"),
        completion_caption=raw.get("completion_caption"),
        language_code=raw.get("language_code"),
        show_queue_status=raw.get("show_queue_status") is not False,
    )[BOT_TASK_RECOVERY_METADATA_KEY]
    # Never trust a persisted flag that claims a hidden result does not need a
    # continuation; hidden private results are fail-closed by construction.
    contract["requires_continuation"] = not contract["send_result"]
    return contract
