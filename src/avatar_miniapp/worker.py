from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import tempfile
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import or_, select, text
from sqlalchemy.orm import selectinload

from config import MINIO_BUCKET
from src.database.core import AsyncSessionLocal, engine
from src.database.models import CharacterModelAsset, CharacterRenderJob
from src.services.redis_client import redis_client
from src.services.storage import storage

from .providers import LocalFixtureModelBuildProvider

logger = logging.getLogger(__name__)
LEASE_DURATION = timedelta(minutes=30)
POLL_SECONDS = float(os.getenv("MINIAPP_WORKER_POLL_SECONDS", "2"))
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
PACKAGE_DIR = Path(__file__).resolve().parent


def safe_error_code(exc: Exception) -> str:
    return type(exc).__name__.upper()[:64]


def ffmpeg_command(*, input_pattern: str, output_path: str, fps: int) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        input_pattern,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        output_path,
    ]


async def _upload(path: Path, object_key: str) -> None:
    uploaded = await asyncio.to_thread(
        storage.upload_file,
        str(path),
        object_key,
        MINIO_BUCKET,
    )
    if not uploaded:
        raise RuntimeError("OBJECT_UPLOAD_FAILED")


async def _download(object_key: str, destination: Path) -> None:
    normalized = object_key.removeprefix(f"{MINIO_BUCKET}/")
    await asyncio.to_thread(
        storage.download_file,
        MINIO_BUCKET,
        normalized,
        str(destination),
    )
    if not destination.is_file():
        raise RuntimeError("OBJECT_DOWNLOAD_FAILED")


async def _run(*command: str) -> None:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode:
        detail = (stderr or stdout).decode("utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"PROCESS_FAILED: {detail}")


async def claim_model_asset() -> str | None:
    now = datetime.now()
    async with AsyncSessionLocal() as db:
        async with db.begin():
            row = (
                (
                    await db.execute(
                        select(CharacterModelAsset)
                        .where(
                            CharacterModelAsset.status.in_(
                                (
                                    "queued",
                                    "preparing_views",
                                    "reconstructing",
                                    "rigging",
                                )
                            ),
                            or_(
                                CharacterModelAsset.lease_expires_at.is_(None),
                                CharacterModelAsset.lease_expires_at < now,
                            ),
                        )
                        .order_by(CharacterModelAsset.created_at)
                        .with_for_update(skip_locked=True)
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            row.status = "preparing_views"
            row.lease_owner = WORKER_ID
            row.lease_expires_at = now + LEASE_DURATION
            row.attempts = int(row.attempts or 0) + 1
            row.updated_at = now
            return row.id


async def claim_render_job() -> str | None:
    now = datetime.now()
    async with AsyncSessionLocal() as db:
        async with db.begin():
            row = (
                (
                    await db.execute(
                        select(CharacterRenderJob)
                        .where(
                            CharacterRenderJob.status.in_(("queued", "rendering")),
                            or_(
                                CharacterRenderJob.lease_expires_at.is_(None),
                                CharacterRenderJob.lease_expires_at < now,
                            ),
                        )
                        .order_by(CharacterRenderJob.created_at)
                        .with_for_update(skip_locked=True)
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            row.status = "rendering"
            row.lease_owner = WORKER_ID
            row.lease_expires_at = now + LEASE_DURATION
            row.attempts = int(row.attempts or 0) + 1
            row.updated_at = now
            return row.id


async def _set_asset_status(asset_id: str, status: str) -> None:
    async with AsyncSessionLocal() as db:
        asset = await db.get(CharacterModelAsset, asset_id)
        if asset is None:
            return
        asset.status = status
        asset.updated_at = datetime.now()
        await db.commit()


async def process_model_asset(asset_id: str) -> None:
    try:
        await _set_asset_status(asset_id, "reconstructing")
        with tempfile.TemporaryDirectory(prefix="avatar-build-") as raw_dir:
            output_dir = Path(raw_dir)
            provider = LocalFixtureModelBuildProvider(
                blender_binary=os.getenv("BLENDER_BINARY", "blender"),
                script_path=PACKAGE_DIR / "blender" / "generate_fixture.py",
            )
            await provider.build(output_dir)
            await _set_asset_status(asset_id, "rigging")
            async with AsyncSessionLocal() as db:
                asset = (
                    (
                        await db.execute(
                            select(CharacterModelAsset)
                            .options(selectinload(CharacterModelAsset.input_views))
                            .where(CharacterModelAsset.id == asset_id)
                        )
                    )
                    .scalars()
                    .one()
                )
                prefix = (
                    f"character_models/{asset.user_id}/{asset.character_id}/{asset.id}"
                )
                view_types = [view.view_type for view in asset.input_views]
                await db.rollback()
            model_key = f"{prefix}/avatar.glb"
            blend_key = f"{prefix}/avatar.blend"
            thumb_key = f"{prefix}/thumbnail.png"
            view_keys = {
                view_type: f"{prefix}/views/{view_type}.png" for view_type in view_types
            }
            await _upload(output_dir / "avatar.glb", model_key)
            await _upload(output_dir / "avatar.blend", blend_key)
            await _upload(output_dir / "thumbnail.png", thumb_key)
            for view_type, key in view_keys.items():
                await _upload(output_dir / f"{view_type}.png", key)
            async with AsyncSessionLocal() as db:
                asset = (
                    (
                        await db.execute(
                            select(CharacterModelAsset)
                            .options(selectinload(CharacterModelAsset.input_views))
                            .where(CharacterModelAsset.id == asset_id)
                        )
                    )
                    .scalars()
                    .one()
                )
                for view in asset.input_views:
                    key = view_keys[view.view_type]
                    view.status = "ready"
                    view.object_key = key
                    view.width = 768
                    view.height = 1024
                    view.updated_at = datetime.now()
                asset.model_object_key = model_key
                asset.render_source_object_key = blend_key
                asset.thumbnail_object_key = thumb_key
                asset.rig_type = "humanoid"
                asset.animation_ids = list(provider.animation_ids)
                asset.model_metadata = {
                    "format": "glb",
                    "fixture": True,
                    "identity_reconstruction": False,
                    "generator": "blender_python",
                }
                asset.status = "ready"
                asset.error_code = None
                asset.lease_owner = None
                asset.lease_expires_at = None
                asset.updated_at = datetime.now()
                await db.commit()
    except Exception as exc:
        logger.exception("Avatar fixture build failed for %s", asset_id)
        async with AsyncSessionLocal() as db:
            asset = await db.get(CharacterModelAsset, asset_id)
            if asset is not None:
                asset.status = "failed"
                asset.error_code = safe_error_code(exc)
                asset.lease_owner = None
                asset.lease_expires_at = None
                asset.updated_at = datetime.now()
                await db.commit()


async def process_render_job(render_id: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            job = (
                (
                    await db.execute(
                        select(CharacterRenderJob)
                        .options(selectinload(CharacterRenderJob.asset))
                        .where(CharacterRenderJob.id == render_id)
                    )
                )
                .scalars()
                .one()
            )
            recipe = dict(job.render_recipe)
            source_key = job.asset.render_source_object_key
            user_id = job.user_id
        if not source_key:
            raise RuntimeError("RENDER_SOURCE_MISSING")
        with tempfile.TemporaryDirectory(prefix="avatar-render-") as raw_dir:
            work_dir = Path(raw_dir)
            blend_path = work_dir / "avatar.blend"
            frames_dir = work_dir / "frames"
            frames_dir.mkdir()
            recipe_path = work_dir / "recipe.json"
            output_path = work_dir / "output.mp4"
            await _download(source_key, blend_path)
            recipe_path.write_text(
                json.dumps(recipe, separators=(",", ":")),
                encoding="utf-8",
            )
            await _run(
                os.getenv("BLENDER_BINARY", "blender"),
                "--background",
                str(blend_path),
                "--python",
                str(PACKAGE_DIR / "blender" / "render_video.py"),
                "--",
                "--recipe",
                str(recipe_path),
                "--frames",
                str(frames_dir),
            )
            await _run(
                *ffmpeg_command(
                    input_pattern=str(frames_dir / "frame_%04d.png"),
                    output_path=str(output_path),
                    fps=int(recipe["fps"]),
                )
            )
            async with AsyncSessionLocal() as db:
                job = await db.get(CharacterRenderJob, render_id)
                if job is None or job.status == "cancelled":
                    return
                output_key = f"character_renders/{user_id}/{render_id}/render.mp4"
                await _upload(output_path, output_key)
                job.status = "ready"
                job.output_object_key = output_key
                job.error_code = None
                job.lease_owner = None
                job.lease_expires_at = None
                job.updated_at = datetime.now()
                await db.commit()
    except Exception as exc:
        logger.exception("Avatar render failed for %s", render_id)
        async with AsyncSessionLocal() as db:
            job = await db.get(CharacterRenderJob, render_id)
            if job is not None and job.status != "cancelled":
                job.status = "failed"
                job.error_code = safe_error_code(exc)
                job.lease_owner = None
                job.lease_expires_at = None
                job.updated_at = datetime.now()
                await db.commit()


async def run_worker() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Avatar Mini App worker started as %s", WORKER_ID)
    try:
        while True:
            asset_id = await claim_model_asset()
            if asset_id:
                await process_model_asset(asset_id)
                continue
            render_id = await claim_render_job()
            if render_id:
                await process_render_job(render_id)
                continue
            await asyncio.sleep(POLL_SECONDS)
    finally:
        await redis_client.close()
        await engine.dispose()


async def check_health() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT 1"))
    if storage.client is None:
        raise RuntimeError("OBJECT_STORAGE_UNAVAILABLE")
    await redis_client.redis.ping()
    if not await asyncio.to_thread(storage.client.bucket_exists, MINIO_BUCKET):
        raise RuntimeError("OBJECT_STORAGE_UNAVAILABLE")
    await redis_client.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check_health() if "--health" in sys.argv else run_worker())
