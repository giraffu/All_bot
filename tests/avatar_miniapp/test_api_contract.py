import os
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.avatar_miniapp import api as avatar_api
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


def test_password_only_miniapp_starts_without_telegram_bot_token():
    environment = {
        **os.environ,
        "ALLBOT_ENV": "test",
        "BOT_TYPE": "TEST",
        "BOT_TOKEN": "",
    }

    result = subprocess.run(
        [sys.executable, "-c", "import src.avatar_miniapp.api"],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_lan_compose_uses_the_shared_runtime_identity():
    compose = (
        Path(__file__).resolve().parents[2]
        / "avatar_miniapp"
        / "docker-compose.lan.yml"
    ).read_text(encoding="utf-8")

    assert "BOT_TYPE: ${BOT_TYPE:-TEST}" in compose
    assert "BOT_TYPE: ${BOT_TYPE:-avatar_miniapp}" not in compose


def test_caddy_selects_the_lan_ip_certificate_without_sni():
    caddyfile = (
        Path(__file__).resolve().parents[2] / "avatar_miniapp" / "Caddyfile"
    ).read_text(encoding="utf-8")

    assert "default_sni {$MINIAPP_LAN_HOST:localhost}" in caddyfile


@pytest.mark.asyncio
async def test_miniapp_lifespan_registers_shared_auth_providers(monkeypatch):
    registered = False

    def register():
        nonlocal registered
        registered = True

    monkeypatch.setattr(
        avatar_api,
        "ensure_billing_core_providers_registered",
        register,
    )

    async with avatar_api.lifespan(app):
        assert registered is True
