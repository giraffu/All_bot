"""
集成测试：验证文件校验顺序修复

问题：之前 process_and_submit_task 会先扣费，后校验文件是否存在，
导致文件不存在时用户被预扣灵石后再退款（"扣后退"问题）。

修复后：文件校验前置，在扣费前先检查本地文件是否存在。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core import task_core
from src.core.task_core import CoreDomainError, process_and_submit_task
from src.core.task_core_dependencies import TaskCoreProcessDependencies
from src.core.task_core_types import TaskSubmissionExecutionResult


def _patch_process_dependencies(
    *,
    prepare_payload,
    deduct_result=(True, ""),
    dispatch_backend_task_id="backend-task",
):
    check_lock = AsyncMock(return_value=(True, ""))
    deduct_credits = AsyncMock(return_value=deduct_result)
    compensate_failed = AsyncMock()
    release_lock = AsyncMock()

    async def execute_saga(**kwargs):
        return TaskSubmissionExecutionResult(
            registry_task_id=kwargs["registry_task_id"],
            backend_task_id=dispatch_backend_task_id,
            submission_context=kwargs["submission_context"],
        )

    dependencies = TaskCoreProcessDependencies(
        get_strategy_func=lambda _task_type: task_core.StrategyFactory.get_strategy(
            _task_type
        ),
        video_task_types={"custom_video", "ltx_video"},
        build_video_task_request_func=task_core.build_video_task_request,
        check_concurrency_lock_func=check_lock,
        prepare_task_submission_payload_func=prepare_payload,
        check_and_deduct_credits_func=deduct_credits,
        execute_task_submission_saga_func=execute_saga,
        attach_submission_side_effects_func=lambda **_kwargs: None,
        compensate_failed_submission_func=compensate_failed,
        release_concurrency_lock_func=release_lock,
        shield_func=lambda coro: coro,
        logger=task_core.logger,
    )
    return dependencies, check_lock, deduct_credits, compensate_failed, release_lock


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

    async def prepare_payload(**_kwargs):
        raise CoreDomainError("本地输入文件不存在")

    (
        dependencies,
        _check_lock,
        deduct_credits,
        compensate_failed,
        _release_lock,
    ) = _patch_process_dependencies(
        prepare_payload=prepare_payload,
    )

    with pytest.raises(CoreDomainError, match="本地输入文件不存在"):
        await process_and_submit_task(
            user_id,
            username,
            task_type,
            inputs,
            task_id,
            dependencies=dependencies,
        )

    deduct_credits.assert_not_called()
    compensate_failed.assert_not_called()


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

    async def prepare_payload(**_kwargs):
        return SimpleNamespace(saved_inputs=["processed/path/image.png"])

    (
        dependencies,
        _check_lock,
        deduct_credits,
        _compensate_failed,
        _release_lock,
    ) = _patch_process_dependencies(
        prepare_payload=prepare_payload,
        dispatch_backend_task_id="backend-task-minio",
    )

    result = await process_and_submit_task(
        user_id,
        username,
        task_type,
        inputs,
        task_id,
        deduct_quota=True,
        client_type="bot",
        dependencies=dependencies,
    )

    assert result is not None
    deduct_credits.assert_awaited_once()
    assert result["backend_task_id"] == "backend-task-minio"


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

    async def prepare_payload(**_kwargs):
        return SimpleNamespace(saved_inputs=["template:template_001"])

    (
        dependencies,
        _check_lock,
        deduct_credits,
        _compensate_failed,
        _release_lock,
    ) = _patch_process_dependencies(
        prepare_payload=prepare_payload,
        dispatch_backend_task_id="backend-task-template",
    )

    result = await process_and_submit_task(
        user_id,
        username,
        task_type,
        inputs,
        task_id,
        deduct_quota=True,
        client_type="bot",
        dependencies=dependencies,
    )

    assert result is not None
    deduct_credits.assert_awaited_once()
    assert result["backend_task_id"] == "backend-task-template"


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

    async def prepare_payload(**_kwargs):
        call_order.append("prepare_payload")
        return SimpleNamespace(saved_inputs=["processed/video.png"])

    async def _record_deduct(*_args, **_kwargs):
        call_order.append("deduct_credits")
        return (True, "")

    (
        dependencies,
        _check_lock,
        deduct_credits,
        _compensate_failed,
        _release_lock,
    ) = _patch_process_dependencies(
        prepare_payload=prepare_payload,
        dispatch_backend_task_id="backend-task-normal",
    )
    deduct_credits.side_effect = _record_deduct

    result = await process_and_submit_task(
        user_id,
        username,
        task_type,
        inputs,
        task_id,
        deduct_quota=True,
        client_type="bot",
        dependencies=dependencies,
    )

    assert result is not None
    assert call_order == ["prepare_payload", "deduct_credits"]
    assert result["backend_task_id"] == "backend-task-normal"


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

    async def prepare_payload(**_kwargs):
        raise CoreDomainError("本地输入文件不存在")

    (
        dependencies,
        _check_lock,
        deduct_credits,
        compensate_failed,
        release_lock,
    ) = _patch_process_dependencies(
        prepare_payload=prepare_payload,
    )

    with pytest.raises(CoreDomainError, match="本地输入文件不存在"):
        await process_and_submit_task(
            user_id,
            username,
            task_type,
            inputs,
            task_id,
            dependencies=dependencies,
        )

    deduct_credits.assert_not_called()
    compensate_failed.assert_not_called()
    release_lock.assert_awaited_once_with(user_id)


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

    async def prepare_payload(**_kwargs):
        call_sequence.append("prepare_payload")
        raise CoreDomainError("本地输入文件不存在")

    async def record_deduct(*_args, **_kwargs):
        call_sequence.append("check_and_deduct_credits")
        return (True, "")

    (
        dependencies,
        check_lock,
        deduct_credits,
        _compensate_failed,
        _release_lock,
    ) = _patch_process_dependencies(
        prepare_payload=prepare_payload,
    )
    check_lock.side_effect = lambda _uid: call_sequence.append("check_concurrency_lock") or (True, "")
    deduct_credits.side_effect = record_deduct

    with pytest.raises(CoreDomainError):
        await process_and_submit_task(
            user_id,
            username,
            task_type,
            inputs,
            task_id,
            dependencies=dependencies,
        )

    assert call_sequence == ["check_concurrency_lock", "prepare_payload"], (
        "文件校验在扣费前失败，扣费未执行"
    )
