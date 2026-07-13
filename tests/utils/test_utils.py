import pytest
from unittest.mock import AsyncMock, MagicMock

from src.utils import (
    create_background_task,
    robust_edit_text,
    robust_edit_caption,
    robust_edit_reply_markup,
    is_maintenance_mode,
)
from telegram.error import BadRequest
import os
import tempfile


@pytest.mark.asyncio
async def test_create_background_task():
    # Mock context and application
    mock_app = MagicMock()
    mock_app.bot_data = {}
    mock_task = MagicMock()
    mock_app.create_task.return_value = mock_task

    mock_context = MagicMock()
    mock_context.application = mock_app

    async def dummy_coro():
        pass

    coro = dummy_coro()
    task = create_background_task(mock_context, coro)

    # Assertions
    mock_app.create_task.assert_called_once_with(coro)
    assert "bg_tasks" in mock_app.bot_data
    assert task in mock_app.bot_data["bg_tasks"]
    mock_task.add_done_callback.assert_called_once()

    # Await coro to prevent "was never awaited" warning
    await coro


@pytest.mark.asyncio
async def test_robust_edit_text_ignores_no_text_error():
    mock_message = AsyncMock()
    # "There is no text in the message to edit"
    mock_message.edit_text.side_effect = BadRequest(
        "There is no text in the message to edit"
    )

    result = await robust_edit_text(mock_message, "new text")

    # Should not raise exception, should return the original message
    assert result == mock_message


@pytest.mark.asyncio
async def test_robust_edit_caption_ignores_not_found_error():
    mock_message = AsyncMock()
    mock_message.edit_caption.side_effect = BadRequest("Message to edit not found")

    result = await robust_edit_caption(mock_message, "new caption")
    assert result == mock_message


@pytest.mark.asyncio
async def test_robust_edit_reply_markup_ignores_not_modified_error():
    mock_message = AsyncMock()
    mock_message.edit_reply_markup.side_effect = BadRequest("Message is not modified")

    result = await robust_edit_reply_markup(mock_message, reply_markup=None)
    assert result == mock_message


def test_is_maintenance_mode():
    import src.utils as utils_module

    original_maintenance_file = utils_module.MAINTENANCE_FILE
    original_generation_maintenance_file = utils_module.GENERATION_MAINTENANCE_FILE

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_maintenance_file = os.path.join(temp_dir, "MAINTENANCE")
        temp_generation_maintenance_file = os.path.join(
            temp_dir, "GENERATION_MAINTENANCE"
        )
        utils_module.MAINTENANCE_FILE = temp_maintenance_file
        utils_module.GENERATION_MAINTENANCE_FILE = temp_generation_maintenance_file

        try:
            assert not is_maintenance_mode()

            with open(temp_generation_maintenance_file, "w") as f:
                f.write("generation")

            assert is_maintenance_mode()

            os.remove(temp_generation_maintenance_file)
            assert not is_maintenance_mode()

            with open(temp_maintenance_file, "w") as f:
                f.write("maintenance")

            assert is_maintenance_mode()
        finally:
            utils_module.MAINTENANCE_FILE = original_maintenance_file
            utils_module.GENERATION_MAINTENANCE_FILE = (
                original_generation_maintenance_file
            )


def test_is_maintenance_mode_honors_generation_maintenance_env(monkeypatch):
    import importlib
    import src.utils as utils_module

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_maintenance_file = os.path.join(temp_dir, "MAINTENANCE")
        temp_generation_maintenance_file = os.path.join(
            temp_dir, "GENERATION_MAINTENANCE"
        )
        monkeypatch.setenv("MAINTENANCE_FILE", temp_maintenance_file)
        monkeypatch.setenv(
            "GENERATION_MAINTENANCE_FILE",
            temp_generation_maintenance_file,
        )
        importlib.reload(utils_module)

        try:
            assert utils_module.MAINTENANCE_FILE == temp_maintenance_file
            assert (
                utils_module.GENERATION_MAINTENANCE_FILE
                == temp_generation_maintenance_file
            )
            assert not utils_module.is_maintenance_mode()

            with open(temp_generation_maintenance_file, "w") as f:
                f.write("generation")

            assert utils_module.is_maintenance_mode()
        finally:
            monkeypatch.delenv("MAINTENANCE_FILE", raising=False)
            monkeypatch.delenv("GENERATION_MAINTENANCE_FILE", raising=False)
            importlib.reload(utils_module)


def test_load_prompts_fallback():
    from src.utils import load_prompts

    with tempfile.TemporaryDirectory() as temp_dir:
        fake_ini = os.path.join(temp_dir, "fake.ini")

        # Missing file, should return defaults
        prompts = load_prompts.__wrapped__(fake_ini)
        assert "undress" in prompts
        assert "face_swap" in prompts

        # Valid file
        with open(fake_ini, "w") as f:
            f.write("[prompts]\ntest_mode=test_prompt\n")

        prompts = load_prompts.__wrapped__(fake_ini)
        assert "test_mode" in prompts
        assert prompts["test_mode"] == "test_prompt"
