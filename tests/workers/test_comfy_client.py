import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = str(ROOT / "workers" / "comfy_agent")


def load_comfy_client_module():
    if MODULE_DIR not in sys.path:
        sys.path.insert(0, MODULE_DIR)
    import comfy_client

    return comfy_client


@pytest.mark.asyncio
async def test_queue_prompt_error_includes_comfy_response_body(monkeypatch):
    module = load_comfy_client_module()

    class FakeResponse:
        status_code = 400
        text = '{"error": "node validation failed", "node_id": "42"}'

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(module.httpx, "AsyncClient", FakeAsyncClient)

    client = module.ComfyClient("http://comfy.local")
    with pytest.raises(RuntimeError) as exc:
        await client.queue_prompt({"1": {"inputs": {}}}, "client-1")

    message = str(exc.value)
    assert "ComfyUI /prompt returned 400" in message
    assert "node validation failed" in message
    assert "node_id" in message
