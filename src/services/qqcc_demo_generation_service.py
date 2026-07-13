from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any, Awaitable, Callable

from config import MINIO_BUCKET
from src.constants import (
    MODE_PORNMASTER_FLUX2_EDIT_BF16,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
)
from src.lora_catalog import get_lora_default_strength
from src.services.image_service import image_service
from src.services.qqcc_config_service import (
    DRAW_SCENE_ENGINE_FREE_EDIT,
    DRAW_SCENE_ENGINE_FREE_EDIT_V3,
    VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
    VIDEO_SCENE_ID_PATTERN,
)
from src.services.qqcc_demo_media_service import (
    build_qqcc_demo_preview_url,
    upload_qqcc_demo_media,
)
from src.services.storage import storage

GENERATION_INPUT_PREFIX = "qqcc/demo-generation"
_GENERATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class QqccDemoGenerationError(ValueError):
    pass


class _BytesUpload:
    def __init__(self, content: bytes, *, mime_type: str, file_name: str):
        self._content = content
        self.content_type = mime_type
        self.filename = file_name

    async def read(self, size: int = -1) -> bytes:
        return self._content if size is None or size < 0 else self._content[:size]


def _validate_request(
    *, scene_kind: str, scene: dict[str, Any], object_prefix: str
) -> tuple[str, str, str]:
    if scene_kind not in {"draw", "filter", "video"}:
        raise QqccDemoGenerationError("Unsupported scene kind")
    scene_id = str(scene.get("id") or "").strip()
    prompt = str(scene.get("prompt") or "").strip()
    if not VIDEO_SCENE_ID_PATTERN.fullmatch(scene_id) or not prompt:
        raise QqccDemoGenerationError("Scene id and prompt are required")
    media = scene.get("demo_input_media")
    if not isinstance(media, dict):
        raise QqccDemoGenerationError("An input media image is required")
    input_key = str(media.get("object_key") or "").strip()
    expected_key = f"{object_prefix.strip().strip('/')}/{scene_kind}/{scene_id}/input"
    if input_key != expected_key:
        raise QqccDemoGenerationError("Invalid input media namespace")
    if str(media.get("mime_type") or "") not in {"image/png", "image/jpeg"}:
        raise QqccDemoGenerationError("Invalid input media type")
    return scene_id, prompt, input_key


def _read_r2_bytes(storage_service, object_key: str) -> bytes:
    if not storage_service.r2_client or not storage_service.r2_bucket:
        raise RuntimeError("R2 storage is unavailable")
    response = storage_service.r2_client.get_object(
        Bucket=storage_service.r2_bucket, Key=object_key
    )
    body = response.get("Body") if isinstance(response, dict) else None
    content = body.read() if body is not None else b""
    if not content:
        raise QqccDemoGenerationError("Input media could not be read")
    return content


def _detect_output_format(content: bytes, *, is_video: bool) -> tuple[str, str]:
    if is_video and b"ftyp" in content[:32]:
        return "video/mp4", ".mp4"
    if not is_video and content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if not is_video and content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    raise QqccDemoGenerationError("Generated media has an unsupported format")


async def _submit_scene(
    *, image_service_instance, scene_kind: str, scene: dict[str, Any], task_id: str, input_key: str
) -> str:
    prompt = str(scene["prompt"]).strip()
    negative = str(scene.get("negative_prompt") or "")
    engine = str(scene.get("engine") or "")
    lora_name = str(scene.get("lora_name") or "").strip()
    if scene_kind in {"draw", "filter"}:
        if engine == DRAW_SCENE_ENGINE_FREE_EDIT:
            if lora_name:
                return await image_service_instance.submit_img2img_lora_task(
                    task_id, prompt, [input_key], lora_name,
                    negative_prompt=negative, priority=0,
                    lora_strength=get_lora_default_strength(lora_name),
                )
            return await image_service_instance.submit_task(
                task_id, prompt, [input_key], negative, priority=0
            )
        execution_type = (
            MODE_PORNMASTER_FLUX2_EDIT_BF16
            if engine == DRAW_SCENE_ENGINE_FREE_EDIT_V3
            else MODE_PORNMASTER_FLUX2_SINGLE_EDIT
        )
        return await image_service_instance.submit_pornmaster_flux2_edit_task(
            task_id,
            execution_task_type=execution_type,
            prompt=prompt,
            image_paths=[input_key],
            negative_prompt=negative,
            priority=0,
        )

    duration = int(str(scene.get("duration") or "5s").removesuffix("s"))
    if engine == VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2:
        return await image_service_instance.submit_wan22_video_v2_task(
            task_id, prompt, input_key, negative_prompt=negative,
            resolution_preset="512p", length=duration, priority=0,
        )
    return await image_service_instance.submit_image_to_video_task(
        task_id, prompt, input_key, lora_name,
        negative_prompt=negative, resolution_preset="512p",
        width=512, height=512, length=duration, priority=0,
    )


async def submit_qqcc_demo_generation(
    *,
    scene_kind: str,
    scene: dict[str, Any],
    object_prefix: str = "qqcc/demo",
    task_id: str | None = None,
    storage_service=storage,
    image_service_instance=image_service,
) -> dict[str, str]:
    _, _, r2_input_key = _validate_request(
        scene_kind=scene_kind, scene=scene, object_prefix=object_prefix
    )
    generation_id = task_id or f"qqcc-demo-{uuid.uuid4().hex}"
    if not _GENERATION_ID_PATTERN.fullmatch(generation_id):
        raise QqccDemoGenerationError("Invalid generation id")
    minio_input_key = f"{GENERATION_INPUT_PREFIX}/{generation_id}/input.png"
    content = await asyncio.to_thread(_read_r2_bytes, storage_service, r2_input_key)
    uploaded = await asyncio.to_thread(
        storage_service.upload_bytes,
        content,
        minio_input_key,
        "image/png",
        MINIO_BUCKET,
    )
    if not uploaded:
        raise RuntimeError("Generation input storage is unavailable")
    try:
        backend_id = await _submit_scene(
            image_service_instance=image_service_instance,
            scene_kind=scene_kind,
            scene=scene,
            task_id=generation_id,
            input_key=minio_input_key,
        )
    except Exception:
        if storage_service.client:
            await asyncio.to_thread(
                storage_service.client.remove_object, MINIO_BUCKET, minio_input_key
            )
        raise
    if backend_id != generation_id:
        raise RuntimeError("Generation backend returned an unexpected task id")
    return {"generation_id": generation_id, "status": "pending"}


async def get_qqcc_demo_generation(
    *,
    generation_id: str,
    scene_kind: str,
    scene_id: str,
    object_prefix: str = "qqcc/demo",
    storage_service=storage,
    image_service_instance=image_service,
    upload_demo_media_func: Callable[..., Awaitable[dict[str, Any]]] = upload_qqcc_demo_media,
    preview_url_builder=build_qqcc_demo_preview_url,
) -> dict[str, Any]:
    if not _GENERATION_ID_PATTERN.fullmatch(generation_id):
        raise QqccDemoGenerationError("Invalid generation id")
    if scene_kind not in {"draw", "filter", "video"} or not VIDEO_SCENE_ID_PATTERN.fullmatch(scene_id):
        raise QqccDemoGenerationError("Invalid scene")
    status = await image_service_instance.get_task_status(generation_id)
    if status is None:
        raise QqccDemoGenerationError("Generation task was not found")
    state = str(status.get("status") or "pending")
    if state in {"error", "cancelled", "failed"}:
        _cleanup_generation_input(storage_service, generation_id)
        return {"generation_id": generation_id, "status": "failed", "error": str(status.get("error") or "Generation failed")}
    if state != "done":
        return {"generation_id": generation_id, "status": state}

    is_video = scene_kind == "video"
    content = (
        await image_service_instance.download_video_result(generation_id)
        if is_video
        else await image_service_instance.download_result(generation_id)
    )
    mime_type, suffix = _detect_output_format(content, is_video=is_video)
    upload = _BytesUpload(content, mime_type=mime_type, file_name=f"generated{suffix}")
    media = await upload_demo_media_func(
        scene_kind=scene_kind,
        scene_id=scene_id,
        slot="output",
        upload=upload,
        object_prefix=object_prefix,
        generated_object_id=generation_id,
    )
    _cleanup_generation_input(storage_service, generation_id)
    return {
        "generation_id": generation_id,
        "status": "done",
        "media": media,
        "preview_url": preview_url_builder(media),
    }


def _cleanup_generation_input(storage_service, generation_id: str) -> None:
    if storage_service.client:
        storage_service.client.remove_object(
            MINIO_BUCKET, f"{GENERATION_INPUT_PREFIX}/{generation_id}/input.png"
        )
