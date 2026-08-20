import asyncio
import json
import os
from io import BytesIO

import httpx
import pytest
from PIL import Image

from src.prompt_optimizer.registry import get_template_by_ref
from src.web_api.services.prompt_optimizer_config_service import (
    get_default_config,
    render_config_snapshot,
)
from workers.prompt_optimizer.executor import (
    PromptOptimizationExecutionError,
    execute_prompt_optimization,
)
from workers.prompt_optimizer.json_stream import OptimizedFieldsJsonExtractor
from workers.prompt_optimizer.media import image_bytes_to_data_url
from workers.prompt_optimizer.provider import LMStudioChatProvider, ModelResponseError

os.environ.setdefault("AGENT_SECRET_TOKEN", "test-token")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-access")
os.environ.setdefault("MINIO_SECRET_KEY", "test-secret")

from workers.prompt_optimizer import worker_main
from workers.prompt_optimizer.worker_main import CentralClient, _safe_failure_reason


class FakeProvider:
    def __init__(self, result_text="optimized scene"):
        self.calls = []
        self.result_text = result_text

    async def optimize(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "optimized_fields": {"positive_prompt": self.result_text},
            "warnings": [],
        }


class SequencedProvider:
    def __init__(self, result_texts):
        self.calls = []
        self.result_texts = iter(result_texts)

    async def optimize(self, **kwargs):
        self.calls.append(kwargs)
        result_text = next(self.result_texts)
        if kwargs.get("on_text_delta") is not None:
            await kwargs["on_text_delta"]("positive_prompt", result_text)
        return {
            "optimized_fields": {"positive_prompt": result_text},
            "warnings": [],
        }


def test_incremental_json_extractor_handles_chunked_escapes_and_unicode():
    extractor = OptimizedFieldsJsonExtractor(("positive_prompt",))
    chunks = [
        '{"optimized_fields":{"positive_prompt":"Line ',
        '\\"one\\" and \\u4f60',
        '\\u597d"},"warnings":[]}',
    ]
    emitted = ""
    for chunk in chunks:
        emitted += extractor.feed(chunk).get("positive_prompt", "")
    parsed = json.loads("".join(chunks))
    extractor.verify(parsed)
    assert emitted == 'Line "one" and 你好'


def _payload(template_ref="ltx_scene_script_cinematic@3"):
    template = get_template_by_ref(template_ref)
    return {
        "profile_ref": "ltx_eros_v14_i2v@1",
        "template_ref": template.ref,
        "template_hash": template.content_hash,
        "target_task_type": "ltx_video_v2",
        "prompt": "subject turns",
        "context": {"duration_seconds": 5},
        "media": [{"role": "start_image", "object_key": "start.webp"}],
    }


@pytest.mark.asyncio
async def test_executor_uses_current_template_and_can_replay_inactive_legacy_version():
    provider = FakeProvider()

    async def loader(_key):
        await asyncio.sleep(0)
        return b"image"

    def preprocess(_payload):
        return "data:image/jpeg;base64,aW1hZ2U="

    first = await execute_prompt_optimization(
        _payload(), provider=provider, load_media=loader, preprocess_media=preprocess
    )
    await execute_prompt_optimization(
        _payload("ltx_timestamp_motion@1"),
        provider=provider,
        load_media=loader,
        preprocess_media=preprocess,
    )

    assert first["result_kind"] == "text"
    assert first["result_text"] == "optimized scene"
    assert provider.calls[0]["user_prompt"] != provider.calls[1]["user_prompt"]
    assert provider.calls[0]["json_schema"] == provider.calls[1]["json_schema"]


@pytest.mark.asyncio
async def test_executor_fails_closed_on_template_hash_mismatch():
    payload = _payload()
    payload["template_hash"] = "bad"
    with pytest.raises(PromptOptimizationExecutionError, match="hash"):
        await execute_prompt_optimization(
            payload,
            provider=FakeProvider(),
            load_media=lambda _key: asyncio.sleep(0, result=b"image"),
            preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result_text",
    [
        "hmmotion, " + "word " * 210,
        "HMBreasts, " + "word " * 210,
        "dynv2, " + "word " * 210,
        "inniepussy, " + "word " * 210,
        "fj., " + "word " * 210,
        "too short",
        "word " * 271,
    ],
)
async def test_minimax_h3_executor_rejects_manual_triggers_and_off_distribution_length(
    result_text,
):
    template = get_template_by_ref("minimax_h3_hmnsfw@1")
    payload = {
        "profile_ref": "minimax_h3_t2v_prompt@1",
        "template_ref": template.ref,
        "template_hash": template.content_hash,
        "target_task_type": "minimax_h3_t2v",
        "prompt": "two adults",
        "context": {"duration_seconds": 5},
        "media": [],
    }
    with pytest.raises(PromptOptimizationExecutionError, match="minimax_h3"):
        await execute_prompt_optimization(
            payload,
            provider=FakeProvider(result_text),
            load_media=lambda _key: asyncio.sleep(0, result=b"image"),
            preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
        )


@pytest.mark.asyncio
async def test_minimax_h3_executor_enforces_dynamic_timestamps_and_forbidden_vocabulary():
    template = get_template_by_ref("minimax_h3_hmnsfw@1")
    base_payload = {
        "profile_ref": "minimax_h3_t2v_prompt@1",
        "template_ref": template.ref,
        "template_hash": template.content_hash,
        "target_task_type": "minimax_h3_t2v",
        "prompt": "two adults",
        "context": {"duration_seconds": 5},
        "media": [],
        "trusted_context": {},
    }
    valid = "missionary, pov, slow, medium shot. " + "word " * 196
    accepted = await execute_prompt_optimization(
        base_payload,
        provider=FakeProvider(valid),
        load_media=lambda _key: asyncio.sleep(0, result=b"image"),
        preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
    )
    assert accepted["result_text"].startswith("missionary")

    for invalid in (
        "missionary, pov, slow, medium shot. areolas " + "word " * 195,
        "missionary, pov, slow, medium shot. [Shot 2] At 00:05.000, " + "word " * 192,
    ):
        with pytest.raises(PromptOptimizationExecutionError, match="minimax_h3"):
            await execute_prompt_optimization(
                base_payload,
                provider=FakeProvider(invalid),
                load_media=lambda _key: asyncio.sleep(0, result=b"image"),
                preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
            )


@pytest.mark.asyncio
async def test_minimax_h3_executor_retries_before_publishing_stream_deltas():
    template = get_template_by_ref("minimax_h3_hmnsfw@1")
    invalid = "missionary, pov, slow, medium shot. " + "word " * 100
    valid = "missionary, pov, slow, medium shot. " + "word " * 196
    provider = SequencedProvider([invalid, valid])
    published = []

    async def on_text_delta(field, delta):
        published.append((field, delta))

    result = await execute_prompt_optimization(
        {
            "profile_ref": "minimax_h3_t2v_prompt@1",
            "template_ref": template.ref,
            "template_hash": template.content_hash,
            "target_task_type": "minimax_h3_t2v",
            "prompt": "two adults",
            "context": {"duration_seconds": 5},
            "media": [],
            "trusted_context": {},
        },
        provider=provider,
        load_media=lambda _key: asyncio.sleep(0, result=b"image"),
        preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
        on_text_delta=on_text_delta,
    )

    assert result["result_text"] == valid.strip()
    assert len(provider.calls) == 2
    assert (
        "previous candidate failed server validation"
        in provider.calls[1]["system_prompt"]
    )
    assert published == [("positive_prompt", valid)]


@pytest.mark.asyncio
async def test_minimax_h3_executor_retries_invalid_model_json_response():
    template = get_template_by_ref("minimax_h3_hmnsfw@1")
    valid = "missionary, pov, slow, medium shot. " + "word " * 196

    class InvalidThenValidProvider(FakeProvider):
        async def optimize(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise ModelResponseError("lmstudio_invalid_json")
            return {
                "optimized_fields": {"positive_prompt": valid},
                "warnings": [],
            }

    provider = InvalidThenValidProvider()
    result = await execute_prompt_optimization(
        {
            "profile_ref": "minimax_h3_t2v_prompt@1",
            "template_ref": template.ref,
            "template_hash": template.content_hash,
            "target_task_type": "minimax_h3_t2v",
            "prompt": "two adults",
            "context": {"duration_seconds": 5},
            "media": [],
            "trusted_context": {"addon_ids": []},
        },
        provider=provider,
        load_media=lambda _key: asyncio.sleep(0, result=b"image"),
        preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
    )

    assert result["result_text"] == valid.strip()
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_minimax_h3_executor_restores_omitted_empty_warnings_field():
    template = get_template_by_ref("minimax_h3_10eros_naughtytimes@4")
    expected = _official_h3_prompt("i2v")
    generated = expected.split("\n\n", 1)[1]
    generated = generated.removeprefix("integrated_multimodal_description: ")

    class MissingWarningsProvider(FakeProvider):
        async def optimize(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("on_text_delta") is not None:
                await kwargs["on_text_delta"]("positive_prompt", generated)
            return {"optimized_fields": {"positive_prompt": generated}}

    published = []

    async def on_text_delta(field, delta):
        published.append((field, delta))

    result = await execute_prompt_optimization(
        {
            "profile_ref": "minimax_h3_i2v_prompt@5",
            "template_ref": template.ref,
            "template_hash": template.content_hash,
            "target_task_type": "minimax_h3_i2v",
            "prompt": "two adults move through the room",
            "context": {"duration_seconds": 10},
            "media": [{"role": "start_image", "object_key": "start.webp"}],
        },
        provider=MissingWarningsProvider(),
        load_media=lambda _key: asyncio.sleep(0, result=b"image"),
        preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
        on_text_delta=on_text_delta,
    )

    assert result["result_text"] == expected
    assert result["result_meta"]["prompt_optimizer"]["warnings"] == []
    assert published == [("positive_prompt", expected)]


@pytest.mark.asyncio
async def test_minimax_h3_executor_still_rejects_unknown_output_fields():
    template = get_template_by_ref("minimax_h3_10eros_naughtytimes@4")

    class ExtraFieldProvider(FakeProvider):
        async def optimize(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "optimized_fields": {
                    "positive_prompt": _official_h3_prompt("t2v")
                },
                "warnings": [],
                "explanation": "not allowed",
            }

    provider = ExtraFieldProvider()
    with pytest.raises(PromptOptimizationExecutionError, match="unknown_output_fields"):
        await execute_prompt_optimization(
            {
                "profile_ref": "minimax_h3_t2v_prompt@5",
                "template_ref": template.ref,
                "template_hash": template.content_hash,
                "target_task_type": "minimax_h3_t2v",
                "prompt": "two adults move through the room",
                "context": {"duration_seconds": 10},
                "media": [],
            },
            provider=provider,
            load_media=lambda _key: asyncio.sleep(0, result=b"image"),
            preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
        )

    assert len(provider.calls) == 5


@pytest.mark.asyncio
async def test_minimax_h3_executor_normalizes_complete_reordered_header():
    template = get_template_by_ref("minimax_h3_hmnsfw@1")
    generated = (
        "wide shot, slow pace, insertion, side view. A woman moves. " + "word " * 194
    )
    published = []

    async def on_text_delta(field, delta):
        published.append((field, delta))

    result = await execute_prompt_optimization(
        {
            "profile_ref": "minimax_h3_t2v_prompt@1",
            "template_ref": template.ref,
            "template_hash": template.content_hash,
            "target_task_type": "minimax_h3_t2v",
            "prompt": "two adults",
            "context": {"duration_seconds": 5},
            "media": [],
            "trusted_context": {"addon_ids": []},
        },
        provider=FakeProvider(generated),
        load_media=lambda _key: asyncio.sleep(0, result=b"image"),
        preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
        on_text_delta=on_text_delta,
    )

    assert result["result_text"].startswith(
        "insertion, side, slow, wide shot. A woman moves."
    )
    assert published == [("positive_prompt", result["result_text"])]


def _official_h3_prompt(
    mode: str, *, duration: int = 10, second_shot: bool = False, dialogue: str = ""
) -> str:
    alignment = ""
    if mode == "i2v":
        alignment = (
            "For the target video, at 0.00 seconds into the target video, "
            "<Picture 1> (from [Shot 1]) is fully referenced.\n\n"
        )
    elif mode == "flf2v":
        last_shot = 2 if second_shot else 1
        alignment = (
            "How the reference pictures align with the target video — "
            "Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; "
            f"Picture 2 (from Shot {last_shot}) aligns with the {duration:.2f}-second mark of the target video.\n\n"
        )
    anchor = (
        "The subjects and composition in <Picture 1> remain exact as motion begins. "
        if mode == "i2v"
        else "The scene begins in the state established by Picture 1 and moves continuously toward Picture 2. "
        if mode == "flf2v"
        else ""
    )
    shot_body = (
        "[Shot 1] Live-action, a medium-wide shot frames two adults moving continuously "
        "through the room while the camera tracks them at slow speed."
    )
    if anchor:
        shot_body += f" {anchor.strip()}"
    if dialogue:
        shot_body += f" {dialogue.strip()}"
    if second_shot:
        shot_body += (
            " [Shot 2] At 00:05.000, the camera cuts to a close shot that reaches "
            "the final pose and composition."
        )
    return (
        alignment
        + "integrated_multimodal_description: "
        + shot_body
        + "\n\noverall_soundscape: Quiet room ambience, footsteps, fabric movement, and steady breathing."
        + "\n\nnon_diegetic_music: N/A"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "profile_ref", "media"),
    [
        ("t2v", "minimax_h3_t2v_prompt@5", []),
        (
            "i2v",
            "minimax_h3_i2v_prompt@5",
            [{"role": "start_image", "object_key": "start.webp"}],
        ),
        (
            "flf2v",
            "minimax_h3_flf2v_prompt@5",
            [
                {"role": "start_image", "object_key": "start.webp"},
                {"role": "end_image", "object_key": "end.webp"},
            ],
        ),
    ],
)
async def test_minimax_h3_official_profiles_accept_mode_specific_three_field_output(
    mode, profile_ref, media
):
    template = get_template_by_ref("minimax_h3_10eros_naughtytimes@4")
    expected = _official_h3_prompt(mode, second_shot=mode == "flf2v")
    result = await execute_prompt_optimization(
        {
            "profile_ref": profile_ref,
            "template_ref": template.ref,
            "template_hash": template.content_hash,
            "target_task_type": f"minimax_h3_{mode}",
            "prompt": "two adults move through the room",
            "context": {"duration_seconds": 10},
            "media": media,
        },
        provider=FakeProvider(expected),
        load_media=lambda _key: asyncio.sleep(0, result=b"image"),
        preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
    )

    assert result["result_text"] == expected


@pytest.mark.asyncio
async def test_minimax_h3_i2v_server_compiles_harmless_model_formatting_variations():
    template = get_template_by_ref("minimax_h3_10eros_naughtytimes@4")
    generated = _official_h3_prompt("i2v")
    generated = generated.split("\n\n", 1)[1]
    generated = generated.replace(
        "remain exact as motion begins. ",
        "remain exact as motion begins.\n\n",
    )

    result = await execute_prompt_optimization(
        {
            "profile_ref": "minimax_h3_i2v_prompt@5",
            "template_ref": template.ref,
            "template_hash": template.content_hash,
            "target_task_type": "minimax_h3_i2v",
            "prompt": "two adults move through the room",
            "context": {"duration_seconds": 10},
            "media": [{"role": "start_image", "object_key": "start.webp"}],
        },
        provider=FakeProvider(generated),
        load_media=lambda _key: asyncio.sleep(0, result=b"image"),
        preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
    )

    assert result["result_text"] == _official_h3_prompt("i2v")
    assert result["result_meta"]["prompt_optimizer"]["optimized_fields"] == {
        "positive_prompt": _official_h3_prompt("i2v")
    }


@pytest.mark.asyncio
async def test_minimax_h3_i2v_server_restores_omitted_integrated_field_header():
    template = get_template_by_ref("minimax_h3_10eros_naughtytimes@4")
    generated = _official_h3_prompt("i2v").split("\n\n", 1)[1]
    generated = generated.removeprefix("integrated_multimodal_description: ")

    result = await execute_prompt_optimization(
        {
            "profile_ref": "minimax_h3_i2v_prompt@5",
            "template_ref": template.ref,
            "template_hash": template.content_hash,
            "target_task_type": "minimax_h3_i2v",
            "prompt": "two adults move through the room",
            "context": {"duration_seconds": 10},
            "media": [{"role": "start_image", "object_key": "start.webp"}],
        },
        provider=FakeProvider(generated),
        load_media=lambda _key: asyncio.sleep(0, result=b"image"),
        preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
    )

    assert result["result_text"] == _official_h3_prompt("i2v")


@pytest.mark.asyncio
async def test_minimax_h3_i2v_server_restores_deterministic_first_frame_anchor():
    template = get_template_by_ref("minimax_h3_10eros_naughtytimes@4")
    alignment, core = _official_h3_prompt("i2v").split("\n\n", 1)
    generated = (
        alignment
        + "\n\n"
        + core.replace(
            "<Picture 1> remain exact as motion begins.",
            "the opening image remains exact as motion begins.",
        )
    )

    result = await execute_prompt_optimization(
        {
            "profile_ref": "minimax_h3_i2v_prompt@5",
            "template_ref": template.ref,
            "template_hash": template.content_hash,
            "target_task_type": "minimax_h3_i2v",
            "prompt": "two adults move through the room",
            "context": {"duration_seconds": 10},
            "media": [{"role": "start_image", "object_key": "start.webp"}],
        },
        provider=FakeProvider(generated),
        load_media=lambda _key: asyncio.sleep(0, result=b"image"),
        preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
    )

    assert result["result_text"].startswith(alignment + "\n\n")
    assert (
        "integrated_multimodal_description: [Shot 1] <Picture 1> is the exact opening frame."
        in result["result_text"]
    )


@pytest.mark.asyncio
async def test_minimax_h3_flf2v_server_restores_deterministic_keyframe_anchors():
    template = get_template_by_ref("minimax_h3_10eros_naughtytimes@4")
    alignment, core = _official_h3_prompt("flf2v", second_shot=True).split("\n\n", 1)
    generated = (
        alignment
        + "\n\n"
        + core.replace("Picture 1", "the opening image", 1).replace(
            "Picture 2", "the final image", 1
        )
    )

    result = await execute_prompt_optimization(
        {
            "profile_ref": "minimax_h3_flf2v_prompt@5",
            "template_ref": template.ref,
            "template_hash": template.content_hash,
            "target_task_type": "minimax_h3_flf2v",
            "prompt": "move continuously from the opening image to the final image",
            "context": {"duration_seconds": 10},
            "media": [
                {"role": "start_image", "object_key": "start.webp"},
                {"role": "end_image", "object_key": "end.webp"},
            ],
        },
        provider=FakeProvider(generated),
        load_media=lambda _key: asyncio.sleep(0, result=b"image"),
        preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
    )

    assert "[Shot 1] Picture 1 is the exact opening frame" in result["result_text"]
    assert "Picture 2 is the exact final frame" in result["result_text"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    [
        (
            "integrated_multimodal_description: [Shot 1] A scene.\n\n"
            "non_diegetic_music: N/A\n\noverall_soundscape: Quiet."
        ),
        _official_h3_prompt("i2v").replace("<Picture 1>", "Picture 1"),
        _official_h3_prompt("flf2v").replace("10.00-second", "9.00-second"),
        _official_h3_prompt("flf2v", second_shot=True).replace(
            "Picture 2 (from Shot 2)", "Picture 2 (from Shot 1)"
        ),
    ],
)
async def test_minimax_h3_official_profile_rejects_invalid_fields_or_alignment(invalid):
    template = get_template_by_ref("minimax_h3_10eros_naughtytimes@4")
    media = (
        [{"role": "start_image", "object_key": "start.webp"}]
        if "For the target video" in invalid
        else [
            {"role": "start_image", "object_key": "start.webp"},
            {"role": "end_image", "object_key": "end.webp"},
        ]
        if "How the reference pictures" in invalid
        else []
    )
    profile_ref = (
        "minimax_h3_i2v_prompt@5"
        if len(media) == 1
        else "minimax_h3_flf2v_prompt@5"
        if len(media) == 2
        else "minimax_h3_t2v_prompt@5"
    )
    with pytest.raises(PromptOptimizationExecutionError, match="minimax_h3"):
        await execute_prompt_optimization(
            {
                "profile_ref": profile_ref,
                "template_ref": template.ref,
                "template_hash": template.content_hash,
                "target_task_type": profile_ref.replace("_prompt@5", ""),
                "prompt": "two adults",
                "context": {"duration_seconds": 10},
                "media": media,
            },
            provider=FakeProvider(invalid),
            load_media=lambda _key: asyncio.sleep(0, result=b"image"),
            preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
        )


@pytest.mark.asyncio
async def test_minimax_h3_retries_when_model_translates_detected_dialogue():
    template = get_template_by_ref("minimax_h3_10eros_naughtytimes@4")
    translated = _official_h3_prompt(
        "t2v", dialogue="(S1) says: <d>[Chinese] 不要离开我。</d>"
    )
    preserved = _official_h3_prompt(
        "t2v", dialogue="(S1) says: <d>[English] Please do not leave me.</d>"
    )
    provider = SequencedProvider([translated, preserved])

    result = await execute_prompt_optimization(
        {
            "profile_ref": "minimax_h3_t2v_prompt@5",
            "template_ref": template.ref,
            "template_hash": template.content_hash,
            "target_task_type": "minimax_h3_t2v",
            "prompt": '女人低声说：“Please do not leave me.”',
            "context": {"duration_seconds": 10},
            "media": [],
        },
        provider=provider,
        load_media=lambda _key: asyncio.sleep(0, result=b"image"),
        preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
    )

    assert len(provider.calls) == 2
    assert "<d>[English] Please do not leave me.</d>" in result["result_text"]
    assert "dialogue" in provider.calls[1]["system_prompt"].casefold()


@pytest.mark.asyncio
async def test_minimax_h3_inactive_v3_snapshot_remains_replayable():
    template = get_template_by_ref("minimax_h3_10eros_naughtytimes@2")
    expected = _official_h3_prompt("t2v")

    result = await execute_prompt_optimization(
        {
            "profile_ref": "minimax_h3_t2v_prompt@3",
            "template_ref": template.ref,
            "template_hash": template.content_hash,
            "target_task_type": "minimax_h3_t2v",
            "prompt": "two adults move through the room",
            "context": {"duration_seconds": 10},
            "media": [],
        },
        provider=FakeProvider(expected),
        load_media=lambda _key: asyncio.sleep(0, result=b"image"),
        preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
    )

    assert result["result_text"] == expected


@pytest.mark.asyncio
async def test_executor_accepts_fenced_dynamic_snapshot_and_rejects_tampering():
    payload = _payload()
    payload["prompt_config_snapshot"] = render_config_snapshot(
        config=get_default_config("ltx_video_v2"),
        profile_ref=payload["profile_ref"],
        variables={
            "duration_seconds": 5,
            "end_frame_clause": "",
            "media_frame_instructions": "start image",
            "original_prompt": "subject turns",
            "character_descriptions": "",
            "environment_description": "",
        },
    )
    provider = FakeProvider()
    await execute_prompt_optimization(
        payload,
        provider=provider,
        load_media=lambda _key: asyncio.sleep(0, result=b"image"),
        preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
    )
    assert (
        provider.calls[0]["system_prompt"]
        == payload["prompt_config_snapshot"]["system_message"]
    )
    payload["prompt_config_snapshot"]["user_message"] += " tampered"
    with pytest.raises(PromptOptimizationExecutionError, match="config_hash"):
        await execute_prompt_optimization(
            payload,
            provider=provider,
            load_media=lambda _key: asyncio.sleep(0, result=b"image"),
            preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
        )


def test_prompt_worker_reports_safe_structured_failure_code():
    assert (
        _safe_failure_reason(
            PromptOptimizationExecutionError("invalid_minimax_h3_field_structure")
        )
        == "PromptOptimizationExecutionError:invalid_minimax_h3_field_structure"
    )
    assert _safe_failure_reason(RuntimeError("secret user input")) == "RuntimeError"


def test_media_preprocessor_resizes_and_normalizes_to_jpeg():
    buffer = BytesIO()
    Image.new("RGB", (2000, 1000), "red").save(buffer, "PNG")
    data_url = image_bytes_to_data_url(buffer.getvalue())
    assert data_url.startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_lmstudio_readiness_requires_vision_context_and_parallel_four():
    async def handler(_request):
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "key": "qwen-source",
                        "loaded_instances": [
                            {
                                "id": "ltx-prompt-optimizer",
                                "vision": True,
                                "context_length": 16384,
                                "parallel": 4,
                            }
                        ],
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = LMStudioChatProvider(
        base_url="http://lmstudio",
        model="ltx-prompt-optimizer",
        client=client,
    )
    readiness = await provider.readiness()
    assert readiness.ready is True
    await client.aclose()


@pytest.mark.asyncio
async def test_lmstudio_provider_uses_visual_notes_then_structured_response():
    requests = []

    async def handler(request):
        payload = json.loads(request.content)
        requests.append((request.url.path, payload))
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "output": [
                        {
                            "type": "reasoning",
                            "content": [
                                {
                                    "type": "reasoning_text",
                                    "text": "subject faces camera",
                                }
                            ],
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "text": '{"optimized_fields":{"positive_prompt":"done"},"warnings":[]}',
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = LMStudioChatProvider(
        base_url="http://lmstudio",
        model="ltx-prompt-optimizer",
        client=client,
    )
    schema = {
        "type": "object",
        "properties": {
            "optimized_fields": {"type": "object"},
            "warnings": {"type": "array"},
        },
        "required": ["optimized_fields", "warnings"],
    }

    result = await provider.optimize(
        system_prompt="system",
        user_prompt="user",
        image_data_urls=["data:image/jpeg;base64,aW1hZ2U="],
        json_schema=schema,
    )

    assert result["optimized_fields"]["positive_prompt"] == "done"
    assert [path for path, _payload in requests] == [
        "/v1/responses",
        "/v1/completions",
    ]
    visual_payload = requests[0][1]
    assert visual_payload["reasoning"] == {"effort": "none"}
    assert visual_payload["store"] is False
    assert any(
        item["type"] == "input_image"
        for message in visual_payload["input"]
        for item in message["content"]
    )
    structured_payload = requests[1][1]
    assert structured_payload["store"] is False
    assert structured_payload["stream"] is False
    assert structured_payload["max_tokens"] == 3072
    assert structured_payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "prompt_optimization_result",
            "strict": True,
            "schema": schema,
        },
    }
    completion_prompt = structured_payload["prompt"]
    assert '"optimized_fields"' in completion_prompt
    assert '"warnings"' in completion_prompt
    assert "subject faces camera" in completion_prompt
    assert completion_prompt.endswith("<think>\n</think>\n")
    await client.aclose()


@pytest.mark.asyncio
async def test_lmstudio_provider_streams_completion_text_deltas():
    requests = []

    async def handler(request):
        requests.append((request.url.path, json.loads(request.content)))
        stream_body = (
            'data: {"choices":[{"text":"{\\"optimized_fields\\":'
            '{\\"positive_prompt\\":\\"hello "}]}\n'
            'data: {"choices":[{"text":"world\\"},\\"warnings\\":[]}"}]}\n'
            "data: [DONE]\n"
        )
        return httpx.Response(200, text=stream_body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = LMStudioChatProvider(
        base_url="http://lmstudio",
        model="ltx-prompt-optimizer",
        client=client,
    )
    streamed = []

    async def on_text_delta(field, delta):
        streamed.append((field, delta))

    result = await provider.optimize(
        system_prompt="system",
        user_prompt="user",
        image_data_urls=[],
        json_schema={"type": "object"},
        output_fields=("positive_prompt",),
        on_text_delta=on_text_delta,
    )

    assert requests[0][0] == "/v1/completions"
    assert requests[0][1]["stream"] is True
    assert requests[0][1]["response_format"]["type"] == "json_schema"
    assert result["optimized_fields"]["positive_prompt"] == "hello world"
    assert "".join(delta for _field, delta in streamed) == "hello world"
    assert {field for field, _delta in streamed} == {"positive_prompt"}
    await client.aclose()


@pytest.mark.asyncio
async def test_central_heartbeat_is_scalar_and_fails_closed_on_http_error():
    requests = []

    async def ok_handler(request):
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    client = httpx.AsyncClient(
        base_url="http://central", transport=httpx.MockTransport(ok_handler)
    )
    central = CentralClient(client=client)
    await central.heartbeat("lane", ready=True, reason="ready")
    await central.task_heartbeat("task-1", "lane")
    payload = json.loads(requests[0].content)
    assert isinstance(payload["model_bundle_versions"], str)
    assert json.loads(payload["model_bundle_versions"])["model"]
    assert requests[1].url.path == "/api/agent/task/task_heartbeat"
    assert json.loads(requests[1].content) == {
        "task_id": "task-1",
        "agent_id": "lane",
    }
    await client.aclose()

    async def failed_handler(_request):
        return httpx.Response(500, text="failed")

    failed_client = httpx.AsyncClient(
        base_url="http://central", transport=httpx.MockTransport(failed_handler)
    )
    with pytest.raises(httpx.HTTPStatusError):
        await CentralClient(client=failed_client).heartbeat(
            "lane", ready=True, reason="ready"
        )
    await failed_client.aclose()


def test_lane_readiness_stays_ready_between_successful_probes():
    worker_main._lane_readiness.clear()
    for lane in range(1, worker_main.LANE_COUNT + 1):
        worker_main._set_lane_readiness(lane, True, "ready")
    assert worker_main._state["ready"] is True

    worker_main._set_lane_readiness(1, False, "central_unavailable")
    assert worker_main._state["ready"] is False
    worker_main._set_lane_readiness(1, True, "ready")
    assert worker_main._state["ready"] is True


@pytest.mark.asyncio
async def test_long_prompt_execution_keeps_task_heartbeat_alive_until_it_finishes():
    class HeartbeatCentral:
        def __init__(self):
            self.calls = []
            self.two_heartbeats = asyncio.Event()

        async def task_heartbeat(self, task_id, agent_id):
            self.calls.append((task_id, agent_id))
            if len(self.calls) >= 2:
                self.two_heartbeats.set()

    central = HeartbeatCentral()

    async def long_execution():
        await asyncio.wait_for(central.two_heartbeats.wait(), timeout=0.5)
        return "optimized"

    result = await worker_main._run_with_task_heartbeats(
        long_execution(),
        central=central,
        task_id="task-long",
        agent_id="prompt_optimizer_test_02",
        interval_seconds=0.001,
    )

    assert result == "optimized"
    assert central.calls[:2] == [
        ("task-long", "prompt_optimizer_test_02"),
        ("task-long", "prompt_optimizer_test_02"),
    ]
    calls_after_completion = len(central.calls)
    await asyncio.sleep(0.01)
    assert len(central.calls) == calls_after_completion
