from typing import Any

from src.core.task_lifecycle_contract import (
    BACKEND_STATUS_CANCELLED,
    BACKEND_STATUS_DONE,
    BACKEND_STATUS_ERROR,
    STREAM_STATUS_CANCELLED,
    STREAM_STATUS_FAILED,
    STREAM_STATUS_SUCCESS,
    normalize_backend_status,
)

RESULT_STATUS_PENDING = "pending_result"


def map_backend_status_to_stream_status(status: str | None) -> str | None:
    normalized_status = normalize_backend_status(status)
    if normalized_status == BACKEND_STATUS_DONE:
        return STREAM_STATUS_SUCCESS
    if normalized_status == BACKEND_STATUS_ERROR:
        return STREAM_STATUS_FAILED
    if normalized_status == BACKEND_STATUS_CANCELLED:
        return STREAM_STATUS_CANCELLED
    return normalized_status


def build_stream_terminal_payload(
    status_data: dict[str, Any],
    task_id: str,
) -> dict[str, Any] | None:
    payload = dict(status_data)
    stream_status = map_backend_status_to_stream_status(payload.get("status"))

    if stream_status == STREAM_STATUS_SUCCESS:
        payload["status"] = STREAM_STATUS_SUCCESS
        payload["task_id"] = task_id
        payload["task_type"] = payload.get("task_type", "edit")
        return payload

    if stream_status == STREAM_STATUS_FAILED:
        payload["status"] = STREAM_STATUS_FAILED
        payload["task_id"] = task_id
        payload["error"] = payload.get("error") or payload.get("error_msg")
        payload.pop("error_msg", None)
        return payload

    if stream_status == STREAM_STATUS_CANCELLED:
        payload["status"] = STREAM_STATUS_CANCELLED
        payload["task_id"] = task_id
        payload["message"] = payload.get("message") or payload.get("error_msg") or "任务已取消"
        payload.pop("error_msg", None)
        return payload

    return None


def build_result_pending_payload(
    *,
    task_id: str,
    task_type: str | None,
    media_type: str | None,
    extra_outputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": RESULT_STATUS_PENDING,
        "task_id": task_id,
        "task_type": task_type,
        "media_type": media_type,
        "extra_outputs": extra_outputs or {},
    }


def build_result_success_payload(
    *,
    task_id: str,
    task_type: str | None,
    media_type: str | None,
    result_url: str,
    extra_outputs: dict[str, Any] | None = None,
    result_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": STREAM_STATUS_SUCCESS,
        "task_id": task_id,
        "task_type": task_type,
        "media_type": media_type,
        "result_url": result_url,
        "extra_outputs": extra_outputs or {},
        "result_meta": result_meta or {},
    }
