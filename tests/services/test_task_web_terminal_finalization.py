from unittest.mock import AsyncMock

import pytest

from src.core.task_core_types import TaskSubmissionContext
from src.services import task_web_terminal_finalization


@pytest.mark.asyncio
async def test_web_success_finalizer_retries_when_history_persistence_fails():
    persist_mock = AsyncMock(side_effect=RuntimeError("history schema mismatch"))
    cleanup_mock = AsyncMock()
    submission_context = TaskSubmissionContext(
        task_type="scail2_action_transfer",
        is_video_task=True,
        user_logger=None,
        prompt="dance",
        saved_inputs=["ref.png", "motion.mp4"],
        metadata={},
        allow_contribute=True,
        final_priority=0,
    )

    with pytest.raises(RuntimeError, match="history schema mismatch"):
        await task_web_terminal_finalization.finalize_monitored_web_task_success(
            backend_task_id="backend-1",
            internal_user_id=123,
            username="tester",
            registry_task_id="registry-1",
            submission_context=submission_context,
            result_path="registry-1__result.mp4",
            extra_outputs={},
            persist_successful_web_history_func=persist_mock,
            cleanup_task_runtime_state_func=cleanup_mock,
            logger=task_web_terminal_finalization.logging.getLogger(__name__),
        )

    persist_mock.assert_awaited_once()
    cleanup_mock.assert_not_awaited()


def test_ltx_history_context_is_merged_into_extra_outputs():
    merged = task_web_terminal_finalization.merge_ltx_history_context_into_extra_outputs(
        task_type="ltx_video",
        extra_outputs={
            "last_frame": {
                "path": "history/ltx-task-2/last_frame.png",
            }
        },
        metadata={
            "ltx_mode": "i2v",
            "ltx_width": 1280,
            "ltx_height": 704,
            "requested_duration": 5,
            "ltx_prev_task_id": "ltx-task-1",
            "ltx_chain_task_ids": ["ltx-task-1"],
            "lora_items": [{"name": "demo.safetensors", "strength": 0.8}],
        },
    )

    assert merged["last_frame"]["path"] == "history/ltx-task-2/last_frame.png"
    assert merged["_ltx_context"] == {
        "ltx_mode": "i2v",
        "ltx_use_end_frame": False,
        "ltx_width": 1280,
        "ltx_height": 704,
        "ltx_duration_seconds": 5,
        "ltx_prev_task_id": "ltx-task-1",
        "ltx_chain_task_ids": ["ltx-task-1"],
        "lora_items": [{"name": "demo.safetensors", "strength": 0.8}],
    }


@pytest.mark.asyncio
async def test_web_success_persists_clean_prompt_and_structured_generation_context():
    persist_mock = AsyncMock()
    cleanup_mock = AsyncMock()
    submission_context = TaskSubmissionContext(
        task_type="img2img_lora",
        is_video_task=False,
        user_logger=None,
        prompt="cinematic portrait",
        saved_inputs=["ref.png"],
        metadata={
            "lora_name": "qwen/YARN_1.0.safetensors",
            "lora_strength": 0.35,
        },
        allow_contribute=True,
        final_priority=0,
    )

    await task_web_terminal_finalization.finalize_monitored_web_task_success(
        backend_task_id="backend-1",
        internal_user_id=123,
        username="tester",
        registry_task_id="registry-1",
        submission_context=submission_context,
        result_path="result.png",
        extra_outputs={},
        persist_successful_web_history_func=persist_mock,
        cleanup_task_runtime_state_func=cleanup_mock,
        logger=task_web_terminal_finalization.logging.getLogger(__name__),
    )

    kwargs = persist_mock.await_args.kwargs
    assert kwargs["prompt"] == "cinematic portrait"
    assert kwargs["extra_outputs"]["_generation_context"] == {
        "version": 1,
        "lora_name": "qwen/YARN_1.0.safetensors",
        "lora_strength": 0.35,
        "public_model_id": "image_realistic",
    }
