from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AnimationId = Literal["idle", "turntable", "photo_pose", "dance_lite"]
CameraPreset = Literal["front", "side", "back", "full_body", "half_body", "portrait"]
RenderResolution = Literal["720x1280", "1280x720", "1024x1024"]
RenderBackground = Literal["light", "dark", "transparent", "studio"]


class ModelInputViewResponse(BaseModel):
    view_type: str
    status: str
    width: int | None = None
    height: int | None = None
    preview_url: str | None = None


class ModelAssetResponse(BaseModel):
    id: str
    character_id: str
    version: int
    provider: str
    status: str
    error_code: str | None = None
    model_url: str | None = None
    thumbnail_url: str | None = None
    rig_type: str | None = None
    animation_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    views: list[ModelInputViewResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class FixtureBuildResponse(BaseModel):
    asset_id: str
    status: str


class RenderCreateRequest(BaseModel):
    asset_id: str = Field(min_length=1, max_length=36)
    animation_id: AnimationId = "idle"
    camera_preset: CameraPreset = "full_body"
    resolution: RenderResolution = "1280x720"
    fps: Literal[24, 30] = 24
    duration_seconds: int = Field(default=5, ge=3, le=10)
    background: RenderBackground = "studio"
    loop: bool = True


class RenderJobResponse(BaseModel):
    id: str
    asset_id: str
    status: str
    recipe: dict
    error_code: str | None = None
    output_url: str | None = None
    created_at: datetime
    updated_at: datetime


class MiniCharacterResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: str
    source_object_key: str
    preview_url: str | None = None
    latest_model: ModelAssetResponse | None = None
