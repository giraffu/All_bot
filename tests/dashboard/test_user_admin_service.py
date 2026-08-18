from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from dashboard.backend.schemas import (
    AdminGiftRequest,
    UpdateChannelMemberRequest,
    UpdateAlipayDirectRequest,
    UpdateSubmissionBanRequest,
)
from dashboard.backend.services import user_admin_service
from src.database.models import User


class _ScalarResult:
    def __init__(self, value=None, rows=None):
        self.value = value
        self.rows = list(rows or [])

    def scalar(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def one_or_none(self):
        return self.value

    def all(self):
        return list(self.rows)

    def scalars(self):
        return self


class _FakeUsersDB:
    def __init__(self, user, comment_counts=None, history_records=None):
        self.user = user
        self.comment_counts = list(comment_counts or [])
        self.history_records = list(history_records or [])
        self.executed_stmts = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.delete = AsyncMock()

    async def execute(self, stmt):
        sql = str(stmt)
        self.executed_stmts.append(sql)
        if "FROM users" in sql:
            return _ScalarResult(self.user)
        if "FROM gallery_comments" in sql and "GROUP BY gallery_comments.post_id" in sql:
            return _ScalarResult(rows=self.comment_counts)
        if "FROM history" in sql and "DELETE" not in sql:
            return _ScalarResult(rows=self.history_records)
        return _ScalarResult(None)


class _FakeGiftSession:
    def __init__(self, execute_results):
        self.execute_results = list(execute_results)
        self.added = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.flush = AsyncMock()

    async def execute(self, stmt):
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return _ScalarResult(self.execute_results.pop(0))

    def add(self, obj):
        self.added.append(obj)


class _FakeUserListDB:
    def __init__(self, execute_results):
        self.execute_results = list(execute_results)
        self.executed_stmts = []

    async def execute(self, stmt):
        self.executed_stmts.append(str(stmt))
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return self.execute_results.pop(0)


@pytest.mark.asyncio
async def test_delete_user_payload_removes_gallery_comments_and_syncs_post_counts():
    user = User(id=123, username="tester")
    db = _FakeUsersDB(user, comment_counts=[(7, 2), (9, 1)])

    response = await user_admin_service.delete_user_payload(user_id=123, db=db)

    assert "message" in response
    assert any("DELETE FROM gallery_comments" in stmt for stmt in db.executed_stmts)
    update_stmts = [stmt for stmt in db.executed_stmts if "UPDATE gallery_posts" in stmt]
    assert len(update_stmts) == 2
    assert all("greatest" in stmt.lower() for stmt in update_stmts)
    db.delete.assert_awaited_once_with(user)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_user_payload_only_decrements_active_gallery_comments():
    user = User(id=123, username="tester")
    db = _FakeUsersDB(user, comment_counts=[(7, 1)])

    await user_admin_service.delete_user_payload(user_id=123, db=db)

    gallery_count_stmt = next(
        stmt
        for stmt in db.executed_stmts
        if "FROM gallery_comments" in stmt and "GROUP BY gallery_comments.post_id" in stmt
    )
    assert "gallery_comments.is_active IS true" in gallery_count_stmt
    update_stmts = [stmt for stmt in db.executed_stmts if "UPDATE gallery_posts" in stmt]
    assert len(update_stmts) == 1


@pytest.mark.asyncio
async def test_admin_gift_plan_payload_uses_unified_membership_settlement_when_enabled(
    monkeypatch,
):
    user = SimpleNamespace(
        id=2002,
        username="gift_user",
        credits=5,
        current_identity="外门弟子",
        identity_expire_at=None,
    )
    plan = SimpleNamespace(
        id=1,
        name="Gift Plan",
        identity_name="内门弟子",
        duration_days=30,
        reward_credits=100,
    )
    db = _FakeGiftSession([user, plan])
    settle_mock = AsyncMock(return_value={"current_credits": 105})

    monkeypatch.setattr(
        user_admin_service, "is_membership_settlement_v2_enabled", lambda: True
    )
    monkeypatch.setattr(
        user_admin_service, "settle_membership_plan_in_session", settle_mock
    )

    result = await user_admin_service.admin_gift_plan_payload(
        user_id=2002,
        request=AdminGiftRequest(plan_id=1, note="test"),
        db=db,
    )

    settle_mock.assert_awaited_once()
    db.flush.assert_awaited_once()
    db.commit.assert_awaited_once()
    assert db.added[0].internal_user_id == 2002
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_update_user_channel_member_payload_triggers_reward_and_refresh(monkeypatch):
    user = User(
        id=123,
        telegram_id=999,
        username="tester",
        full_name="Tester",
        credits=10,
        is_channel_member=False,
    )
    db = _FakeUsersDB(user)
    log_action = AsyncMock()
    permission_service = SimpleNamespace(
        check_channel_reward=AsyncMock(),
        refresh_user_group=AsyncMock(),
    )

    monkeypatch.setattr(
        "src.services.log_service.LogService.log_action",
        log_action,
    )
    monkeypatch.setattr(
        "src.services.permission_service.permission_service",
        permission_service,
    )

    result = await user_admin_service.update_user_channel_member_payload(
        user_id=123,
        request=UpdateChannelMemberRequest(is_channel_member=True),
        db=db,
    )

    assert result == {"status": "ok", "id": 123, "is_channel_member": True}
    db.commit.assert_awaited_once()
    log_action.assert_awaited_once()
    permission_service.check_channel_reward.assert_awaited_once_with(
        tg_id=999,
        username="tester",
        full_name="Tester",
        internal_user_id=123,
    )
    permission_service.refresh_user_group.assert_awaited_once_with(123, is_member=True)


@pytest.mark.asyncio
async def test_update_user_submission_ban_payload_sets_default_reason_and_timestamp(monkeypatch):
    user = User(
        id=123,
        username="tester",
        full_name="Tester",
        credits=10,
        is_submission_banned=False,
        submission_ban_reason=None,
    )
    db = _FakeUsersDB(user)
    log_action = AsyncMock()

    monkeypatch.setattr(
        "src.services.log_service.LogService.log_action",
        log_action,
    )

    result = await user_admin_service.update_user_submission_ban_payload(
        user_id=123,
        request=UpdateSubmissionBanRequest(is_submission_banned=True),
        db=db,
    )

    assert result["status"] == "ok"
    assert result["is_submission_banned"] is True
    assert result["submission_ban_reason"] == "违禁被封，请联系管理员解封"
    assert result["submission_banned_at"] is not None
    db.commit.assert_awaited_once()
    log_action.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_user_alipay_direct_payload_writes_audit_log(monkeypatch):
    user = User(
        id=123,
        username="tester",
        credits=10,
        alipay_direct_enabled=False,
    )
    db = _FakeUsersDB(user)
    log_action = AsyncMock()
    monkeypatch.setattr(
        "src.services.log_service.LogService.log_action",
        log_action,
    )

    result = await user_admin_service.update_user_alipay_direct_payload(
        user_id=123,
        request=UpdateAlipayDirectRequest(enabled=True),
        db=db,
    )

    assert result == {
        "status": "ok",
        "id": 123,
        "alipay_direct_enabled": True,
    }
    assert user.alipay_direct_enabled is True
    db.commit.assert_awaited_once()
    log_action.assert_awaited_once()
    assert log_action.await_args.kwargs["operation_type"] == "admin_update_alipay_direct"


@pytest.mark.asyncio
async def test_get_users_payload_applies_requested_sort_order():
    db = _FakeUserListDB(
        [
            _ScalarResult(value=2),
            _ScalarResult(
                rows=[
                    User(id=200, username="beta", credits=9, referral_count=3),
                    User(id=100, username="alpha", credits=9, referral_count=2),
                ]
            ),
            _ScalarResult(rows=[]),
        ]
    )

    result = await user_admin_service.get_users_payload(
        db=db,
        sort_by="credits",
        sort_order="desc",
    )

    assert result["sort_by"] == "credits"
    assert result["sort_order"] == "desc"
    assert [item["id"] for item in result["items"]] == [200, 100]
    list_stmt = db.executed_stmts[1]
    assert "ORDER BY users.credits DESC NULLS LAST, users.id DESC" in list_stmt


@pytest.mark.asyncio
async def test_get_users_payload_includes_invited_recharge_usdt(monkeypatch):
    db = _FakeUserListDB(
        [
            _ScalarResult(value=2),
            _ScalarResult(
                rows=[
                    User(id=200, username="beta", credits=9, referral_count=3),
                    User(id=100, username="alpha", credits=9, referral_count=2),
                ]
            ),
        ]
    )
    totals_mock = AsyncMock(return_value={200: 14.85})
    monkeypatch.setattr(
        user_admin_service,
        "query_invited_recharge_totals_usdt",
        totals_mock,
    )

    result = await user_admin_service.get_users_payload(db=db)

    totals_mock.assert_awaited_once_with(db, [200, 100])
    items_by_id = {item["id"]: item for item in result["items"]}
    assert items_by_id[200]["invited_total_usdt"] == 14.85
    assert items_by_id[100]["invited_total_usdt"] == 0.0


@pytest.mark.asyncio
async def test_get_users_payload_rejects_unknown_sort_field():
    db = _FakeUserListDB([])

    with pytest.raises(user_admin_service.HTTPException) as exc_info:
        await user_admin_service.get_users_payload(
            db=db,
            sort_by="full_name",
            sort_order="asc",
        )

    assert exc_info.value.status_code == 400
    assert "Invalid sort_by" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_users_payload_filters_submission_banned_users():
    db = _FakeUserListDB(
        [
            _ScalarResult(value=1),
            _ScalarResult(
                rows=[
                    User(id=300, username="blocked", is_submission_banned=True),
                ]
            ),
            _ScalarResult(rows=[]),
        ]
    )

    result = await user_admin_service.get_users_payload(
        db=db,
        submission_banned=True,
    )

    assert result["total"] == 1
    assert result["items"][0]["id"] == 300
    count_stmt = db.executed_stmts[0]
    list_stmt = db.executed_stmts[1]
    assert "users.is_submission_banned IS true" in count_stmt
    assert "users.is_submission_banned IS true" in list_stmt


@pytest.mark.asyncio
async def test_get_users_payload_filters_alipay_direct_users():
    db = _FakeUserListDB(
        [
            _ScalarResult(value=1),
            _ScalarResult(
                rows=[User(id=301, username="direct", alipay_direct_enabled=True)]
            ),
            _ScalarResult(rows=[]),
        ]
    )

    result = await user_admin_service.get_users_payload(
        db=db,
        alipay_direct_enabled=True,
    )

    assert result["items"][0]["alipay_direct_enabled"] is True
    assert "users.alipay_direct_enabled IS true" in db.executed_stmts[0]
    assert "users.alipay_direct_enabled IS true" in db.executed_stmts[1]


@pytest.mark.asyncio
async def test_get_users_payload_filters_by_user_id():
    db = _FakeUserListDB(
        [
            _ScalarResult(value=1),
            _ScalarResult(rows=[User(id=8106178029, username="cccmmmmm")]),
            _ScalarResult(rows=[]),
        ]
    )

    result = await user_admin_service.get_users_payload(
        db=db,
        user_id=8106178029,
    )

    assert result["total"] == 1
    assert result["items"][0]["id"] == 8106178029
    count_stmt = db.executed_stmts[0]
    list_stmt = db.executed_stmts[1]
    assert "users.id = :id_1" in count_stmt
    assert "users.id = :id_1" in list_stmt
