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
from workers.prompt_optimizer.provider import LMStudioChatProvider

os.environ.setdefault("AGENT_SECRET_TOKEN", "test-token")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-access")
os.environ.setdefault("MINIO_SECRET_KEY", "test-secret")

from workers.prompt_optimizer import worker_main
from workers.prompt_optimizer.worker_main import CentralClient


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
async def test_minimax_h3_executor_enforces_dynamic_timestamps_and_breast_vocabulary():
    template = get_template_by_ref("minimax_h3_hmnsfw@1")
    base_payload = {
        "profile_ref": "minimax_h3_t2v_prompt@1",
        "template_ref": template.ref,
        "template_hash": template.content_hash,
        "target_task_type": "minimax_h3_t2v",
        "prompt": "two adults",
        "context": {"duration_seconds": 5},
        "media": [],
        "trusted_context": {"addon_ids": []},
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
        "missionary, pov, slow, medium shot. nipples " + "word " * 195,
        "missionary, pov, slow, medium shot. [Shot 2] At 00:05.000, " + "word " * 192,
    ):
        with pytest.raises(PromptOptimizationExecutionError, match="minimax_h3"):
            await execute_prompt_optimization(
                base_payload,
                provider=FakeProvider(invalid),
                load_media=lambda _key: asyncio.sleep(0, result=b"image"),
                preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
            )

    breast_payload = {**base_payload, "trusted_context": {"addon_ids": ["breasts"]}}
    breast_result = (
        "missionary, pov, slow, medium shot. nipples and areoles " + "word " * 193
    )
    await execute_prompt_optimization(
        breast_payload,
        provider=FakeProvider(breast_result),
        load_media=lambda _key: asyncio.sleep(0, result=b"image"),
        preprocess_media=lambda _payload: "data:image/jpeg;base64,aW1hZ2U=",
    )


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
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"optimized_fields":{"positive_prompt":"done"},"warnings":[]}',
                            }
                        ],
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
    assert [path for path, _payload in requests] == ["/v1/responses", "/v1/responses"]
    visual_payload = requests[0][1]
    assert visual_payload["reasoning"] == {"effort": "none"}
    assert visual_payload["store"] is False
    assert any(
        item["type"] == "input_image"
        for message in visual_payload["input"]
        for item in message["content"]
    )
    structured_payload = requests[1][1]
    assert structured_payload["reasoning"] == {"effort": "none"}
    assert structured_payload["store"] is False
    assert structured_payload["text"]["format"]["schema"] == schema
    structured_system = structured_payload["input"][0]["content"][0]["text"]
    assert '"optimized_fields"' in structured_system
    assert '"warnings"' in structured_system
    assert (
        "subject faces camera" in structured_payload["input"][1]["content"][0]["text"]
    )
    assert all(
        item["type"] != "input_image"
        for message in structured_payload["input"]
        for item in message["content"]
    )
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
    payload = json.loads(requests[0].content)
    assert isinstance(payload["model_bundle_versions"], str)
    assert json.loads(payload["model_bundle_versions"])["model"]
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
