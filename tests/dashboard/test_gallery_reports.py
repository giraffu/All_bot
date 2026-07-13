from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from dashboard.backend.presenters import gallery_admin_presenter
from dashboard.backend.services import gallery_admin_service
from src.database.models import GalleryPost, GalleryReport


class _ScalarResult:
    def __init__(self, value=None, rows=None, rowcount=0):
        self.value = value
        self.rows = list(rows or [])
        self.rowcount = rowcount

    def scalars(self):
        return self

    def all(self):
        if self.rows:
            return list(self.rows)
        if self.value is not None:
            return [self.value]
        return []


class _ReportsListDB:
    def __init__(self, reports, total=0):
        self.reports = list(reports)
        self.total = total
        self.executed_stmts = []

    async def scalar(self, stmt):
        self.executed_stmts.append(str(stmt))
        return self.total

    async def execute(self, stmt):
        self.executed_stmts.append(str(stmt))
        return _ScalarResult(rows=self.reports)


class _ResolveReportDB:
    def __init__(self, report):
        self.report = report
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def get(self, model, ident):
        if model is GalleryReport and self.report and ident == self.report.id:
            return self.report
        return None


class _TakedownReportDB:
    def __init__(self, report, post, history_count=2, report_count=3):
        self.report = report
        self.post = post
        self.history_count = history_count
        self.report_count = report_count
        self.executed_stmts = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def get(self, model, ident):
        if model is GalleryReport and self.report and ident == self.report.id:
            return self.report
        if model is GalleryPost and self.post and ident == self.post.id:
            return self.post
        return None

    async def execute(self, stmt):
        sql = str(stmt)
        self.executed_stmts.append(sql)
        if "UPDATE history" in sql:
            return _ScalarResult(rowcount=self.history_count)
        if "UPDATE gallery_reports" in sql:
            return _ScalarResult(rowcount=self.report_count)
        raise AssertionError(f"unexpected statement: {sql}")


def _build_report(**overrides):
    history = SimpleNamespace(output_file="demo.png", prompt="demo prompt")
    post = SimpleNamespace(
        id=7,
        task_id="task-7",
        user_id=456,
        is_active=True,
        media_type="image",
        histories=[history],
    )
    base = {
        "id": 10,
        "post_id": 7,
        "post": post,
        "post_task_id": "task-7",
        "post_author_user_id": 456,
        "post_author": SimpleNamespace(username="author", full_name=None),
        "reporter_user_id": 123,
        "reporter": SimpleNamespace(username="reporter", full_name="Reporter"),
        "reason": "gore",
        "status": "pending",
        "created_at": datetime(2026, 7, 4, 12, 0, 0),
        "resolved_at": None,
        "resolution_action": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_dashboard_report_item_formats_report_metadata():
    report = _build_report()

    result = gallery_admin_presenter.build_dashboard_report_item(
        report=report,
        storage_service=SimpleNamespace(get_file_url=lambda value: f"file://{value}"),
    )

    assert result["id"] == 10
    assert result["post_task_id"] == "task-7"
    assert result["reporter_name"] == "Reporter"
    assert result["post_author_name"] == "author"
    assert result["reason"] == "gore"
    assert result["prompt"] == "demo prompt"
    assert result["media_url"] == "file://demo.png"


@pytest.mark.asyncio
async def test_get_all_gallery_reports_payload_supports_filters_and_ordering():
    report = _build_report()
    db = _ReportsListDB([report], total=1)

    response = await gallery_admin_service.get_all_gallery_reports_payload(
        page=1,
        page_size=20,
        status="pending",
        reason="gore",
        post_id=7,
        db=db,
        storage_service=SimpleNamespace(get_file_url=lambda value: f"file://{value}"),
    )

    assert response["total"] == 1
    assert response["items"][0]["reporter_name"] == "Reporter"
    list_stmt = next(
        stmt for stmt in db.executed_stmts if "FROM gallery_reports" in stmt and "ORDER BY" in stmt
    )
    assert "gallery_reports.status = :status_1" in list_stmt
    assert "gallery_reports.reason = :reason_1" in list_stmt
    assert "gallery_reports.post_id = :post_id_1" in list_stmt
    assert "gallery_reports.created_at DESC, gallery_reports.id DESC" in list_stmt


@pytest.mark.asyncio
async def test_resolve_gallery_report_marks_report_resolved():
    report = _build_report()
    db = _ResolveReportDB(report)

    response = await gallery_admin_service.resolve_gallery_report_payload(
        report_id=10,
        db=db,
    )

    assert response == {"status": "ok", "resolved_reports": 1}
    assert report.status == "resolved"
    assert report.resolution_action == "manual_resolve"
    assert report.resolved_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_takedown_gallery_report_deactivates_post_and_resolves_pending_reports():
    report = _build_report()
    post = GalleryPost(
        id=7,
        task_id="task-7",
        user_id=456,
        media_type="image",
        is_active=True,
    )
    db = _TakedownReportDB(report=report, post=post, history_count=2, report_count=3)

    response = await gallery_admin_service.takedown_gallery_report_payload(
        report_id=10,
        db=db,
    )

    assert response["status"] == "ok"
    assert response["affected_posts"] == 1
    assert response["affected_histories"] == 2
    assert response["resolved_reports"] == 3
    assert response["resolution_action"] == "takedown"
    assert post.is_active is False
    assert any("UPDATE history" in stmt for stmt in db.executed_stmts)
    assert any("UPDATE gallery_reports" in stmt for stmt in db.executed_stmts)
    db.commit.assert_awaited_once()
