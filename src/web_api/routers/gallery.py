import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import desc, select, update
from sqlalchemy.exc import IntegrityError

from src.config_mapping import (
    ALL_LORA_MODELS,
    IMAGE_LORA_MODELS,
    VIDEO_LORA_MODELS,
    translate_tags,
)
from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_EDIT,
    MODE_I2I_PRO,
    MODE_LTX_VIDEO,
    MODE_NAME_MAP,
    MODE_VIDEO_LORA,
)
from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, History, User, UserInteraction
from src.web_api.dependencies import get_current_user
from src.web_api.schemas.gallery_schema import (
    ApplyContextResponse,
    GalleryPostResponse,
    PaginatedGalleryResponse,
)

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
            {"id": MODE_I2I_PRO, "name": MODE_NAME_MAP.get(MODE_I2I_PRO, "task.mode_i2i_pro")},
            {"id": MODE_EDIT, "name": MODE_NAME_MAP.get(MODE_EDIT, "task.mode_edit")},
            {"id": "img2img_lora", "name": "task.mode_img2img_lora"},
            {"id": MODE_CUSTOM_VIDEO, "name": MODE_NAME_MAP.get(MODE_CUSTOM_VIDEO, "task.mode_custom_video")},
            {"id": MODE_VIDEO_LORA, "name": MODE_NAME_MAP.get(MODE_VIDEO_LORA, "task.mode_video_lora")},
            {"id": MODE_LTX_VIDEO, "name": MODE_NAME_MAP.get(MODE_LTX_VIDEO, "task.mode_ltx_video")}
        ],
        "lora_models": [{"id": k, "name": v} for k, v in VIDEO_LORA_MODELS.items()],
        "img2img_lora_models": [{"id": k, "name": v} for k, v in IMAGE_LORA_MODELS.items() if k]
    }

async def _build_post_responses(session, posts, current_user: Optional[User]):
    if not posts:
        return []

    post_ids = [p.id for p in posts]
    task_ids = [p.task_id for p in posts if p.task_id]

    user_likes = set()
    user_dislikes = set()
    if current_user and post_ids:
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

    history_map = {}
    if task_ids:
        histories = (await session.execute(
            select(History).where(History.task_id.in_(task_ids))
        )).scalars().all()
        history_map = {h.task_id: h for h in histories}

    response_items = []
    for post in posts:
        try:
            tags = json.loads(post.tags) if post.tags else []
        except Exception:
            tags = []
        translated_tags = translate_tags(tags)

        history = history_map.get(post.task_id)
        output_file = history.output_file if history else None
        prompt = history.prompt if history else None
        task_type_from_history = history.type if history else None

        media_url = get_media_url(output_file)
        thumbnail_url = media_url

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
    return response_items

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
        response_items = await _build_post_responses(session, posts, current_user)
            
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
        
        response_items = await _build_post_responses(session, posts, current_user)
            
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
        
        response_items = await _build_post_responses(session, posts, current_user)
            
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
    from src.core.gallery_core import toggle_like, GalleryCoreError, DuplicateInteractionError
    try:
        result = await toggle_like(current_user.id, post_id, action)
        return {"status": "success", "message": f"{'点赞' if action == 'like' else '点踩'}成功", "data": result}
    except DuplicateInteractionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GalleryCoreError as e:
        if "不存在" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="内部服务器错误")

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

from src.core.gallery_core import (
    GalleryCoreError,
    get_gallery_feed,
    process_submit_to_gallery,
)


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
