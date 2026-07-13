from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.database.models import GalleryPost, User
from src.web_api.schemas.gallery_schema import GalleryReportCreate
from src.web_api.services.gallery_report_service import create_gallery_report_payload


class _CreateReportSession:
    def __init__(self, post, flush_error: Exception | None = None):
        self.post = post
        self.flush_error = flush_error
        self.added = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def get(self, model, ident):
        if model is GalleryPost and self.post and ident == self.post.id:
            return self.post
        return None

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        if self.flush_error is not None:
            raise self.flush_error
        if self.added:
            self.added[-1].id = 99
            self.added[-1].created_at = datetime(2026, 7, 4, 12, 0, 0)


@pytest.mark.asyncio
async def test_create_gallery_report_records_reason_and_snapshots_post():
    post = GalleryPost(
        id=7,
        task_id="task-7",
        user_id=456,
        media_type="image",
        is_active=True,
    )
    session = _CreateReportSession(post)

    response = await create_gallery_report_payload(
        post_id=7,
        report=GalleryReportCreate(reason="gore"),
        current_user=User(id=123, username="reporter"),
        db=session,
    )

    assert response == {"status": "ok", "report_id": 99}
    session.commit.assert_awaited_once()
    assert len(session.added) == 1
    saved_report = session.added[0]
    assert saved_report.post_id == 7
    assert saved_report.reporter_user_id == 123
    assert saved_report.post_author_user_id == 456
    assert saved_report.post_task_id == "task-7"
    assert saved_report.reason == "gore"
    assert saved_report.status == "pending"


@pytest.mark.asyncio
async def test_create_gallery_report_rejects_inactive_or_missing_post():
    session = _CreateReportSession(
        GalleryPost(id=7, task_id="task-7", media_type="image", is_active=False)
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_gallery_report_payload(
            post_id=7,
            report=GalleryReportCreate(reason="children"),
            current_user=User(id=123),
            db=session,
        )

    assert exc_info.value.status_code == 404
    assert session.added == []
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_gallery_report_rejects_duplicate_report():
    post = GalleryPost(id=7, task_id="task-7", user_id=456, media_type="image", is_active=True)
    session = _CreateReportSession(
        post,
        flush_error=IntegrityError("insert into gallery_reports", {}, Exception("duplicate")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_gallery_report_payload(
            post_id=7,
            report=GalleryReportCreate(reason="gross"),
            current_user=User(id=123),
            db=session,
        )

    assert exc_info.value.status_code == 409
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_gallery_report_reason_is_limited_to_known_values():
    with pytest.raises(ValidationError):
        GalleryReportCreate(reason="spam")
