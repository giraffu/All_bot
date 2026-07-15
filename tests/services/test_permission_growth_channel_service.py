from types import SimpleNamespace

import pytest

from src.services.permission_growth_channel_service import PermissionGrowthChannelService


class _QuotaSpy:
    def __init__(self):
        self.checkin_kwargs = None

    async def checkin(self, user_id: int, **kwargs):
        self.checkin_kwargs = {"user_id": user_id, **kwargs}
        return True

    async def get_user_stats(self, user_id: int):
        return {"checkin_count": 8}


class _ReferralQuotaSpy:
    def __init__(self):
        self.process_referral_calls = []

    async def process_referral(self, *args, **kwargs):
        self.process_referral_calls.append((args, kwargs))
        return True


@pytest.mark.asyncio
async def test_perform_checkin_records_base_and_identity_bonus(monkeypatch):
    async def fake_get_or_create_user_by_telegram(tg_id, username=None, full_name=None):
        return SimpleNamespace(id=123), False

    async def refresh_user_group(user_id, is_member=None):
        return None

    async def get_user_group(user_id):
        return "筑基期"

    async def get_user_identity(user_id):
        return "核心弟子"

    async def get_user_credits(tg_id, username, full_name):
        return 88

    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        fake_get_or_create_user_by_telegram,
    )

    quota = _QuotaSpy()
    service = PermissionGrowthChannelService(
        quota,
        refresh_user_group_func=refresh_user_group,
        get_user_group_func=get_user_group,
        get_user_identity_func=get_user_identity,
        get_user_credits_func=get_user_credits,
    )

    success, current_credits, message, total_checkins, reward = await service.perform_checkin(
        54321,
        "tester",
        "测试修士",
    )

    assert success is True
    assert current_credits == 88
    assert message == ""
    assert total_checkins == 8
    assert reward == 52
    assert quota.checkin_kwargs == {
        "user_id": 123,
        "username": "tester",
        "full_name": "测试修士",
        "reward": 52,
        "checkin_base_reward": 12,
        "checkin_identity_bonus": 40,
        "checkin_user_group": "筑基期",
        "checkin_identity": "核心弟子",
    }


@pytest.mark.asyncio
async def test_existing_user_cannot_be_attached_to_referral(monkeypatch):
    async def fake_get_or_create_user_by_telegram(
        tg_id, username=None, full_name=None
    ):
        if tg_id == 111:
            return SimpleNamespace(id=1), False
        return SimpleNamespace(id=2), False

    async def refresh_user_group(user_id, is_member=None):
        return None

    async def get_user_group(user_id):
        return "练气期"

    async def unused(*args, **kwargs):
        raise AssertionError("unexpected dependency call")

    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        fake_get_or_create_user_by_telegram,
    )

    quota = _ReferralQuotaSpy()
    service = PermissionGrowthChannelService(
        quota,
        refresh_user_group_func=refresh_user_group,
        get_user_group_func=get_user_group,
        get_user_identity_func=unused,
        get_user_credits_func=unused,
    )

    result = await service.process_referral(
        tg_id=222,
        username="existing_user",
        full_name="老用户",
        inviter_tg_id=111,
    )

    assert result == (False, "existing_user")
    assert quota.process_referral_calls == []


@pytest.mark.asyncio
async def test_new_user_can_be_attached_to_referral(monkeypatch):
    async def fake_get_or_create_user_by_telegram(
        tg_id, username=None, full_name=None
    ):
        if tg_id == 111:
            return SimpleNamespace(id=1), False
        return SimpleNamespace(id=2), True

    refreshed_user_ids = []

    async def refresh_user_group(user_id, is_member=None):
        refreshed_user_ids.append(user_id)

    async def get_user_group(user_id):
        return "练气期"

    async def unused(*args, **kwargs):
        raise AssertionError("unexpected dependency call")

    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        fake_get_or_create_user_by_telegram,
    )

    quota = _ReferralQuotaSpy()
    service = PermissionGrowthChannelService(
        quota,
        refresh_user_group_func=refresh_user_group,
        get_user_group_func=get_user_group,
        get_user_identity_func=unused,
        get_user_credits_func=unused,
    )

    result = await service.process_referral(
        tg_id=222,
        username="new_user",
        full_name="新用户",
        inviter_tg_id=111,
    )

    assert result == (True, "success")
    assert quota.process_referral_calls == [
        (
            (1, 2),
            {
                "new_user_was_created": True,
                "new_username": "new_user",
                "_new_full_name": "新用户",
            },
        )
    ]
    assert refreshed_user_ids == [1]
