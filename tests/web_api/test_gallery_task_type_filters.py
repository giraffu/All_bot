import pytest

from src.web_api.routers import gallery as gallery_router
from src.web_api.routers import users as users_router


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


def _statement_contains_task_type_filter(stmt, expected_task_type: str) -> bool:
    compiled = stmt.compile()
    sql = str(compiled)
    return "history.type" in sql.lower() and expected_task_type in compiled.params.values()


@pytest.mark.asyncio
async def test_get_my_gallery_posts_applies_task_type_filter(monkeypatch):
    session = _AsyncSessionContext([
        _ScalarResult(0),
        _ItemsResult([]),
    ])
    monkeypatch.setattr(gallery_router, "AsyncSessionLocal", lambda: session)

    response = await gallery_router.get_my_gallery_posts(
        page=1,
        size=20,
        task_type="edit",
        current_user=type("User", (), {"id": 123})(),
    )

    assert response.total == 0
    assert any(
        _statement_contains_task_type_filter(stmt, "edit")
        for stmt in session.executed_statements
    )


@pytest.mark.asyncio
async def test_get_my_favorite_posts_applies_task_type_filter(monkeypatch):
    session = _AsyncSessionContext([
        _ScalarResult(0),
        _ItemsResult([]),
    ])
    monkeypatch.setattr(gallery_router, "AsyncSessionLocal", lambda: session)

    response = await gallery_router.get_my_favorite_posts(
        page=1,
        size=20,
        filter_type="apply",
        task_type="custom_video",
        current_user=type("User", (), {"id": 123})(),
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
