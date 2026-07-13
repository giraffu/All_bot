from unittest.mock import AsyncMock

import pytest

from dashboard.backend.routers import gallery as gallery_router


@pytest.mark.asyncio
async def test_get_all_gallery_posts_routes_to_service(monkeypatch):
    expected = {"items": [], "total": 0, "page": 1, "page_size": 20}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(gallery_router, "get_all_gallery_posts_payload", service_mock)

    result = await gallery_router.get_all_gallery_posts(
        page=1,
        page_size=20,
        is_active=True,
        media_type="image",
        task_type="img2img",
        sort_by="latest",
        username="tester",
        prompt_contains="demo",
        prompt_max_length=80,
    )

    assert result == expected
    service_mock.assert_awaited_once_with(
        page=1,
        page_size=20,
        is_active=True,
        media_type="image",
        task_type="img2img",
        sort_by="latest",
        username="tester",
        prompt_contains="demo",
        prompt_max_length=80,
        logger_override=gallery_router.logger,
    )


@pytest.mark.asyncio
async def test_get_all_gallery_comments_routes_to_service(monkeypatch):
    expected = {"items": [], "total": 0, "page": 1, "page_size": 20}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        gallery_router, "get_all_gallery_comments_payload", service_mock
    )
    db = object()

    result = await gallery_router.get_all_gallery_comments(
        page=1,
        page_size=20,
        post_id=7,
        is_active=True,
        db=db,
    )

    assert result == expected
    service_mock.assert_awaited_once_with(
        page=1,
        page_size=20,
        post_id=7,
        is_active=True,
        db=db,
        logger_override=gallery_router.logger,
    )


@pytest.mark.asyncio
async def test_get_gallery_comments_routes_to_service(monkeypatch):
    expected = {"items": [], "total": 0, "active_total": 0, "page": 1, "page_size": 20}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(gallery_router, "get_gallery_comments_payload", service_mock)
    db = object()

    result = await gallery_router.get_gallery_comments(
        post_id=7, page=1, page_size=20, db=db
    )

    assert result == expected
    service_mock.assert_awaited_once_with(
        post_id=7,
        page=1,
        page_size=20,
        db=db,
        logger_override=gallery_router.logger,
    )


@pytest.mark.asyncio
async def test_update_gallery_comment_routes_to_service(monkeypatch):
    expected = {"success": True, "message": "ok"}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(gallery_router, "update_gallery_comment_payload", service_mock)
    db = object()
    update_data = gallery_router.CommentUpdate(is_active=False)

    result = await gallery_router.update_gallery_comment(10, update_data, db=db)

    assert result == expected
    service_mock.assert_awaited_once_with(
        comment_id=10,
        update_data=update_data,
        db=db,
        logger_override=gallery_router.logger,
    )


@pytest.mark.asyncio
async def test_update_gallery_post_routes_to_service(monkeypatch):
    expected = {"success": True, "message": "ok"}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(gallery_router, "update_gallery_post_payload", service_mock)
    db = object()
    update_data = gallery_router.GalleryPostUpdate(is_active=True, likes_count=3)

    result = await gallery_router.update_gallery_post(9, update_data, db=db)

    assert result == expected
    service_mock.assert_awaited_once_with(
        post_id=9,
        update_data=update_data,
        db=db,
        logger_override=gallery_router.logger,
    )


@pytest.mark.asyncio
async def test_ban_user_submissions_and_takedown_routes_to_service(monkeypatch):
    expected = {"status": "ok", "affected_posts": 2}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        gallery_router,
        "ban_user_submissions_and_takedown_payload",
        service_mock,
    )
    db = object()
    request = gallery_router.GalleryUserSubmissionModerationRequest(reason=None)

    result = await gallery_router.ban_user_submissions_and_takedown(
        123,
        request,
        db=db,
    )

    assert result == expected
    service_mock.assert_awaited_once_with(
        user_id=123,
        request=request,
        db=db,
        logger_override=gallery_router.logger,
    )


@pytest.mark.asyncio
async def test_get_all_gallery_reports_routes_to_service(monkeypatch):
    expected = {"items": [], "total": 0, "page": 1, "page_size": 20}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(gallery_router, "get_all_gallery_reports_payload", service_mock)
    db = object()

    result = await gallery_router.get_all_gallery_reports(
        page=1,
        page_size=20,
        status="pending",
        reason="gore",
        post_id=7,
        db=db,
    )

    assert result == expected
    service_mock.assert_awaited_once_with(
        page=1,
        page_size=20,
        status="pending",
        reason="gore",
        post_id=7,
        db=db,
        logger_override=gallery_router.logger,
    )


@pytest.mark.asyncio
async def test_resolve_gallery_report_routes_to_service(monkeypatch):
    expected = {"status": "ok"}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(gallery_router, "resolve_gallery_report_payload", service_mock)
    db = object()

    result = await gallery_router.resolve_gallery_report(10, db=db)

    assert result == expected
    service_mock.assert_awaited_once_with(
        report_id=10,
        db=db,
        logger_override=gallery_router.logger,
    )


@pytest.mark.asyncio
async def test_takedown_gallery_report_routes_to_service(monkeypatch):
    expected = {"status": "ok"}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(gallery_router, "takedown_gallery_report_payload", service_mock)
    db = object()

    result = await gallery_router.takedown_gallery_report(10, db=db)

    assert result == expected
    service_mock.assert_awaited_once_with(
        report_id=10,
        db=db,
        logger_override=gallery_router.logger,
    )
