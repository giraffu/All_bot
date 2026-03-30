import pytest
from fastapi.testclient import TestClient

def test_no_token_fails(client):
    # Try accessing a protected endpoint without headers
    response = client.post(
        "/comfy_img2img",
        files={"image": ("test.png", b"fake", "image/png")},
        data={"prompt": "test"}
    )
    # HTTPBearer with auto_error=True (default) returns 403 when header is missing
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authenticated"

def test_invalid_token_fails(client):
    headers = {"Authorization": "Bearer invalid_token"}
    response = client.post(
        "/comfy_img2img",
        files={"image": ("test.png", b"fake", "image/png")},
        data={"prompt": "test"},
        headers=headers
    )
    # Our verify_token function raises 401 for invalid token
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"

def test_wrong_scheme_fails(client):
    headers = {"Authorization": "Basic somebase64"}
    response = client.post(
        "/comfy_img2img",
        files={"image": ("test.png", b"fake", "image/png")},
        data={"prompt": "test"},
        headers=headers
    )
    # HTTPBearer expects Bearer scheme, raises 403 if scheme matches but invalid? 
    # Or 403 if scheme is wrong.
    assert response.status_code == 403
