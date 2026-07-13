from types import SimpleNamespace

import pytest

from src.handlers import callback_handler


@pytest.mark.asyncio
async def test_global_callback_is_acknowledged_before_user_sync(monkeypatch):
    call_order = []

    async def answer(query):
        call_order.append("answer")

    async def ensure_user(*_args):
        call_order.append("ensure_user")

    async def route(_update, _context):
        call_order.append("route")

    monkeypatch.setattr(callback_handler, "safe_answer_query", answer)
    monkeypatch.setattr(
        callback_handler.permission_service, "ensure_user", ensure_user
    )
    monkeypatch.setattr(callback_handler.router, "SORTED_ROUTES", ("fast:",))
    monkeypatch.setattr(callback_handler.router, "CALLBACK_ROUTES", {"fast:": route})

    query = SimpleNamespace(data="fast:1", from_user=SimpleNamespace(id=123))
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
            language_code="zh",
        ),
    )

    await callback_handler.handle_callback_query.__wrapped__(update, SimpleNamespace())

    assert call_order == ["answer", "ensure_user", "route"]
