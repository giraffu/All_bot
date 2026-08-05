from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.web_api.routers import storage as storage_router
from src.web_api.services import storage_api_service


def _build_current_user():
    return type("User", (), {"id": 123, "username": "tester"})()


def test_build_presigned_upload_object_key_keeps_extension(monkeypatch):
    class _FakeUUID:
        hex = "abcdef1234567890"

        def __str__(self):
            return self.hex

    monkeypatch.setattr(storage_api_service.uuid, "uuid4", lambda: _FakeUUID())

    object_key = storage_api_service.build_presigned_upload_object_key(
        user_id=123,
        filename="demo.png",
        now=datetime(2026, 5, 23, 12, 0, 0),
    )

    assert object_key == "staging/user-uploads/123/abcdef12.png"


def test_build_presigned_upload_object_key_without_extension(monkeypatch):
    class _FakeUUID:
        hex = "12345678abcdef90"

        def __str__(self):
            return self.hex

    monkeypatch.setattr(storage_api_service.uuid, "uuid4", lambda: _FakeUUID())

    object_key = storage_api_service.build_presigned_upload_object_key(
        user_id=123,
        filename="demo",
        now=datetime(2026, 5, 23, 12, 0, 0),
    )

    assert object_key == "staging/user-uploads/123/12345678.bin"


@pytest.mark.asyncio
async def test_get_presigned_upload_url_payload_builds_expected_response(monkeypatch):
    monkeypatch.setattr(
        storage_api_service,
        "build_presigned_upload_object_key",
        lambda **_: "web_uploads/123/20260523_abcd1234.mp4",
    )

    response = await storage_api_service.get_presigned_upload_url_payload(
        filename="demo.mp4",
        content_type="video/mp4",
        current_user=_build_current_user(),
        get_presigned_put_url_func=lambda *args, **kwargs: "https://upload.example.com",
    )

    assert response == {
        "upload_url": "https://upload.example.com",
        "object_key": f"{storage_api_service.MINIO_BUCKET}/web_uploads/123/20260523_abcd1234.mp4",
        "expires_in_minutes": 15,
    }


@pytest.mark.asyncio
async def test_get_presigned_upload_url_payload_rejects_missing_fields():
    with pytest.raises(HTTPException) as exc_info:
        await storage_api_service.get_presigned_upload_url_payload(
            filename="",
            content_type="video/mp4",
            current_user=_build_current_user(),
            get_presigned_put_url_func=lambda *args, **kwargs: "ignored",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Filename and content_type are required"


@pytest.mark.asyncio
async def test_get_presigned_upload_url_payload_maps_empty_url_to_500(monkeypatch):
    monkeypatch.setattr(
        storage_api_service,
        "build_presigned_upload_object_key",
        lambda **_: "web_uploads/123/20260523_abcd1234.mp4",
    )

    with pytest.raises(HTTPException) as exc_info:
        await storage_api_service.get_presigned_upload_url_payload(
            filename="demo.mp4",
            content_type="video/mp4",
            current_user=_build_current_user(),
            get_presigned_put_url_func=lambda *args, **kwargs: None,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to generate upload URL"


@pytest.mark.asyncio
async def test_get_presigned_upload_url_payload_maps_storage_error_to_500(monkeypatch):
    monkeypatch.setattr(
        storage_api_service,
        "build_presigned_upload_object_key",
        lambda **_: "web_uploads/123/20260523_abcd1234.mp4",
    )

    def _raise_storage_error(*args, **kwargs):
        raise RuntimeError("storage down")

    with pytest.raises(HTTPException) as exc_info:
        await storage_api_service.get_presigned_upload_url_payload(
            filename="demo.mp4",
            content_type="video/mp4",
            current_user=_build_current_user(),
            get_presigned_put_url_func=_raise_storage_error,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal server error generating URL"


@pytest.mark.asyncio
async def test_storage_router_routes_to_service():
    current_user = _build_current_user()
    expected = {
        "upload_url": "https://upload.example.com",
        "object_key": "bucket/path",
        "expires_in_minutes": 15,
    }

    with patch(
        "src.web_api.routers.storage.get_presigned_upload_url_payload",
        new=AsyncMock(return_value=expected),
    ) as mock_service:
        response = await storage_router.get_presigned_upload_url(
            filename="demo.png",
            content_type="image/png",
            current_user=current_user,
        )

    assert response == expected
    mock_service.assert_awaited_once_with(
        filename="demo.png",
        content_type="image/png",
        current_user=current_user,
    )
