from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import select, desc, update
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, UserInteraction, History, User
from src.web_api.dependencies import get_current_user
from src.web_api.schemas.gallery_schema import GalleryPostResponse, PaginatedGalleryResponse, ApplyContextResponse
from src.handlers.fsm.video_lora_fsm import LORA_MODELS
from src.constants import MODE_NAME_MAP, MODE_I2I_PRO, MODE_EDIT, MODE_CUSTOM_VIDEO, MODE_VIDEO_LORA
from src.services.redis_client import redis_client
import json
import logging
import os
import re
from src.services.storage import storage

router = APIRouter()
logger = logging.getLogger(__name__)

# Allowed task types for web gallery submission
ALLOWED_WEB_SUBMIT_TYPES = {MODE_I2I_PRO, MODE_EDIT, MODE_CUSTOM_VIDEO, MODE_VIDEO_LORA}

def translate_tags(tags_list: List[str]) -> List[str]:
    translated_tags = []
    for tag in tags_list:
        raw_tag = tag.strip("#")
        if raw_tag in LORA_MODELS:
            translated_tags.append(f"#{LORA_MODELS[raw_tag]}")
        else:
            translated_tags.append(tag)
    return translated_tags

from config import R2_PUBLIC_DOMAIN

def get_media_url(output_file: str) -> str:
    """
    Generate the media URL for a gallery post.
    If R2 is configured, return the R2 public URL directly.
    Otherwise, return the relative path for the frontend to resolve via MinIO.
    """
    if not output_file:
        return ""
        
    # If R2 is configured, return the CDN URL directly
    if R2_PUBLIC_DOMAIN:
        # Extract just the filename from paths like 'bot-data/users/xxx.mp4' or 'comfyui-temp/yyy.mp4'
        filename = output_file.split("/")[-1]
        base_url = R2_PUBLIC_DOMAIN.rstrip("/")
        return f"{base_url}/{filename}"

    # Fallback: We return the raw output_file here, and let the frontend use its `getFileUrl`
    # logic to prepend the correct MinIO endpoint.
    return output_file

def generate_thumbnail_url(output_file: str, media_type: str) -> str:
    # 假设使用 imgproxy 并且可以通过代理来访问缩略图
    # 此时直接返回原文件路径即可，前端组装 URL 时会加上 imgproxy 规则
    return get_media_url(output_file)

@router.get("/config")
async def get_gallery_config():
    return {
        "allowed_types": [
            {"id": MODE_I2I_PRO, "name": MODE_NAME_MAP.get(MODE_I2I_PRO, "幻想换脸")},
            {"id": MODE_EDIT, "name": MODE_NAME_MAP.get(MODE_EDIT, "自由P图")},
            {"id": MODE_CUSTOM_VIDEO, "name": MODE_NAME_MAP.get(MODE_CUSTOM_VIDEO, "自定义图生视频")},
            {"id": MODE_VIDEO_LORA, "name": MODE_NAME_MAP.get(MODE_VIDEO_LORA, "图生视频(附加模型)")}
        ],
        "lora_models": [{"id": k, "name": v} for k, v in LORA_MODELS.items()]
    }

@router.get("/posts", response_model=PaginatedGalleryResponse)
async def get_gallery_posts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    media_type: Optional[str] = None,
    task_type: Optional[str] = None,
    lora_model: Optional[str] = None,
    sort_by: str = Query("latest", pattern="^(latest|likes|applied)$"),
    time_range: str = Query("all", pattern="^(today|week|month|all)$"),
    current_user: Optional[User] = Depends(get_current_user)
):
    async with AsyncSessionLocal() as session:
        query = select(GalleryPost).where(GalleryPost.is_active == True)
        
        # Join with History to filter by task_type
        if task_type and task_type != "all":
            query = query.join(History, GalleryPost.task_id == History.task_id)
            query = query.where(History.type == task_type)
            
        if media_type and media_type != "all" and not task_type:
            query = query.where(GalleryPost.media_type == media_type)
            
        # Filter by lora_model if provided (search in tags JSON string)
        if lora_model:
            # tag in DB is like "#LorAName"
            lora_tag = f'"#{lora_model}"'
            query = query.where(GalleryPost.tags.like(f"%{lora_tag}%"))
            
        # Filter by time_range
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
            query = query.order_by(desc(GalleryPost.likes_count), desc(GalleryPost.id))
        elif sort_by == "applied":
            query = query.order_by(desc(GalleryPost.applied_count), desc(GalleryPost.id))
        else:
            query = query.order_by(desc(GalleryPost.id))
            
        # Get total count
        from sqlalchemy import func
        total_query = select(func.count()).select_from(query.subquery())
        total = (await session.execute(total_query)).scalar()
        
        # Paginate
        offset = (page - 1) * size
        query = query.offset(offset).limit(size)
        
        result = await session.execute(query)
        posts = result.scalars().all()
        
        # Load interactions for current user
        user_likes = set()
        user_dislikes = set()
        if current_user:
            post_ids = [p.id for p in posts]
            if post_ids:
                interactions = (await session.execute(
                    select(UserInteraction)
                    .where(UserInteraction.user_id == current_user.id)
                    .where(UserInteraction.post_id.in_(post_ids))
                    .where(UserInteraction.action_type.in_(["like", "dislike"]))
                )).scalars().all()
                for inter in interactions:
                    if inter.action_type == "like":
                        user_likes.add(inter.post_id)
                    elif inter.action_type == "dislike":
                        user_dislikes.add(inter.post_id)
                        
        response_items = []
        for post in posts:
            try:
                tags = json.loads(post.tags) if post.tags else []
            except:
                tags = []
            translated_tags = translate_tags(tags)
            
            # Fetch history to get output_file for URL generation
            hist_res = await session.execute(select(History).where(History.task_id == post.task_id))
            history = hist_res.scalar_one_or_none()
            output_file = history.output_file if history else None
            prompt = history.prompt if history else None
            task_type = history.type if history else None
            
            media_url = get_media_url(output_file)
            thumbnail_url = media_url # 暂时代替，后续可替换为 imgproxy 格式
            
            response_items.append(GalleryPostResponse(
                id=post.id,
                task_id=post.task_id,
                media_type=post.media_type,
                width=post.width,
                height=post.height,
                duration=post.duration,
                tags=translated_tags,
                likes_count=post.likes_count,
                dislikes_count=post.dislikes_count,
                applied_count=post.applied_count,
                thumbnail_url=thumbnail_url,
                media_url=media_url,
                created_at=post.created_at,
                is_active=post.is_active,
                prompt=prompt,
                task_type=task_type,
                has_liked=post.id in user_likes,
                has_disliked=post.id in user_dislikes
            ))
            
        pages = (total + size - 1) // size
        return PaginatedGalleryResponse(
            items=response_items,
            total=total,
            page=page,
            size=size,
            pages=pages
        )

@router.get("/my-posts", response_model=PaginatedGalleryResponse)
async def get_my_gallery_posts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    async with AsyncSessionLocal() as session:
        query = select(GalleryPost).where(GalleryPost.user_id == current_user.id)
        
        query = query.order_by(desc(GalleryPost.id))
            
        # Get total count
        from sqlalchemy import func
        total_query = select(func.count()).select_from(query.subquery())
        total = (await session.execute(total_query)).scalar()
        
        # Paginate
        offset = (page - 1) * size
        query = query.offset(offset).limit(size)
        
        result = await session.execute(query)
        posts = result.scalars().all()
        
        # Load interactions for current user
        user_likes = set()
        user_dislikes = set()
        if posts:
            post_ids = [p.id for p in posts]
            interactions = (await session.execute(
                select(UserInteraction)
                .where(UserInteraction.user_id == current_user.id)
                .where(UserInteraction.post_id.in_(post_ids))
                .where(UserInteraction.action_type.in_(["like", "dislike"]))
            )).scalars().all()
            for inter in interactions:
                if inter.action_type == "like":
                    user_likes.add(inter.post_id)
                elif inter.action_type == "dislike":
                    user_dislikes.add(inter.post_id)
                        
        response_items = []
        for post in posts:
            try:
                tags = json.loads(post.tags) if post.tags else []
            except:
                tags = []
            translated_tags = translate_tags(tags)
            
            hist_res = await session.execute(select(History).where(History.task_id == post.task_id))
            history = hist_res.scalar_one_or_none()
            output_file = history.output_file if history else None
            prompt = history.prompt if history else None
            task_type = history.type if history else None
            
            media_url = get_media_url(output_file)
            thumbnail_url = media_url # 暂时代替，后续可替换为 imgproxy 格式
            
            response_items.append(GalleryPostResponse(
                id=post.id,
                task_id=post.task_id,
                media_type=post.media_type,
                width=post.width,
                height=post.height,
                duration=post.duration,
                tags=translated_tags,
                likes_count=post.likes_count,
                dislikes_count=post.dislikes_count,
                applied_count=post.applied_count,
                thumbnail_url=thumbnail_url,
                media_url=media_url,
                created_at=post.created_at,
                is_active=post.is_active,
                prompt=prompt,
                task_type=task_type,
                has_liked=post.id in user_likes,
                has_disliked=post.id in user_dislikes
            ))
            
        pages = (total + size - 1) // size
        return PaginatedGalleryResponse(
            items=response_items,
            total=total,
            page=page,
            size=size,
            pages=pages
        )

@router.get("/my-favorites", response_model=PaginatedGalleryResponse)
async def get_my_favorite_posts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    filter_type: str = Query("all", pattern="^(all|like|apply)$"),
    current_user: User = Depends(get_current_user)
):
    async with AsyncSessionLocal() as session:
        action_types = ["like", "apply"]
        if filter_type == "like":
            action_types = ["like"]
        elif filter_type == "apply":
            action_types = ["apply"]

        query = select(GalleryPost).join(
            UserInteraction, GalleryPost.id == UserInteraction.post_id
        ).where(
            UserInteraction.user_id == current_user.id,
            UserInteraction.action_type.in_(action_types),
            GalleryPost.is_active == True
        ).distinct().order_by(desc(GalleryPost.id))
            
        # Get total count
        from sqlalchemy import func
        total_query = select(func.count()).select_from(query.subquery())
        total = (await session.execute(total_query)).scalar()
        
        # Paginate
        offset = (page - 1) * size
        query = query.offset(offset).limit(size)
        
        result = await session.execute(query)
        posts = result.scalars().all()
        
        # Load interactions for current user
        user_likes = set()
        user_dislikes = set()
        if posts:
            post_ids = [p.id for p in posts]
            interactions = (await session.execute(
                select(UserInteraction)
                .where(UserInteraction.user_id == current_user.id)
                .where(UserInteraction.post_id.in_(post_ids))
                .where(UserInteraction.action_type.in_(["like", "dislike"]))
            )).scalars().all()
            for inter in interactions:
                if inter.action_type == "like":
                    user_likes.add(inter.post_id)
                elif inter.action_type == "dislike":
                    user_dislikes.add(inter.post_id)
                        
        response_items = []
        for post in posts:
            try:
                tags = json.loads(post.tags) if post.tags else []
            except:
                tags = []
            translated_tags = translate_tags(tags)
            
            hist_res = await session.execute(select(History).where(History.task_id == post.task_id))
            history = hist_res.scalar_one_or_none()
            output_file = history.output_file if history else None
            prompt = history.prompt if history else None
            task_type = history.type if history else None
            
            media_url = get_media_url(output_file)
            thumbnail_url = media_url # 暂时代替，后续可替换为 imgproxy 格式
            
            response_items.append(GalleryPostResponse(
                id=post.id,
                task_id=post.task_id,
                media_type=post.media_type,
                width=post.width,
                height=post.height,
                duration=post.duration,
                tags=translated_tags,
                likes_count=post.likes_count,
                dislikes_count=post.dislikes_count,
                applied_count=post.applied_count,
                thumbnail_url=thumbnail_url,
                media_url=media_url,
                created_at=post.created_at,
                is_active=post.is_active,
                prompt=prompt,
                task_type=task_type,
                has_liked=post.id in user_likes,
                has_disliked=post.id in user_dislikes
            ))
            
        pages = (total + size - 1) // size
        return PaginatedGalleryResponse(
            items=response_items,
            total=total,
            page=page,
            size=size,
            pages=pages
        )

@router.put("/posts/{post_id}/status")
async def update_post_status(
    post_id: int,
    is_active: bool = Query(...),
    current_user: User = Depends(get_current_user)
):
    async with AsyncSessionLocal() as session:
        post = (await session.execute(select(GalleryPost).where(GalleryPost.id == post_id))).scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="帖子不存在")
        if post.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权操作此帖子")
            
        await session.execute(update(GalleryPost).where(GalleryPost.id == post_id).values(is_active=is_active))
        await session.commit()
        return {"status": "success", "message": f"已{'上架' if is_active else '下架'}"}

@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user)
):
    from sqlalchemy import delete
    async with AsyncSessionLocal() as session:
        post = (await session.execute(select(GalleryPost).where(GalleryPost.id == post_id))).scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="帖子不存在")
        if post.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权操作此帖子")
            
        # Delete related interactions first
        await session.execute(delete(UserInteraction).where(UserInteraction.post_id == post_id))
        
        # Unlink history from this post
        await session.execute(update(History).where(History.task_id == post.task_id).values(is_public=False)) # Optionally reset is_public
        
        # Delete post
        await session.execute(delete(GalleryPost).where(GalleryPost.id == post_id))
        
        # Decrement total_contributions in users table
        user_record = await session.execute(select(User).where(User.id == current_user.id))
        user_obj = user_record.scalar_one_or_none()
        if user_obj and user_obj.total_contributions > 0:
            user_obj.total_contributions -= 1
            
        await session.commit()
        return {"status": "success", "message": "删除成功"}

@router.post("/posts/{post_id}/interact")
async def interact_with_post(
    post_id: int,
    action: str = Query(..., pattern="^(like|dislike)$"),
    current_user: User = Depends(get_current_user)
):
    async with AsyncSessionLocal() as session:
        post = (await session.execute(select(GalleryPost).where(GalleryPost.id == post_id))).scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="帖子不存在或已失效")
            
        # Check mutual exclusion
        existing = (await session.execute(
            select(UserInteraction)
            .where(UserInteraction.user_id == current_user.id)
            .where(UserInteraction.post_id == post_id)
            .where(UserInteraction.action_type.in_(["like", "dislike"]))
        )).scalars().all()
        
        if existing:
            for ex in existing:
                if ex.action_type == action:
                    raise HTTPException(status_code=400, detail=f"您已经{'点过赞' if action == 'like' else '点过踩'}啦！")
            raise HTTPException(status_code=400, detail="互斥操作：您已经给过评价了！")
            
        interaction = UserInteraction(user_id=current_user.id, post_id=post.id, action_type=action)
        session.add(interaction)
        
        if action == "like":
            await session.execute(update(GalleryPost).where(GalleryPost.id == post.id).values(likes_count=GalleryPost.likes_count + 1))
        else:
            await session.execute(update(GalleryPost).where(GalleryPost.id == post.id).values(dislikes_count=GalleryPost.dislikes_count + 1))
            
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(status_code=400, detail="重复操作：您已经给过评价了！")
        return {"status": "success", "message": f"{'点赞' if action == 'like' else '点踩'}成功"}

@router.get("/posts/{post_id}/apply-context", response_model=ApplyContextResponse)
async def get_apply_context(
    post_id: int,
    current_user: User = Depends(get_current_user)
):
    async with AsyncSessionLocal() as session:
        post = (await session.execute(select(GalleryPost).where(GalleryPost.id == post_id))).scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="帖子不存在或已失效")
            
        hist_res = await session.execute(select(History).where(History.task_id == post.task_id))
        history = hist_res.scalar_one_or_none()
        
        if not history:
            raise HTTPException(status_code=404, detail="未找到原任务详情")
            
        # record apply action
        interaction = UserInteraction(user_id=current_user.id, post_id=post.id, action_type="apply")
        session.add(interaction)
        await session.execute(update(GalleryPost).where(GalleryPost.id == post.id).values(applied_count=GalleryPost.applied_count + 1))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            # Already applied, just ignore the increment
            pass
        
        input_file_url = None
        if history.input_file:
            input_file_url = get_media_url(history.input_file)
        
        return ApplyContextResponse(
            post_id=post.id,
            task_id=post.task_id,
            media_type=post.media_type,
            prompt=history.prompt,
            input_file=history.input_file,
            input_file_url=input_file_url,
            width=post.width,
            height=post.height,
            duration=post.duration,
            task_type=history.type
        )

@router.post("/posts/submit/{task_id}")
async def submit_to_gallery(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    async with AsyncSessionLocal() as session:
        # Check limit
        can_submit = await redis_client.check_gallery_submit_limit(current_user.id, limit=10)
        if not can_submit:
            raise HTTPException(status_code=400, detail="您今日的投稿次数已达 10 次上限，请明日再来~")

        # Check existing
        existing = await session.execute(select(GalleryPost).where(GalleryPost.task_id == task_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="您已经投稿过此内容啦！")

        # Get History
        hist_res = await session.execute(select(History).where(History.task_id == task_id).where(History.user_id == current_user.id))
        history = hist_res.scalar_one_or_none()
        if not history:
            raise HTTPException(status_code=404, detail="无法找到对应的任务记录，投稿失败")

        if history.type not in ALLOWED_WEB_SUBMIT_TYPES:
            allowed_names = [MODE_NAME_MAP.get(t, t) for t in ALLOWED_WEB_SUBMIT_TYPES]
            raise HTTPException(status_code=400, detail=f"暂不支持该类型记录的投稿，目前仅支持：{', '.join(allowed_names)}")

        if not history.output_file:
            raise HTTPException(status_code=400, detail="此任务没有生成文件，无法投稿")

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
            match = re.search(r"\[模型:\s*(.*?)\]", history.prompt)
            if match:
                lora_tag = match.group(1).strip()
                tags.append(f"#{lora_tag}")

        tags_json = json.dumps(tags, ensure_ascii=False)

        new_post = GalleryPost(
            task_id=task_id,
            user_id=current_user.id,
            media_type=media_type,
            width=width,
            height=height,
            duration=duration,
            tags=tags_json
        )
        session.add(new_post)
        
        # Increment total_contributions in users table
        user_record = await session.execute(select(User).where(User.id == current_user.id))
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

        try:
            # Await the copy directly to avoid frontend race conditions (cached 404 on CDN)
            await storage.async_copy_to_r2(bucket_name, object_name, r2_object_name)
        except Exception as e:
            logger.error(f"Failed to copy {object_name} to R2 during submit: {e}")

        await redis_client.increment_gallery_submit(current_user.id)

        tags_str = " ".join(tags)
        return {"status": "success", "message": f"投稿成功！已自动添加标签：{tags_str}"}
