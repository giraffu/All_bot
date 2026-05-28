from datetime import datetime

import pytest

from src.database.models import SiteNotice
from src.web_api.services.site_notice_service import get_active_site_notice_payload


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _Result:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarsResult(self._values)


class _FakeSession:
    def __init__(self, notices=None):
        self.notices = list(notices or [])

    async def execute(self, _stmt):
        return _Result(self.notices)


class _CurrentUser:
    def __init__(self, user_id=1, user_group="练气期", current_identity="外门弟子"):
        self.id = user_id
        self.user_group = user_group
        self.current_identity = current_identity


def _build_stats_loader(group: str, identity: str):
    async def _loader(_user_id: int):
        return {"group": group, "identity": identity}

    return _loader


@pytest.mark.asyncio
async def test_get_active_site_notice_payload_returns_hidden_payload_when_missing():
    payload = await get_active_site_notice_payload(
        db=_FakeSession(),
        current_user=_CurrentUser(),
        get_user_detailed_stats_func=_build_stats_loader("练气期", "外门弟子"),
    )

    assert payload.featured_notice is None
    assert payload.notices == []


@pytest.mark.asyncio
async def test_get_active_site_notice_payload_hides_inactive_or_blank_notice():
    blank_notice = SiteNotice(id=1, title="空白", content="   ", is_active=True)
    blank_notice.published_at = datetime.now()

    payload = await get_active_site_notice_payload(
        db=_FakeSession([blank_notice]),
        current_user=_CurrentUser(),
        get_user_detailed_stats_func=_build_stats_loader("练气期", "外门弟子"),
    )

    assert payload.featured_notice is None
    assert payload.notices == []


@pytest.mark.asyncio
async def test_get_active_site_notice_payload_returns_active_notice():
    notice = SiteNotice(id=1, title="维护公告", content="维护内容", is_active=True)
    notice.published_at = datetime.now()

    payload = await get_active_site_notice_payload(
        db=_FakeSession([notice]),
        current_user=_CurrentUser(),
        get_user_detailed_stats_func=_build_stats_loader("练气期", "外门弟子"),
    )

    assert payload.featured_notice is not None
    assert payload.featured_notice.title == "维护公告"
    assert payload.featured_notice.content == "维护内容"
    assert len(payload.notices) == 1


@pytest.mark.asyncio
async def test_get_active_site_notice_payload_filters_by_group_or_identity_and_sorts_pinned_first():
    hidden_notice = SiteNotice(
        id=1,
        title="定向公告",
        content="仅核心可见",
        is_active=True,
        target_groups=["金丹期"],
        target_identities=["核心弟子"],
    )
    hidden_notice.published_at = datetime.now()

    pinned_notice = SiteNotice(
        id=2,
        title="置顶公告",
        content="全员置顶",
        is_active=True,
        is_pinned=True,
    )
    pinned_notice.published_at = datetime.now()

    history_notice = SiteNotice(
        id=3,
        title="历史公告",
        content="历史内容",
        is_active=False,
    )
    history_notice.published_at = datetime.now()

    matched_payload = await get_active_site_notice_payload(
        db=_FakeSession([hidden_notice, pinned_notice, history_notice]),
        current_user=_CurrentUser(),
        get_user_detailed_stats_func=_build_stats_loader("练气期", "外门弟子"),
    )
    hidden_payload = await get_active_site_notice_payload(
        db=_FakeSession([hidden_notice]),
        current_user=_CurrentUser(),
        get_user_detailed_stats_func=_build_stats_loader("练气期", "外门弟子"),
    )

    assert matched_payload.featured_notice is not None
    assert matched_payload.featured_notice.id == 2
    assert [item.id for item in matched_payload.notices] == [2, 3]
    assert hidden_payload.featured_notice is None
    assert hidden_payload.notices == []
