import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from dashboard.backend.services.support_ticket_admin_service import (
    SupportTicketAdminError,
    reply_support_ticket_admin,
)


ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "dashboard" / "backend" / "routers" / "support_tickets.py"


def test_support_ticket_router_is_http_mapping_only():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "select" not in imports
    assert "Bot" not in imports
    assert called_attributes.isdisjoint({"execute", "commit", "add", "send_message"})


@pytest.mark.asyncio
async def test_reply_delivery_failure_does_not_commit_ticket_state():
    ticket = SimpleNamespace(
        id=7,
        telegram_user_id=99,
        status="open",
        assigned_admin=None,
        last_message_at=None,
        closed_at=None,
    )
    db = SimpleNamespace(get=AsyncMock(return_value=ticket), add=Mock(), commit=AsyncMock())

    async def fail_delivery(_chat_id: int, _body: str) -> int:
        raise SupportTicketAdminError("reply_delivery_failed")

    with pytest.raises(SupportTicketAdminError, match="reply_delivery_failed"):
        await reply_support_ticket_admin(
            db,
            ticket_id=7,
            body="reply",
            status="processing",
            admin_username="admin",
            send_reply=fail_delivery,
        )

    assert ticket.status == "open"
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reply_persists_only_after_delivery_succeeds():
    ticket = SimpleNamespace(
        id=7,
        telegram_user_id=99,
        internal_user_id=3,
        category="billing",
        status="open",
        username="user",
        full_name="User",
        assigned_admin=None,
        created_at=None,
        last_message_at=None,
        closed_at=None,
    )
    db = SimpleNamespace(get=AsyncMock(return_value=ticket), add=Mock(), commit=AsyncMock())

    result = await reply_support_ticket_admin(
        db,
        ticket_id=7,
        body="reply",
        status="resolved",
        admin_username="admin",
        send_reply=AsyncMock(return_value=123),
    )

    assert result["status"] == "resolved"
    assert ticket.assigned_admin == "admin"
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
