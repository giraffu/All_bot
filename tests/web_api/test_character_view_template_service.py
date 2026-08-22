from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.web_api.services import character_view_template_service as service


class _Db:
    def __init__(self, row=None, execute_results=None):
        self.row = row
        self.execute_results = iter(execute_results or [])
        self.added = []
        self.commit = AsyncMock()

    async def get(self, _model, _id):
        return self.row

    def add(self, row):
        self.added.append(row)

    async def execute(self, _statement):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: next(self.execute_results))
        )


@pytest.mark.asyncio
async def test_admin_can_create_multiple_templates_for_the_same_detail_slot(monkeypatch):
    db = _Db()
    monkeypatch.setattr(service.storage, "upload_bytes", MagicMock(return_value="stored"))
    monkeypatch.setattr(
        service.storage,
        "get_presigned_url",
        MagicMock(return_value="https://media/template"),
    )

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
        is_default=False,
    )
    db = _Db(row)
    monkeypatch.setattr(
        service.storage,
        "get_presigned_url",
        MagicMock(return_value="https://media/template"),
    )
    payload = SimpleNamespace(
        name="新名称",
        gender="female",
        sort_order=30,
        status="disabled",
        is_default=None,
    )

    result = await service.update_character_view_template(
        db, template_id="template-1", payload=payload
    )

    assert result["name"] == "新名称"
    assert result["status"] == "disabled"
    assert result["sort_order"] == 30
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_setting_default_replaces_the_previous_default_for_the_slot(monkeypatch):
    previous = SimpleNamespace(
        id="template-old",
        view_type="torso_front",
        name="旧默认",
        gender="female",
        object_key="bot-data/old.png",
        sort_order=10,
        status="active",
        is_default=True,
    )
    selected = SimpleNamespace(
        id="template-new",
        view_type="torso_front",
        name="新默认",
        gender="female",
        object_key="bot-data/new.png",
        sort_order=20,
        status="active",
        is_default=False,
    )
    db = _Db(selected, execute_results=[[previous, selected]])
    monkeypatch.setattr(
        service.storage,
        "get_presigned_url",
        MagicMock(return_value="https://media/template"),
    )

    result = await service.update_character_view_template(
        db,
        template_id=selected.id,
        payload=SimpleNamespace(
            name=None,
            gender=None,
            sort_order=None,
            status=None,
            is_default=True,
        ),
    )

    assert previous.is_default is False
    assert selected.is_default is True
    assert result["is_default"] is True
    db.commit.assert_awaited_once()
