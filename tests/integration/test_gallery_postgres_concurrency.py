import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.gallery_interactions_core import (
    record_apply_interaction_impl,
    toggle_like_impl,
)
from src.services import gallery_repository


POSTGRES_URL = os.getenv("GALLERY_POSTGRES_TEST_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not POSTGRES_URL,
        reason="GALLERY_POSTGRES_TEST_URL is required for real PostgreSQL concurrency tests",
    ),
]


def _async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


@pytest_asyncio.fixture
async def postgres_gallery():
    schema = f"gallery_p0_{uuid.uuid4().hex}"
    engine = create_async_engine(_async_url(POSTGRES_URL), pool_size=5)
    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        ddl_statements = [
            f"""
                CREATE TABLE "{schema}".gallery_posts (
                    id serial PRIMARY KEY,
                    task_id varchar(64), user_id bigint,
                    media_type varchar(20), width integer, height integer,
                    duration integer, tags text DEFAULT '[]',
                    likes_count integer DEFAULT 0,
                    dislikes_count integer DEFAULT 0,
                    applied_count integer DEFAULT 0,
                    comments_count integer DEFAULT 0,
                    telegram_file_id varchar(255),
                    is_active boolean DEFAULT true,
                    created_at timestamp DEFAULT CURRENT_TIMESTAMP
                )
            """,
            f"""
                CREATE TABLE "{schema}".user_interactions (
                    id serial PRIMARY KEY,
                    user_id bigint, post_id integer,
                    action_type varchar(20),
                    created_at timestamp DEFAULT CURRENT_TIMESTAMP
                )
            """,
            f"""
                CREATE UNIQUE INDEX uq_gallery_posts_task_user
                    ON "{schema}".gallery_posts(task_id, user_id)
            """,
            f"""
                CREATE UNIQUE INDEX uq_user_interactions_reaction
                    ON "{schema}".user_interactions(user_id, post_id)
                    WHERE action_type IN ('like', 'dislike')
            """,
            f"""
                CREATE UNIQUE INDEX uq_user_interactions_apply
                    ON "{schema}".user_interactions(user_id, post_id)
                    WHERE action_type = 'apply'
            """,
        ]
        for ddl in ddl_statements:
            await connection.execute(text(ddl))
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    @asynccontextmanager
    async def session_factory():
        async with maker() as session:
            await session.execute(text(f'SET search_path TO "{schema}"'))
            yield session

    try:
        yield engine, schema, session_factory
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


def _interaction_dependencies(session_factory):
    return SimpleNamespace(
        session_factory=session_factory,
        acquire_gallery_reaction_lock_func=gallery_repository.acquire_gallery_reaction_lock,
        get_gallery_post_by_id_func=gallery_repository.get_gallery_post_by_id,
        get_gallery_reaction_interaction_func=(
            gallery_repository.get_gallery_reaction_interaction
        ),
        remove_gallery_reaction_func=gallery_repository.remove_gallery_reaction,
        decrement_gallery_reaction_counter_func=(
            gallery_repository.decrement_gallery_reaction_counter
        ),
        switch_gallery_reaction_func=gallery_repository.switch_gallery_reaction,
        insert_gallery_reaction_if_absent_func=(
            gallery_repository.insert_gallery_reaction_if_absent
        ),
        increment_gallery_reaction_counter_func=(
            gallery_repository.increment_gallery_reaction_counter
        ),
        insert_gallery_apply_interaction_if_absent_func=(
            gallery_repository.insert_gallery_apply_interaction_if_absent
        ),
        increment_gallery_apply_counter_func=gallery_repository.increment_gallery_apply_counter,
    )


async def _create_post(engine, schema) -> int:
    async with engine.begin() as connection:
        return int(
            (
                await connection.execute(
                    text(
                        f'INSERT INTO "{schema}".gallery_posts(task_id, user_id) '
                        "VALUES ('task-1', 123) RETURNING id"
                    )
                )
            ).scalar_one()
        )


async def _facts(engine, schema, post_id):
    async with engine.connect() as connection:
        reactions = (
            await connection.execute(
                text(
                    f'SELECT action_type FROM "{schema}".user_interactions '
                    "WHERE user_id=123 AND post_id=:post_id "
                    "AND action_type IN ('like', 'dislike')"
                ),
                {"post_id": post_id},
            )
        ).scalars().all()
        applies = int(
            (
                await connection.execute(
                    text(
                        f'SELECT count(*) FROM "{schema}".user_interactions '
                        "WHERE user_id=123 AND post_id=:post_id AND action_type='apply'"
                    ),
                    {"post_id": post_id},
                )
            ).scalar_one()
        )
        counters = (
            await connection.execute(
                text(
                    f'SELECT likes_count, dislikes_count, applied_count '
                    f'FROM "{schema}".gallery_posts WHERE id=:post_id'
                ),
                {"post_id": post_id},
            )
        ).one()
    return reactions, applies, counters


@pytest.mark.asyncio
@pytest.mark.parametrize("actions", [("like", "like"), ("like", "dislike")])
async def test_two_sessions_keep_reaction_fact_and_counters_consistent(
    postgres_gallery,
    actions,
):
    engine, schema, session_factory = postgres_gallery
    post_id = await _create_post(engine, schema)
    dependencies = _interaction_dependencies(session_factory)

    await asyncio.gather(
        *(toggle_like_impl(123, post_id, action, dependencies=dependencies) for action in actions)
    )

    reactions, _applies, counters = await _facts(engine, schema, post_id)
    assert len(reactions) <= 1
    assert counters.likes_count == reactions.count("like")
    assert counters.dislikes_count == reactions.count("dislike")


@pytest.mark.asyncio
async def test_two_sessions_keep_apply_idempotent(postgres_gallery):
    engine, schema, session_factory = postgres_gallery
    post_id = await _create_post(engine, schema)
    dependencies = _interaction_dependencies(session_factory)

    await asyncio.gather(
        *(
            record_apply_interaction_impl(123, post_id, dependencies=dependencies)
            for _ in range(2)
        )
    )

    _reactions, applies, counters = await _facts(engine, schema, post_id)
    assert applies == 1
    assert counters.applied_count == 1


@pytest.mark.asyncio
async def test_two_sessions_create_only_one_gallery_post(
    postgres_gallery,
    monkeypatch,
):
    engine, schema, session_factory = postgres_gallery
    monkeypatch.setattr(
        gallery_repository,
        "enqueue_history_media_restore",
        AsyncMock(),
    )

    async def create_once():
        async with session_factory() as session:
            return await gallery_repository.create_gallery_post_from_history(
                session,
                task_id="task-concurrent",
                user_id=123,
                media_type="image",
                width=512,
                height=512,
                duration=None,
                tags_json="[]",
                history=SimpleNamespace(is_public=False),
                user=SimpleNamespace(total_contributions=0),
            )

    states = await asyncio.gather(create_once(), create_once())
    async with engine.connect() as connection:
        count = int(
            (
                await connection.execute(
                    text(
                        f'SELECT count(*) FROM "{schema}".gallery_posts '
                        "WHERE task_id='task-concurrent' AND user_id=123"
                    )
                )
            ).scalar_one()
        )

    assert sorted(states) == ["created", "duplicate"]
    assert count == 1
