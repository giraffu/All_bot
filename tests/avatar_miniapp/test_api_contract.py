import pytest
from httpx import ASGITransport, AsyncClient

from src.avatar_miniapp.api import app
from src.database.models import (
    CharacterModelAsset,
    CharacterModelInputView,
    CharacterRenderJob,
)


def test_miniapp_exposes_only_the_planned_routes():
    routes = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }

    assert ("POST", "/api/auth/login") in routes
    assert ("GET", "/api/users/me") in routes
    assert ("GET", "/api/characters") in routes
    assert ("POST", "/api/characters/drafts") in routes
    assert ("POST", "/api/miniapp/characters/{character_id}/fixture-build") in routes
    assert ("GET", "/api/miniapp/model-assets/{asset_id}") in routes
    assert ("POST", "/api/miniapp/renders") in routes
    assert ("GET", "/api/miniapp/renders/{render_id}") in routes
    assert ("POST", "/api/miniapp/renders/{render_id}/cancel") in routes
    assert ("POST", "/api/auth/telegram") not in routes
    assert ("POST", "/api/tasks/generate") not in routes


def test_avatar_tables_are_owned_by_the_shared_metadata():
    table_names = {
        CharacterModelAsset.__table__.name,
        CharacterModelInputView.__table__.name,
        CharacterRenderJob.__table__.name,
    }

    assert table_names == {
        "character_model_assets",
        "character_model_input_views",
        "character_render_jobs",
    }
    assert (
        CharacterModelAsset.__table__.metadata is CharacterRenderJob.__table__.metadata
    )


@pytest.mark.asyncio
async def test_miniapp_character_list_requires_real_authentication():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/miniapp/characters")

    assert response.status_code == 401
