import httpx
import pytest

from observer_bot.lmstudio_client import LMStudioClient


@pytest.mark.asyncio
async def test_lmstudio_client_selects_best_downloaded_instruction_model():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "text-embedding-nomic"},
                        {"id": "qwen3-8b-instruct-q4"},
                        {"id": "qwen3-30b-a3b-instruct-2507-q4"},
                    ]
                },
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "摘要结果"}}]},
        )

    http = httpx.AsyncClient(
        base_url="http://lmstudio:1234", transport=httpx.MockTransport(handler)
    )
    client = LMStudioClient(
        base_url="http://lmstudio:1234", http_client=http
    )

    result = await client.generate("请总结")

    assert result.model_id == "qwen3-30b-a3b-instruct-2507-q4"
    assert result.content == "摘要结果"
    assert requests[1].url.path == "/v1/chat/completions"
    assert b"qwen3-30b-a3b-instruct-2507-q4" in requests[1].content
    await client.close()


@pytest.mark.asyncio
async def test_lmstudio_client_honors_explicit_model():
    def handler(request):
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "local-model"}]})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}
        )

    http = httpx.AsyncClient(
        base_url="http://lmstudio:1234", transport=httpx.MockTransport(handler)
    )
    client = LMStudioClient(
        base_url="http://lmstudio:1234",
        preferred_model="local-model",
        http_client=http,
    )

    assert (await client.generate("prompt")).model_id == "local-model"
    await client.close()


@pytest.mark.asyncio
async def test_lmstudio_client_falls_back_when_best_model_cannot_load():
    attempted = []

    def handler(request):
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "qwen3-30b-a3b-instruct-2507-q4"},
                        {"id": "qwen3-8b-instruct-q4"},
                    ]
                },
            )
        model = request.content.decode()
        attempted.append(model)
        if "30b" in model:
            return httpx.Response(500, json={"error": "not enough memory"})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "fallback ok"}}]}
        )

    http = httpx.AsyncClient(
        base_url="http://lmstudio:1234", transport=httpx.MockTransport(handler)
    )
    client = LMStudioClient(base_url="http://lmstudio:1234", http_client=http)

    result = await client.generate("prompt")

    assert result.model_id == "qwen3-8b-instruct-q4"
    assert len(attempted) == 2
    await client.close()
