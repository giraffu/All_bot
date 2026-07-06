from types import SimpleNamespace

import pytest

from src.handlers.error_handlers import global_error_handler
from src.services import fsm_temp_file_service


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
