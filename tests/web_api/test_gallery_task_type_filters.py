import pytest

from src.web_api.routers import users as users_router
from src.web_api.schemas.gallery_schema import GalleryPostResponse
from src.web_api.services.gallery_service_queries import (
    get_gallery_posts_payload,
    get_my_favorite_posts_payload,
    get_my_gallery_posts_payload,
)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _ItemsResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _AsyncSessionContext:
    def __init__(self, results):
        self._results = iter(results)
        self.executed_statements = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        return next(self._results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DbSession:
    def __init__(self, results):
        self._results = iter(results)
        self.executed_statements = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        return next(self._results)


class _NoopSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _statement_contains_task_type_filter(stmt, expected_task_type: str) -> bool:
    compiled = stmt.compile()
    sql = str(compiled)
    return "history.type" in sql.lower() and expected_task_type in compiled.params.values()


@pytest.mark.asyncio
async def test_get_my_gallery_posts_applies_task_type_filter():
    session = _AsyncSessionContext([
        _ScalarResult(0),
        _ItemsResult([]),
    ])

    response = await get_my_gallery_posts_payload(
        page=1,
        size=20,
        task_type="edit",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.total == 0
    assert any(
        _statement_contains_task_type_filter(stmt, "edit")
        for stmt in session.executed_statements
    )


@pytest.mark.asyncio
async def test_get_my_favorite_posts_applies_task_type_filter():
    session = _AsyncSessionContext([
        _ScalarResult(0),
        _ItemsResult([]),
    ])

    response = await get_my_favorite_posts_payload(
        page=1,
        size=20,
        filter_type="apply",
        task_type="custom_video",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.total == 0
    assert any(
        _statement_contains_task_type_filter(stmt, "custom_video")
        for stmt in session.executed_statements
    )


@pytest.mark.asyncio
async def test_get_my_favorites_applies_task_type_filter():
    db = _DbSession([
        _ScalarResult(0),
        _ItemsResult([]),
    ])

    response = await users_router.get_my_favorites(
        page=1,
        size=20,
        task_type="img2img_lora",
        current_user=type("User", (), {"id": 123})(),
        db=db,
    )

    assert response.total == 0
    assert any(
        _statement_contains_task_type_filter(stmt, "img2img_lora")
        for stmt in db.executed_statements
    )


@pytest.mark.asyncio
async def test_get_gallery_posts_normalizes_all_filters_and_builds_response():
    fetch_calls = {}
    build_calls = {}
    db = _NoopSession()
    current_user = type("User", (), {"id": 123})()

    async def fake_get_gallery_feed(**kwargs):
        fetch_calls.update(kwargs)
        return ["post-1"], 21

    async def fake_build_post_responses(*, session, posts, current_user):
        build_calls["session"] = session
        build_calls["posts"] = posts
        build_calls["user"] = current_user
        return [
            GalleryPostResponse(
                id=1,
                task_id="task-1",
                media_type="image",
                width=None,
                height=None,
                duration=None,
                tags=[],
                likes_count=0,
                dislikes_count=0,
                applied_count=0,
                comments_count=0,
                thumbnail_url="thumb",
                media_url="media",
                created_at="2026-05-22T00:00:00",
                is_active=True,
                has_liked=False,
                has_disliked=False,
            )
        ]

    response = await get_gallery_posts_payload(
        page=2,
        size=10,
        media_type="all",
        task_type="all",
        lora_model="lora-a",
        sort_by="likes",
        time_range="week",
        current_user=current_user,
        db=db,
        fetch_gallery_feed=fake_get_gallery_feed,
        build_post_responses_fn=fake_build_post_responses,
    )

    assert len(response.items) == 1
    assert response.items[0].task_id == "task-1"
    assert response.total == 21
    assert response.pages == 3
    assert fetch_calls == {
        "page": 2,
        "size": 10,
        "media_type": None,
        "task_type": None,
        "lora_model": "lora-a",
        "sort_by": "likes",
        "time_range": "week",
        "user_id": 123,
    }
    assert build_calls == {
        "session": db,
        "posts": ["post-1"],
        "user": current_user,
    }
