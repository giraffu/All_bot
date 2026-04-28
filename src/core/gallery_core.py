import re
import json
import logging
import asyncio
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, History, User, UserInteraction
from src.services.redis_client import redis_client
from src.services.storage import storage

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

class DuplicateInteractionError(GalleryCoreError):
    pass

async def async_copy_to_r2_background(bucket_name: str, object_name: str, r2_object_name: str):
    """Background task to copy file to R2."""
    try:
        await storage.async_copy_to_r2(bucket_name, object_name, r2_object_name)
    except Exception as e:
        logger.error(f"Background task failed to copy {object_name} to R2: {e}")

async def process_submit_to_gallery(user_id: int, task_id: str, background_tasks, width: int = None, height: int = None, duration: int = None) -> dict:
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

async def toggle_like(user_id: int, post_id: int, action: str) -> dict:
    """Core logic for toggling like/dislike on a gallery post."""
    if action not in ["like", "dislike"]:
        raise GalleryCoreError("无效的操作类型")

    async with AsyncSessionLocal() as session:
        post = await session.get(GalleryPost, post_id)
        if not post:
            raise GalleryCoreError("帖子不存在")

        existing_inter = await session.execute(
            select(UserInteraction).where(
                UserInteraction.user_id == user_id,
                UserInteraction.post_id == post_id
            )
        )
        inter = existing_inter.scalars().first()

        if inter:
            if inter.action_type == action:
                raise DuplicateInteractionError("您已经进行过此操作啦！")
            
            # Toggle using atomic update
            from sqlalchemy import update
            if inter.action_type == "like" and action == "dislike":
                stmt = update(GalleryPost).where(GalleryPost.id == post_id).values(
                    likes_count=GalleryPost.likes_count - 1,
                    dislikes_count=GalleryPost.dislikes_count + 1
                ).returning(GalleryPost.likes_count, GalleryPost.dislikes_count)
            elif inter.action_type == "dislike" and action == "like":
                stmt = update(GalleryPost).where(GalleryPost.id == post_id).values(
                    likes_count=GalleryPost.likes_count + 1,
                    dislikes_count=GalleryPost.dislikes_count - 1
                ).returning(GalleryPost.likes_count, GalleryPost.dislikes_count)
                
            res = await session.execute(stmt)
            updated = res.fetchone()
            post.likes_count = updated[0]
            post.dislikes_count = updated[1]
                
            inter.action_type = action
        else:
            new_inter = UserInteraction(user_id=user_id, post_id=post_id, action_type=action)
            session.add(new_inter)
            
            from sqlalchemy import update
            if action == "like":
                stmt = update(GalleryPost).where(GalleryPost.id == post_id).values(
                    likes_count=GalleryPost.likes_count + 1
                ).returning(GalleryPost.likes_count, GalleryPost.dislikes_count)
            else:
                stmt = update(GalleryPost).where(GalleryPost.id == post_id).values(
                    dislikes_count=GalleryPost.dislikes_count + 1
                ).returning(GalleryPost.likes_count, GalleryPost.dislikes_count)
                
            res = await session.execute(stmt)
            updated = res.fetchone()
            post.likes_count = updated[0]
            post.dislikes_count = updated[1]

        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise DuplicateInteractionError("您已经进行过此操作啦！")
            
        return {
            "likes_count": post.likes_count,
            "dislikes_count": post.dislikes_count
        }

async def get_gallery_feed(
    page: int = 1,
    size: int = 20,
    media_type: str = None,
    task_type: str = None,
    lora_model: str = None,
    sort_by: str = "latest",
    time_range: str = "all",
    user_id: int = None,
    category: str = None,
    is_active: bool = True
) -> tuple[list, int]:
    """
    Core logic to fetch paginated gallery feed.
    Returns (posts, total_count).
    """
    async with AsyncSessionLocal() as session:
        query = select(GalleryPost)
        if is_active is True:
            query = query.where(GalleryPost.is_active == True)
        elif is_active is False:
            query = query.where(GalleryPost.is_active == False)
        
        # Join with History to filter by task_type or category
        if task_type and task_type != "all":
            query = query.join(History, GalleryPost.task_id == History.task_id)
            query = query.where(History.type == task_type)
        elif category and category != "all":
            query = query.join(History, GalleryPost.task_id == History.task_id)
            if category == 'i2ipro':
                query = query.where(History.type == 'i2i_pro')
            elif category == 'faceswap':
                query = query.where(History.type.in_(['face_video']))
            elif category == 'edit':
                query = query.where(History.type.in_(['edit', 'quick_image']))
            elif category == 'imglora':
                query = query.where(History.type == 'img2img_lora')
            elif category == 'custvid':
                query = query.where(History.type == 'custom_video')
            elif category == 'vidlora':
                query = query.where(History.type == 'video_lora')
            elif category == 'ltxvid':
                query = query.where(History.type == 'ltx_video')
            
        if media_type and media_type != "all" and not task_type and not category:
            query = query.where(GalleryPost.media_type == media_type)
            
        if lora_model:
            lora_tag = f'"#{lora_model}"'
            query = query.where(GalleryPost.tags.like(f"%{lora_tag}%"))
            
        if user_id and sort_by == "mine":
            query = query.where(GalleryPost.user_id == user_id)
            
        from datetime import datetime, timedelta
        now = datetime.now()
        if time_range == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.where(GalleryPost.created_at >= start_time)
        elif time_range == "week":
            start_time = now - timedelta(days=7)
            query = query.where(GalleryPost.created_at >= start_time)
        elif time_range == "month":
            start_time = now - timedelta(days=30)
            query = query.where(GalleryPost.created_at >= start_time)
            
        if sort_by == "likes":
            query = query.order_by(desc(GalleryPost.likes_count), desc(GalleryPost.created_at))
        elif sort_by == "applied":
            query = query.order_by(desc(GalleryPost.applied_count), desc(GalleryPost.created_at))
        else:
            query = query.order_by(desc(GalleryPost.created_at))
            
        # Get total count dynamically
        total_query = select(func.count()).select_from(query.subquery())
        total = (await session.execute(total_query)).scalar()
        
        # Eager load related User and History
        query = query.options(selectinload(GalleryPost.user))
        
        # Paginate
        offset = (page - 1) * size if page > 0 else 0
        query = query.offset(offset).limit(size)
        
        result = await session.execute(query)
        posts = result.scalars().all()
        
        return posts, total
