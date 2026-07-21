import logging
import base64
import binascii

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import QqccBotConfigRequest, QqccBotConfigResponse
from src.database.core import get_db
from src.services.qqcc_config_service import (
    load_qqcc_config_payload,
    save_qqcc_config_payload,
)
from src.services.qqcc_demo_media_service import (
    QqccDemoMediaValidationError,
    build_qqcc_demo_preview_url,
    upload_qqcc_demo_media,
)
from src.services.qqcc_demo_generation_service import (
    QqccDemoGenerationError,
    get_qqcc_demo_generation,
    submit_qqcc_demo_generation,
)
from src.services.qqcc_video_scene_chain_service import QqccVideoSceneChainError

router = APIRouter(prefix="/api/qqcc", tags=["qqcc"])
logger = logging.getLogger("dashboard.qqcc")


class QqccDemoMediaJsonRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=100)
    content_base64: str = Field(min_length=1, max_length=70 * 1024 * 1024)


class QqccDemoGenerationRequest(BaseModel):
    scene: dict


class _MemoryUpload:
    def __init__(self, *, content: bytes, content_type: str, filename: str):
        self._content = content
        self.content_type = content_type
        self.filename = filename

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            return self._content
        return self._content[:size]


@router.get("/config", response_model=QqccBotConfigResponse)
async def get_qqcc_config(db: AsyncSession = Depends(get_db)):
    return await load_qqcc_config_payload(db)


@router.put("/config", response_model=QqccBotConfigResponse)
async def update_qqcc_config(
    payload: QqccBotConfigRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await save_qqcc_config_payload(
            db, payload.model_dump(exclude_unset=True)
        )
    except QqccVideoSceneChainError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/demo-media/{scene_kind}/{scene_id}/{slot}")
async def upload_qqcc_scene_demo_media(
    scene_kind: str,
    scene_id: str,
    slot: str,
    file: UploadFile = File(...),
):
    try:
        media = await upload_qqcc_demo_media(
            scene_kind=scene_kind,
            scene_id=scene_id,
            slot=slot,
            upload=file,
        )
    except QqccDemoMediaValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "Failed to upload QQCC demo media kind=%s scene=%s slot=%s",
            scene_kind,
            scene_id,
            slot,
        )
        raise HTTPException(status_code=503, detail="Demo media storage unavailable") from exc
    return {
        "media": media,
        "preview_url": build_qqcc_demo_preview_url(media),
    }


@router.put("/demo-media/{scene_kind}/{scene_id}/{slot}")
async def put_qqcc_scene_demo_media(
    scene_kind: str,
    scene_id: str,
    slot: str,
    file: UploadFile = File(...),
):
    return await upload_qqcc_scene_demo_media(
        scene_kind=scene_kind,
        scene_id=scene_id,
        slot=slot,
        file=file,
    )


@router.put("/demo-media-json/{scene_kind}/{scene_id}/{slot}")
async def put_qqcc_scene_demo_media_json(
    scene_kind: str,
    scene_id: str,
    slot: str,
    payload: QqccDemoMediaJsonRequest,
):
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid demo media encoding") from exc
    upload = _MemoryUpload(
        content=content,
        content_type=payload.mime_type,
        filename=payload.file_name,
    )
    return await upload_qqcc_scene_demo_media(
        scene_kind=scene_kind,
        scene_id=scene_id,
        slot=slot,
        file=upload,
    )


@router.post("/demo-generation/{scene_kind}")
async def submit_qqcc_scene_demo_generation(
    scene_kind: str,
    payload: QqccDemoGenerationRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        config_payload = (
            await load_qqcc_config_payload(db, include_preview_urls=False)
            if hasattr(db, "execute")
            else None
        )
        submit_kwargs = {"scene_kind": scene_kind, "scene": payload.scene}
        if config_payload:
            submit_kwargs["config"] = config_payload["config"]
        return await submit_qqcc_demo_generation(**submit_kwargs)
    except QqccDemoGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to submit QQCC demo generation kind=%s", scene_kind)
        raise HTTPException(status_code=503, detail="Demo generation unavailable") from exc


@router.get("/demo-generation/{scene_kind}/{scene_id}/{generation_id}")
async def get_qqcc_scene_demo_generation(
    scene_kind: str,
    scene_id: str,
    generation_id: str,
):
    try:
        return await get_qqcc_demo_generation(
            scene_kind=scene_kind,
            scene_id=scene_id,
            generation_id=generation_id,
        )
    except QqccDemoGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to poll QQCC demo generation id=%s", generation_id)
        raise HTTPException(status_code=503, detail="Demo generation unavailable") from exc
