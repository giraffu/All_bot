import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
COMFY_CLIENT_PATHS = [
    ROOT / "workers" / "comfy_agent" / "comfy_client.py",
    ROOT / "remote_workers" / "comfy_agent" / "comfy_client.py",
]


def load_comfy_client_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"comfy_client_{path.parent.name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
@pytest.mark.parametrize("module_path", COMFY_CLIENT_PATHS)
async def test_queue_prompt_error_includes_comfy_response_body(
    monkeypatch, module_path: Path
):
    module = load_comfy_client_module(module_path)

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
