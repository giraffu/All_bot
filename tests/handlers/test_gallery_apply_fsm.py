from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.constants import MODE_LTX_VIDEO
from src.database.models import GalleryPost, History
from src.handlers.fsm import gallery_apply_fsm


class _FakeResult:
    def __init__(self, *, single=None, many=None):
        self._single = single
        if many is None:
            self._many = [] if single is None else [single]
        else:
            self._many = list(many)

    def scalar_one_or_none(self):
        return self._single

    def scalars(self):
        return self

    def first(self):
        return self._many[0] if self._many else None


class _FakeSession:
    def __init__(self, results):
        self._results = iter(results)

    async def execute(self, _stmt):
        return next(self._results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _build_update(post_id: int):
    query = SimpleNamespace(
        data=f"gallery_apply_{post_id}",
        from_user=SimpleNamespace(id=1001),
        message=SimpleNamespace(chat_id=2001),
        answer=AsyncMock(),
    )
    return SimpleNamespace(callback_query=query)


def _build_context():
    return SimpleNamespace(
        user_data={},
        t=lambda text: text,
    )


@pytest.mark.asyncio
async def test_start_gallery_apply_prefers_requested_duration_over_legacy_prefix(
    monkeypatch,
):
    post = GalleryPost(
        id=9,
        task_id="task-1",
        media_type="video",
        width=1344,
        height=768,
        duration=1,
    )
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type=MODE_LTX_VIDEO,
        prompt="[1344x768|5s] wide cinematic dolly shot",
        input_file="history/template.png",
        requested_duration=20,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.core.user_core.get_or_create_user_by_telegram", AsyncMock(return_value=(SimpleNamespace(id=123), None)))
    monkeypatch.setattr("src.database.core.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(gallery_apply_fsm, "is_maintenance_mode", lambda: False)
    monkeypatch.setattr(gallery_apply_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        gallery_apply_fsm.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )

    update = _build_update(9)
    context = _build_context()

    state = await gallery_apply_fsm.start_gallery_apply(update, context)

    assert state == gallery_apply_fsm.WAIT_REFERENCE_IMAGE
    assert context.user_data["gallery_apply_data"]["res_str"] == "1344x768"
    assert context.user_data["gallery_apply_data"]["dur_str"] == "20s"
    assert context.user_data["gallery_apply_data"]["prompt"] == "wide cinematic dolly shot"
    reply_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_gallery_apply_falls_back_to_legacy_prefix_when_requested_duration_missing(
    monkeypatch,
):
    post = GalleryPost(
        id=9,
        task_id="task-1",
        media_type="video",
        width=1344,
        height=768,
        duration=1,
    )
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type=MODE_LTX_VIDEO,
        prompt="[1344x768|20s] wide cinematic dolly shot",
        input_file="history/template.png",
        requested_duration=None,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )
    reply_mock = AsyncMock()

    monkeypatch.setattr("src.core.user_core.get_or_create_user_by_telegram", AsyncMock(return_value=(SimpleNamespace(id=123), None)))
    monkeypatch.setattr("src.database.core.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(gallery_apply_fsm, "is_maintenance_mode", lambda: False)
    monkeypatch.setattr(gallery_apply_fsm, "robust_reply_text", reply_mock)
    monkeypatch.setattr(
        gallery_apply_fsm.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )

    update = _build_update(9)
    context = _build_context()

    state = await gallery_apply_fsm.start_gallery_apply(update, context)

    assert state == gallery_apply_fsm.WAIT_REFERENCE_IMAGE
    assert context.user_data["gallery_apply_data"]["dur_str"] == "20s"
    assert context.user_data["gallery_apply_data"]["prompt"] == "wide cinematic dolly shot"
    reply_mock.assert_awaited_once()
