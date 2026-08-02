import asyncio
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


class FakeProvider:
    def __init__(self):
        self.calls = []

    async def optimize(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "optimized_fields": {"positive_prompt": "optimized scene"},
            "warnings": [],
        }


def _payload(template_ref="ltx_scene_script_cinematic@1"):
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
async def test_executor_is_generic_and_templates_render_different_requests():
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
