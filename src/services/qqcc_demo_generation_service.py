from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any, Awaitable, Callable

from config import MINIO_BUCKET
from src.constants import (
    MODE_PORNMASTER_FLUX2_EDIT_BF16,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
)
from src.lora_catalog import get_lora_default_strength
from src.domain_config.minimax_h3 import MINIMAX_H3_I2V, build_minimax_h3_spec
from src.services.image_service import image_service
from src.services.qqcc_config_service import (
    DRAW_SCENE_ENGINE_FREE_EDIT,
    DRAW_SCENE_ENGINE_FREE_EDIT_V3,
    VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2,
    VIDEO_SCENE_ID_PATTERN,
)
from src.qqcc_video_lora_catalog import normalize_qqcc_video_lora_items
from src.services.qqcc_demo_media_service import (
    build_qqcc_demo_preview_url,
    upload_qqcc_demo_media,
)
from src.services.qqcc_video_frame_adapter import (
    QQCC_VIDEO_ASPECT_SOURCE,
    adapt_qqcc_video_frame_bytes,
    normalize_qqcc_video_aspect_ratio,
)
from src.services.storage import storage
from src.services.redis_client import redis_client
from src.services.qqcc_video_scene_chain_service import resolve_qqcc_video_scene_chain
from src.services.qqcc_video_chain_stitch_service import (
    extract_qqcc_video_last_frame,
    stitch_qqcc_video_segments,
)

GENERATION_INPUT_PREFIX = "qqcc/demo-generation"
_GENERATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
DEMO_CHAIN_TTL_SECONDS = 24 * 60 * 60


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
    if scene_kind not in {"draw", "draw_v1", "filter", "video", "video_v1", "ai_video"}:
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


def _read_minio_bytes(storage_service, object_key: str) -> bytes:
    if not storage_service.client:
        raise RuntimeError("Generation storage is unavailable")
    response = storage_service.client.get_object(MINIO_BUCKET, object_key)
    try:
        content = response.read()
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
        release_conn = getattr(response, "release_conn", None)
        if callable(release_conn):
            release_conn()
    if not content:
        raise QqccDemoGenerationError("Generated segment could not be read")
    return content


def _demo_chain_key(generation_id: str) -> str:
    return f"qqcc:demo_generation_chain:{generation_id}"


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
    if scene_kind in {"draw", "draw_v1", "filter"}:
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

    if scene_kind == "ai_video":
        spec = build_minimax_h3_spec(
            MINIMAX_H3_I2V,
            {
                "prompt": prompt,
                "images": [input_key],
                "duration": int(scene.get("duration") or 5),
                "resolution_preset": str(scene.get("resolution") or "preview"),
                "aspect_ratio": "source",
                "lora_items": scene.get("lora_items") or [],
            },
        )
        return await image_service_instance.submit_minimax_h3_task(
            task_id,
            task_type=spec.task_type,
            prompt=prompt,
            images=spec.images,
            reference_descriptions=(),
            duration=spec.duration_seconds,
            resolution_preset=spec.resolution_preset,
            aspect_ratio=spec.aspect_ratio,
            width=spec.width,
            height=spec.height,
            frame_count=spec.frame_count,
            fps=spec.fps,
            seed=None,
            lora_items=tuple(
                {"name": item.name, "strength": item.strength}
                for item in spec.addon_items
            ),
            priority=0,
        )

    duration = int(str(scene.get("duration") or "5s").removesuffix("s"))
    video_lora_items = normalize_qqcc_video_lora_items(
        scene.get("lora_items"),
        legacy_name=scene.get("lora_name"),
        legacy_strength=scene.get("lora_strength"),
    )
    if engine == VIDEO_SCENE_ENGINE_WAN22_VIDEO_V2:
        return await image_service_instance.submit_wan22_video_v2_task(
            task_id, prompt, input_key, negative_prompt=negative,
            resolution_preset="512p", length=duration, priority=0,
            lora_items=video_lora_items or None,
        )
    return await image_service_instance.submit_image_to_video_task(
        task_id, prompt, input_key, lora_name,
        negative_prompt=negative, resolution_preset="512p",
        width=512, height=512, length=duration, priority=0,
        lora_items=video_lora_items or None,
    )


async def submit_qqcc_demo_generation(
    *,
    scene_kind: str,
    scene: dict[str, Any],
    object_prefix: str = "qqcc/demo",
    task_id: str | None = None,
    storage_service=storage,
    image_service_instance=image_service,
    config: dict[str, Any] | None = None,
    redis_instance=None,
) -> dict[str, str]:
    _, _, r2_input_key = _validate_request(
        scene_kind=scene_kind, scene=scene, object_prefix=object_prefix
    )
    generation_id = task_id or f"qqcc-demo-{uuid.uuid4().hex}"
    if not _GENERATION_ID_PATTERN.fullmatch(generation_id):
        raise QqccDemoGenerationError("Invalid generation id")
    scene_chain = [scene]
    if scene_kind in {"video", "video_v1", "ai_video"} and config is not None:
        resolved = list(
            resolve_qqcc_video_scene_chain(
                config,
                scene_kind=scene_kind,
                root_scene_id=str(scene.get("id") or ""),
            )
        )
        if resolved:
            resolved[0] = dict(scene)
            scene_chain = resolved
    minio_input_key = (
        f"{GENERATION_INPUT_PREFIX}/{generation_id}/input_0.png"
        if len(scene_chain) > 1
        else f"{GENERATION_INPUT_PREFIX}/{generation_id}/input.png"
    )
    content = await asyncio.to_thread(_read_r2_bytes, storage_service, r2_input_key)
    aspect_ratio = normalize_qqcc_video_aspect_ratio(scene.get("aspect_ratio"))
    if scene_kind in {"video", "video_v1"} and aspect_ratio != QQCC_VIDEO_ASPECT_SOURCE:
        content = await asyncio.to_thread(
            adapt_qqcc_video_frame_bytes,
            content,
            aspect_ratio=aspect_ratio,
        )
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
        first_task_id = generation_id if len(scene_chain) == 1 else f"{generation_id}-0"
        backend_id = await _submit_scene(
            image_service_instance=image_service_instance,
            scene_kind=scene_kind,
            scene=scene,
            task_id=first_task_id,
            input_key=minio_input_key,
        )
    except Exception:
        if storage_service.client:
            await asyncio.to_thread(
                storage_service.client.remove_object, MINIO_BUCKET, minio_input_key
            )
        raise
    if backend_id != first_task_id:
        raise RuntimeError("Generation backend returned an unexpected task id")
    if len(scene_chain) > 1:
        redis_conn = redis_instance or redis_client.redis
        state = {
            "version": 1,
            "generation_id": generation_id,
            "scene_kind": scene_kind,
            "scene_id": str(scene.get("id") or ""),
            "object_prefix": object_prefix,
            "scenes": scene_chain,
            "current_index": 0,
            "current_task_id": first_task_id,
            "input_keys": [minio_input_key],
            "segment_keys": [],
        }
        await redis_conn.set(
            _demo_chain_key(generation_id),
            json.dumps(state, ensure_ascii=False, separators=(",", ":")),
            ex=DEMO_CHAIN_TTL_SECONDS,
        )
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
    redis_instance=None,
) -> dict[str, Any]:
    if not _GENERATION_ID_PATTERN.fullmatch(generation_id):
        raise QqccDemoGenerationError("Invalid generation id")
    if scene_kind not in {"draw", "draw_v1", "filter", "video", "video_v1", "ai_video"} or not VIDEO_SCENE_ID_PATTERN.fullmatch(scene_id):
        raise QqccDemoGenerationError("Invalid scene")
    redis_conn = redis_instance or redis_client.redis
    try:
        raw_chain = await redis_conn.get(_demo_chain_key(generation_id))
    except Exception:
        raw_chain = None
    if raw_chain:
        state = json.loads(raw_chain)
        return await _advance_demo_video_chain(
            state=state,
            storage_service=storage_service,
            image_service_instance=image_service_instance,
            upload_demo_media_func=upload_demo_media_func,
            preview_url_builder=preview_url_builder,
            redis_instance=redis_conn,
        )

    status = await image_service_instance.get_task_status(generation_id)
    if status is None:
        raise QqccDemoGenerationError("Generation task was not found")
    state = str(status.get("status") or "pending")
    if state in {"error", "cancelled", "failed"}:
        _cleanup_generation_input(storage_service, generation_id)
        return {"generation_id": generation_id, "status": "failed", "error": str(status.get("error") or "Generation failed")}
    if state != "done":
        return {"generation_id": generation_id, "status": state}

    is_video = scene_kind in {"video", "video_v1", "ai_video"}
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


def _cleanup_demo_chain_objects(storage_service, state: dict[str, Any]) -> None:
    if not storage_service.client:
        return
    for object_key in [*(state.get("input_keys") or []), *(state.get("segment_keys") or [])]:
        storage_service.client.remove_object(MINIO_BUCKET, str(object_key))


async def _advance_demo_video_chain(
    *,
    state: dict[str, Any],
    storage_service,
    image_service_instance,
    upload_demo_media_func,
    preview_url_builder,
    redis_instance,
) -> dict[str, Any]:
    generation_id = str(state["generation_id"])
    task_id = str(state["current_task_id"])
    index = int(state["current_index"])
    scenes = list(state.get("scenes") or [])
    status = await image_service_instance.get_task_status(task_id)
    if status is None:
        raise QqccDemoGenerationError("Generation task was not found")
    task_state = str(status.get("status") or "pending")
    if task_state in {"error", "cancelled", "failed"}:
        _cleanup_demo_chain_objects(storage_service, state)
        await redis_instance.delete(_demo_chain_key(generation_id))
        return {
            "generation_id": generation_id,
            "status": "failed",
            "error": str(status.get("error") or f"Segment {index + 1} failed"),
        }
    if task_state != "done":
        return {"generation_id": generation_id, "status": task_state}

    content = await image_service_instance.download_video_result(task_id)
    _detect_output_format(content, is_video=True)
    segment_key = f"{GENERATION_INPUT_PREFIX}/{generation_id}/segment_{index}.mp4"
    uploaded = await asyncio.to_thread(
        storage_service.upload_bytes,
        content,
        segment_key,
        "video/mp4",
        MINIO_BUCKET,
    )
    if not uploaded:
        raise RuntimeError("Generation segment storage is unavailable")
    state.setdefault("segment_keys", []).append(segment_key)

    if index + 1 < len(scenes):
        next_index = index + 1
        frame = await extract_qqcc_video_last_frame(content)
        next_scene = scenes[next_index]
        if state.get("scene_kind") == "video":
            ratio = normalize_qqcc_video_aspect_ratio(next_scene.get("aspect_ratio"))
            if ratio != QQCC_VIDEO_ASPECT_SOURCE:
                frame = await asyncio.to_thread(
                    adapt_qqcc_video_frame_bytes, frame, aspect_ratio=ratio
                )
        input_key = f"{GENERATION_INPUT_PREFIX}/{generation_id}/input_{next_index}.png"
        uploaded = await asyncio.to_thread(
            storage_service.upload_bytes,
            frame,
            input_key,
            "image/png",
            MINIO_BUCKET,
        )
        if not uploaded:
            raise RuntimeError("Generation input storage is unavailable")
        next_task_id = f"{generation_id}-{next_index}"
        backend_id = await _submit_scene(
            image_service_instance=image_service_instance,
            scene_kind=str(state["scene_kind"]),
            scene=next_scene,
            task_id=next_task_id,
            input_key=input_key,
        )
        if backend_id != next_task_id:
            raise RuntimeError("Generation backend returned an unexpected task id")
        state["current_index"] = next_index
        state["current_task_id"] = next_task_id
        state.setdefault("input_keys", []).append(input_key)
        await redis_instance.set(
            _demo_chain_key(generation_id),
            json.dumps(state, ensure_ascii=False, separators=(",", ":")),
            ex=DEMO_CHAIN_TTL_SECONDS,
        )
        return {"generation_id": generation_id, "status": "pending"}

    segment_payloads = [
        await asyncio.to_thread(_read_minio_bytes, storage_service, key)
        for key in state.get("segment_keys") or []
    ]
    stitched = await stitch_qqcc_video_segments(segment_payloads)
    upload = _BytesUpload(stitched, mime_type="video/mp4", file_name="generated.mp4")
    media = await upload_demo_media_func(
        scene_kind=str(state["scene_kind"]),
        scene_id=str(state["scene_id"]),
        slot="output",
        upload=upload,
        object_prefix=str(state["object_prefix"]),
        generated_object_id=generation_id,
    )
    _cleanup_demo_chain_objects(storage_service, state)
    await redis_instance.delete(_demo_chain_key(generation_id))
    return {
        "generation_id": generation_id,
        "status": "done",
        "media": media,
        "preview_url": preview_url_builder(media),
    }
