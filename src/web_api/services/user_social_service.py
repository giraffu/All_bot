from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.database.models import GalleryPost, History, User, UserFollow
from src.web_api.schemas.user_social_schema import (
    FollowActionResponse,
    FollowingListResponse,
    PublicUserProfileResponse,
    PublicUserSummary,
)
from src.web_api.services.gallery_response_builder import build_gallery_post_responses


def _resolve_author_name(user: User) -> str:
    return user.full_name or user.username or f"User {user.id}"


def _public_post_count_subquery():
    return (
        select(func.count(func.distinct(GalleryPost.id)))
        .select_from(GalleryPost)
        .outerjoin(History, GalleryPost.task_id == History.task_id)
        .where(
            GalleryPost.user_id == User.id,
            GalleryPost.is_active.is_(True),
            History.is_visible.is_not(False),
        )
        .correlate(User)
        .scalar_subquery()
    )


def _followers_count_subquery():
    return (
        select(func.count())
        .select_from(UserFollow)
        .where(UserFollow.followee_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )


def _following_count_subquery():
    return (
        select(func.count())
        .select_from(UserFollow)
        .where(UserFollow.follower_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )


async def _is_following(*, db, follower_id: int, followee_id: int) -> bool:
    if follower_id == followee_id:
        return False
    result = await db.execute(
        select(UserFollow.id).where(
            UserFollow.follower_id == follower_id,
            UserFollow.followee_id == followee_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def _fetch_public_recent_posts(*, db, user_id: int, limit: int):
    query = (
        select(GalleryPost)
        .outerjoin(History, GalleryPost.task_id == History.task_id)
        .where(
            GalleryPost.user_id == user_id,
            GalleryPost.is_active.is_(True),
            History.is_visible.is_not(False),
        )
        .distinct()
        .order_by(GalleryPost.id.desc())
        .limit(limit)
    )
    return (await db.execute(query)).scalars().all()


def _build_public_user_summary(
    *,
    user: User,
    public_posts_count: int,
    followers_count: int,
    following_count: int,
    is_following: bool,
    current_user_id: int,
) -> PublicUserSummary:
    return PublicUserSummary(
        id=user.id,
        author_name=_resolve_author_name(user),
        username=user.username,
        user_group=user.user_group or "凡人",
        current_identity=user.current_identity or "外门弟子",
        checkin_count=user.checkin_count or 0,
        total_public_posts=public_posts_count or 0,
        followers_count=followers_count or 0,
        following_count=following_count or 0,
        is_following=is_following,
        is_self=user.id == current_user_id,
    )


async def follow_user_payload(
    *,
    target_user_id: int,
    current_user,
    db,
) -> FollowActionResponse:
    if target_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能关注自己")

    target_user = await db.get(User, target_user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="目标用户不存在")

    existing_follow = await db.execute(
        select(UserFollow).where(
            UserFollow.follower_id == current_user.id,
            UserFollow.followee_id == target_user_id,
        )
    )
    if existing_follow.scalar_one_or_none():
        return FollowActionResponse(success=True, is_following=True)

    db.add(UserFollow(follower_id=current_user.id, followee_id=target_user_id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return FollowActionResponse(success=True, is_following=True)

    return FollowActionResponse(success=True, is_following=True)


async def unfollow_user_payload(
    *,
    target_user_id: int,
    current_user,
    db,
) -> FollowActionResponse:
    follow_link = (
        await db.execute(
            select(UserFollow).where(
                UserFollow.follower_id == current_user.id,
                UserFollow.followee_id == target_user_id,
            )
        )
    ).scalar_one_or_none()

    if follow_link:
        await db.delete(follow_link)
        await db.commit()

    return FollowActionResponse(success=True, is_following=False)


async def get_my_following_payload(
    *,
    current_user,
    db,
) -> FollowingListResponse:
    public_posts_count = _public_post_count_subquery()
    followers_count = _followers_count_subquery()
    following_count = _following_count_subquery()

    result = await db.execute(
        select(
            User,
            public_posts_count.label("public_posts_count"),
            followers_count.label("followers_count"),
            following_count.label("following_count"),
        )
        .join(UserFollow, User.id == UserFollow.followee_id)
        .where(UserFollow.follower_id == current_user.id)
        .order_by(UserFollow.created_at.desc(), User.id.desc())
    )
    rows = result.all()

    items = [
        _build_public_user_summary(
            user=user,
            public_posts_count=public_posts_count_value or 0,
            followers_count=followers_count_value or 0,
            following_count=following_count_value or 0,
            is_following=True,
            current_user_id=current_user.id,
        )
        for user, public_posts_count_value, followers_count_value, following_count_value in rows
    ]
    return FollowingListResponse(items=items, total=len(items))


async def get_public_user_profile_payload(
    *,
    target_user_id: int,
    current_user,
    db,
    recent_posts_limit: int = 12,
) -> PublicUserProfileResponse:
    public_posts_count = _public_post_count_subquery()
    followers_count = _followers_count_subquery()
    following_count = _following_count_subquery()

    row = (
        await db.execute(
            select(
                User,
                public_posts_count.label("public_posts_count"),
                followers_count.label("followers_count"),
                following_count.label("following_count"),
            ).where(User.id == target_user_id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")

    target_user, public_posts_count_value, followers_count_value, following_count_value = row
    is_following = await _is_following(
        db=db,
        follower_id=current_user.id,
        followee_id=target_user.id,
    )

    recent_posts = await _fetch_public_recent_posts(
        db=db,
        user_id=target_user.id,
        limit=recent_posts_limit,
    )
    recent_post_responses = await build_gallery_post_responses(
        session=db,
        posts=recent_posts,
        current_user=current_user,
    )

    return PublicUserProfileResponse(
        user=_build_public_user_summary(
            user=target_user,
            public_posts_count=public_posts_count_value or 0,
            followers_count=followers_count_value or 0,
            following_count=following_count_value or 0,
            is_following=is_following,
            current_user_id=current_user.id,
        ),
        recent_posts=recent_post_responses,
    )
