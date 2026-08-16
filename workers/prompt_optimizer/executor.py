from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from itertools import pairwise
from typing import Any

from src.prompt_optimizer.config_snapshot import snapshot_content_hash
from src.prompt_optimizer.registry import (
    build_output_json_schema,
    get_profile_by_ref,
    get_template_by_ref,
    render_prompt_messages,
)
from workers.prompt_optimizer.provider import ModelResponseError


class PromptOptimizationExecutionError(RuntimeError):
    pass


_MINIMAX_H3_PROFILE_PREFIX = "minimax_h3_"
_MINIMAX_H3_FORBIDDEN_TRIGGERS = ("hmmotion", "hmbreasts", "hmpenis", "hmpussy")
_MINIMAX_H3_MAX_GENERATION_ATTEMPTS = 5
_MINIMAX_H3_HEADER_CLASSES = (
    "handjob",
    "insertion",
    "missionary",
    "cowgirl",
    "blowjob",
    "doggy",
)
_MINIMAX_H3_HEADER_SHOTS = (
    "third-person side view",
    "high-angle downward shot",
    "medium shot",
    "close-up",
    "low angle",
    "wide shot",
)


def _normalize_minimax_h3_header(result_text: str) -> str:
    header_window = result_text[:160]

    def find(pattern: str):
        return re.search(pattern, header_window, flags=re.IGNORECASE)

    class_match = find(rf"\b({'|'.join(_MINIMAX_H3_HEADER_CLASSES)})\b")
    viewpoint_match = find(r"\b(pov|side(?: view)?)\b")
    pace_match = find(r"\b(fast|slow)(?: pace| motion)?\b")
    shot_match = find(
        rf"\b({'|'.join(re.escape(item) for item in _MINIMAX_H3_HEADER_SHOTS)})\b"
    )
    matches = (class_match, viewpoint_match, pace_match, shot_match)
    if not all(matches):
        return result_text
    body_start = max(match.end() for match in matches if match is not None)
    body = result_text[body_start:].lstrip(" ,.;:-")
    if not body:
        return result_text
    viewpoint = "pov" if viewpoint_match.group(1).casefold() == "pov" else "side"
    pace = pace_match.group(1).casefold()
    return (
        f"{class_match.group(1).casefold()}, {viewpoint}, {pace}, "
        f"{shot_match.group(1).casefold()}. {body}"
    )


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
    if profile.version >= 3:
        _validate_official_minimax_h3_output(
            profile,
            result_text,
            context=context,
        )
        return
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
        current <= previous for previous, current in pairwise(timestamps)
    ):
        raise PromptOptimizationExecutionError("invalid_minimax_h3_timestamp")
    word_count = len(re.findall(r"\b[\w'-]+\b", result_text, flags=re.UNICODE))
    if not 200 <= word_count <= 270:
        raise PromptOptimizationExecutionError("invalid_minimax_h3_word_count")


def _validate_official_minimax_h3_output(
    profile,
    result_text: str,
    *,
    context: dict[str, Any],
) -> None:
    duration = int(context.get("duration_seconds") or 0)
    normalized = result_text.replace("\r\n", "\n")
    blocks = normalized.split("\n\n")
    alignment = None
    if profile.id == "minimax_h3_t2v_prompt":
        core_blocks = blocks
    elif profile.id == "minimax_h3_i2v_prompt":
        if len(blocks) != 4:
            raise PromptOptimizationExecutionError("invalid_minimax_h3_field_structure")
        alignment, *core_blocks = blocks
        expected = (
            "For the target video, at 0.00 seconds into the target video, "
            "<Picture 1> (from [Shot 1]) is fully referenced."
        )
        if alignment != expected:
            raise PromptOptimizationExecutionError("invalid_minimax_h3_i2v_alignment")
    elif profile.id == "minimax_h3_flf2v_prompt":
        if len(blocks) != 4:
            raise PromptOptimizationExecutionError("invalid_minimax_h3_field_structure")
        alignment, *core_blocks = blocks
    else:
        raise PromptOptimizationExecutionError("invalid_minimax_h3_profile")

    if len(core_blocks) != 3:
        raise PromptOptimizationExecutionError("invalid_minimax_h3_field_structure")
    field_names = (
        "integrated_multimodal_description",
        "overall_soundscape",
        "non_diegetic_music",
    )
    values: list[str] = []
    for block, field_name in zip(core_blocks, field_names):
        prefix = f"{field_name}: "
        if not block.startswith(prefix) or not block[len(prefix) :].strip():
            raise PromptOptimizationExecutionError("invalid_minimax_h3_field_structure")
        values.append(block[len(prefix) :].strip())
    if any(normalized.count(f"{field_name}:") != 1 for field_name in field_names):
        raise PromptOptimizationExecutionError("invalid_minimax_h3_field_structure")

    integrated = values[0]
    if not integrated.startswith("[Shot 1]"):
        raise PromptOptimizationExecutionError("invalid_minimax_h3_first_shot")
    if re.search(r"\[Shot 1\]\s+At\b", integrated, flags=re.IGNORECASE):
        raise PromptOptimizationExecutionError("invalid_minimax_h3_first_timestamp")
    shot_numbers = [
        int(value) for value in re.findall(r"\[Shot\s+(\d+)\]", integrated)
    ]
    if not shot_numbers or shot_numbers != list(range(1, len(shot_numbers) + 1)):
        raise PromptOptimizationExecutionError("invalid_minimax_h3_shot_sequence")
    for shot_number in shot_numbers[1:]:
        if not re.search(
            rf"\[Shot {shot_number}\]\s+At\s+\d{{2}}:\d{{2}}\.\d{{3}},",
            integrated,
        ):
            raise PromptOptimizationExecutionError("invalid_minimax_h3_shot_timestamp")

    timestamps: list[float] = []
    for minutes, seconds, milliseconds in re.findall(
        r"(?<!\d)(\d{2}):(\d{2})\.(\d{3})(?!\d)", integrated
    ):
        if int(seconds) >= 60:
            raise PromptOptimizationExecutionError("invalid_minimax_h3_timestamp")
        timestamps.append(int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000)
    if len(timestamps) != len(shot_numbers) - 1 or any(
        value >= duration for value in timestamps
    ) or any(
        current <= previous for previous, current in pairwise(timestamps)
    ):
        raise PromptOptimizationExecutionError("invalid_minimax_h3_timestamp")

    if profile.id == "minimax_h3_i2v_prompt" and "<Picture 1>" not in integrated:
        raise PromptOptimizationExecutionError("invalid_minimax_h3_i2v_anchor")
    if profile.id == "minimax_h3_flf2v_prompt":
        pattern = re.compile(
            r"How the reference pictures align with the target video — "
            r"Picture 1 \(from Shot 1\) aligns with the 0\.00-second mark of the target video; "
            rf"Picture 2 \(from Shot (?P<last_shot>\d+)\) aligns with the {duration:.2f}-second mark of the target video\."
        )
        match = pattern.fullmatch(alignment or "")
        if match is None:
            raise PromptOptimizationExecutionError("invalid_minimax_h3_flf2v_alignment")
        if int(match.group("last_shot")) != shot_numbers[-1]:
            raise PromptOptimizationExecutionError("invalid_minimax_h3_flf2v_final_shot")
        if "Picture 1" not in integrated or "Picture 2" not in integrated:
            raise PromptOptimizationExecutionError("invalid_minimax_h3_flf2v_anchor")


def _validated_result(
    raw: dict[str, Any],
    *,
    profile,
    context: dict[str, Any],
    trusted_context: dict[str, Any],
) -> tuple[str, dict[str, str], list[str]]:
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
    normalized_fields = {
        key: value.strip() for key, value in optimized_fields.items()
    }
    result_text = normalized_fields[profile.primary_field]
    if profile.id.startswith(_MINIMAX_H3_PROFILE_PREFIX) and profile.version < 3:
        result_text = _normalize_minimax_h3_header(result_text)
        normalized_fields[profile.primary_field] = result_text
    _validate_profile_output(
        profile,
        result_text,
        context=context,
        trusted_context=trusted_context,
    )
    return result_text, normalized_fields, warnings


def _minimax_h3_retry_instruction(
    reason: str,
    *,
    profile,
    context: dict[str, Any],
    trusted_context: dict[str, Any],
) -> str:
    if profile.version >= 3:
        mode_requirement = {
            "minimax_h3_t2v_prompt": (
                "begin directly with integrated_multimodal_description"
            ),
            "minimax_h3_i2v_prompt": (
                "begin with the exact <Picture 1> first-frame alignment line"
            ),
            "minimax_h3_flf2v_prompt": (
                f"begin with the first/last-frame alignment line ending at "
                f"{int(context.get('duration_seconds') or 0):.2f} seconds and name the actual final Shot"
            ),
        }[profile.id]
        return (
            "\n\nSERVER VALIDATION RETRY: The previous candidate failed server validation "
            f"({reason}). Regenerate from the original inputs instead of explaining the "
            f"failure. {mode_requirement}; then output exactly "
            "integrated_multimodal_description, overall_soundscape, and "
            "non_diegetic_music in that order with one blank line between sections. "
            "Start the timeline with untimestamped [Shot 1], keep later Shot numbers "
            "sequential and timestamps within the declared duration, and use no manual "
            "trigger tokens. Return only the required JSON object."
        )
    return (
        "\n\nSERVER VALIDATION RETRY: The previous candidate failed server validation "
        f"({reason}). Regenerate from the original inputs instead of explaining the "
        "failure. Produce 220-240 English words in exactly one paragraph, begin with "
        "an allowed class word, use no manual trigger token, keep every timestamp "
        "strictly within the declared duration, and recheck the full forbidden-word "
        "list. nipples and areoles require textual or visual support; areolas is always "
        "forbidden. Return only the required JSON object."
    )


def _make_delta_buffer(buffer: list[tuple[str, str]]):
    async def add(field: str, delta: str) -> None:
        buffer.append((field, delta))

    return add


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
    context = payload.get("context") or {}
    trusted_context = payload.get("trusted_context") or {}
    max_attempts = (
        _MINIMAX_H3_MAX_GENERATION_ATTEMPTS
        if profile.id.startswith(_MINIMAX_H3_PROFILE_PREFIX)
        else 1
    )
    attempt_system_prompt = system_prompt
    for attempt in range(max_attempts):
        buffered_deltas: list[tuple[str, str]] = []
        try:
            raw = await provider.optimize(
                system_prompt=attempt_system_prompt,
                user_prompt=user_prompt,
                image_data_urls=image_data_urls,
                json_schema=build_output_json_schema(profile),
                output_fields=profile.output_fields,
                on_text_delta=(
                    _make_delta_buffer(buffered_deltas)
                    if on_text_delta is not None
                    else None
                ),
            )
            result_text, optimized_fields, warnings = _validated_result(
                raw,
                profile=profile,
                context=context,
                trusted_context=trusted_context,
            )
            if (
                on_text_delta is not None
                and str(raw["optimized_fields"][profile.primary_field]).strip()
                != result_text
            ):
                buffered_deltas = [(profile.primary_field, result_text)]
        except (PromptOptimizationExecutionError, ModelResponseError) as exc:
            if attempt + 1 >= max_attempts:
                raise
            attempt_system_prompt = system_prompt + _minimax_h3_retry_instruction(
                str(exc),
                profile=profile,
                context=context,
                trusted_context=trusted_context,
            )
            continue
        if on_text_delta is not None:
            for field, delta in buffered_deltas:
                await on_text_delta(field, delta)
        break
    return {
        "result_kind": "text",
        "result_text": result_text,
        "result_meta": {
            "prompt_optimizer": {
                "schema_version": "allbot.prompt_optimizer.v1",
                "profile_ref": profile.ref,
                "template_ref": template.ref,
                "primary_field": profile.primary_field,
                "optimized_fields": optimized_fields,
                "warnings": warnings,
            }
        },
    }
