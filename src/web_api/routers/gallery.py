from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import select, desc, update
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, UserInteraction, History, User
from src.web_api.dependencies import get_current_user
from src.web_api.schemas.gallery_schema import GalleryPostResponse, PaginatedGalleryResponse, ApplyContextResponse
from src.config_mapping import ALL_LORA_MODELS, translate_tags

from src.constants import MODE_NAME_MAP, MODE_I2I_PRO, MODE_EDIT, MODE_CUSTOM_VIDEO, MODE_VIDEO_LORA, MODE_LTX_VIDEO
from src.services.redis_client import redis_client
import json
import logging
import os
import re
from src.services.storage import storage

router = APIRouter()
logger = logging.getLogger(__name__)

# Allowed task types for web gallery submission
ALLOWED_WEB_SUBMIT_TYPES = {MODE_I2I_PRO, MODE_EDIT, MODE_CUSTOM_VIDEO, MODE_VIDEO_LORA, MODE_LTX_VIDEO, "img2img_lora"}

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
            {"id": "img2img_lora", "name": "图生图(附加模型)"},
            {"id": MODE_CUSTOM_VIDEO, "name": MODE_NAME_MAP.get(MODE_CUSTOM_VIDEO, "自定义图生视频")},
            {"id": MODE_VIDEO_LORA, "name": MODE_NAME_MAP.get(MODE_VIDEO_LORA, "图生视频(附加模型)")},
            {"id": MODE_LTX_VIDEO, "name": MODE_NAME_MAP.get(MODE_LTX_VIDEO, "高级图生视频")}
        ],
        "lora_models": [{"id": k, "name": v} for k, v in VIDEO_LORA_MODELS.items()],
        "img2img_lora_models": [{"id": k, "name": v} for k, v in IMAGE_LORA_MODELS.items() if k]
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
    posts, total = await get_gallery_feed(
        page=page,
        size=size,
        media_type=media_type if media_type != "all" else None,
        task_type=task_type if task_type != "all" else None,
        lora_model=lora_model,
        sort_by=sort_by,
        time_range=time_range,
        user_id=current_user.id if current_user else None
    )
    
    async with AsyncSessionLocal() as session:
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
            except Exception:
                tags = []
            translated_tags = translate_tags(tags)
            
            # Fetch history to get output_file for URL generation
            hist_res = await session.execute(select(History).where(History.task_id == post.task_id))
            history = hist_res.scalars().first()
            output_file = history.output_file if history else None
            prompt = history.prompt if history else None
            task_type_from_history = history.type if history else None
            
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
                task_type=task_type_from_history,
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
            except Exception:
                tags = []
            translated_tags = translate_tags(tags)
            
            hist_res = await session.execute(select(History).where(History.task_id == post.task_id))
            history = hist_res.scalars().first()
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
            except Exception:
                tags = []
            translated_tags = translate_tags(tags)
            
            hist_res = await session.execute(select(History).where(History.task_id == post.task_id))
            history = hist_res.scalars().first()
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
        history = hist_res.scalars().first()
        
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
            
        prompt = history.prompt or ""
        lora_name = None
        match = re.search(r"\[模型:\s*(.*?)\]\s*(.*)", prompt, re.DOTALL)
        if match:
            lora_tag = match.group(1).strip()
            prompt = match.group(2).strip()
            
            # Map Chinese lora_tag back to ID if needed
            reverse_lora_models = {v: k for k, v in ALL_LORA_MODELS.items()}
            # also handle qwen/YARN explicitly since we might map it differently
            reverse_lora_models["逼真"] = "qwen/YARN_1.0.safetensors"
            reverse_lora_models["菊花+内凹穴"] = "qwen/adjust_pussy_anus.safetensors"
            reverse_lora_models["真实质感"] = "qwen/realistic_texture.safetensors"
            reverse_lora_models["平胸/无毛穴"] = "qwen/flat_chest_hairless.safetensors"
            reverse_lora_models["扶他(阴茎)"] = "qwen/penis.safetensors"
            
            if lora_tag in reverse_lora_models:
                lora_name = reverse_lora_models[lora_tag]
            else:
                lora_name = lora_tag
        
        return ApplyContextResponse(
            post_id=post.id,
            task_id=post.task_id,
            media_type=post.media_type,
            prompt=prompt,
            lora_name=lora_name,
            input_file=history.input_file,
            input_file_url=input_file_url,
            width=post.width,
            height=post.height,
            duration=post.duration,
            task_type=history.type
        )

from src.core.gallery_core import process_submit_to_gallery, GalleryCoreError, toggle_like, DuplicateInteractionError, get_gallery_feed

@router.post("/posts/submit/{task_id}")
async def submit_to_gallery(
    task_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    try:
        result = await process_submit_to_gallery(current_user.id, task_id, background_tasks)
        return result
    except GalleryCoreError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error submitting to gallery: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
