from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.constants import MODE_I2I_PRO
from src.services import task_service_entrypoints_generation


@pytest.mark.asyncio
async def test_process_i2i_pro_task_builds_flow_without_explicit_runtime_state(
    monkeypatch,
):
    resolve_internal_user_id = AsyncMock(return_value=321)
    run_bot_task_application = AsyncMock(return_value=(b"img-bytes", "result.png"))

    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "resolve_internal_user_id",
        resolve_internal_user_id,
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "get_acceleration_notice",
        AsyncMock(return_value="notice"),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "translate_context_text",
        lambda *args, **kwargs: kwargs.get("mode_name", "text"),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_status_message",
        lambda text, notice=None: f"{text}|{notice}",
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_message_spec",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_task_inputs",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "build_translated_cost_status_builder",
        lambda *args, **kwargs: (lambda cost: f"submitted:{cost}"),
    )
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "run_bot_task_application",
        run_bot_task_application,
    )

    result = await task_service_entrypoints_generation.process_i2i_pro_task(
        context=SimpleNamespace(bot=object()),
        chat_id=123,
        user_id=456,
        username="tester",
        prompt="hello",
        images=["/tmp/input.png"],
        allow_contribute=False,
        source_post_id=9,
    )

    assert result == (b"img-bytes", "result.png")
    resolve_internal_user_id.assert_awaited_once_with(456, "tester")

    flow = run_bot_task_application.await_args.kwargs["flow"]
    assert flow.runtime_state is not None
    assert flow.request.chat_id == 123
    assert flow.request.internal_user_id == 321
    assert flow.request.task_type == MODE_I2I_PRO
    assert flow.request.source_post_id == 9
    assert flow.presentation.allow_contribute is False


@pytest.mark.asyncio
async def test_process_i2i_pro_task_requires_images(monkeypatch):
    send_message = AsyncMock()
    monkeypatch.setattr(
        task_service_entrypoints_generation,
        "robust_send_message",
        send_message,
    )

    result = await task_service_entrypoints_generation.process_i2i_pro_task(
        context=SimpleNamespace(bot=object()),
        chat_id=123,
        user_id=456,
        username="tester",
        prompt="hello",
        images=[],
    )

    assert result == (None, None)
    send_message.assert_awaited_once()
