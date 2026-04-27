import re
import json
import logging
import asyncio
from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, History, User
from src.services.redis_client import redis_client
from src.services.storage import storage
from sqlalchemy import select

logger = logging.getLogger(__name__)

ALLOWED_WEB_SUBMIT_TYPES = [
    "i2i_pro", "face_video", "custom_video", "txt2video",
    "video_lora", "perfect_video_insert", "doggy_style",
    "blowjob", "undress_tongue", "closeup_blowjob", "ltx_video"
]

MODE_NAME_MAP = {
    "i2i_pro": "图生图",
    "face_video": "视频换脸",
    "custom_video": "自定义视频",
    "txt2video": "文生视频",
    "video_lora": "视频微调",
    "perfect_video_insert": "完美插入",
    "doggy_style": "后入",
    "blowjob": "口交",
    "undress_tongue": "脱衣舔",
    "closeup_blowjob": "特写口交",
    "ltx_video": "LTX视频"
}

class GalleryCoreError(Exception):
    pass

async def async_copy_to_r2_background(bucket_name: str, object_name: str, r2_object_name: str):
    """Background task to copy file to R2."""
    try:
        await storage.async_copy_to_r2(bucket_name, object_name, r2_object_name)
    except Exception as e:
        logger.error(f"Background task failed to copy {object_name} to R2: {e}")

async def process_submit_to_gallery(user_id: int, task_id: str, background_tasks) -> dict:
    """Core logic for submitting a task to the gallery."""
    # Check limit
    can_submit = await redis_client.check_gallery_submit_limit(user_id, limit=10)
    if not can_submit:
        raise GalleryCoreError("您今日的投稿次数已达 10 次上限，请明日再来~")

    async with AsyncSessionLocal() as session:
        # Check existing
        existing = await session.execute(select(GalleryPost).where(GalleryPost.task_id == task_id))
        if existing.scalars().first():
            raise GalleryCoreError("您已经投稿过此内容啦！")

        # Get History
        hist_res = await session.execute(select(History).where(History.task_id == task_id).where(History.user_id == user_id))
        history = hist_res.scalars().first()
        if not history:
            raise GalleryCoreError("无法找到对应的任务记录，投稿失败")

        if getattr(history, 'allow_contribute', True) is False:
            raise GalleryCoreError("这是一键应用他人的模板生成的作品，为了保护原创，暂不支持再次投稿。")

        if history.type not in ALLOWED_WEB_SUBMIT_TYPES:
            allowed_names = [MODE_NAME_MAP.get(t, t) for t in ALLOWED_WEB_SUBMIT_TYPES]
            raise GalleryCoreError(f"暂不支持该类型记录的投稿，目前仅支持：{', '.join(allowed_names)}")

        if not history.output_file:
            raise GalleryCoreError("此任务没有生成文件，无法投稿")

        # Determine media_type from output_file extension
        lower_path = history.output_file.lower()
        is_video = any(lower_path.endswith(ext) for ext in ['.mp4', '.mov', '.webm', '.mkv', '.avi'])
        media_type = 'video' if is_video else 'image'

        width, height, duration = None, None, None

        # Auto Tags
        tags = []
        base_tag = MODE_NAME_MAP.get(history.type, history.type)
        if base_tag:
            tags.append(f"#{base_tag}")

        if history.prompt:
            match = re.search(r"\[模型:\s*(.*?)\]\s*(.*)", history.prompt, re.DOTALL)
            if match:
                lora_tag = match.group(1).strip()
                tags.append(f"#{lora_tag}")

        tags_json = json.dumps(tags, ensure_ascii=False)

        new_post = GalleryPost(
            task_id=task_id,
            user_id=user_id,
            media_type=media_type,
            width=width,
            height=height,
            duration=duration,
            tags=tags_json
        )
        session.add(new_post)
        
        # Increment total_contributions in users table
        user_record = await session.execute(select(User).where(User.id == user_id))
        user_obj = user_record.scalar_one_or_none()
        if user_obj:
            user_obj.total_contributions = (user_obj.total_contributions or 0) + 1
            
        await session.commit()

        # R2 copy logic
        parts = history.output_file.split("/")
        if len(parts) > 1 and parts[0] in ["bot-data", "comfyui-temp"]:
            bucket_name = parts[0]
            object_name = "/".join(parts[1:])
        elif "comfyui-temp" not in history.output_file and "bot-data" not in history.output_file:
            bucket_name = "comfyui-temp" if not "/" in history.output_file else "bot-data"
            object_name = history.output_file
        else:
            bucket_name = "bot-data"
            object_name = history.output_file

        r2_object_name = parts[-1]

        # Add R2 copy to BackgroundTasks instead of awaiting it directly
        background_tasks.add_task(async_copy_to_r2_background, bucket_name, object_name, r2_object_name)

        await redis_client.increment_gallery_submit(user_id)

        tags_str = " ".join(tags)
        return {
            "status": "success", 
            "message": f"投稿成功！已自动添加标签：{tags_str}",
            "tags": tags
        }
