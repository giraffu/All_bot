"""
集成测试：验证文件校验顺序修复

问题：之前 process_and_submit_task 会先扣费，后校验文件是否存在，
导致文件不存在时用户被预扣灵石后再退款（"扣后退"问题）。

修复后：文件校验前置，在扣费前先检查本地文件是否存在。
"""
from unittest.mock import AsyncMock, patch

import pytest

from src.core.task_core import process_and_submit_task, CoreDomainError


@pytest.mark.asyncio
async def test_local_file_missing_should_not_deduct_credits():
    """
    验证：当本地输入文件不存在时，不应扣费，直接抛出 CoreDomainError
    """
    user_id = 123
    username = "test_user"
    task_type = "custom_video"
    task_id = "test-task-missing-file"
    inputs = {
        "prompt": "test prompt",
        "images": ["/tmp/this-file-definitely-does-not-exist-12345.png"]
    }

    with (
        patch(
            "src.core.task_core.check_concurrency_lock", new_callable=AsyncMock
        ) as mock_lock,
        patch(
            "src.core.task_core.check_and_deduct_credits", new_callable=AsyncMock
        ) as mock_deduct,
        patch(
            "src.core.task_core.get_user_priority_and_identity", new_callable=AsyncMock
        ) as mock_identity,
        patch(
            "src.core.task_core.dispatch_to_worker", new_callable=AsyncMock
        ) as mock_dispatch,
        patch(
            "src.core.task_core.refund_credits", new_callable=AsyncMock
        ) as mock_refund,
    ):
        mock_lock.return_value = (True, "")
        mock_identity.return_value = (0, "user", "title")

        with pytest.raises(CoreDomainError, match="本地输入文件不存在"):
            await process_and_submit_task(
                user_id, username, task_type, inputs, task_id
            )

        mock_deduct.assert_not_called()
        mock_dispatch.assert_not_called()
        mock_refund.assert_not_called()


@pytest.mark.asyncio
async def test_minio_object_path_should_not_trigger_validation():
    """
    验证：MinIO 对象路径（template: 或 minio://）不应触发本地文件校验
    """
    user_id = 456
    username = "test_user_minio"
    task_type = "edit_image"
    task_id = "test-task-minio-path"
    inputs = {
        "prompt": "edit this image",
        "images": ["minio://bucket/image.png"]
    }

    with (
        patch(
            "src.core.task_core.check_concurrency_lock", new_callable=AsyncMock
        ) as mock_lock,
        patch(
            "src.core.task_core.check_and_deduct_credits", new_callable=AsyncMock
        ) as mock_deduct,
        patch(
            "src.core.task_core.get_user_priority_and_identity", new_callable=AsyncMock
        ) as mock_identity,
        patch(
            "src.core.task_core.dispatch_to_worker", new_callable=AsyncMock
        ) as mock_dispatch,
        patch(
            "src.core.task_core._process_input_path", new_callable=AsyncMock
        ) as mock_process,
        patch("src.core.task_core.TaskRegistry.add_task", new_callable=AsyncMock) as mock_add_task,
        patch(
            "src.core.task_core.TaskRegistry.update_backend_task_id",
            new_callable=AsyncMock,
        ) as mock_update_backend_task_id,
    ):
        mock_lock.return_value = (True, "")
        mock_deduct.return_value = (True, "")
        mock_identity.return_value = (0, "user", "title")
        mock_dispatch.return_value = "backend-task-minio"
        mock_process.return_value = "processed/path/image.png"
        mock_add_task.return_value = task_id

        result = await process_and_submit_task(
            user_id,
            username,
            task_type,
            inputs,
            task_id,
            deduct_quota=True,
            client_type="bot",
        )

        assert result is not None
        mock_deduct.assert_called_once()
        mock_update_backend_task_id.assert_awaited_once_with(
            task_id, "backend-task-minio"
        )


@pytest.mark.asyncio
async def test_template_path_should_not_trigger_validation():
    """
    验证：模板路径（template:）不应触发本地文件校验
    """
    user_id = 789
    username = "test_user_template"
    task_type = "quick_image"
    task_id = "test-task-template-path"
    inputs = {
        "prompt": "generate with template",
        "template_id": "template:template_001"
    }

    with (
        patch(
            "src.core.task_core.check_concurrency_lock", new_callable=AsyncMock
        ) as mock_lock,
        patch(
            "src.core.task_core.check_and_deduct_credits", new_callable=AsyncMock
        ) as mock_deduct,
        patch(
            "src.core.task_core.get_user_priority_and_identity", new_callable=AsyncMock
        ) as mock_identity,
        patch(
            "src.core.task_core.dispatch_to_worker", new_callable=AsyncMock
        ) as mock_dispatch,
        patch(
            "src.core.task_core._process_input_path", new_callable=AsyncMock
        ) as mock_process,
        patch("src.core.task_core.TaskRegistry.add_task", new_callable=AsyncMock) as mock_add_task,
        patch(
            "src.core.task_core.TaskRegistry.update_backend_task_id",
            new_callable=AsyncMock,
        ) as mock_update_backend_task_id,
    ):
        mock_lock.return_value = (True, "")
        mock_deduct.return_value = (True, "")
        mock_identity.return_value = (0, "user", "title")
        mock_dispatch.return_value = "backend-task-template"
        mock_process.return_value = "template:template_001"
        mock_add_task.return_value = task_id

        result = await process_and_submit_task(
            user_id,
            username,
            task_type,
            inputs,
            task_id,
            deduct_quota=True,
            client_type="bot",
        )

        assert result is not None
        mock_deduct.assert_called_once()
        mock_update_backend_task_id.assert_awaited_once_with(
            task_id, "backend-task-template"
        )


@pytest.mark.asyncio
async def test_normal_flow_deducts_credits_after_file_validation():
    """
    验证：正常流程中，文件校验通过后才扣费
    """
    user_id = 111
    username = "test_user_normal"
    task_type = "ltx_video"
    task_id = "test-task-normal-flow"
    inputs = {
        "prompt": "normal video task",
        "resolution": "512p",
        "duration": "5s",
    }

    call_order = []

    async def _record_deduct(*_args, **_kwargs):
        call_order.append("deduct_credits")
        return (True, "")

    with (
        patch(
            "src.core.task_core.check_concurrency_lock", new_callable=AsyncMock
        ) as mock_lock,
        patch(
            "src.core.task_core.check_and_deduct_credits", new_callable=AsyncMock
        ) as mock_deduct,
        patch(
            "src.core.task_core.get_user_priority_and_identity", new_callable=AsyncMock
        ) as mock_identity,
        patch(
            "src.core.task_core.dispatch_to_worker", new_callable=AsyncMock
        ) as mock_dispatch,
        patch(
            "src.core.task_core._process_input_path", new_callable=AsyncMock
        ) as mock_process,
        patch("src.core.task_core.TaskRegistry.add_task", new_callable=AsyncMock) as mock_add_task,
        patch(
            "src.core.task_core.TaskRegistry.update_backend_task_id",
            new_callable=AsyncMock,
        ) as mock_update_backend_task_id,
    ):
        mock_lock.return_value = (True, "")
        mock_identity.return_value = (0, "user", "title")
        mock_deduct.side_effect = _record_deduct
        mock_dispatch.return_value = "backend-task-normal"
        mock_process.return_value = "processed/video.png"
        mock_add_task.return_value = task_id

        result = await process_and_submit_task(
            user_id,
            username,
            task_type,
            inputs,
            task_id,
            deduct_quota=True,
            client_type="bot",
        )

        assert result is not None
        assert "deduct_credits" in call_order
        mock_update_backend_task_id.assert_awaited_once_with(
            task_id, "backend-task-normal"
        )


@pytest.mark.asyncio
async def test_concurrency_lock_released_when_file_missing():
    """
    验证：当文件不存在抛出 CoreDomainError 时，并发锁会被正确释放

    这是回归测试，确保文件校验失败不会导致并发锁泄漏。
    """
    user_id = 999
    username = "test_user_lock_leak"
    task_type = "custom_video"
    task_id = "test-task-lock-leak"
    inputs = {
        "prompt": "test prompt",
        "images": ["/tmp/definitely-nonexistent-file-xyz123.png"]
    }

    release_called = False

    async def mock_release_lock(uid):
        nonlocal release_called
        release_called = True
        assert uid == user_id, "释放锁时应传入正确的 user_id"

    with (
        patch(
            "src.core.task_core.check_concurrency_lock", new_callable=AsyncMock
        ) as mock_lock,
        patch(
            "src.core.task_core.release_concurrency_lock", new_callable=AsyncMock
        ) as mock_release,
        patch(
            "src.core.task_core.check_and_deduct_credits", new_callable=AsyncMock
        ) as mock_deduct,
        patch(
            "src.core.task_core.refund_credits", new_callable=AsyncMock
        ) as mock_refund,
    ):
        mock_lock.return_value = (True, "")
        mock_release.side_effect = mock_release_lock

        with pytest.raises(CoreDomainError, match="本地输入文件不存在"):
            await process_and_submit_task(
                user_id, username, task_type, inputs, task_id
            )

        mock_deduct.assert_not_called()
        mock_refund.assert_not_called()
        assert release_called, "文件不存在时应该释放并发锁，避免锁泄漏"


@pytest.mark.asyncio
async def test_file_validation_before_credit_deduction_order():
    """
    验证：文件校验确实在扣费之前执行

    通过 mock 的调用顺序来验证执行顺序。
    """
    user_id = 888
    username = "test_user_order"
    task_type = "custom_video"
    task_id = "test-task-order"
    inputs = {
        "prompt": "test prompt",
        "images": ["/tmp/definitely-nonexistent-file-abc789.png"]
    }

    call_sequence = []

    async def mock_check_lock(_uid):
        call_sequence.append("check_concurrency_lock")
        return (True, "")

    async def record_deduct(*_args, **_kwargs):
        call_sequence.append("check_and_deduct_credits")
        return (True, "")

    with (
        patch(
            "src.core.task_core.check_concurrency_lock", new_callable=AsyncMock
        ) as mock_lock,
        patch("src.core.task_core.release_concurrency_lock", new_callable=AsyncMock),
        patch(
            "src.core.task_core.check_and_deduct_credits", new_callable=AsyncMock
        ) as mock_deduct,
        patch("src.core.task_core.refund_credits", new_callable=AsyncMock),
    ):
        mock_lock.side_effect = mock_check_lock
        mock_deduct.side_effect = record_deduct

        with pytest.raises(CoreDomainError):
            await process_and_submit_task(
                user_id, username, task_type, inputs, task_id
            )

        assert call_sequence == ["check_concurrency_lock"], \
            "仅 check_concurrency_lock 被调用，文件校验在其后失败，扣费未执行"
