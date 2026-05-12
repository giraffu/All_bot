import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from PIL import Image, ImageOps

from src.core.media_paths import build_legacy_r2_key
from src.services.storage import storage

logger = logging.getLogger(__name__)


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

    # Determine bucket and object paths based on how gallery_core handles it
    parts = output_file.split("/")
    if len(parts) > 1 and parts[0] in ["bot-data", "comfyui-temp"]:
        bucket_name = parts[0]
        object_name = "/".join(parts[1:])
    elif "comfyui-temp" not in output_file and "bot-data" not in output_file:
        bucket_name = "comfyui-temp" if "/" not in output_file else "bot-data"
        object_name = output_file
    else:
        bucket_name = "bot-data"
        object_name = output_file

    base_path = object_name.rsplit(".", 1)[0]

    if media_type == "video":
        thumb_object_name = f"{base_path}_thumb.jpg"
    else:
        thumb_object_name = f"{base_path}_thumb.webp"

    target_r2_key = r2_object_name or build_legacy_r2_key(thumb_object_name)

    # If the thumbnail already exists in MinIO, skip regeneration but still补齐 R2 同步。
    try:
        thumb_exists, r2_exists = await asyncio.gather(
            storage.async_object_exists(bucket_name, thumb_object_name),
            storage.async_r2_object_exists(target_r2_key),
        )
        if thumb_exists:
            if not r2_exists:
                await storage.async_copy_to_r2(
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
            input_url = await asyncio.to_thread(storage.get_presigned_url, object_name, 1.0, bucket_name)
            
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
            await asyncio.to_thread(storage.download_file, bucket_name, object_name, original_local_path)
            
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
        await asyncio.to_thread(storage.upload_file, thumb_local_path, thumb_object_name, bucket_name)
        
        # Also sync to R2
        try:
            await storage.async_copy_to_r2(
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
