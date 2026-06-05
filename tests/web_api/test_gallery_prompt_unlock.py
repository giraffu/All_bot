from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.database.models import GalleryPost, GalleryPromptUnlock, History
from src.web_api.services.gallery_prompt_unlock_service import (
    unlock_gallery_prompt_payload,
)


class _Result:
    def __init__(self, *, scalar=None, single=None, many=None):
        self._scalar = scalar
        self._single = single
        self._many = list(many or [])

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._single

    def scalars(self):
        return self

    def first(self):
        return self._many[0] if self._many else None

    def all(self):
        return list(self._many)


class _Session:
    def __init__(self, results, *, flush_error=None):
        self._results = iter(results)
        self.flush_error = flush_error
        self.added = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, _stmt):
        return next(self._results)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        if self.flush_error is not None:
            raise self.flush_error
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = 77


class _Quota:
    def __init__(self):
        self.transfer_kwargs = None

    async def transfer_credits(self, **kwargs):
        self.transfer_kwargs = kwargs
        return SimpleNamespace(from_user=SimpleNamespace(new_balance=4))


def _post() -> GalleryPost:
    return GalleryPost(
        id=10,
        task_id="task-1",
        user_id=200,
        media_type="image",
        is_active=True,
    )


def _history() -> History:
    return History(
        id=12,
        task_id="task-1",
        user_id=200,
        prompt="full secret prompt",
    )


@pytest.mark.asyncio
async def test_unlock_gallery_prompt_creates_unlock_and_transfers_credit():
    quota = _Quota()
    session = _Session(
        [
            _Result(single=_post()),
            _Result(many=[_history()]),
            _Result(scalar=5),
            _Result(single=None),
        ]
    )

    response = await unlock_gallery_prompt_payload(
        post_id=10,
        current_user=SimpleNamespace(id=123, username="buyer"),
        db=session,
        quota_manager=quota,
    )

    assert response.prompt == "full secret prompt"
    assert response.current_credits == 4
    assert response.already_unlocked is False
    assert isinstance(session.added[0], GalleryPromptUnlock)
    assert session.added[0].user_id == 123
    assert session.added[0].author_id == 200
    assert quota.transfer_kwargs == {
        "from_user_id": 123,
        "to_user_id": 200,
        "amount": 1,
        "from_username": "buyer",
        "debit_task_type": "gallery_prompt_unlock_purchase",
        "credit_task_type": "gallery_prompt_unlock_reward",
        "session": session,
        "extra_info": {
            "post_id": 10,
            "task_id": "task-1",
            "author_id": 200,
            "unlock_id": 77,
            "cost_credits": 1,
        },
    }
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_unlock_gallery_prompt_existing_unlock_is_idempotent():
    session = _Session(
        [
            _Result(single=_post()),
            _Result(many=[_history()]),
            _Result(scalar=5),
            _Result(single=GalleryPromptUnlock(user_id=123, post_id=10, author_id=200)),
        ]
    )
    quota = _Quota()

    response = await unlock_gallery_prompt_payload(
        post_id=10,
        current_user=SimpleNamespace(id=123, username="buyer"),
        db=session,
        quota_manager=quota,
    )

    assert response.prompt == "full secret prompt"
    assert response.current_credits == 5
    assert response.already_unlocked is True
    assert session.added == []
    assert quota.transfer_kwargs is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_unlock_gallery_prompt_unique_conflict_rolls_back_without_transfer():
    session = _Session(
        [
            _Result(single=_post()),
            _Result(many=[_history()]),
            _Result(scalar=5),
            _Result(single=None),
            _Result(scalar=5),
        ],
        flush_error=IntegrityError("insert unlock", {}, Exception("unique")),
    )
    quota = _Quota()

    response = await unlock_gallery_prompt_payload(
        post_id=10,
        current_user=SimpleNamespace(id=123, username="buyer"),
        db=session,
        quota_manager=quota,
    )

    assert response.already_unlocked is True
    assert response.current_credits == 5
    assert quota.transfer_kwargs is None
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
