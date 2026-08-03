from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


TEXT_STREAM_SCHEMA_VERSION = "allbot.text_stream.v1"
TEXT_STREAM_TTL_SECONDS = 24 * 60 * 60
TEXT_STREAM_KEY_PREFIX = "comfy:task_text_stream:"


class TextStreamConflictError(RuntimeError):
    def __init__(self, code: str, *, expected_sequence: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.expected_sequence = expected_sequence


@dataclass(frozen=True, slots=True)
class TextDeltaAppendResult:
    accepted: bool
    last_sequence: int
    snapshot: dict[str, str]


_APPEND_TEXT_DELTA_SCRIPT = r"""
local task_status = redis.call('HGET', KEYS[1], 'status')
if not task_status then return {-10, 0} end
if task_status ~= 'running' then return {-11, 0} end
if redis.call('HGET', KEYS[1], 'type') ~= 'prompt_optimize' then return {-12, 0} end
if redis.call('HGET', KEYS[1], 'worker_id') ~= ARGV[1] then return {-13, 0} end

local params_raw = redis.call('HGET', KEYS[1], 'params')
if not params_raw then return {-14, 0} end
local params = cjson.decode(params_raw)
local contract = params['text_stream_contract']
if not contract or contract['schema_version'] ~= 'allbot.text_stream.v1' then
  return {-14, 0}
end
local field_allowed = false
for _, field in ipairs(contract['fields'] or {}) do
  if field == ARGV[4] then field_allowed = true end
end
if not field_allowed then return {-15, 0} end

local current_attempt = redis.call('HGET', KEYS[2], 'attempt_id')
if current_attempt and current_attempt ~= ARGV[2] then return {-16, 0} end
local last_sequence = tonumber(redis.call('HGET', KEYS[2], 'last_sequence') or '0')
local sequence = tonumber(ARGV[3])
if sequence <= last_sequence then return {0, last_sequence} end
if sequence ~= last_sequence + 1 then return {-17, last_sequence + 1} end

local current_chars = tonumber(redis.call('HGET', KEYS[2], 'character_count') or '0')
local next_chars = current_chars + tonumber(ARGV[6])
if next_chars > tonumber(contract['max_chars']) then return {-18, last_sequence} end

local value_field = 'field:' .. ARGV[4]
redis.call('HSET', KEYS[2],
  'schema_version', 'allbot.text_stream.v1',
  'attempt_id', ARGV[2],
  'last_sequence', sequence,
  'character_count', next_chars,
  'updated_at', ARGV[7],
  value_field, (redis.call('HGET', KEYS[2], value_field) or '') .. ARGV[5]
)
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[8]))
return {1, sequence}
"""


_ERROR_CODES = {
    -10: "task_not_found",
    -11: "task_not_running",
    -12: "task_type_not_streamable",
    -13: "worker_mismatch",
    -14: "stream_contract_missing",
    -15: "field_not_allowed",
    -16: "stale_attempt",
    -17: "sequence_gap",
    -18: "stream_too_long",
}


def text_stream_key(task_id: str) -> str:
    return f"{TEXT_STREAM_KEY_PREFIX}{task_id}"


def _decode(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


async def read_text_stream_snapshot(redis, task_id: str) -> dict[str, Any] | None:
    if not hasattr(redis, "hgetall"):
        return None
    raw = await redis.hgetall(text_stream_key(task_id))
    if not raw:
        return None
    data = {_decode(key): _decode(value) for key, value in raw.items()}
    fields = {
        key.removeprefix("field:"): value
        for key, value in data.items()
        if key.startswith("field:")
    }
    return {
        "schema_version": data.get("schema_version", TEXT_STREAM_SCHEMA_VERSION),
        "attempt_id": data.get("attempt_id", ""),
        "sequence": int(data.get("last_sequence") or 0),
        "fields": fields,
    }


async def append_text_delta(
    redis,
    *,
    task_key: str,
    task_id: str,
    agent_id: str,
    attempt_id: str,
    sequence: int,
    field: str,
    delta: str,
    updated_at: float,
) -> TextDeltaAppendResult:
    raw_result = await redis.eval(
        _APPEND_TEXT_DELTA_SCRIPT,
        2,
        task_key,
        text_stream_key(task_id),
        agent_id,
        attempt_id,
        str(sequence),
        field,
        delta,
        str(len(delta)),
        str(updated_at),
        str(TEXT_STREAM_TTL_SECONDS),
    )
    code, last_sequence = (int(raw_result[0]), int(raw_result[1]))
    if code < 0:
        raise TextStreamConflictError(
            _ERROR_CODES.get(code, "text_stream_conflict"),
            expected_sequence=last_sequence if code == -17 else None,
        )
    snapshot = await read_text_stream_snapshot(redis, task_id) or {
        "fields": {},
    }
    return TextDeltaAppendResult(
        accepted=code == 1,
        last_sequence=last_sequence,
        snapshot=dict(snapshot.get("fields") or {}),
    )


def build_text_stream_contract(fields: tuple[str, ...], max_chars: int) -> dict[str, Any]:
    return {
        "schema_version": TEXT_STREAM_SCHEMA_VERSION,
        "fields": list(fields),
        "max_chars": int(max_chars),
    }


def serialize_text_stream_event(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
