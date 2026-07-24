import logging
import base64
import binascii
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import QqccBotConfigRequest, QqccBotConfigResponse
from src.database.core import get_db
from src.services.qqcc_config_service import (
    QqccSceneCreditCostError,
    QqccSceneResolutionError,
    load_qqcc_config_payload,
    save_qqcc_generated_demo_output_media,
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


async def complete_qqcc_demo_generation(
    *,
    scene_kind: str,
    scene_id: str,
    generation_id: str,
    max_wait_seconds: float = 24 * 60 * 60,
    poll_interval_seconds: float = 3,
    poll_func: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    persist_func: Callable[..., Awaitable[bool]] | None = None,
    session_factory=None,
    sleep_func: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> None:
    """Finish and persist a demo even when the submitting browser disconnects."""

    poll = poll_func or get_qqcc_demo_generation
    persist = persist_func or save_qqcc_generated_demo_output_media
    if session_factory is None:
        from src.database.core import AsyncSessionLocal

        session_factory = AsyncSessionLocal
    deadline = asyncio.get_running_loop().time() + max_wait_seconds
    while asyncio.get_running_loop().time() < deadline:
        try:
            result = await poll(
                scene_kind=scene_kind,
                scene_id=scene_id,
                generation_id=generation_id,
            )
            status = str(result.get("status") or "")
            if status == "done" and isinstance(result.get("media"), dict):
                async with session_factory() as db:
                    saved = await persist(
                        db,
                        scene_kind=scene_kind,
                        scene_id=scene_id,
                        generation_id=generation_id,
                        media=result["media"],
                    )
                if not saved:
                    logger.warning(
                        "Completed QQCC demo could not be attached kind=%s scene=%s id=%s",
                        scene_kind,
                        scene_id,
                        generation_id,
                    )
                return
            if status in {"failed", "error", "cancelled"}:
                return
        except Exception:
            logger.warning(
                "QQCC demo completion monitor retrying after failure kind=%s scene=%s id=%s",
                scene_kind,
                scene_id,
                generation_id,
                exc_info=True,
            )
        await sleep_func(poll_interval_seconds)
    logger.warning(
        "QQCC demo completion monitor timed out kind=%s scene=%s id=%s",
        scene_kind,
        scene_id,
        generation_id,
    )


async def load_qqcc_demo_generation_config() -> dict[str, Any]:
    """Load generation config without retaining a request-scoped DB session."""

    from src.database.core import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        payload = await load_qqcc_config_payload(
            db,
            include_preview_urls=False,
        )
    return payload["config"]


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
    except QqccSceneCreditCostError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except QqccSceneResolutionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
        raise HTTPException(
            status_code=503, detail="Demo media storage unavailable"
        ) from exc
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
        raise HTTPException(
            status_code=400, detail="Invalid demo media encoding"
        ) from exc
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
    background_tasks: BackgroundTasks,
):
    try:
        config = await load_qqcc_demo_generation_config()
        submit_kwargs = {"scene_kind": scene_kind, "scene": payload.scene}
        if config:
            submit_kwargs["config"] = config
        result = await submit_qqcc_demo_generation(**submit_kwargs)
        generation_id = str(result.get("generation_id") or "")
        scene_id = str(payload.scene.get("id") or "")
        if generation_id and scene_id and result.get("status") not in {
            "failed",
            "error",
            "cancelled",
        }:
            background_tasks.add_task(
                complete_qqcc_demo_generation,
                scene_kind=scene_kind,
                scene_id=scene_id,
                generation_id=generation_id,
            )
        return result
    except QqccDemoGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to submit QQCC demo generation kind=%s", scene_kind)
        raise HTTPException(
            status_code=503, detail="Demo generation unavailable"
        ) from exc


@router.get("/demo-generation/{scene_kind}/{scene_id}/{generation_id}")
async def get_qqcc_scene_demo_generation(
    scene_kind: str,
    scene_id: str,
    generation_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await get_qqcc_demo_generation(
            scene_kind=scene_kind,
            scene_id=scene_id,
            generation_id=generation_id,
        )
        if result.get("status") == "done" and isinstance(result.get("media"), dict):
            saved = await save_qqcc_generated_demo_output_media(
                db,
                scene_kind=scene_kind,
                scene_id=scene_id,
                generation_id=generation_id,
                media=result["media"],
            )
            if not saved:
                raise QqccDemoGenerationError(
                    "Generated output could not be attached to the current scene"
                )
            result["config_saved"] = True
        return result
    except QqccDemoGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to poll QQCC demo generation id=%s", generation_id)
        raise HTTPException(
            status_code=503, detail="Demo generation unavailable"
        ) from exc
