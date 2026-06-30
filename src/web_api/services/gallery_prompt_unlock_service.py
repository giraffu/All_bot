from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.database.models import GalleryPost, GalleryPromptUnlock, History, User
from src.quota import QuotaManager
from src.web_api.schemas.gallery_schema import PromptUnlockResponse
from src.web_api.services.gallery_response_builder import PROMPT_UNLOCK_PRICE_CREDITS


async def _fetch_current_credits(*, db, user_id: int) -> int:
    result = await db.execute(select(User.credits).where(User.id == user_id))
    return int(result.scalar() or 0)


async def _fetch_prompt_unlock_entities(*, db, post_id: int):
    post = (
        await db.execute(select(GalleryPost).where(GalleryPost.id == post_id))
    ).scalar_one_or_none()
    if not post or post.is_active is False:
        raise HTTPException(status_code=404, detail="帖子不存在或已失效")

    history = (
        await db.execute(select(History).where(History.task_id == post.task_id))
    ).scalars().first()
    if not history:
        raise HTTPException(status_code=404, detail="未找到原任务详情")

    prompt = history.prompt.strip() if isinstance(history.prompt, str) else ""
    if not prompt:
        raise HTTPException(status_code=400, detail="此投稿没有提示词")
    if not post.user_id:
        raise HTTPException(status_code=400, detail="作者信息缺失，暂时无法解锁")

    return post, prompt


async def _fetch_existing_unlock(*, db, user_id: int, post_id: int):
    return (
        await db.execute(
            select(GalleryPromptUnlock).where(
                GalleryPromptUnlock.user_id == user_id,
                GalleryPromptUnlock.post_id == post_id,
            )
        )
    ).scalar_one_or_none()


async def _is_low_trust_free_tier_user(user_id: int) -> bool:
    from src.services.permission_service import permission_service

    return await permission_service.is_low_trust_free_tier_user(user_id)


async def unlock_gallery_prompt_payload(
    *,
    post_id: int,
    current_user,
    db,
    quota_manager: QuotaManager | None = None,
    is_low_trust_free_tier_user_func=None,
) -> PromptUnlockResponse:
    post, prompt = await _fetch_prompt_unlock_entities(db=db, post_id=post_id)
    current_credits = await _fetch_current_credits(db=db, user_id=current_user.id)

    if post.user_id == current_user.id:
        return PromptUnlockResponse(
            post_id=post.id,
            prompt=prompt,
            current_credits=current_credits,
            already_unlocked=True,
        )

    existing_unlock = await _fetch_existing_unlock(
        db=db,
        user_id=current_user.id,
        post_id=post.id,
    )
    if existing_unlock:
        return PromptUnlockResponse(
            post_id=post.id,
            prompt=prompt,
            current_credits=current_credits,
            already_unlocked=True,
        )

    is_low_trust_free_tier_user_func = (
        is_low_trust_free_tier_user_func or _is_low_trust_free_tier_user
    )
    if await is_low_trust_free_tier_user_func(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="当前账号暂不可解锁提示词，请完成一次充值后再试",
        )

    unlock = GalleryPromptUnlock(
        user_id=current_user.id,
        post_id=post.id,
        author_id=post.user_id,
        cost_credits=PROMPT_UNLOCK_PRICE_CREDITS,
    )
    db.add(unlock)
    resolved_post_id = post.id

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        current_credits = await _fetch_current_credits(db=db, user_id=current_user.id)
        return PromptUnlockResponse(
            post_id=resolved_post_id,
            prompt=prompt,
            current_credits=current_credits,
            already_unlocked=True,
        )

    transfer_extra = {
        "post_id": post.id,
        "task_id": post.task_id,
        "author_id": post.user_id,
        "unlock_id": unlock.id,
        "cost_credits": PROMPT_UNLOCK_PRICE_CREDITS,
    }
    quota_manager = quota_manager or QuotaManager()
    try:
        transfer_result = await quota_manager.transfer_credits(
            from_user_id=current_user.id,
            to_user_id=post.user_id,
            amount=PROMPT_UNLOCK_PRICE_CREDITS,
            from_username=getattr(current_user, "username", None),
            debit_task_type="gallery_prompt_unlock_purchase",
            credit_task_type="gallery_prompt_unlock_reward",
            session=db,
            extra_info=transfer_extra,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return PromptUnlockResponse(
        post_id=post.id,
        prompt=prompt,
        current_credits=transfer_result.from_user.new_balance,
        already_unlocked=False,
    )
