"""Pure key planning contract for transient and durable R2 media objects."""

from __future__ import annotations

from pathlib import PurePosixPath
import re


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_SUFFIX = re.compile(r"^\.[A-Za-z0-9]{1,10}$")


def _require_safe_id(value: object, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not _SAFE_ID.fullmatch(normalized):
        raise ValueError(f"{label} must be a non-empty safe identifier")
    return normalized


def _suffix(source_name: str) -> str:
    suffix = PurePosixPath(str(source_name or "")).suffix.lower()
    return suffix if _SAFE_SUFFIX.fullmatch(suffix) else ".bin"


def _role_segment(role: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(role or "").strip())
    normalized = normalized.strip(".-_").lower()
    if not normalized or normalized in {".", ".."}:
        raise ValueError("role must contain a safe segment")
    return normalized[:64]


def build_staged_worker_result_key(
    *,
    task_id: str,
    source_name: str,
    role: str,
    ordinal: int = 0,
) -> str:
    task_segment = _require_safe_id(task_id, label="task_id")
    if role == "primary":
        return f"staging/worker-results/{task_segment}/primary{_suffix(source_name)}"
    if ordinal < 0:
        raise ValueError("ordinal must not be negative")
    return (
        f"staging/worker-results/{task_segment}/extras/"
        f"{_role_segment(role)}-{ordinal}{_suffix(source_name)}"
    )


def build_task_result_key(
    *,
    task_id: str,
    source_name: str,
    role: str,
    ordinal: int = 0,
) -> str:
    staged = build_staged_worker_result_key(
        task_id=task_id,
        source_name=source_name,
        role=role,
        ordinal=ordinal,
    )
    return staged.replace("staging/worker-results/", "task-results/", 1)


def build_staged_user_upload_key(
    *, user_id: int, upload_id: str, filename: str
) -> str:
    try:
        user_segment = str(int(user_id))
    except (TypeError, ValueError) as exc:
        raise ValueError("user_id must be a positive integer") from exc
    if int(user_segment) <= 0:
        raise ValueError("user_id must be a positive integer")
    upload_segment = _require_safe_id(upload_id, label="upload_id")
    return f"staging/user-uploads/{user_segment}/{upload_segment}{_suffix(filename)}"


def build_task_input_key(*, task_id: str, ordinal: int, source_name: str) -> str:
    task_segment = _require_safe_id(task_id, label="task_id")
    if ordinal < 0:
        raise ValueError("ordinal must not be negative")
    return f"task-inputs/{task_segment}/{ordinal}{_suffix(source_name)}"
