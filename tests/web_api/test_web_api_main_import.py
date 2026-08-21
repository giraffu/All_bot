import importlib

import pytest
from starlette.requests import Request
from starlette.responses import Response


def test_web_api_main_imports_with_runtime_finalizer_dependencies():
    module = importlib.import_module("src.web_api.main")

    assert module.app is not None


@pytest.mark.asyncio
async def test_character_assets_middleware_allows_enabled_requests(monkeypatch):
    module = importlib.import_module("src.web_api.main")
    middleware = module.ReferenceAssetFeatureGateMiddleware(app=lambda *_: None)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/characters",
            "headers": [],
        }
    )
    called = False

    async def call_next(_request):
        nonlocal called
        called = True
        return Response(status_code=204)

    monkeypatch.setenv("CHARACTER_ASSETS_ENABLED", "true")

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 204
    assert called is True


@pytest.mark.asyncio
async def test_character_assets_middleware_hides_disabled_requests(monkeypatch):
    module = importlib.import_module("src.web_api.main")
    middleware = module.ReferenceAssetFeatureGateMiddleware(app=lambda *_: None)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/characters",
            "headers": [],
        }
    )

    async def call_next(_request):
        raise AssertionError("disabled character requests must not reach the router")

    monkeypatch.setenv("CHARACTER_ASSETS_ENABLED", "false")

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ltx_reference_assets_middleware_allows_enabled_requests(monkeypatch):
    module = importlib.import_module("src.web_api.main")
    middleware = module.ReferenceAssetFeatureGateMiddleware(app=lambda *_: None)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/reference-assets",
            "headers": [],
        }
    )

    async def call_next(_request):
        return Response(status_code=204)

    monkeypatch.setenv("LTX_T2V_BACKEND_ENABLED", "true")

    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 204
