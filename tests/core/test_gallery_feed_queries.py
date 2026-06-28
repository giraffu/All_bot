import pytest

from src.services.gallery_feed_queries import fetch_gallery_feed_page


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


class _FakeSession:
    def __init__(self, results):
        self._results = iter(results)
        self.executed_statements = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        return next(self._results)


@pytest.mark.asyncio
async def test_fetch_gallery_feed_page_applies_vidlora_category_and_sort():
    session = _FakeSession([_ScalarResult(0), _ItemsResult([])])

    posts, total = await fetch_gallery_feed_page(
        session=session,
        page=1,
        size=20,
        media_type=None,
        task_type=None,
        lora_model=None,
        sort_by="likes",
        time_range="all",
        user_id=None,
        category="vidlora",
        is_active=True,
    )

    assert posts == []
    assert total == 0
    list_stmt = session.executed_statements[1]
    compiled = list_stmt.compile()
    sql = str(compiled)
    assert "history.type" in sql.lower()
    assert "gallery_posts.likes_count" in sql.lower()
    assert "video_lora" in compiled.params.values()


@pytest.mark.asyncio
async def test_fetch_gallery_feed_page_faceswap_category_includes_scail2_face_swap_v2():
    session = _FakeSession([_ScalarResult(0), _ItemsResult([])])

    await fetch_gallery_feed_page(
        session=session,
        page=1,
        size=20,
        media_type=None,
        task_type=None,
        lora_model=None,
        sort_by="latest",
        time_range="all",
        user_id=None,
        category="faceswap",
        is_active=True,
    )

    compiled = session.executed_statements[1].compile()
    sql = str(compiled).lower()
    task_types = next(
        value for value in compiled.params.values() if isinstance(value, list)
    )

    assert "history.type" in sql
    assert task_types == ["face_video", "scail2_face_swap_v2"]


@pytest.mark.asyncio
async def test_fetch_gallery_feed_page_uses_media_type_only_without_category_or_task_type():
    session = _FakeSession([_ScalarResult(0), _ItemsResult([])])

    await fetch_gallery_feed_page(
        session=session,
        page=2,
        size=10,
        media_type="video",
        task_type=None,
        lora_model="model-a",
        sort_by="mine",
        time_range="week",
        user_id=321,
        category=None,
        is_active=False,
    )

    list_stmt = session.executed_statements[1]
    compiled = list_stmt.compile()
    sql = str(compiled).lower()

    assert "gallery_posts.media_type" in sql
    assert "gallery_posts.user_id" in sql
    assert "gallery_posts.is_active is false" in sql
    assert "gallery_posts.created_at >=" in sql
    assert "history.type" not in sql
    assert "video" in compiled.params.values()
    assert 321 in compiled.params.values()
    assert '%"#model-a"%' in compiled.params.values()


@pytest.mark.asyncio
async def test_fetch_gallery_feed_page_supports_dashboard_author_and_prompt_filters():
    session = _FakeSession([_ScalarResult(0), _ItemsResult([])])

    await fetch_gallery_feed_page(
        session=session,
        page=1,
        size=20,
        media_type=None,
        task_type=None,
        lora_model=None,
        sort_by="latest",
        time_range="all",
        user_id=None,
        category=None,
        is_active=None,
        username="sk dom",
        prompt_contains="cinematic",
        prompt_max_length=120,
    )

    compiled = session.executed_statements[1].compile()
    sql = str(compiled).lower()
    params = list(compiled.params.values())

    assert "join history" in sql
    assert "join users" in sql
    assert "users.username" in sql
    assert "users.full_name" in sql
    assert "history.prompt" in sql
    assert "length" in sql
    assert "trim" in sql
    assert "%sk dom%" in params
    assert "%cinematic%" in params
    assert 120 in params


@pytest.mark.asyncio
async def test_fetch_gallery_feed_page_supports_edit_group_none_filter():
    session = _FakeSession([_ScalarResult(0), _ItemsResult([])])

    await fetch_gallery_feed_page(
        session=session,
        page=1,
        size=20,
        media_type=None,
        task_type="edit_group",
        lora_model="__none__",
        sort_by="latest",
        time_range="all",
        user_id=None,
        category=None,
        is_active=True,
    )

    compiled = session.executed_statements[1].compile()
    sql = str(compiled).lower()
    task_types = next(
        value for value in compiled.params.values() if isinstance(value, list)
    )

    assert "history.type" in sql
    assert task_types == ["edit", "quick_image", "img2img_lora"]
    assert '%"#qwen/YARN_1.0.safetensors"%' in compiled.params.values()
    assert '%"#__none__"%' not in compiled.params.values()


@pytest.mark.asyncio
async def test_fetch_gallery_feed_page_supports_free_edit_v2_group_filter():
    session = _FakeSession([_ScalarResult(0), _ItemsResult([])])

    await fetch_gallery_feed_page(
        session=session,
        page=1,
        size=20,
        media_type=None,
        task_type="free_edit_v2_group",
        lora_model=None,
        sort_by="latest",
        time_range="all",
        user_id=None,
        category=None,
        is_active=True,
    )

    compiled = session.executed_statements[1].compile()
    sql = str(compiled).lower()
    task_types = next(
        value for value in compiled.params.values() if isinstance(value, list)
    )

    assert "history.type" in sql
    assert task_types == [
        "pornmaster_flux2_single_edit",
        "pornmaster_flux2_multi_edit",
    ]


@pytest.mark.asyncio
async def test_fetch_gallery_feed_page_merges_legacy_long_action_transfer_filter():
    session = _FakeSession([_ScalarResult(0), _ItemsResult([])])

    await fetch_gallery_feed_page(
        session=session,
        page=1,
        size=20,
        media_type=None,
        task_type="scail2_action_transfer",
        lora_model=None,
        sort_by="latest",
        time_range="all",
        user_id=None,
        category=None,
        is_active=True,
    )

    compiled = session.executed_statements[1].compile()
    task_types = next(
        value for value in compiled.params.values() if isinstance(value, list)
    )

    assert task_types == [
        "scail2_action_transfer",
        "scail2_action_transfer_long",
    ]


@pytest.mark.asyncio
async def test_fetch_gallery_feed_page_supports_img2video_group_model_filter():
    session = _FakeSession([_ScalarResult(0), _ItemsResult([])])

    await fetch_gallery_feed_page(
        session=session,
        page=1,
        size=20,
        media_type=None,
        task_type="img2video_group",
        lora_model="motion-a",
        sort_by="latest",
        time_range="all",
        user_id=None,
        category=None,
        is_active=True,
    )

    compiled = session.executed_statements[1].compile()
    sql = str(compiled).lower()
    task_types = next(
        value for value in compiled.params.values() if isinstance(value, list)
    )

    assert "history.type" in sql
    assert task_types == ["custom_video", "video_lora"]
    assert '%"#motion-a"%' in compiled.params.values()
