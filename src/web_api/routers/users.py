import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.core import AsyncSessionLocal
from src.database.models import History, User
from src.web_api.dependencies import get_current_user
from src.web_api.schemas.auth_schema import InvitationRechargeStats, UserResponse
from src.web_api.schemas.user_schema import PaginatedHistory, CheckinResponse
from src.web_api.schemas.gallery_schema import PaginatedGalleryResponse, ApplyContextResponse, GalleryPostResponse
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
import re

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.get("/me", response_model=UserResponse)
async def get_user_profile(current_user: User = Depends(get_current_user)):
    """
    Get current logged in user's profile and credit balance.
    """
    from src.core.user_facade import get_user_dashboard_info
    
    # We pass telegram_id and full_name to the facade.
    dto = await get_user_dashboard_info(
        current_user.telegram_id, 
        current_user.full_name or current_user.username or "道友"
    )
    
    return UserResponse(
        id=current_user.id,
        telegram_id=current_user.telegram_id,
        username=current_user.username,
        full_name=current_user.full_name,
        language_code=current_user.language_code,
        credits=dto.credits,
        user_group=dto.current_group,
        current_identity=dto.current_identity,
        identity_expire_at=dto.identity_expire_at,
        priority=dto.current_priority,
        generation_count=dto.generations,
        checkin_count=dto.checkins,
        invitation_count=dto.invitations,
        invitation_recharge=InvitationRechargeStats(**dto.invitation_recharge),
        breakthrough_conditions=[cond.dict() for cond in dto.breakthrough_conditions],
        is_unlocked=dto.is_unlocked
    )

class PreferencesUpdate(BaseModel):
    language_code: str

@router.patch("/preferences")
async def update_user_preferences(
    prefs: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update user preferences like language_code.
    """
    from src.database.models import User
    from sqlalchemy import update
    
    stmt = (
        update(User)
        .where(User.id == current_user.id)
        .values(language_code=prefs.language_code)
    )
    await db.execute(stmt)
    await db.commit()
    
    # Sync to Redis cache
    from src.services.redis_client import redis_client
    if redis_client and redis_client.redis:
        await redis_client.redis.set(f"allbot:user_lang:{current_user.id}", prefs.language_code)
        
    return {"status": "success", "language_code": prefs.language_code}

@router.get("/history", response_model=PaginatedHistory)
async def get_user_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get generation history for the current user, limited to the 8 most recent items
    to save VPS bandwidth, reduce CDN caching pressure, and protect privacy.
    """
    limit = 8
    
    # First get the latest 8 items regardless of visibility to enforce the strict 8-item window limit
    subq = (
        select(History.id)
        .where(History.user_id == current_user.id)
        .order_by(History.created_at.desc())
        .limit(limit)
        .subquery()
    )
    
    # Then filter out the invisible ones from those 8 items
    stmt = (
        select(History)
        .where(History.id.in_(select(subq.c.id)))
        .where(History.is_visible.is_not(False))
        .order_by(History.created_at.desc())
    )
    result = await db.execute(stmt)
    items = result.scalars().all()
    
    # Batch check gallery status for items to avoid N+1 queries
    task_ids_to_check = [item.task_id for item in items if item.is_public and item.task_id]
    
    if task_ids_to_check:
        from src.database.models import GalleryPost
        gp_stmt = select(GalleryPost.task_id).where(
            GalleryPost.task_id.in_(task_ids_to_check), 
            GalleryPost.is_active == True
        )
        gp_result = await db.execute(gp_stmt)
        active_task_ids = set(gp_result.scalars().all())
        
        for item in items:
            if item.is_public and item.task_id:
                if item.task_id not in active_task_ids:
                    item.is_public = False
    
    return PaginatedHistory(
        items=list(items),
        total=len(items),
        page=1,
        size=limit
    )

@router.post("/checkin", response_model=CheckinResponse)
async def checkin_user(current_user: User = Depends(get_current_user)):
    """
    Perform daily check-in for the current user.
    """
    from src.services.permission_service import permission_service
    
    success, current_credits, error_msg, total_days, reward = await permission_service.perform_checkin(
        current_user.telegram_id, 
        current_user.username or "", 
        current_user.full_name or ""
    )
    
    return CheckinResponse(
        success=success,
        current_credits=current_credits,
        error_msg=error_msg,
        total_days=total_days,
        reward=reward
    )

@router.post("/history/{task_id}/favorite")
async def favorite_history(
    task_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(History).where(History.task_id == task_id, History.user_id == current_user.id)
    result = await db.execute(stmt)
    history = result.scalar_one_or_none()
    
    if not history:
        raise HTTPException(status_code=404, detail="未找到原任务详情")
    
    if not history.output_file:
        raise HTTPException(status_code=400, detail="该任务没有生成文件")

    if not history.is_favorited:
        history.is_favorited = True
        await db.commit()
        
        # 触发 R2 上传
        from src.core.gallery_core import async_copy_to_r2_background
        
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

        background_tasks.add_task(async_copy_to_r2_background, bucket_name, object_name, r2_object_name)
        
    return {"status": "success", "message": "收藏成功"}

@router.delete("/history/{task_id}/favorite")
async def unfavorite_history(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(History).where(History.task_id == task_id, History.user_id == current_user.id)
    result = await db.execute(stmt)
    history = result.scalar_one_or_none()
    
    if not history:
        raise HTTPException(status_code=404, detail="未找到原任务详情")

    if history.is_favorited:
        history.is_favorited = False
        await db.commit()
        
    return {"status": "success", "message": "已取消收藏"}

@router.delete("/history/{history_id}")
async def delete_history(
    history_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import update
    from src.database.models import GalleryPost
    
    stmt = select(History).where(History.id == history_id, History.user_id == current_user.id)
    result = await db.execute(stmt)
    history = result.scalar_one_or_none()
    
    if not history:
        raise HTTPException(status_code=404, detail="未找到对应的记录")
        
    if not history.is_visible:
        return {"status": "success", "message": "记录已删除"}
        
    # Soft delete in history
    history.is_visible = False
    
    # If it was public and has a task_id, also hide the gallery post
    if history.is_public and history.task_id:
        upd_stmt = (
            update(GalleryPost)
            .where(
                GalleryPost.task_id == history.task_id,
                GalleryPost.user_id == current_user.id,
                GalleryPost.is_active == True
            )
            .values(is_active=False)
        )
        upd_result = await db.execute(upd_stmt)
        
        if upd_result.rowcount > 0:
            current_user.total_contributions = max(current_user.total_contributions - 1, 0)
            
    await db.commit()
    return {"status": "success", "message": "记录已删除"}

@router.get("/my-favorites", response_model=PaginatedGalleryResponse)
async def get_my_favorites(
    page: int = 1,
    size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import desc
    from src.web_api.routers.gallery import get_media_url
    
    # Query current user's favorite histories
    stmt = select(History).where(
        History.user_id == current_user.id,
        History.is_favorited == True,
        History.is_visible.is_not(False)
    ).order_by(desc(History.created_at))
    
    # Get total
    from sqlalchemy import func
    total_query = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_query)).scalar()
    
    # Paginate
    offset = (page - 1) * size
    stmt = stmt.offset(offset).limit(size)
    result = await db.execute(stmt)
    histories = result.scalars().all()
    
    response_items = []
    for history in histories:
        media_url = get_media_url(history.output_file)
        
        # media_type mapping
        media_type = 'image'
        if history.type and 'video' in history.type.lower():
            media_type = 'video'
            
        # extract tags from prompt
        tags = []
        if history.prompt:
            match = re.search(r"\[模型:\s*(.*?)\]", history.prompt)
            if match:
                tags.append(f"#{match.group(1).strip()}")
                
        response_items.append(GalleryPostResponse(
            id=history.id,
            task_id=history.task_id,
            media_type=media_type,
            width=None,
            height=None,
            duration=None,
            tags=tags,
            likes_count=0,
            dislikes_count=0,
            applied_count=0,
            thumbnail_url=media_url,
            media_url=media_url,
            created_at=history.created_at,
            is_active=True,
            prompt=history.prompt,
            task_type=history.type,
            has_liked=False,
            has_disliked=False
        ))
        
    pages = (total + size - 1) // size
    return PaginatedGalleryResponse(
        items=response_items,
        total=total,
        page=page,
        size=size,
        pages=pages
    )

@router.get("/history/{task_id}/apply-context", response_model=ApplyContextResponse)
async def get_favorite_apply_context(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from src.web_api.routers.gallery import get_media_url
    from src.config_mapping import ALL_LORA_MODELS
    
    stmt = select(History).where(History.task_id == task_id, History.user_id == current_user.id)
    result = await db.execute(stmt)
    history = result.scalar_one_or_none()
    
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
        
        reverse_lora_models = {v: k for k, v in ALL_LORA_MODELS.items()}
        reverse_lora_models["逼真"] = "qwen/YARN_1.0.safetensors"
        reverse_lora_models["菊花+内凹穴"] = "qwen/adjust_pussy_anus.safetensors"
        reverse_lora_models["真实质感"] = "qwen/realistic_texture.safetensors"
        reverse_lora_models["平胸/无毛穴"] = "qwen/flat_chest_hairless.safetensors"
        reverse_lora_models["扶他(阴茎)"] = "qwen/penis.safetensors"
        
        if lora_tag in reverse_lora_models:
            lora_name = reverse_lora_models[lora_tag]
        else:
            lora_name = lora_tag
            
    media_type = 'image'
    if history.type and 'video' in history.type.lower():
        media_type = 'video'
        
    return ApplyContextResponse(
        post_id=history.id,  # mock post_id
        task_id=history.task_id,
        media_type=media_type,
        prompt=prompt,
        lora_name=lora_name,
        input_file=history.input_file,
        input_file_url=input_file_url,
        width=None,
        height=None,
        duration=None,
        task_type=history.type
    )
