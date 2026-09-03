import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main
from local_analytics_platform.app.auth import hash_password


@pytest.mark.asyncio
async def test_local_analytics_auth_blocks_pages_and_apis(monkeypatch):
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_ENABLED", "true")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_USERNAME", "admin")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_PASSWORD", "secret-pass")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_SESSION_SECRET", "test-session-secret")

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        page_response = await client.get("/")
        api_response = await client.get("/api/health")

    assert page_response.status_code == 303
    assert page_response.headers["location"].startswith("/login?next=")
    assert api_response.status_code == 401
    assert api_response.json() == {"detail": "authentication required"}


@pytest.mark.asyncio
async def test_local_analytics_auth_login_sets_signed_cookie(monkeypatch):
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_ENABLED", "true")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_USERNAME", "admin")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_PASSWORD_HASH", hash_password("secret-pass", salt="fixed-salt"))
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_SESSION_SECRET", "test-session-secret")

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        bad_response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        login_response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "secret-pass"},
        )
        session_response = await client.get("/api/auth/session")
        page_response = await client.get("/")

    assert bad_response.status_code == 401
    assert login_response.status_code == 200
    assert login_response.json()["authenticated"] is True
    assert "local_analytics_session=" in login_response.headers["set-cookie"]
    assert "HttpOnly" in login_response.headers["set-cookie"]
    assert session_response.json() == {
        "auth_enabled": True,
        "authenticated": True,
        "username": "admin",
    }
    assert page_response.status_code == 200


@pytest.mark.asyncio
async def test_local_analytics_auth_logout_clears_session(monkeypatch):
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_ENABLED", "true")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_USERNAME", "admin")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_PASSWORD", "secret-pass")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_SESSION_SECRET", "test-session-secret")

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        await client.post("/api/auth/login", json={"username": "admin", "password": "secret-pass"})
        logout_response = await client.post("/api/auth/logout")
        session_response = await client.get("/api/auth/session")

    assert logout_response.status_code == 200
    assert "local_analytics_session=" in logout_response.headers["set-cookie"]
    assert session_response.json()["authenticated"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(("base_url", "expects_secure"), [("http://test", False), ("https://test", True)])
async def test_secure_cookie_setting_still_allows_authenticated_lan_http(
    monkeypatch, base_url, expects_secure
):
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_ENABLED", "true")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_USERNAME", "admin")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_PASSWORD", "secret-pass")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_COOKIE_SECURE", "true")

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app), base_url=base_url
    ) as client:
        response = await client.post(
            "/api/auth/login", json={"username": "admin", "password": "secret-pass"}
        )
        session = await client.get("/api/auth/session")

    cookie = response.headers["set-cookie"]
    assert ("; Secure" in cookie) is expects_secure
    assert session.json()["authenticated"] is True
