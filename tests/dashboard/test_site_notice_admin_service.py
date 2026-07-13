import pytest

from dashboard.backend.schemas import SiteNoticeCreateRequest, SiteNoticeUpdateRequest
from dashboard.backend.services.site_notice_admin_service import (
    create_site_notice_payload,
    delete_site_notice_payload,
    get_site_notice_payload,
    list_site_notice_payloads,
    update_site_notice_payload,
)
from src.database.models import SiteNotice


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
        self.added = []
        self.committed = False
        self.refreshed = []

    async def execute(self, _stmt):
        return _Result(self.notices)

    def add(self, notice):
        if getattr(notice, "id", None) is None:
            notice.id = len(self.notices) + 1
        self.notices.append(notice)
        self.added.append(notice)

    async def commit(self):
        self.committed = True

    async def refresh(self, notice):
        self.refreshed.append(notice)


@pytest.mark.asyncio
async def test_list_site_notice_payloads_returns_sorted_visible_items():
    pinned_notice = SiteNotice(id=2, title="置顶", content="B", is_active=True, is_pinned=True)
    normal_notice = SiteNotice(id=1, title="普通", content="A", is_active=True, is_pinned=False)
    deleted_notice = SiteNotice(id=3, title="已删", content="C", is_active=True)
    deleted_notice.deleted_at = object()

    db = _FakeSession([normal_notice, pinned_notice, deleted_notice])

    response = await list_site_notice_payloads(db=db)

    assert [item.id for item in response.items] == [2, 1]
    assert response.items[0].is_pinned is True


@pytest.mark.asyncio
async def test_get_site_notice_payload_returns_target_notice():
    db = _FakeSession([SiteNotice(id=7, title="维护", content="notice", is_active=True)])

    response = await get_site_notice_payload(notice_id=7, db=db)

    assert response.id == 7
    assert response.title == "维护"


@pytest.mark.asyncio
async def test_create_site_notice_payload_creates_and_normalizes_notice():
    db = _FakeSession()
    payload = SiteNoticeCreateRequest(
        title="  大版本更新  ",
        content="  今晚 23:00 系统维护  ",
        is_active=True,
        is_pinned=True,
        target_groups=["金丹期", "金丹期", "bad"],
        target_identities=["核心弟子", "bad"],
    )

    response = await create_site_notice_payload(payload=payload, db=db)

    assert len(db.added) == 1
    assert isinstance(db.notices[0], SiteNotice)
    assert db.committed is True
    assert db.refreshed == [db.notices[0]]
    assert response.title == "大版本更新"
    assert response.content == "今晚 23:00 系统维护"
    assert response.is_active is True
    assert response.is_pinned is True
    assert response.target_groups == ["金丹期"]
    assert response.target_identities == ["核心弟子"]
    assert response.published_at is not None


@pytest.mark.asyncio
async def test_update_site_notice_payload_disables_blank_notice_and_unpins():
    notice = SiteNotice(
        id=1,
        title="旧通知",
        content="旧内容",
        is_active=True,
        is_pinned=True,
        target_groups=["筑基期"],
        target_identities=["内门弟子"],
    )
    db = _FakeSession([notice])
    payload = SiteNoticeUpdateRequest(
        title="   ",
        content="   ",
        is_active=True,
        is_pinned=True,
        target_groups=[],
        target_identities=[],
    )

    response = await update_site_notice_payload(notice_id=1, payload=payload, db=db)

    assert db.committed is True
    assert db.refreshed == [notice]
    assert response.title == "站点通知"
    assert response.content == ""
    assert response.is_active is False
    assert response.is_pinned is False
    assert response.target_groups == []
    assert response.target_identities == []


@pytest.mark.asyncio
async def test_delete_site_notice_payload_soft_deletes_notice():
    notice = SiteNotice(id=1, title="旧通知", content="旧内容", is_active=True, is_pinned=True)
    db = _FakeSession([notice])

    response = await delete_site_notice_payload(notice_id=1, db=db)

    assert response == {"success": True}
    assert notice.deleted_at is not None
    assert notice.is_active is False
    assert notice.is_pinned is False
