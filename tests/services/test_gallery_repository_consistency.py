from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from src.services import gallery_repository


class _InsertResult:
    def __init__(self, value):
        self.value = value
        self.rowcount = 1 if value is not None else 0

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, *, insert_result=1, postgresql_bind=False):
        self.insert_result = insert_result
        self.statements = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self._postgresql_bind = postgresql_bind

    def get_bind(self):
        dialect_name = "postgresql" if self._postgresql_bind else "sqlite"
        return SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))

    async def execute(self, statement, params=None):
        self.statements.append((statement, params))
        return _InsertResult(self.insert_result)


@pytest.mark.asyncio
async def test_gallery_post_insert_has_explicit_conflict_target_and_returning(
    monkeypatch,
):
    session = _Session(insert_result=1)
    history = SimpleNamespace(is_public=False)
    user = SimpleNamespace(total_contributions=2)
    enqueue_restore = AsyncMock()
    monkeypatch.setattr(
        gallery_repository,
        "enqueue_history_media_restore",
        enqueue_restore,
    )

    state = await gallery_repository.create_gallery_post_from_history(
        session,
        task_id="task-1",
        user_id=123,
        media_type="image",
        width=512,
        height=512,
        duration=None,
        tags_json="[]",
        history=history,
        user=user,
    )

    sql = str(
        session.statements[0][0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert "on conflict (task_id, user_id) do nothing" in sql
    assert "returning gallery_posts.id" in sql
    assert state == "created"
    assert user.total_contributions == 3
    assert history.is_public is True
    enqueue_restore.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_gallery_post_conflict_has_no_contribution_or_media_side_effect(
    monkeypatch,
):
    session = _Session(insert_result=None)
    history = SimpleNamespace(is_public=False)
    user = SimpleNamespace(total_contributions=2)
    enqueue_restore = AsyncMock()
    monkeypatch.setattr(
        gallery_repository,
        "enqueue_history_media_restore",
        enqueue_restore,
    )

    state = await gallery_repository.create_gallery_post_from_history(
        session,
        task_id="task-1",
        user_id=123,
        media_type="image",
        width=None,
        height=None,
        duration=None,
        tags_json="[]",
        history=history,
        user=user,
    )

    assert state == "duplicate"
    assert user.total_contributions == 2
    assert history.is_public is False
    enqueue_restore.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_reaction_lock_uses_postgresql_transaction_advisory_lock():
    session = _Session(postgresql_bind=True)

    await gallery_repository.acquire_gallery_reaction_lock(
        session,
        user_id=123,
        post_id=456,
    )

    statement, params = session.statements[0]
    assert "pg_advisory_xact_lock" in str(statement)
    assert params == {"reaction_owner": "gallery-reaction:123:456"}


@pytest.mark.asyncio
async def test_interaction_inserts_target_their_partial_unique_indexes():
    reaction_session = _Session()
    apply_session = _Session()

    await gallery_repository.insert_gallery_reaction_if_absent(
        reaction_session,
        user_id=123,
        post_id=456,
        action="like",
    )
    await gallery_repository.insert_gallery_apply_interaction_if_absent(
        apply_session,
        user_id=123,
        post_id=456,
    )

    reaction_sql = str(
        reaction_session.statements[0][0].compile(dialect=postgresql.dialect())
    ).lower()
    apply_sql = str(
        apply_session.statements[0][0].compile(dialect=postgresql.dialect())
    ).lower()
    assert "on conflict (user_id, post_id)" in reaction_sql
    assert "action_type in" in reaction_sql
    assert "on conflict (user_id, post_id)" in apply_sql
    assert "action_type =" in apply_sql
