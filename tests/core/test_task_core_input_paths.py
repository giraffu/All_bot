from unittest.mock import MagicMock

import pytest

from src.core.task_core import CoreDomainError, _process_input_path


@pytest.mark.asyncio
async def test_process_input_path_keeps_plain_object_key():
    user_logger = MagicMock()

    result = await _process_input_path(
        user_logger, "123456/input_images/example.png"
    )

    assert result == "123456/input_images/example.png"
    user_logger.save_input_image.assert_not_called()


@pytest.mark.asyncio
async def test_process_input_path_rejects_missing_absolute_local_file():
    user_logger = MagicMock()
    missing_path = "/tmp/does-not-exist-custom-video.png"

    with pytest.raises(CoreDomainError, match="本地输入文件不存在"):
        await _process_input_path(user_logger, missing_path)

    user_logger.save_input_image.assert_not_called()


@pytest.mark.asyncio
async def test_process_input_path_rejects_failed_local_upload(tmp_path):
    user_logger = MagicMock()
    local_file = tmp_path / "custom-video.png"
    local_file.write_bytes(b"fake-image")
    user_logger.save_input_image.return_value = ""

    with pytest.raises(CoreDomainError, match="本地输入文件上传失败"):
        await _process_input_path(user_logger, str(local_file))

    user_logger.save_input_image.assert_called_once_with(str(local_file))
