import asyncio
import json
import os
from io import BytesIO

import httpx
import pytest
from PIL import Image

from src.prompt_optimizer.registry import get_template_by_ref
from workers.prompt_optimizer.executor import (
    PromptOptimizationExecutionError,
    execute_prompt_optimization,
)
from workers.prompt_optimizer.media import image_bytes_to_data_url
from workers.prompt_optimizer.provider import LMStudioChatProvider

os.environ.setdefault("AGENT_SECRET_TOKEN", "test-token")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-access")
os.environ.setdefault("MINIO_SECRET_KEY", "test-secret")

from workers.prompt_optimizer import worker_main  # noqa: E402
from workers.prompt_optimizer.worker_main import CentralClient  # noqa: E402


class FakeProvider:
    def __init__(self):
        self.calls = []

    async def optimize(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "optimized_fields": {"positive_prompt": "optimized scene"},
            "warnings": [],
        }


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
    assert "subject faces camera" in structured_payload["input"][1]["content"][0]["text"]
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
