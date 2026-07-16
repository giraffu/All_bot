import importlib.util
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.models import User, UserLog
from src.web_api.services.user_credit_ledger_service import (
    get_current_user_credit_ledger_payload,
)


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "9b2f7c4d1a88_add_user_log_credit_ledger_index.py"
)


async def _create_credit_ledger_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(UserLog.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory()


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "credit_ledger_index_migration",
        MIGRATION_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_credit_ledger_returns_current_user_nonzero_logs_ordered_and_paginated():
    engine, session = await _create_credit_ledger_session()
    now = datetime(2026, 7, 3, 12, 0, 0)
    try:
        me = User(id=1, username="me", full_name="Me", credits=58)
        other = User(id=2, username="other", full_name="Other", credits=99)
        session.add_all([me, other])
        session.add_all(
            [
                UserLog(
                    id=1,
                    user_id=me.id,
                    username=me.username,
                    operation_type="recharge",
                    credit_change=50,
                    current_balance=60,
                    created_at=now,
                    extra_info=json.dumps(
                        {
                            "reason": "TON purchase",
                            "plan_name": "Inner Disciple",
                            "amount_usdt": "1.0000",
                            "order_id": "secret-order",
                            "source_tx_hash": "secret-hash",
                            "inviter_id": 999,
                        }
                    ),
                ),
                UserLog(
                    id=2,
                    user_id=me.id,
                    username=me.username,
                    operation_type="txt2img",
                    credit_change=-2,
                    current_balance=58,
                    created_at=now + timedelta(minutes=1),
                    extra_info=json.dumps({"old_balance": 60, "task_id": "hidden-task"}),
                ),
                UserLog(
                    id=3,
                    user_id=me.id,
                    username=me.username,
                    operation_type="checkin",
                    credit_change=10,
                    current_balance=68,
                    created_at=now + timedelta(minutes=2),
                    extra_info=json.dumps({"checkin_date": "2026-07-03", "reward": 10}),
                ),
                UserLog(
                    id=4,
                    user_id=me.id,
                    username=me.username,
                    operation_type="template_submission",
                    credit_change=0,
                    current_balance=68,
                    created_at=now + timedelta(minutes=3),
                ),
                UserLog(
                    id=5,
                    user_id=other.id,
                    username=other.username,
                    operation_type="recharge",
                    credit_change=99,
                    current_balance=99,
                    created_at=now + timedelta(minutes=4),
                ),
            ]
        )
        await session.commit()

        first_page = await get_current_user_credit_ledger_payload(
            current_user=me,
            db=session,
            page=1,
            page_size=2,
        )
        second_page = await get_current_user_credit_ledger_payload(
            current_user=me,
            db=session,
            page=2,
            page_size=2,
        )

        assert first_page.total == 3
        assert first_page.total_pages == 2
        assert [item.id for item in first_page.items] == [3, 2]
        assert [item.id for item in second_page.items] == [1]

        assert first_page.items[0].direction == "income"
        assert first_page.items[0].display_key == "credit_ledger.operation_types.checkin"
        assert first_page.items[1].direction == "expense"
        assert first_page.items[1].display_key == "task_type.txt2img"

        recharge = second_page.items[0]
        assert recharge.display_context == {
            "reason": "TON purchase",
            "plan_name": "Inner Disciple",
            "amount_usdt": "1.0000",
        }
    finally:
        await session.close()
        await engine.dispose()


def test_user_log_model_declares_credit_ledger_index():
    index_columns = {
        index.name: [column.name for column in index.columns]
        for index in UserLog.__table__.indexes
    }

    assert index_columns["ix_user_logs_user_created_at_id"] == [
        "user_id",
        "created_at",
        "id",
    ]


def test_credit_ledger_migration_creates_user_created_at_id_index(monkeypatch):
    module = _load_migration_module()
    created_indexes = []
    autocommit_entries = []

    @contextmanager
    def autocommit_block():
        autocommit_entries.append("entered")
        yield

    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda *args, **kwargs: created_indexes.append((args, kwargs)),
    )
    monkeypatch.setattr(
        module.op,
        "get_bind",
        lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
    )
    monkeypatch.setattr(
        module.op,
        "get_context",
        lambda: SimpleNamespace(autocommit_block=autocommit_block),
    )

    module.upgrade()

    assert created_indexes == [
        (
            (
                "ix_user_logs_user_created_at_id",
                "user_logs",
                ["user_id", "created_at", "id"],
            ),
            {"unique": False, "postgresql_concurrently": True},
        )
    ]
    assert autocommit_entries == ["entered"]
