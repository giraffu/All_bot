import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
COMFY_CLIENT_PATHS = [
    ROOT / "workers" / "comfy_agent" / "comfy_client.py",
]


def load_comfy_client_module(path: Path):
    spec = importlib.util.spec_from_file_location(
        f"comfy_client_{path.parent.name}", path
    )
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


@pytest.mark.asyncio
@pytest.mark.parametrize("module_path", COMFY_CLIENT_PATHS)
async def test_interrupt_posts_to_comfy_interrupt(monkeypatch, module_path: Path):
    module = load_comfy_client_module(module_path)
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def post(self, path, **kwargs):
            calls.append((path, kwargs))
            return FakeResponse()

    monkeypatch.setattr(module.httpx, "AsyncClient", FakeAsyncClient)

    client = module.ComfyClient("http://comfy.local")

    assert await client.interrupt() is True
    assert calls == [("/interrupt", {"json": {}})]


@pytest.mark.asyncio
@pytest.mark.parametrize("module_path", COMFY_CLIENT_PATHS)
async def test_free_memory_unloads_models_and_releases_allocator(
    monkeypatch, module_path: Path
):
    module = load_comfy_client_module(module_path)
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def post(self, path, **kwargs):
            calls.append((path, kwargs))
            return FakeResponse()

    monkeypatch.setattr(module.httpx, "AsyncClient", FakeAsyncClient)

    client = module.ComfyClient("http://comfy.local")
    await client.free_memory()

    assert calls == [
        (
            "/free",
            {"json": {"unload_models": True, "free_memory": True}},
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("module_path", COMFY_CLIENT_PATHS)
async def test_upload_image_uses_dedicated_media_timeout(
    monkeypatch, module_path: Path
):
    module = load_comfy_client_module(module_path)
    calls = []

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"name": "input.png"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def post(self, path, **kwargs):
            calls.append((path, kwargs))
            return FakeResponse()

    monkeypatch.setattr(module.httpx, "AsyncClient", FakeAsyncClient)

    client = module.ComfyClient(
        "http://comfy.local",
        upload_timeout_seconds=120.0,
    )
    await client.upload_image(b"image-bytes", "input.png")

    assert calls == [
        (
            "/upload/image",
            {
                "files": {
                    "image": ("input.png", b"image-bytes", "image/png")
                },
                "data": {"overwrite": "true"},
                "timeout": 120.0,
            },
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("module_path", COMFY_CLIENT_PATHS)
async def test_upload_image_uses_webp_content_type(monkeypatch, module_path: Path):
    module = load_comfy_client_module(module_path)
    calls = []

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"name": "input.webp"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def post(self, path, **kwargs):
            calls.append((path, kwargs))
            return FakeResponse()

    monkeypatch.setattr(module.httpx, "AsyncClient", FakeAsyncClient)

    client = module.ComfyClient("http://comfy.local")
    await client.upload_image(b"webp-bytes", "input.webp")

    assert calls[0][1]["files"] == {
        "image": ("input.webp", b"webp-bytes", "image/webp")
    }
