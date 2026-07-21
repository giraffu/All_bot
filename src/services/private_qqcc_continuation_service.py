from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import secrets
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass, replace
from typing import Any, Protocol

from config import REDIS_PREFIX
from src.services.private_bot_update_admission import (
    PrivateBotUpdateAdmissionScope,
    activate_private_bot_update_scope,
    get_private_bot_submission_cursor,
)
from src.services.redis_client import redis_client


PRIVATE_QQCC_CONTINUATION_METADATA_KEY = "_private_qqcc_continuation"
PRIVATE_QQCC_CONTINUATION_VERSION = 1
PRIVATE_QQCC_CONTINUATION_TTL_SECONDS = 7 * 24 * 60 * 60
PRIVATE_QQCC_CONTINUATION_LOCK_SECONDS = 120
PRIVATE_QQCC_CONTINUATION_MAX_STAGES = 64

logger = logging.getLogger(__name__)


class PrivateQqccContinuationError(RuntimeError):
    pass


class PrivateQqccContinuationConflict(PrivateQqccContinuationError):
    pass


class PrivateQqccContinuationUnavailable(PrivateQqccContinuationError):
    pass


@dataclass(frozen=True, slots=True)
class PrivateQqccContinuationTaskRef:
    chain_id: str
    stage_index: int
    submission_sequence: int
    registry_task_id: str
    executor_token: str


@dataclass(frozen=True, slots=True)
class PrivateQqccContinuationCheckpoint:
    version: int
    chain_id: str
    plan_sha256: str
    private_bot_id: int
    update_id: int
    telegram_user_id: int
    username: str | None
    chat_id: int
    status_message_id: int | None
    language_code: str
    stages: tuple[dict[str, Any], ...]
    status: str
    next_stage_index: int
    next_submission_sequence: int
    original_input_ref: str
    original_input_durable: bool
    current_output_ref: str | None = None
    current_stage_index: int | None = None
    current_submission_sequence: int | None = None
    current_registry_task_id: str | None = None
    current_executor_token: str | None = None
    error_code: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in {"completed", "failed"}

    @property
    def has_more_stages(self) -> bool:
        return self.next_stage_index < len(self.stages)


class PrivateQqccContinuationStore(Protocol):
    async def create(
        self, checkpoint: PrivateQqccContinuationCheckpoint
    ) -> PrivateQqccContinuationCheckpoint: ...

    async def get(
        self, chain_id: str
    ) -> PrivateQqccContinuationCheckpoint | None: ...

    async def list_all(
        self, *, tolerate_corrupt: bool = False
    ) -> list[PrivateQqccContinuationCheckpoint]: ...

    async def mark_running(
        self,
        *,
        chain_id: str,
        stage_index: int,
        submission_sequence: int,
        registry_task_id: str,
        executor_token: str,
    ) -> PrivateQqccContinuationCheckpoint: ...

    async def record_completed_stage(
        self,
        *,
        ref: PrivateQqccContinuationTaskRef,
        output_file: str,
        saved_inputs: list[str],
    ) -> PrivateQqccContinuationCheckpoint: ...

    async def claim_delivery(
        self,
        *,
        chain_id: str,
        stage_index: int,
        registry_task_id: str,
        executor_token: str,
    ) -> PrivateQqccContinuationCheckpoint: ...

    async def mark_delivered(
        self,
        *,
        ref: PrivateQqccContinuationTaskRef,
    ) -> PrivateQqccContinuationCheckpoint: ...

    async def rewind_orphaned_stage(
        self, *, chain_id: str
    ) -> PrivateQqccContinuationCheckpoint: ...

    async def mark_failed(
        self, *, ref: PrivateQqccContinuationTaskRef, error_code: str
    ) -> PrivateQqccContinuationCheckpoint: ...

    async def acquire_lock(self, chain_id: str) -> str | None: ...

    async def renew_lock(self, chain_id: str, token: str) -> bool: ...

    async def release_lock(self, chain_id: str, token: str | None) -> None: ...


_CURRENT_TASK_REF: ContextVar[PrivateQqccContinuationTaskRef | None] = ContextVar(
    "private_qqcc_continuation_task_ref",
    default=None,
)


@contextmanager
def activate_private_qqcc_continuation_task(
    ref: PrivateQqccContinuationTaskRef,
):
    token: Token = _CURRENT_TASK_REF.set(ref)
    try:
        yield ref
    finally:
        _CURRENT_TASK_REF.reset(token)


def get_private_qqcc_continuation_task_ref(
) -> PrivateQqccContinuationTaskRef | None:
    return _CURRENT_TASK_REF.get()


def build_private_qqcc_continuation_registry_metadata() -> dict[str, Any]:
    ref = get_private_qqcc_continuation_task_ref()
    if ref is None:
        return {}
    return {
        PRIVATE_QQCC_CONTINUATION_METADATA_KEY: {
            "version": PRIVATE_QQCC_CONTINUATION_VERSION,
            "chain_id": ref.chain_id,
            "stage_index": ref.stage_index,
            "submission_sequence": ref.submission_sequence,
            "registry_task_id": ref.registry_task_id,
            "executor_token": ref.executor_token,
        }
    }


def normalize_private_qqcc_continuation_task_ref(
    metadata: Any,
) -> PrivateQqccContinuationTaskRef | None:
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get(PRIVATE_QQCC_CONTINUATION_METADATA_KEY)
    if not isinstance(raw, dict):
        return None
    if raw.get("version") != PRIVATE_QQCC_CONTINUATION_VERSION:
        return None
    try:
        stage_index = int(raw["stage_index"])
        submission_sequence = int(raw["submission_sequence"])
    except (KeyError, TypeError, ValueError):
        return None
    chain_id = str(raw.get("chain_id") or "").strip()
    registry_task_id = str(raw.get("registry_task_id") or "").strip()
    executor_token = str(raw.get("executor_token") or "").strip()
    if (
        not chain_id
        or not registry_task_id
        or not executor_token
        or stage_index < 0
        or submission_sequence < 0
    ):
        return None
    return PrivateQqccContinuationTaskRef(
        chain_id=chain_id,
        stage_index=stage_index,
        submission_sequence=submission_sequence,
        registry_task_id=registry_task_id,
        executor_token=executor_token,
    )


def _checkpoint_to_json(checkpoint: PrivateQqccContinuationCheckpoint) -> str:
    payload = asdict(checkpoint)
    payload["stages"] = list(checkpoint.stages)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _checkpoint_from_json(raw: str | bytes) -> PrivateQqccContinuationCheckpoint:
    payload = json.loads(raw)
    payload["stages"] = tuple(payload.get("stages") or [])
    checkpoint = PrivateQqccContinuationCheckpoint(**payload)
    if checkpoint.version != PRIVATE_QQCC_CONTINUATION_VERSION:
        raise ValueError("unsupported private QQCC continuation version")
    if checkpoint.status not in {
        "ready",
        "running",
        "delivery_pending",
        "completed",
        "failed",
    }:
        raise ValueError("invalid private QQCC continuation status")
    return checkpoint


_MARK_RUNNING_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return '' end
local data = cjson.decode(raw)
if data['status'] ~= 'ready' then return raw end
if tonumber(data['next_stage_index']) ~= tonumber(ARGV[1]) then return raw end
if tonumber(data['next_submission_sequence']) ~= tonumber(ARGV[2]) then return raw end
data['status'] = 'running'
data['current_stage_index'] = tonumber(ARGV[1])
data['current_submission_sequence'] = tonumber(ARGV[2])
data['current_registry_task_id'] = ARGV[3]
data['current_executor_token'] = ARGV[4]
data['next_submission_sequence'] = tonumber(ARGV[2]) + 1
local encoded = cjson.encode(data)
redis.call('SET', KEYS[1], encoded, 'EX', ARGV[5])
return encoded
"""

_RECORD_COMPLETED_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return '' end
local data = cjson.decode(raw)
if tonumber(data['next_stage_index']) > tonumber(ARGV[1]) then return raw end
if data['status'] == 'delivery_pending' then
    if tonumber(data['current_stage_index']) ~= tonumber(ARGV[1]) then return raw end
    if data['current_registry_task_id'] ~= ARGV[2] then return raw end
    if data['current_output_ref'] ~= ARGV[4] then return raw end
    return raw
end
if data['status'] ~= 'running' then return raw end
if tonumber(data['current_stage_index']) ~= tonumber(ARGV[1]) then return raw end
if data['current_registry_task_id'] ~= ARGV[2] then return raw end
if data['current_executor_token'] ~= ARGV[3] then return raw end
data['current_output_ref'] = ARGV[4]
if tonumber(ARGV[1]) == 0 and ARGV[5] ~= '' then
    data['original_input_ref'] = ARGV[5]
    data['original_input_durable'] = true
end
local stage = data['stages'][tonumber(ARGV[1]) + 1]
if stage and stage['delivery_required'] == true then
    data['status'] = 'delivery_pending'
    data['current_executor_token'] = cjson.null
else
    data['next_stage_index'] = tonumber(ARGV[1]) + 1
    data['current_stage_index'] = cjson.null
    data['current_submission_sequence'] = cjson.null
    data['current_registry_task_id'] = cjson.null
    data['current_executor_token'] = cjson.null
    if tonumber(data['next_stage_index']) >= #data['stages'] then
        data['status'] = 'completed'
    else
        data['status'] = 'ready'
    end
end
local encoded = cjson.encode(data)
redis.call('SET', KEYS[1], encoded, 'EX', ARGV[6])
return encoded
"""

_CLAIM_DELIVERY_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return '' end
local data = cjson.decode(raw)
if data['status'] ~= 'delivery_pending' then return raw end
if tonumber(data['current_stage_index']) ~= tonumber(ARGV[1]) then return raw end
if data['current_registry_task_id'] ~= ARGV[2] then return raw end
if redis.call('GET', KEYS[2]) ~= ARGV[3] then return raw end
data['current_executor_token'] = ARGV[3]
local encoded = cjson.encode(data)
redis.call('SET', KEYS[1], encoded, 'EX', ARGV[4])
return encoded
"""

_MARK_DELIVERED_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return '' end
local data = cjson.decode(raw)
if tonumber(data['next_stage_index']) > tonumber(ARGV[1]) then return raw end
if data['status'] ~= 'delivery_pending' then return raw end
if tonumber(data['current_stage_index']) ~= tonumber(ARGV[1]) then return raw end
if data['current_registry_task_id'] ~= ARGV[2] then return raw end
if data['current_executor_token'] ~= ARGV[3] then return raw end
data['next_stage_index'] = tonumber(ARGV[1]) + 1
data['current_stage_index'] = cjson.null
data['current_submission_sequence'] = cjson.null
data['current_registry_task_id'] = cjson.null
data['current_executor_token'] = cjson.null
if tonumber(data['next_stage_index']) >= #data['stages'] then
    data['status'] = 'completed'
else
    data['status'] = 'ready'
end
local encoded = cjson.encode(data)
redis.call('SET', KEYS[1], encoded, 'EX', ARGV[4])
return encoded
"""

_REWIND_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return '' end
local data = cjson.decode(raw)
if data['status'] ~= 'running' then return raw end
if redis.call('EXISTS', KEYS[2]) == 1 then return raw end
data['status'] = 'ready'
data['next_stage_index'] = data['current_stage_index']
data['next_submission_sequence'] = data['current_submission_sequence']
data['current_stage_index'] = cjson.null
data['current_submission_sequence'] = cjson.null
data['current_registry_task_id'] = cjson.null
data['current_executor_token'] = cjson.null
local encoded = cjson.encode(data)
redis.call('SET', KEYS[1], encoded, 'EX', ARGV[1])
return encoded
"""

_MARK_FAILED_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return '' end
local data = cjson.decode(raw)
if data['status'] ~= 'running' then return raw end
if tonumber(data['current_stage_index']) ~= tonumber(ARGV[1]) then return raw end
if data['current_registry_task_id'] ~= ARGV[2] then return raw end
if data['current_executor_token'] ~= ARGV[3] then return raw end
data['status'] = 'failed'
data['error_code'] = ARGV[4]
local encoded = cjson.encode(data)
redis.call('SET', KEYS[1], encoded, 'EX', ARGV[5])
return encoded
"""

_RELEASE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""

_RENEW_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""


class RedisPrivateQqccContinuationStore:
    def __init__(
        self,
        *,
        redis=None,
        redis_prefix: str = REDIS_PREFIX,
        ttl_seconds: int = PRIVATE_QQCC_CONTINUATION_TTL_SECONDS,
    ):
        self.redis = redis or redis_client.redis
        self.redis_prefix = redis_prefix
        self.ttl_seconds = ttl_seconds

    def _key(self, chain_id: str) -> str:
        return f"{self.redis_prefix}private_qqcc_bot:continuation:{chain_id}"

    def _lock_key(self, chain_id: str) -> str:
        return f"{self._key(chain_id)}:lock"

    async def create(
        self, checkpoint: PrivateQqccContinuationCheckpoint
    ) -> PrivateQqccContinuationCheckpoint:
        key = self._key(checkpoint.chain_id)
        created = await self.redis.set(
            key,
            _checkpoint_to_json(checkpoint),
            ex=self.ttl_seconds,
            nx=True,
        )
        if created:
            return checkpoint
        existing = await self.get(checkpoint.chain_id)
        if existing is None:
            raise PrivateQqccContinuationUnavailable("continuation checkpoint missing")
        if (
            existing.plan_sha256 != checkpoint.plan_sha256
            or existing.private_bot_id != checkpoint.private_bot_id
            or existing.update_id != checkpoint.update_id
        ):
            raise PrivateQqccContinuationConflict(
                "continuation checkpoint conflicts with persisted plan"
            )
        if not existing.original_input_durable and checkpoint.original_input_ref:
            existing = replace(
                existing,
                original_input_ref=checkpoint.original_input_ref,
                original_input_durable=checkpoint.original_input_durable,
            )
            await self.redis.set(
                key,
                _checkpoint_to_json(existing),
                ex=self.ttl_seconds,
                xx=True,
            )
        return existing

    async def get(
        self, chain_id: str
    ) -> PrivateQqccContinuationCheckpoint | None:
        raw = await self.redis.get(self._key(chain_id))
        return _checkpoint_from_json(raw) if raw else None

    async def list_all(
        self, *, tolerate_corrupt: bool = False
    ) -> list[PrivateQqccContinuationCheckpoint]:
        pattern = f"{self.redis_prefix}private_qqcc_bot:continuation:*"
        checkpoints: list[PrivateQqccContinuationCheckpoint] = []
        async for key in self.redis.scan_iter(match=pattern, count=200):
            key_text = (
                key.decode("utf-8", errors="strict")
                if isinstance(key, bytes)
                else str(key)
            )
            if key_text.endswith(":lock"):
                continue
            raw = await self.redis.get(key)
            if raw:
                try:
                    checkpoints.append(_checkpoint_from_json(raw))
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    logger.error(
                        "Invalid private QQCC continuation checkpoint key=%s "
                        "error_type=%s",
                        key_text,
                        type(exc).__name__,
                    )
                    if not tolerate_corrupt:
                        raise PrivateQqccContinuationUnavailable(
                            "invalid private QQCC continuation checkpoint"
                        ) from exc
        return checkpoints

    async def mark_running(
        self,
        *,
        chain_id: str,
        stage_index: int,
        submission_sequence: int,
        registry_task_id: str,
        executor_token: str,
    ) -> PrivateQqccContinuationCheckpoint:
        raw = await self.redis.eval(
            _MARK_RUNNING_SCRIPT,
            1,
            self._key(chain_id),
            stage_index,
            submission_sequence,
            registry_task_id,
            executor_token,
            self.ttl_seconds,
        )
        if not raw:
            raise PrivateQqccContinuationUnavailable("continuation checkpoint missing")
        checkpoint = _checkpoint_from_json(raw)
        if (
            checkpoint.status != "running"
            or checkpoint.current_stage_index != stage_index
            or checkpoint.current_registry_task_id != registry_task_id
            or checkpoint.current_executor_token != executor_token
        ):
            raise PrivateQqccContinuationConflict(
                "continuation stage is not ready for dispatch"
            )
        return checkpoint

    async def record_completed_stage(
        self,
        *,
        ref: PrivateQqccContinuationTaskRef,
        output_file: str,
        saved_inputs: list[str],
    ) -> PrivateQqccContinuationCheckpoint:
        original_input = str(saved_inputs[0]) if ref.stage_index == 0 and saved_inputs else ""
        raw = await self.redis.eval(
            _RECORD_COMPLETED_SCRIPT,
            1,
            self._key(ref.chain_id),
            ref.stage_index,
            ref.registry_task_id,
            ref.executor_token,
            output_file,
            original_input,
            self.ttl_seconds,
        )
        if not raw:
            raise PrivateQqccContinuationUnavailable("continuation checkpoint missing")
        checkpoint = _checkpoint_from_json(raw)
        if checkpoint.next_stage_index <= ref.stage_index and not (
            checkpoint.status == "delivery_pending"
            and checkpoint.current_stage_index == ref.stage_index
            and checkpoint.current_registry_task_id == ref.registry_task_id
            and checkpoint.current_output_ref == str(output_file)
        ):
            raise PrivateQqccContinuationConflict(
                "continuation completion did not persist the stage result"
            )
        return checkpoint

    async def claim_delivery(
        self,
        *,
        chain_id: str,
        stage_index: int,
        registry_task_id: str,
        executor_token: str,
    ) -> PrivateQqccContinuationCheckpoint:
        raw = await self.redis.eval(
            _CLAIM_DELIVERY_SCRIPT,
            2,
            self._key(chain_id),
            self._lock_key(chain_id),
            stage_index,
            registry_task_id,
            executor_token,
            self.ttl_seconds,
        )
        if not raw:
            raise PrivateQqccContinuationUnavailable("continuation checkpoint missing")
        checkpoint = _checkpoint_from_json(raw)
        if (
            checkpoint.status != "delivery_pending"
            or checkpoint.current_stage_index != stage_index
            or checkpoint.current_registry_task_id != registry_task_id
            or checkpoint.current_executor_token != executor_token
        ):
            raise PrivateQqccContinuationConflict(
                "continuation delivery ownership could not be claimed"
            )
        return checkpoint

    async def mark_delivered(
        self,
        *,
        ref: PrivateQqccContinuationTaskRef,
    ) -> PrivateQqccContinuationCheckpoint:
        raw = await self.redis.eval(
            _MARK_DELIVERED_SCRIPT,
            1,
            self._key(ref.chain_id),
            ref.stage_index,
            ref.registry_task_id,
            ref.executor_token,
            self.ttl_seconds,
        )
        if not raw:
            raise PrivateQqccContinuationUnavailable("continuation checkpoint missing")
        checkpoint = _checkpoint_from_json(raw)
        if checkpoint.next_stage_index <= ref.stage_index:
            raise PrivateQqccContinuationConflict(
                "continuation delivery did not advance the stage"
            )
        return checkpoint

    async def rewind_orphaned_stage(
        self, *, chain_id: str
    ) -> PrivateQqccContinuationCheckpoint:
        raw = await self.redis.eval(
            _REWIND_SCRIPT,
            2,
            self._key(chain_id),
            self._lock_key(chain_id),
            self.ttl_seconds,
        )
        if not raw:
            raise PrivateQqccContinuationUnavailable("continuation checkpoint missing")
        return _checkpoint_from_json(raw)

    async def mark_failed(
        self, *, ref: PrivateQqccContinuationTaskRef, error_code: str
    ) -> PrivateQqccContinuationCheckpoint:
        raw = await self.redis.eval(
            _MARK_FAILED_SCRIPT,
            1,
            self._key(ref.chain_id),
            ref.stage_index,
            ref.registry_task_id,
            ref.executor_token,
            str(error_code)[:64],
            self.ttl_seconds,
        )
        if not raw:
            raise PrivateQqccContinuationUnavailable("continuation checkpoint missing")
        checkpoint = _checkpoint_from_json(raw)
        if (
            checkpoint.status != "failed"
            or checkpoint.current_stage_index != ref.stage_index
            or checkpoint.current_registry_task_id != ref.registry_task_id
            or checkpoint.current_executor_token != ref.executor_token
        ):
            raise PrivateQqccContinuationConflict(
                "continuation stage failure did not pass its executor fence"
            )
        return checkpoint

    async def acquire_lock(self, chain_id: str) -> str | None:
        token = secrets.token_urlsafe(24)
        acquired = await self.redis.set(
            self._lock_key(chain_id),
            token,
            ex=PRIVATE_QQCC_CONTINUATION_LOCK_SECONDS,
            nx=True,
        )
        return token if acquired else None

    async def renew_lock(self, chain_id: str, token: str) -> bool:
        renewed = await self.redis.eval(
            _RENEW_LOCK_SCRIPT,
            1,
            self._lock_key(chain_id),
            token,
            PRIVATE_QQCC_CONTINUATION_LOCK_SECONDS,
        )
        return int(renewed or 0) == 1

    async def release_lock(self, chain_id: str, token: str | None) -> None:
        if token:
            await self.redis.eval(
                _RELEASE_LOCK_SCRIPT,
                1,
                self._lock_key(chain_id),
                token,
            )


_default_store: PrivateQqccContinuationStore | None = None


def get_private_qqcc_continuation_store() -> PrivateQqccContinuationStore:
    global _default_store
    if _default_store is None:
        _default_store = RedisPrivateQqccContinuationStore()
    return _default_store


def _normalized_stages(stages: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    if not stages or len(stages) > PRIVATE_QQCC_CONTINUATION_MAX_STAGES:
        raise PrivateQqccContinuationConflict("invalid continuation stage count")
    try:
        encoded = json.dumps(
            stages,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise PrivateQqccContinuationConflict(
            "continuation stages must be JSON serializable"
        ) from exc
    if not isinstance(decoded, list) or not all(
        isinstance(stage, dict) for stage in decoded
    ):
        raise PrivateQqccContinuationConflict("invalid continuation stages")
    for index, stage in enumerate(decoded):
        task_kwargs = stage.get("task_kwargs")
        if not isinstance(task_kwargs, dict):
            raise PrivateQqccContinuationConflict(
                "continuation stage task kwargs are invalid"
            )
        delivery_required = bool(
            stage.get("delivery_required", task_kwargs.get("send_result", False))
        )
        if delivery_required and index != len(decoded) - 1:
            raise PrivateQqccContinuationConflict(
                "only the final continuation stage may deliver a result"
            )
        stage["delivery_required"] = delivery_required
    return tuple(decoded)


def _assert_private_bot_context_tenant(context, private_bot_id: int) -> None:
    bot_data = getattr(context, "bot_data", None)
    if not isinstance(bot_data, dict):
        return
    raw_private_bot_id = bot_data.get("private_qqcc_bot_id")
    if raw_private_bot_id is None:
        return
    try:
        context_private_bot_id = int(raw_private_bot_id)
    except (TypeError, ValueError) as exc:
        raise PrivateQqccContinuationConflict(
            "private continuation context tenant is invalid"
        ) from exc
    if context_private_bot_id != int(private_bot_id):
        raise PrivateQqccContinuationConflict(
            "private continuation context tenant does not match checkpoint"
        )


def build_private_qqcc_draw_continuation_stages(
    *,
    chain: list[dict[str, Any]],
    final_send_result: bool,
    final_allow_contribute: bool,
    final_delete_status: bool,
    final_display_mode_name: str | None = None,
    final_result_meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    from src.lora_catalog import get_lora_default_strength
    from src.services.qqcc_draw_chain_service import (
        QQCC_ORIGINAL_FACE_SWAP_COST,
        QQCC_ORIGINAL_FACE_SWAP_PROMPT,
        is_qqcc_original_face_swap_enabled,
        resolve_qqcc_draw_scene_task_type,
    )

    stages: list[dict[str, Any]] = []
    for index, scene in enumerate(chain):
        is_last_scene = index == len(chain) - 1
        face_swap_enabled = is_qqcc_original_face_swap_enabled(scene)
        task_type = resolve_qqcc_draw_scene_task_type(scene)
        draw_sends_result = (
            final_send_result and is_last_scene and not face_swap_enabled
        )
        task_kwargs: dict[str, Any] = {
            "prompt": str(scene.get("prompt") or ""),
            "negative_prompt": str(scene.get("negative_prompt") or ""),
            "task_type": task_type,
            "delete_status": final_delete_status if draw_sends_result else False,
            "cleanup": True,
            "send_result": draw_sends_result,
            "record_history": draw_sends_result,
            "allow_contribute": (
                final_allow_contribute if draw_sends_result else False
            ),
            "base_priority": 0 if not stages else 100,
            "allow_cancel": not stages,
            "user_cancel_allowed": not stages,
            "show_queue_status": not stages,
        }
        lora_name = str(scene.get("lora_name") or "")
        if lora_name and task_type == "img2img_lora":
            task_kwargs["lora_name"] = lora_name
            task_kwargs["lora_strength"] = get_lora_default_strength(lora_name)
        if draw_sends_result:
            if final_display_mode_name:
                task_kwargs["display_mode_name_override"] = final_display_mode_name
            if final_result_meta is not None:
                task_kwargs["result_meta"] = final_result_meta
        stages.append(
            {
                "executor": "generation",
                "input_mode": "current",
                "delivery_required": draw_sends_result,
                "task_kwargs": task_kwargs,
            }
        )

        if not face_swap_enabled:
            continue
        face_sends_result = final_send_result and is_last_scene
        face_kwargs: dict[str, Any] = {
            "prompt": QQCC_ORIGINAL_FACE_SWAP_PROMPT,
            "task_type": "face_swap_v2",
            "delete_status": final_delete_status if face_sends_result else False,
            "cleanup": True,
            "send_result": face_sends_result,
            "record_history": face_sends_result,
            "allow_contribute": (
                final_allow_contribute if face_sends_result else False
            ),
            "cost_override": QQCC_ORIGINAL_FACE_SWAP_COST,
            "base_priority": 100,
            "allow_cancel": False,
            "user_cancel_allowed": False,
            "show_queue_status": False,
        }
        if face_sends_result:
            face_kwargs["result_task_type"] = task_type
            face_kwargs["result_prompt"] = str(scene.get("prompt") or "")
            face_kwargs["result_input_image_indices"] = [1]
            if final_display_mode_name:
                face_kwargs["display_mode_name_override"] = final_display_mode_name
            if final_result_meta is not None:
                face_kwargs["result_meta"] = final_result_meta
        stages.append(
            {
                "executor": "generation",
                "input_mode": "current_original",
                "delivery_required": face_sends_result,
                "task_kwargs": face_kwargs,
            }
        )
    return stages


async def create_private_qqcc_continuation(
    *,
    stages: list[dict[str, Any]],
    original_input_ref: str,
    context,
    chat_id: int,
    telegram_user_id: int,
    username: str | None,
    status_message_id: int | None,
    original_input_durable: bool = False,
    store: PrivateQqccContinuationStore | None = None,
) -> PrivateQqccContinuationCheckpoint:
    cursor = get_private_bot_submission_cursor()
    if cursor is None:
        raise PrivateQqccContinuationUnavailable(
            "private continuation requires a durable webhook update scope"
        )
    _assert_private_bot_context_tenant(context, cursor.private_bot_id)
    normalized_stages = _normalized_stages(stages)
    stages_json = json.dumps(
        normalized_stages,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    plan_sha256 = hashlib.sha256(stages_json.encode("utf-8")).hexdigest()
    chain_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            (
                f"private_qqcc_continuation:{cursor.private_bot_id}:"
                f"{cursor.update_id}:{cursor.next_sequence}"
            ),
        )
    )
    checkpoint = PrivateQqccContinuationCheckpoint(
        version=PRIVATE_QQCC_CONTINUATION_VERSION,
        chain_id=chain_id,
        plan_sha256=plan_sha256,
        private_bot_id=cursor.private_bot_id,
        update_id=cursor.update_id,
        telegram_user_id=int(telegram_user_id),
        username=str(username) if username else None,
        chat_id=int(chat_id),
        status_message_id=(
            int(status_message_id) if status_message_id is not None else None
        ),
        language_code=str(getattr(context, "lang", None) or "zh")[:16],
        stages=normalized_stages,
        status="ready",
        next_stage_index=0,
        next_submission_sequence=cursor.next_sequence,
        original_input_ref=str(original_input_ref),
        original_input_durable=bool(original_input_durable),
    )
    return await (store or get_private_qqcc_continuation_store()).create(checkpoint)


async def persist_private_qqcc_continuation_input(
    *,
    input_ref: str,
    telegram_user_id: int,
    username: str | None,
) -> str:
    input_ref = str(input_ref or "").strip()
    if not input_ref:
        raise PrivateQqccContinuationUnavailable("continuation input is missing")
    is_local = os.path.isabs(input_ref) or os.path.exists(input_ref)
    if not is_local:
        return input_ref
    if not os.path.exists(input_ref):
        raise PrivateQqccContinuationUnavailable(
            "continuation input disappeared before persistence"
        )

    from src.core import user_core
    from src.logger import UserLogger

    internal_user, _ = await user_core.get_or_create_user_by_telegram(
        telegram_user_id,
        username,
    )
    persisted = await asyncio.to_thread(
        UserLogger(internal_user.id, username).save_input_image,
        input_ref,
    )
    if not persisted:
        raise PrivateQqccContinuationUnavailable(
            "continuation input could not be persisted"
        )
    return str(persisted)


StageExecutor = Callable[
    [PrivateQqccContinuationCheckpoint, dict[str, Any], PrivateQqccContinuationTaskRef, Any],
    Awaitable[tuple[bytes | None, str | None]],
]

DeliveryExecutor = Callable[
    [PrivateQqccContinuationCheckpoint, dict[str, Any], PrivateQqccContinuationTaskRef, Any, bytes],
    Awaitable[None],
]


def _resolve_stage_images(
    checkpoint: PrivateQqccContinuationCheckpoint,
    stage: dict[str, Any],
) -> list[str]:
    original = checkpoint.original_input_ref
    current = checkpoint.current_output_ref or original
    mode = stage.get("input_mode")
    if mode == "current_original":
        return [current, original]
    if mode == "original_current":
        return [original, current]
    return [current]


async def execute_private_qqcc_continuation_stage_default(
    checkpoint: PrivateQqccContinuationCheckpoint,
    stage: dict[str, Any],
    ref: PrivateQqccContinuationTaskRef,
    context,
    *,
    process_generation_task_func=None,
    process_video_task_template_func=None,
    process_ltx_video_task_func=None,
) -> tuple[bytes | None, str | None]:
    if process_generation_task_func is None:
        from src.services.task_service_generation_image import (
            process_standard_generation_task,
        )

        process_generation_task_func = process_standard_generation_task
    if process_video_task_template_func is None:
        from src.services.task_service_entrypoints_video import (
            process_video_task_template,
        )

        process_video_task_template_func = process_video_task_template
    if process_ltx_video_task_func is None:
        from src.services.task_service_entrypoints_specialized import (
            process_ltx_video_task_for_actor,
        )

        process_ltx_video_task_func = process_ltx_video_task_for_actor

    executor = str(stage.get("executor") or "")
    task_kwargs = dict(stage.get("task_kwargs") or {})
    if executor == "generation" and task_kwargs.get("task_type") == "face_swap":
        # Legacy QQCC continuation checkpoints used the old execution label for
        # the internal original-face restoration stage. Standalone quick face
        # swap never enters this continuation executor and remains V1.
        task_kwargs["task_type"] = "face_swap_v2"
    with activate_private_qqcc_continuation_task(ref):
        if executor == "generation":
            result = await process_generation_task_func(
                context=context,
                chat_id=checkpoint.chat_id,
                user_id=checkpoint.telegram_user_id,
                username=checkpoint.username,
                images=_resolve_stage_images(checkpoint, stage),
                status_msg_id=checkpoint.status_message_id,
                **task_kwargs,
            )
            return result
        if executor == "legacy_video":
            images = _resolve_stage_images(checkpoint, stage)
            if len(images) != 2:
                raise PrivateQqccContinuationConflict(
                    "tail-frame video stage requires two inputs"
                )
            result = await process_video_task_template_func(
                context=context,
                image_path=images[0],
                end_image_path=images[1],
                chat_id=checkpoint.chat_id,
                user_id=checkpoint.telegram_user_id,
                username=checkpoint.username,
                status_msg_id=checkpoint.status_message_id,
                **task_kwargs,
            )
            if isinstance(result, tuple):
                return result
            return None, None
        if executor == "ltx_video":
            images = _resolve_stage_images(checkpoint, stage)
            if len(images) != 2:
                raise PrivateQqccContinuationConflict(
                    "LTX tail-frame video stage requires two inputs"
                )
            result = await process_ltx_video_task_func(
                context=context,
                chat_id=checkpoint.chat_id,
                user_id=checkpoint.telegram_user_id,
                username=checkpoint.username,
                image_path=images[0],
                end_image_path=images[1],
                status_msg_id=checkpoint.status_message_id,
                **task_kwargs,
            )
            if isinstance(result, tuple):
                return result
            return None, None
    raise PrivateQqccContinuationConflict(f"unknown continuation executor: {executor}")


async def _load_continuation_output_bytes(output_file: str) -> bytes:
    from src.core.media_paths import resolve_storage_object
    from src.services.storage import storage

    bucket_name, object_name = resolve_storage_object(output_file)

    def download() -> bytes:
        fd, local_path = tempfile.mkstemp(prefix="private_qqcc_delivery_")
        os.close(fd)
        try:
            storage.download_file(bucket_name, object_name, local_path)
            with open(local_path, "rb") as media_file:
                return media_file.read()
        finally:
            with contextlib.suppress(OSError):
                os.unlink(local_path)

    media_bytes = await asyncio.to_thread(download)
    if not media_bytes:
        raise PrivateQqccContinuationUnavailable(
            "continuation delivery output is empty"
        )
    return media_bytes


async def deliver_private_qqcc_continuation_result_default(
    checkpoint: PrivateQqccContinuationCheckpoint,
    stage: dict[str, Any],
    ref: PrivateQqccContinuationTaskRef,
    context,
    media_bytes: bytes,
) -> None:
    from src.services.task_service_generation_common import (
        build_generation_completion_caption,
    )
    from src.services.tg_task_runtime import send_result_media

    task_kwargs = dict(stage.get("task_kwargs") or {})
    task_type = str(
        task_kwargs.get("result_task_type")
        or task_kwargs.get("task_type")
        or task_kwargs.get("mode")
        or (
            "video"
            if stage.get("executor") in {"legacy_video", "ltx_video"}
            else "image"
        )
    )
    prompt = str(
        task_kwargs.get("result_prompt")
        or task_kwargs.get("prompt")
        or task_kwargs.get("prompt_override")
        or task_kwargs.get("default_prompt_text")
        or ""
    )
    is_video = bool(task_kwargs.get("is_video")) or (
        stage.get("executor") in {"legacy_video", "ltx_video"}
    )
    caption = build_generation_completion_caption(
        context,
        task_type,
        display_mode_name_override=(
            str(task_kwargs.get("display_mode_name_override"))
            if task_kwargs.get("display_mode_name_override")
            else None
        ),
    )
    await send_result_media(
        context=context,
        chat_id=checkpoint.chat_id,
        media_bytes=media_bytes,
        is_video=is_video,
        caption=caption,
        task_type=task_type,
        task_id=ref.registry_task_id,
        allow_contribute=bool(task_kwargs.get("allow_contribute", True)),
        reply_markup=None,
        prompt=prompt,
        result_meta=(
            task_kwargs.get("result_meta")
            if isinstance(task_kwargs.get("result_meta"), dict)
            else None
        ),
        lang=checkpoint.language_code,
    )


async def _delete_continuation_status_best_effort(
    checkpoint: PrivateQqccContinuationCheckpoint,
    stage: dict[str, Any],
    context,
) -> None:
    task_kwargs = dict(stage.get("task_kwargs") or {})
    if not task_kwargs.get("delete_status") or checkpoint.status_message_id is None:
        return
    try:
        await context.bot.delete_message(
            chat_id=checkpoint.chat_id,
            message_id=checkpoint.status_message_id,
        )
    except Exception:
        logger.debug(
            "Private QQCC continuation status cleanup failed chain_id=%s",
            checkpoint.chain_id,
            exc_info=True,
        )


async def _deliver_pending_continuation(
    *,
    checkpoint: PrivateQqccContinuationCheckpoint,
    context,
    store: PrivateQqccContinuationStore,
    executor_token: str,
    media_bytes: bytes | None,
    deliver_result_func: DeliveryExecutor | None,
    lease_lost: asyncio.Event,
) -> PrivateQqccContinuationCheckpoint:
    stage_index = checkpoint.current_stage_index
    registry_task_id = checkpoint.current_registry_task_id
    submission_sequence = checkpoint.current_submission_sequence
    if (
        checkpoint.status != "delivery_pending"
        or stage_index is None
        or submission_sequence is None
        or not registry_task_id
        or stage_index < 0
        or stage_index >= len(checkpoint.stages)
    ):
        raise PrivateQqccContinuationConflict(
            "continuation delivery checkpoint is invalid"
        )
    if lease_lost.is_set():
        raise PrivateQqccContinuationUnavailable(
            "continuation lease was lost before delivery"
        )
    checkpoint = await store.claim_delivery(
        chain_id=checkpoint.chain_id,
        stage_index=stage_index,
        registry_task_id=registry_task_id,
        executor_token=executor_token,
    )
    ref = PrivateQqccContinuationTaskRef(
        chain_id=checkpoint.chain_id,
        stage_index=stage_index,
        submission_sequence=submission_sequence,
        registry_task_id=registry_task_id,
        executor_token=executor_token,
    )
    payload = media_bytes or await _load_continuation_output_bytes(
        checkpoint.current_output_ref or ""
    )
    if lease_lost.is_set():
        raise PrivateQqccContinuationUnavailable(
            "continuation lease was lost before delivery"
        )
    deliver = deliver_result_func or deliver_private_qqcc_continuation_result_default
    await deliver(checkpoint, checkpoint.stages[stage_index], ref, context, payload)
    delivered = await store.mark_delivered(ref=ref)
    await _delete_continuation_status_best_effort(
        checkpoint,
        checkpoint.stages[stage_index],
        context,
    )
    return delivered


def _registry_task_id_for_cursor(private_bot_id: int, update_id: int, sequence: int) -> str:
    submission_key = f"private_bot_update:{private_bot_id}:{update_id}:{sequence}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, submission_key))


async def resume_private_qqcc_continuation(
    *,
    chain_id: str,
    context,
    store: PrivateQqccContinuationStore | None = None,
    execute_stage_func: StageExecutor | None = None,
    deliver_result_func: DeliveryExecutor | None = None,
) -> PrivateQqccContinuationCheckpoint | None:
    store = store or get_private_qqcc_continuation_store()
    token = await store.acquire_lock(chain_id)
    if not token:
        return await store.get(chain_id)
    stop_renewal = asyncio.Event()
    lease_lost = asyncio.Event()
    owner_task = asyncio.current_task()

    async def renew_lease() -> None:
        interval = max(0.05, PRIVATE_QQCC_CONTINUATION_LOCK_SECONDS / 3)
        while not stop_renewal.is_set():
            try:
                await asyncio.wait_for(stop_renewal.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                pass
            try:
                renewed = await store.renew_lock(chain_id, token)
            except asyncio.CancelledError:
                raise
            except Exception:
                renewed = False
            if not renewed:
                lease_lost.set()
                if owner_task is not None:
                    owner_task.cancel()
                return

    renewal_task = asyncio.create_task(
        renew_lease(),
        name=f"private-qqcc-continuation-lease:{chain_id}",
    )
    try:
        checkpoint = await store.get(chain_id)
        if checkpoint is None or checkpoint.is_terminal:
            return checkpoint
        _assert_private_bot_context_tenant(context, checkpoint.private_bot_id)
        if checkpoint.status == "running":
            return checkpoint
        context.lang = checkpoint.language_code

        current_cursor = get_private_bot_submission_cursor()
        needs_resumed_scope = not (
            current_cursor is not None
            and current_cursor.private_bot_id == checkpoint.private_bot_id
            and current_cursor.update_id == checkpoint.update_id
            and current_cursor.next_sequence == checkpoint.next_submission_sequence
        )
        scope_manager = (
            activate_private_bot_update_scope(
                PrivateBotUpdateAdmissionScope(
                    private_bot_id=checkpoint.private_bot_id,
                    update_id=checkpoint.update_id,
                    _task_sequence=checkpoint.next_submission_sequence,
                )
            )
            if needs_resumed_scope
            else contextlib.nullcontext()
        )
        with scope_manager:
            while not checkpoint.is_terminal:
                if lease_lost.is_set():
                    raise PrivateQqccContinuationUnavailable(
                        "continuation execution lease was lost"
                    )
                if checkpoint.status == "delivery_pending":
                    checkpoint = await _deliver_pending_continuation(
                        checkpoint=checkpoint,
                        context=context,
                        store=store,
                        executor_token=token,
                        media_bytes=None,
                        deliver_result_func=deliver_result_func,
                        lease_lost=lease_lost,
                    )
                    continue
                if checkpoint.status != "ready" or not checkpoint.has_more_stages:
                    return checkpoint
                stage_index = checkpoint.next_stage_index
                sequence = checkpoint.next_submission_sequence
                registry_task_id = _registry_task_id_for_cursor(
                    checkpoint.private_bot_id,
                    checkpoint.update_id,
                    sequence,
                )
                checkpoint = await store.mark_running(
                    chain_id=chain_id,
                    stage_index=stage_index,
                    submission_sequence=sequence,
                    registry_task_id=registry_task_id,
                    executor_token=token,
                )
                ref = PrivateQqccContinuationTaskRef(
                    chain_id=chain_id,
                    stage_index=stage_index,
                    submission_sequence=sequence,
                    registry_task_id=registry_task_id,
                    executor_token=token,
                )
                stage = checkpoint.stages[stage_index]
                executor = execute_stage_func or (
                    execute_private_qqcc_continuation_stage_default
                )
                media_bytes, output_file = await executor(
                    checkpoint,
                    stage,
                    ref,
                    context,
                )
                if lease_lost.is_set():
                    raise PrivateQqccContinuationUnavailable(
                        "continuation execution lease was lost"
                    )
                checkpoint = await store.get(chain_id)
                if checkpoint is None:
                    raise PrivateQqccContinuationUnavailable(
                        "continuation checkpoint disappeared after stage completion"
                    )
                if not output_file:
                    if checkpoint.status == "delivery_pending":
                        checkpoint = await _deliver_pending_continuation(
                            checkpoint=checkpoint,
                            context=context,
                            store=store,
                            executor_token=token,
                            media_bytes=None,
                            deliver_result_func=deliver_result_func,
                            lease_lost=lease_lost,
                        )
                        continue
                    if checkpoint.status in {"ready", "completed", "failed"}:
                        return checkpoint
                    if checkpoint.status != "running":
                        raise PrivateQqccContinuationConflict(
                            "continuation stage returned no output in an invalid state"
                        )
                    from src.services.task_registry import TaskRegistry

                    try:
                        active_registry_task = await TaskRegistry.get_task_strict(
                            registry_task_id
                        )
                    except Exception as exc:
                        raise PrivateQqccContinuationUnavailable(
                            "continuation registry state is unavailable"
                        ) from exc
                    if active_registry_task is not None:
                        raise PrivateQqccContinuationUnavailable(
                            "continuation stage monitor was interrupted"
                        )
                    return await store.mark_failed(
                        ref=ref,
                        error_code="stage_returned_no_output",
                    )
                # The task flow completion hook must advance the checkpoint
                # before it removes active registry/runtime state.
                if checkpoint.status == "running":
                    return checkpoint
                if lease_lost.is_set():
                    raise PrivateQqccContinuationUnavailable(
                        "continuation execution lease was lost"
                    )
                if checkpoint.status == "delivery_pending":
                    checkpoint = await _deliver_pending_continuation(
                        checkpoint=checkpoint,
                        context=context,
                        store=store,
                        executor_token=token,
                        media_bytes=media_bytes,
                        deliver_result_func=deliver_result_func,
                        lease_lost=lease_lost,
                    )
        return checkpoint
    except asyncio.CancelledError:
        if lease_lost.is_set():
            raise PrivateQqccContinuationUnavailable(
                "continuation execution lease was lost"
            ) from None
        raise
    finally:
        stop_renewal.set()
        renewal_task.cancel()
        await asyncio.gather(renewal_task, return_exceptions=True)
        await store.release_lock(chain_id, token)


async def record_private_qqcc_continuation_task_result(
    *,
    registry_metadata: Any,
    registry_task_id: str,
    saved_inputs: list[str],
    output_file: str | None,
    store: PrivateQqccContinuationStore | None = None,
) -> PrivateQqccContinuationCheckpoint | None:
    ref = normalize_private_qqcc_continuation_task_ref(registry_metadata)
    if ref is None:
        return None
    if ref.registry_task_id != registry_task_id:
        raise PrivateQqccContinuationConflict(
            "registry task id does not match continuation stage"
        )
    if not output_file:
        raise PrivateQqccContinuationUnavailable(
            "continuation stage completed without a durable output"
        )
    return await (store or get_private_qqcc_continuation_store()).record_completed_stage(
        ref=ref,
        output_file=str(output_file),
        saved_inputs=list(saved_inputs or []),
    )


async def list_private_qqcc_continuations_for_recovery(
    *,
    active_registry_task_ids: set[str],
    active_chain_ids: set[str] | None = None,
    store: PrivateQqccContinuationStore | None = None,
) -> list[PrivateQqccContinuationCheckpoint]:
    store = store or get_private_qqcc_continuation_store()
    active_chain_ids = active_chain_ids or set()
    recoverable: list[PrivateQqccContinuationCheckpoint] = []
    for checkpoint in await store.list_all(tolerate_corrupt=True):
        if checkpoint.is_terminal:
            continue
        # A stage result can advance its checkpoint immediately before the
        # old TaskRegistry record/user lock is cleaned. Let that task's
        # recovery owner finish cleanup and resume the chain; otherwise a
        # parallel ready-stage recovery can collide with the old user lock.
        if checkpoint.chain_id in active_chain_ids:
            continue
        if checkpoint.status == "running":
            if checkpoint.current_registry_task_id in active_registry_task_ids:
                continue
            checkpoint = await store.rewind_orphaned_stage(
                chain_id=checkpoint.chain_id
            )
        if checkpoint.status in {"ready", "delivery_pending"}:
            recoverable.append(checkpoint)
    return recoverable


async def private_bot_has_nonterminal_continuations(
    private_bot_id: int,
    *,
    store: PrivateQqccContinuationStore | None = None,
) -> bool:
    store = store or get_private_qqcc_continuation_store()
    return any(
        checkpoint.private_bot_id == int(private_bot_id)
        and not checkpoint.is_terminal
        for checkpoint in await store.list_all()
    )
