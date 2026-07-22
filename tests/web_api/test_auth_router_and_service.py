from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.web_api.routers import auth as auth_router
from src.web_api.services import auth_api_service


def _build_request(real_ip=None, forwarded_for=None, client_host="127.0.0.1"):
    headers = {}
    if real_ip is not None:
        headers["X-Real-IP"] = real_ip
    if forwarded_for is not None:
        headers["X-Forwarded-For"] = forwarded_for
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=client_host))


def _build_user(**overrides):
    defaults = {
        "id": 123,
        "telegram_id": 456,
        "password_version": 3,
        "username": "tester",
        "full_name": "Tester",
        "language_code": "zh-hans",
        "credits": 100,
        "user_group": "练气期",
        "current_identity": "外门弟子",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_extract_client_ip_prefers_x_real_ip():
    request = _build_request(real_ip="1.1.1.1", forwarded_for="2.2.2.2", client_host="3.3.3.3")
    assert auth_api_service.extract_client_ip(request) == "1.1.1.1"


def test_extract_client_ip_falls_back_in_order():
    request = _build_request(forwarded_for="2.2.2.2", client_host="3.3.3.3")
    assert auth_api_service.extract_client_ip(request) == "2.2.2.2"

    request = _build_request(client_host="3.3.3.3")
    assert auth_api_service.extract_client_ip(request) == "3.3.3.3"


def test_build_auth_token_payload_uses_channel():
    user = _build_user()
    stats = {"credits": 88}

    with patch(
        "src.web_api.services.auth_api_service.create_access_token",
        return_value="token-1",
    ) as mock_create_token:
        payload = auth_api_service.build_auth_token_payload(
            user=user,
            stats=stats,
            channel="password",
        )

    assert payload["access_token"] == "token-1"
    assert payload["token_type"] == "bearer"
    assert payload["user"]["credits"] == 88
    mock_create_token.assert_called_once_with(
        subject=123,
        pwd_ver=3,
        channel="password",
    )


@pytest.mark.asyncio
async def test_login_telegram_payload_checks_permission_and_builds_token():
    req = SimpleNamespace(
        initData="init-data",
        model_dump=lambda **kwargs: {"id": 1},
    )
    user = _build_user()

    with patch(
        "src.web_api.services.auth_api_service.authenticate_and_get_user",
        new=AsyncMock(return_value=(user, {"credits": 66})),
    ) as mock_auth, patch(
        "src.web_api.services.auth_api_service.permission_service.check_web_access",
        new=AsyncMock(return_value=True),
    ) as mock_permission, patch(
        "src.web_api.services.auth_api_service.build_auth_token_payload",
        return_value={"access_token": "token"},
    ) as mock_build_payload:
        response = await auth_api_service.login_telegram_payload(req=req)

    assert response == {"access_token": "token"}
    mock_auth.assert_awaited_once_with(init_data="init-data", widget_data=None)
    mock_permission.assert_awaited_once_with(123)
    mock_build_payload.assert_called_once_with(user=user, stats={"credits": 66})


@pytest.mark.asyncio
async def test_login_telegram_payment_payload_skips_web_access_gate():
    req = SimpleNamespace(
        initData="init-data",
        model_dump=lambda **kwargs: {"id": 1},
    )
    user = _build_user(user_group="凡人", current_identity="外门弟子")

    with patch(
        "src.web_api.services.auth_api_service.authenticate_and_get_user",
        new=AsyncMock(return_value=(user, {"credits": 6})),
    ) as mock_auth, patch(
        "src.web_api.services.auth_api_service.permission_service.check_web_access",
        new=AsyncMock(),
    ) as mock_permission, patch(
        "src.web_api.services.auth_api_service.build_auth_token_payload",
        return_value={"access_token": "payment-token"},
    ) as mock_build_payload:
        response = await auth_api_service.login_telegram_payment_payload(req=req)

    assert response == {"access_token": "payment-token"}
    mock_auth.assert_awaited_once_with(init_data="init-data", widget_data=None)
    mock_permission.assert_not_awaited()
    mock_build_payload.assert_called_once_with(
        user=user,
        stats={"credits": 6},
        channel="telegram_payment",
    )


@pytest.mark.asyncio
async def test_login_with_password_payload_extracts_ip_and_schedules_notification():
    req = SimpleNamespace(username="tester", password="secret")
    request = _build_request(real_ip="8.8.8.8")
    user = _build_user()

    with patch(
        "src.web_api.services.auth_api_service.authenticate_user_by_password",
        new=AsyncMock(return_value=(user, {"credits": 66})),
    ) as mock_auth, patch(
        "src.web_api.services.auth_api_service.schedule_password_login_notification"
    ) as mock_notify, patch(
        "src.web_api.services.auth_api_service.build_auth_token_payload",
        return_value={"access_token": "token"},
    ) as mock_build_payload:
        response = await auth_api_service.login_with_password_payload(
            req=req,
            request=request,
        )

    assert response == {"access_token": "token"}
    mock_auth.assert_awaited_once_with("tester", "secret", "8.8.8.8")
    mock_notify.assert_called_once_with(456, "8.8.8.8")
    mock_build_payload.assert_called_once_with(
        user=user,
        stats={"credits": 66},
        channel="password",
    )


@pytest.mark.asyncio
async def test_bind_password_payload_maps_auth_core_error_to_400():
    req = SimpleNamespace(username="tester", password="secret")
    request = _build_request(real_ip="8.8.8.8")
    current_user = _build_user()

    with patch(
        "src.web_api.services.auth_api_service.bind_user_password",
        new=AsyncMock(side_effect=auth_api_service.AuthCoreError("bad password")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await auth_api_service.bind_password_payload(
                req=req,
                request=request,
                current_user=current_user,
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "bad password"


@pytest.mark.asyncio
async def test_auth_router_routes_to_service():
    req = SimpleNamespace(initData="init-data")

    with patch(
        "src.web_api.routers.auth.login_telegram_payload",
        new=AsyncMock(return_value={"access_token": "token"}),
    ) as mock_service:
        response = await auth_router.login_telegram(req)

    assert response == {"access_token": "token"}
    mock_service.assert_awaited_once_with(req=req)


@pytest.mark.asyncio
async def test_payment_auth_router_routes_to_payment_login_service():
    req = SimpleNamespace(initData="init-data")

    with patch(
        "src.web_api.routers.auth.login_telegram_payment_payload",
        new=AsyncMock(return_value={"access_token": "payment-token"}),
    ) as mock_service:
        response = await auth_router.login_telegram_payment(req)

    assert response == {"access_token": "payment-token"}
    mock_service.assert_awaited_once_with(req=req)


@pytest.mark.asyncio
async def test_password_login_router_routes_to_service():
    req = SimpleNamespace(username="tester", password="secret")
    request = _build_request(real_ip="8.8.8.8")

    with patch(
        "src.web_api.routers.auth.login_with_password_payload",
        new=AsyncMock(return_value={"access_token": "token"}),
    ) as mock_service:
        response = await auth_router.login_with_password(req, request)

    assert response == {"access_token": "token"}
    mock_service.assert_awaited_once_with(req=req, request=request)


@pytest.mark.asyncio
async def test_bind_password_router_routes_to_service():
    req = SimpleNamespace(username="tester", password="secret")
    request = _build_request(real_ip="8.8.8.8")
    current_user = _build_user()

    with patch(
        "src.web_api.routers.auth.bind_password_payload",
        new=AsyncMock(return_value={"status": "success"}),
    ) as mock_service:
        response = await auth_router.bind_password(
            req=req,
            request=request,
            current_user=current_user,
        )

    assert response == {"status": "success"}
    mock_service.assert_awaited_once_with(
        req=req,
        request=request,
        current_user=current_user,
    )
