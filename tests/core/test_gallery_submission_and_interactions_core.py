from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.gallery_core_errors import DuplicateInteractionError
from src.core.gallery_interactions_core import (
    record_apply_interaction_impl,
    toggle_like_impl,
)
from src.core.gallery_submission_core import (
    ALLOWED_WEB_SUBMIT_TYPES,
    _build_gallery_tags,
    _validate_gallery_submit_history,
    process_submit_to_gallery_result_impl,
)


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def first(self):
        return self._value

    def scalars(self):
        return self

    def scalar_one_or_none(self):
        return self._value


class _FakeExecuteResult:
    def __init__(self, *, rowcount=0, row=None):
        self.rowcount = rowcount
        self._row = row

    def fetchone(self):
        return self._row


class _FakeSession:
    def __init__(self, execute_results, *, post=None):
        self.execute_results = list(execute_results)
        self.post = post
        self.added = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.flush = AsyncMock()

    async def execute(self, _stmt):
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        result = self.execute_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def get(self, _model, _pk):
        return self.post

    def add(self, obj):
        self.added.append(obj)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _GallerySubmitOutcome:
    def __init__(self, *, payload, side_effects):
        self.payload = payload
        self.side_effects = side_effects


@pytest.mark.asyncio
async def test_process_submit_to_gallery_result_impl_reactivates_existing_post():
    existing_post = SimpleNamespace(user_id=123, is_active=False)
    history = SimpleNamespace(id=11, is_public=False)
    user = SimpleNamespace(total_contributions=2)
    session = _FakeSession(
        [
            _FakeScalarResult(existing_post),
            _FakeScalarResult(history),
            _FakeScalarResult(user),
            _FakeScalarResult(None),
        ]
    )

    outcome = await process_submit_to_gallery_result_impl(
        gallery_submit_outcome_cls=_GallerySubmitOutcome,
        user_id=123,
        task_id="task-1",
        session_factory=lambda: session,
        check_gallery_submit_limit_func=AsyncMock(return_value=True),
        increment_gallery_submit_func=AsyncMock(),
    )

    assert outcome.payload["message"] == "已为您重新上架该作品！"
    assert existing_post.is_active is True
    assert history.is_public is True
    assert user.total_contributions == 3
    session.commit.assert_awaited_once()


def test_build_gallery_tags_keeps_mode_and_omits_unknown_internal_model_name():
    history = SimpleNamespace(
        type="i2i_pro",
        prompt="[模型: Foo Bar] A prompt body",
    )

    assert _build_gallery_tags(history) == ["#task.mode_i2i_pro"]


def test_build_gallery_tags_hides_unknown_internal_task_type():
    history = SimpleNamespace(type="secret_worker_stage", prompt="A prompt body")

    assert _build_gallery_tags(history) == ["#task_type.other"]


def test_allowed_web_submit_types_include_txt2img():
    assert "txt2img" in ALLOWED_WEB_SUBMIT_TYPES


def test_allowed_web_submit_types_include_wan22_video_v2():
    assert "wan22_video_v2" in ALLOWED_WEB_SUBMIT_TYPES


def test_allowed_web_submit_types_include_scail2_video_modes():
    assert "scail2_action_transfer" in ALLOWED_WEB_SUBMIT_TYPES
    assert "scail2_action_transfer_long" in ALLOWED_WEB_SUBMIT_TYPES
    assert "scail2_video_replacement" in ALLOWED_WEB_SUBMIT_TYPES
    assert "scail2_face_swap_v2" in ALLOWED_WEB_SUBMIT_TYPES


def test_allowed_web_submit_types_only_include_minimax_h3_image_modes():
    assert "minimax_h3_i2v" in ALLOWED_WEB_SUBMIT_TYPES
    assert "minimax_h3_flf2v" in ALLOWED_WEB_SUBMIT_TYPES
    assert "minimax_h3_t2v" not in ALLOWED_WEB_SUBMIT_TYPES
    assert "minimax_h3_ref2v" not in ALLOWED_WEB_SUBMIT_TYPES


def test_minimax_h3_template_derived_history_cannot_be_submitted_again():
    history = SimpleNamespace(
        type="minimax_h3_i2v",
        allow_contribute=False,
        output_file="history/result.mp4",
    )
    with pytest.raises(Exception, match="一键应用他人的模板"):
        _validate_gallery_submit_history(history)


@pytest.mark.asyncio
async def test_toggle_like_impl_raises_duplicate_interaction_when_insert_conflicts():
    post = SimpleNamespace(likes_count=0, dislikes_count=0)
    session = _FakeSession(
        [
            _FakeScalarResult(None),
            _FakeExecuteResult(rowcount=0),
        ],
        post=post,
    )

    with pytest.raises(DuplicateInteractionError):
        await toggle_like_impl(
            user_id=123,
            post_id=456,
            action="like",
            session_factory=lambda: session,
        )

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_apply_interaction_impl_updates_counter_on_first_insert():
    session = _FakeSession(
        [
            _FakeExecuteResult(rowcount=1),
            _FakeExecuteResult(rowcount=1),
        ]
    )

    await record_apply_interaction_impl(
        user_id=123,
        post_id=456,
        session_factory=lambda: session,
    )

    assert len(session.execute_results) == 0
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_apply_interaction_impl_does_not_increment_duplicate_apply():
    increment_counter = AsyncMock()
    dependencies = SimpleNamespace(
        session_factory=lambda: _FakeSession([]),
        insert_gallery_apply_interaction_if_absent_func=AsyncMock(return_value=0),
        increment_gallery_apply_counter_func=increment_counter,
    )

    await record_apply_interaction_impl(
        user_id=123,
        post_id=456,
        dependencies=dependencies,
    )

    increment_counter.assert_not_awaited()
