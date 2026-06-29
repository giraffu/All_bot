from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.models import GalleryPost, History, User, UserFollow
from src.web_api.schemas.gallery_schema import GalleryPostResponse
from src.web_api.services.user_social_service import (
    get_my_followers_payload,
    get_public_user_profile_payload,
)


async def _create_social_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(UserFollow.__table__.create)
        await conn.run_sync(History.__table__.create)
        await conn.run_sync(GalleryPost.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory()


async def _build_stub_gallery_responses(*, session, posts, current_user):
    return [
        GalleryPostResponse(
            id=post.id,
            task_id=post.task_id,
            media_type=post.media_type,
            width=post.width,
            height=post.height,
            duration=post.duration,
            tags=[],
            likes_count=post.likes_count or 0,
            dislikes_count=post.dislikes_count or 0,
            applied_count=post.applied_count or 0,
            comments_count=post.comments_count or 0,
            thumbnail_url=f"thumb-{post.task_id}",
            media_url=f"media-{post.task_id}",
            created_at=post.created_at,
            is_active=post.is_active,
        )
        for post in posts
    ]


@pytest.mark.asyncio
async def test_public_user_profile_returns_paginated_public_posts_only():
    engine, session = await _create_social_session()
    now = datetime(2026, 6, 29, 12, 0, 0)
    try:
        viewer = User(id=1, username="viewer", full_name="Viewer")
        author = User(id=2, username="author", full_name="Author")
        session.add_all([viewer, author])

        for index in range(1, 20):
            task_id = f"visible-{index:02d}"
            session.add(
                GalleryPost(
                    id=index,
                    task_id=task_id,
                    user_id=author.id,
                    media_type="image",
                    is_active=True,
                    created_at=now + timedelta(minutes=index),
                )
            )
            session.add(
                History(
                    id=index,
                    task_id=task_id,
                    user_id=author.id,
                    is_visible=True,
                    is_public=True,
                    created_at=now + timedelta(minutes=index),
                )
            )

        session.add_all(
            [
                GalleryPost(
                    id=100,
                    task_id="hidden-history",
                    user_id=author.id,
                    media_type="image",
                    is_active=True,
                    created_at=now,
                ),
                History(
                    id=100,
                    task_id="hidden-history",
                    user_id=author.id,
                    is_visible=False,
                    is_public=True,
                    created_at=now,
                ),
                GalleryPost(
                    id=101,
                    task_id="inactive-post",
                    user_id=author.id,
                    media_type="image",
                    is_active=False,
                    created_at=now,
                ),
                History(
                    id=101,
                    task_id="inactive-post",
                    user_id=author.id,
                    is_visible=True,
                    is_public=True,
                    created_at=now,
                ),
            ]
        )
        await session.commit()

        first_page = await get_public_user_profile_payload(
            target_user_id=author.id,
            current_user=viewer,
            db=session,
            page=1,
            size=12,
            build_post_responses_fn=_build_stub_gallery_responses,
        )
        second_page = await get_public_user_profile_payload(
            target_user_id=author.id,
            current_user=viewer,
            db=session,
            page=2,
            size=12,
            build_post_responses_fn=_build_stub_gallery_responses,
        )

        assert first_page.user.total_public_posts == 19
        assert first_page.posts.total == 19
        assert first_page.posts.pages == 2
        assert [post.task_id for post in first_page.posts.items] == [
            f"visible-{index:02d}" for index in range(19, 7, -1)
        ]
        assert first_page.recent_posts == first_page.posts.items
        assert [post.task_id for post in second_page.posts.items] == [
            f"visible-{index:02d}" for index in range(7, 0, -1)
        ]
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_my_followers_returns_followers_with_mutual_follow_state():
    engine, session = await _create_social_session()
    now = datetime(2026, 6, 29, 12, 0, 0)
    try:
        me = User(id=1, username="me", full_name="Me")
        follower = User(id=2, username="fan-one", full_name="Fan One")
        mutual_follower = User(id=3, username="fan-two", full_name="Fan Two")
        following_only = User(id=4, username="only-followed", full_name="Only Followed")
        session.add_all([me, follower, mutual_follower, following_only])
        session.add_all(
            [
                UserFollow(
                    follower_id=follower.id,
                    followee_id=me.id,
                    created_at=now,
                ),
                UserFollow(
                    follower_id=mutual_follower.id,
                    followee_id=me.id,
                    created_at=now + timedelta(minutes=1),
                ),
                UserFollow(
                    follower_id=me.id,
                    followee_id=mutual_follower.id,
                    created_at=now + timedelta(minutes=2),
                ),
                UserFollow(
                    follower_id=me.id,
                    followee_id=following_only.id,
                    created_at=now + timedelta(minutes=3),
                ),
            ]
        )
        await session.commit()

        response = await get_my_followers_payload(current_user=me, db=session)

        assert response.total == 2
        assert [item.id for item in response.items] == [mutual_follower.id, follower.id]
        assert {item.id: item.is_following for item in response.items} == {
            follower.id: False,
            mutual_follower.id: True,
        }
        assert following_only.id not in {item.id for item in response.items}
    finally:
        await session.close()
        await engine.dispose()
