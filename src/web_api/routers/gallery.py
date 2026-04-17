from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, update
from typing import List, Optional
from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, UserInteraction, History, User
from src.web_api.dependencies import get_current_user
from src.web_api.schemas.gallery_schema import GalleryPostResponse, PaginatedGalleryResponse, ApplyContextResponse
from src.handlers.fsm.video_lora_fsm import LORA_MODELS
import json
import logging
import os
from src.services.storage import storage

router = APIRouter()
logger = logging.getLogger(__name__)

def translate_tags(tags_list: List[str]) -> List[str]:
    translated_tags = []
    for tag in tags_list:
        raw_tag = tag.strip("#")
        if raw_tag in LORA_MODELS:
            translated_tags.append(f"#{LORA_MODELS[raw_tag]}")
        else:
            translated_tags.append(tag)
    return translated_tags

def get_media_url(output_file: str) -> str:
    if not output_file:
        return ""
    # We return the raw output_file here, and let the frontend use its `getFileUrl`
    # function to prepend the CDN URL (e.g. assets.aivison.it.com)
    return output_file

def generate_thumbnail_url(output_file: str, media_type: str) -> str:
    # 假设使用 imgproxy 并且可以通过代理来访问缩略图
    # 此时直接返回原文件路径即可，前端组装 URL 时会加上 imgproxy 规则
    return get_media_url(output_file)

@router.get("/posts", response_model=PaginatedGalleryResponse)
async def get_gallery_posts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    media_type: Optional[str] = None,
    sort_by: str = Query("latest", pattern="^(latest|likes|applied)$"),
    current_user: Optional[User] = Depends(get_current_user)
):
    async with AsyncSessionLocal() as session:
        query = select(GalleryPost).where(GalleryPost.is_active == True)
        
        if media_type and media_type != "all":
            query = query.where(GalleryPost.media_type == media_type)
            
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
            
        await session.commit()
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
        await session.commit()
        
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
            task_type=history.task_type
        )
