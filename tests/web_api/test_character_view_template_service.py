from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.web_api.services import character_view_template_service as service


class _Db:
    def __init__(self, row=None):
        self.row = row
        self.added = []
        self.commit = AsyncMock()

    async def get(self, _model, _id):
        return self.row

    def add(self, row):
        self.added.append(row)


@pytest.mark.asyncio
async def test_admin_can_create_multiple_templates_for_the_same_detail_slot(monkeypatch):
    db = _Db()
    monkeypatch.setattr(service.storage, "upload_bytes", MagicMock(return_value="stored"))
    monkeypatch.setattr(service.storage, "get_presigned_url", MagicMock(return_value="https://media/template"))

    first = await service.create_character_view_template(
        db,
        view_type="genitals_front",
        name="模板 A",
        gender="female",
        sort_order=10,
        image_bytes=b"first",
        content_type="image/png",
        created_by="admin",
    )
    second = await service.create_character_view_template(
        db,
        view_type="genitals_front",
        name="模板 B",
        gender="female",
        sort_order=20,
        image_bytes=b"second",
        content_type="image/jpeg",
        created_by="admin",
    )

    assert first["view_type"] == second["view_type"] == "genitals_front"
    assert first["id"] != second["id"]
    assert [row.name for row in db.added] == ["模板 A", "模板 B"]
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_admin_can_disable_and_reorder_a_template(monkeypatch):
    row = SimpleNamespace(
        id="template-1",
        view_type="torso_front",
        name="旧名称",
        gender="neutral",
        object_key="bot-data/template.png",
        sort_order=0,
        status="active",
    )
    db = _Db(row)
    monkeypatch.setattr(service.storage, "get_presigned_url", MagicMock(return_value="https://media/template"))
    payload = SimpleNamespace(name="新名称", gender="female", sort_order=30, status="disabled")

    result = await service.update_character_view_template(
        db, template_id="template-1", payload=payload
    )

    assert result["name"] == "新名称"
    assert result["status"] == "disabled"
    assert result["sort_order"] == 30
    db.commit.assert_awaited_once()
