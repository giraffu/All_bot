import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from io import BytesIO
from PIL import Image, ImageOps

from src.core.media_paths import build_flat_r2_compatibility_key, resolve_storage_object
from src.core.task_core_service_providers import get_task_core_storage_service

logger = logging.getLogger(__name__)


def _get_media_storage_service():
    return get_task_core_storage_service()


def _extract_image_metadata_from_file(file_path: str) -> tuple[int | None, int | None, None]:
    with Image.open(file_path) as img:
        img = ImageOps.exif_transpose(img)
        return img.width, img.height, None


def _extract_video_metadata_with_ffprobe(input_source: str) -> tuple[int | None, int | None, int | None]:
    ffprobe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height:format=duration",
        "-of",
        "json",
        input_source,
    ]
    result = subprocess.run(
        ffprobe_cmd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams") or []
    stream = streams[0] if streams else {}
    raw_duration = (payload.get("format") or {}).get("duration")
    duration = int(round(float(raw_duration))) if raw_duration is not None else None
    return stream.get("width"), stream.get("height"), duration


def extract_media_metadata_from_bytes(
    media_bytes: bytes,
    media_type: str,
    file_extension: str | None = None,
) -> tuple[int | None, int | None, int | None]:
    if not media_bytes:
        return None, None, None

    normalized_media_type = "video" if media_type == "video" else "image"
    if normalized_media_type == "image":
        with Image.open(BytesIO(media_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            return img.width, img.height, None

    temp_dir = tempfile.mkdtemp()
    try:
        suffix = f".{(file_extension or 'mp4').lstrip('.')}"
        media_path = os.path.join(temp_dir, f"media{suffix}")
        with open(media_path, "wb") as f:
            f.write(media_bytes)
        return _extract_video_metadata_with_ffprobe(media_path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def extract_media_metadata_from_bytes_best_effort(
    media_bytes: bytes,
    media_type: str,
    file_extension: str | None = None,
    fallback: tuple[int | None, int | None, int | None] = (None, None, None),
) -> tuple[int | None, int | None, int | None]:
    try:
        return extract_media_metadata_from_bytes(
            media_bytes, media_type, file_extension
        )
    except Exception as exc:
        logger.warning("Failed to extract media metadata from bytes: %s", exc)
        return fallback


async def extract_media_metadata_from_storage(
    output_file: str,
    media_type: str,
) -> tuple[int | None, int | None, int | None]:
    if not output_file:
        return None, None, None

    normalized_media_type = "video" if media_type == "video" else "image"
    bucket_name, object_name = resolve_storage_object(output_file)
    storage_service = _get_media_storage_service()

    if normalized_media_type == "video":
        input_url = await asyncio.to_thread(
            storage_service.get_presigned_url, object_name, 1.0, bucket_name
        )
        return await asyncio.to_thread(_extract_video_metadata_with_ffprobe, input_url)

    temp_dir = tempfile.mkdtemp()
    try:
        original_ext = object_name.rsplit(".", 1)[-1] if "." in object_name else "png"
        local_path = os.path.join(temp_dir, f"media.{original_ext}")
        await asyncio.to_thread(
            storage_service.download_file, bucket_name, object_name, local_path
        )
        return await asyncio.to_thread(_extract_image_metadata_from_file, local_path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def extract_media_metadata_from_storage_best_effort(
    output_file: str,
    media_type: str,
    fallback: tuple[int | None, int | None, int | None] = (None, None, None),
) -> tuple[int | None, int | None, int | None]:
    try:
        return await extract_media_metadata_from_storage(output_file, media_type)
    except Exception as exc:
        logger.warning("Failed to extract media metadata from storage: %s", exc)
        return fallback


async def generate_and_upload_thumbnail(
    output_file: str, media_type: str, r2_object_name: str | None = None
) -> None:
    """
    Generate a thumbnail for a given output_file and upload it to MinIO/R2.
    - Videos: Extract the first frame using FFmpeg (-> .jpg).
    - Images: Resize and convert to WebP using Pillow (-> .webp).
    """
    if not output_file:
        return

    bucket_name, object_name = resolve_storage_object(output_file)
    storage_service = _get_media_storage_service()

    base_path = object_name.rsplit(".", 1)[0]

    if media_type == "video":
        thumb_object_name = f"{base_path}_thumb.jpg"
    else:
        thumb_object_name = f"{base_path}_thumb.webp"

    target_r2_key = r2_object_name or build_flat_r2_compatibility_key(thumb_object_name)

    # If the thumbnail already exists in MinIO, skip regeneration but still补齐 R2 同步。
    try:
        thumb_exists, r2_exists = await asyncio.gather(
            storage_service.async_object_exists(bucket_name, thumb_object_name),
            storage_service.async_r2_object_exists(target_r2_key),
        )
        if thumb_exists:
            if not r2_exists:
                await storage_service.async_copy_to_r2(
                    bucket_name, thumb_object_name, target_r2_key
                )
            logger.info(
                f"Thumbnail {thumb_object_name} already exists in {bucket_name}, skipping."
            )
            return
    except Exception as e:
        logger.warning(f"Failed to check object existence: {e}, proceeding with generation.")

    # Create an isolated temporary directory
    temp_dir = tempfile.mkdtemp()
    try:
        thumb_local_path = os.path.join(temp_dir, os.path.basename(thumb_object_name))

        if media_type == "video":
            # For video, use FFmpeg with presigned URL (HTTP Range support)
            # Fallback to synchronous get_presigned_url
            # 兼容：storage.get_presigned_url 的签名是 (object_name, expires_hours, bucket)
            input_url = await asyncio.to_thread(
                storage_service.get_presigned_url, object_name, 1.0, bucket_name
            )
            
            # Run FFmpeg in a separate thread to prevent event loop blocking
            # Fast seek (-ss 00:00:00.000) before -i is crucial for performance on large files
            ffmpeg_cmd = [
                "ffmpeg",
                "-y",
                "-ss", "00:00:00.000",
                "-i", input_url,
                "-frames:v", "1",
                "-q:v", "5",  # JPEG quality (2-31, lower is better, 5 is a good balance)
                thumb_local_path
            ]
            
            logger.info(f"Generating video thumbnail: {' '.join(ffmpeg_cmd)}")
            await asyncio.to_thread(
                subprocess.run,
                ffmpeg_cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

        else:
            # For image, download locally first, then process with Pillow
            original_ext = object_name.rsplit(".", 1)[-1]
            original_local_path = os.path.join(temp_dir, f"original.{original_ext}")
            
            logger.info(f"Downloading {object_name} for image thumbnail generation")
            # Fallback to synchronous download_file
            await asyncio.to_thread(
                storage_service.download_file,
                bucket_name,
                object_name,
                original_local_path,
            )
            
            def process_image(src_path: str, dest_path: str):
                with Image.open(src_path) as img:
                    # Correct orientation based on EXIF
                    img = ImageOps.exif_transpose(img)
                    
                    # Convert to RGB (to handle RGBA/P images saving as JPEG/WEBP)
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                        
                    # Calculate new dimensions (max width 600)
                    max_width = 600
                    if img.width > max_width:
                        ratio = max_width / img.width
                        new_height = int(img.height * ratio)
                        img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                        
                    # Save as WebP with high compression
                    img.save(dest_path, "WEBP", quality=80, method=6)

            logger.info(f"Processing image thumbnail for {object_name}")
            await asyncio.to_thread(process_image, original_local_path, thumb_local_path)

        # Upload the generated thumbnail back to MinIO
        logger.info(f"Uploading thumbnail to {bucket_name}/{thumb_object_name}")
        # Fallback to synchronous upload_file
        await asyncio.to_thread(
            storage_service.upload_file,
            thumb_local_path,
            thumb_object_name,
            bucket_name,
        )
        
        # Also sync to R2
        try:
            await storage_service.async_copy_to_r2(
                bucket_name, thumb_object_name, target_r2_key
            )
        except Exception as e:
            logger.error(f"Failed to sync thumbnail {thumb_object_name} to R2: {e}")

    except Exception as e:
        logger.error(f"Error generating thumbnail for {output_file}: {e}", exc_info=True)
        # We intentionally do not re-raise to avoid failing the main workflow if thumbnail generation fails.
    finally:
        # Force cleanup of the temporary directory
        shutil.rmtree(temp_dir, ignore_errors=True)
