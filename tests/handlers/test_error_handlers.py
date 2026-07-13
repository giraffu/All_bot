from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import InsufficientCreditsError
from src.handlers import error_handlers
from src.handlers.error_handlers import global_error_handler
from src.services import fsm_temp_file_service
from src.services.private_bot_update_admission import (
    PrivateBotUpdateAdmissionScope,
    activate_private_bot_update_scope,
)


@pytest.mark.asyncio
async def test_global_error_handler_cleans_fsm_temp_files(tmp_path, monkeypatch):
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    image_path = temp_root / "image.png"
    image_path.write_text("x")
    monkeypatch.setattr(fsm_temp_file_service, "TMP_DIR", str(temp_root))

    context = SimpleNamespace(
        user_data={
            "language_code": "zh",
            "in_conversation": "QUICK_IMAGE",
            "quick_image_data": {"image_path": str(image_path)},
        },
        error=RuntimeError("boom"),
    )

    await global_error_handler(object(), context)

    assert not image_path.exists()
    assert context.user_data == {"language_code": "zh"}


@pytest.mark.asyncio
async def test_private_update_is_not_acked_when_error_notification_fails(monkeypatch):
    class FakeUpdate:
        callback_query = None
        effective_chat = SimpleNamespace(id=12345)

    send_message = AsyncMock(side_effect=RuntimeError("telegram unavailable"))
    monkeypatch.setattr(error_handlers, "Update", FakeUpdate)
    monkeypatch.setattr(error_handlers, "robust_send_message", send_message)
    context = SimpleNamespace(
        user_data={"language_code": "zh"},
        bot=object(),
        error=InsufficientCreditsError(current=1, cost=2),
    )
    admission = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=701)

    with activate_private_bot_update_scope(admission):
        with pytest.raises(RuntimeError, match="telegram unavailable"):
            await global_error_handler(FakeUpdate(), context)

    assert admission.failed is True
    send_message.assert_awaited_once()
