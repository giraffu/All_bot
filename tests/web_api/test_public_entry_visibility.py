from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.services.feature_entry_visibility_service import (
    FEATURE_ENTRY_VISIBILITY_CONFIG_KEY,
)
from src.web_api.routers import entry_visibility as entry_router


class _Result:
    def __init__(self, checkpoint):
        self._checkpoint = checkpoint

    def scalar_one_or_none(self):
        return self._checkpoint


class _FakeSession:
    def __init__(self, checkpoint):
        self.checkpoint = checkpoint

    async def execute(self, _stmt):
        return _Result(self.checkpoint)


@pytest.mark.asyncio
async def test_public_entry_visibility_returns_only_safe_flags_without_cache():
    fake_db = _FakeSession(
        SimpleNamespace(
            key=FEATURE_ENTRY_VISIBILITY_CONFIG_KEY,
            value={
                "web": {
                    "edit": False,
                    "custom_video": False,
                    "ltx_video": True,
                    "minimax_h3": False,
                    "character_assets": False,
                },
                "gallery": {"minimax_h3": True},
            },
            updated_at=None,
        )
    )

    async def override_get_db():
        yield fake_db

    app = FastAPI()
    app.include_router(entry_router.router)
    app.dependency_overrides[entry_router.get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/app/entry-visibility")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "task_price_overrides": {},
        "flags": {
            "enable_edit_entry": False,
            "enable_edit_v2_5_entry": True,
            "enable_edit_v3_entry": True,
            "enable_txt2img_entry": True,
            "enable_i2i_pro_entry": True,
            "enable_custom_video_entry": False,
            "enable_face_swap_entry": True,
            "enable_random_faceswap_entry": True,
            "enable_ltx_video_entry": True,
            "enable_ltx_video_v2_entry": True,
            "enable_ltx_t2v_entry": True,
            "enable_ltx25_video_upscale_entry": False,
            "enable_minimax_h3_entry": False,
            "enable_wan22_video_v2_entry": True,
            "enable_scail2_action_transfer_entry": True,
            "enable_scail2_video_replacement_entry": True,
            "enable_scail2_face_swap_v2_entry": True,
            "enable_character_assets_entry": False,
            "enable_gallery_txt2img_entry": True,
            "enable_gallery_i2i_pro_entry": True,
            "enable_gallery_edit_entry": True,
            "enable_gallery_free_edit_v2_5_entry": True,
            "enable_gallery_free_edit_v3_entry": True,
            "enable_gallery_custom_video_entry": True,
            "enable_gallery_ltx_video_entry": True,
            "enable_gallery_minimax_h3_entry": True,
            "enable_gallery_wan22_video_v2_entry": True,
            "enable_gallery_scail2_action_transfer_entry": True,
            "enable_gallery_scail2_video_replacement_entry": True,
            "enable_gallery_scail2_face_swap_v2_entry": True,
        }
    }
