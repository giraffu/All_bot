from unittest.mock import AsyncMock

import pytest

from src.core.task_dispatcher import (
    StrategyFactory,
    DefaultImageStrategy,
    FaceSwapStrategy,
    BaseVideoStrategy,
    LtxVideoStrategy,
)
from src.constants import MODE_I2I_PRO, MODE_IMAGE_TO_VIDEO


def test_strategy_factory_returns_correct_strategy():
    # Face swap
    strategy = StrategyFactory.get_strategy("face_swap")
    assert isinstance(strategy, FaceSwapStrategy)

    # LTX Video
    strategy = StrategyFactory.get_strategy("ltx_video")
    assert isinstance(strategy, LtxVideoStrategy)

    # Standard Video
    strategy = StrategyFactory.get_strategy("doggy_style")
    assert isinstance(strategy, BaseVideoStrategy)
    assert strategy.mode == "doggy_style"

    # I2I Pro (Default Image Strategy)
    strategy = StrategyFactory.get_strategy(MODE_I2I_PRO)
    assert isinstance(strategy, DefaultImageStrategy)
    assert strategy.mode == MODE_I2I_PRO

    # Default Image (fallback)
    strategy = StrategyFactory.get_strategy("unknown_mode")
    assert isinstance(strategy, DefaultImageStrategy)
    assert strategy.mode == "unknown_mode"


def test_video_strategy_cost_calculation():
    strategy = StrategyFactory.get_strategy("doggy_style")
    # Base doggy style cost is 6, 512p multiplier is 1.0, 5s multiplier is 1.0
    cost = strategy.get_cost({"resolution": "512p", "duration": "5s"})
    assert cost == 6

    # 720p base is 18, 5s multiplier is 1.0
    cost = strategy.get_cost({"resolution": "720p", "duration": "5s"})
    assert cost == 18

    # 720p base is 18, 8s multiplier is 2.0
    cost = strategy.get_cost({"resolution": "720p", "duration": "8s"})
    assert cost == 36


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("duration", "expected_length"),
    [(5, 5), ("10s", 10), (15, 15), ("20", 20)],
)
async def test_ltx_video_submit_task_passes_seconds_to_workflow_slider(
    monkeypatch, duration, expected_length
):
    strategy = StrategyFactory.get_strategy("ltx_video")
    submit_mock = AsyncMock(return_value="backend-task-id")
    monkeypatch.setattr(
        "src.core.task_dispatcher.image_service.submit_ltx_video_task", submit_mock
    )

    result = await strategy.submit_task(
        "task-1",
        {
            "prompt": "cinematic motion",
            "resolution": "1280x704",
            "duration": duration,
            "saved_input_images": ["demo/input.png"],
        },
        priority=3,
    )

    assert result == "backend-task-id"
    submit_mock.assert_awaited_once_with(
        "task-1",
        prompt="cinematic motion",
        image_path="demo/input.png",
        width=1280,
        height=704,
        length=expected_length,
        priority=3,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "lora_name", "expected_backend_task_id", "use_lora_endpoint"),
    [
        (MODE_IMAGE_TO_VIDEO, "BreastGrow", "backend-lora", True),
        (MODE_IMAGE_TO_VIDEO, "", "backend-edit", False),
        ("custom_video", "BreastGrow", "backend-lora", True),
        ("custom_video", "", "backend-edit", False),
        ("video_edit", "BreastGrow", "backend-lora", True),
        ("perfect_video_edit", "BreastGrow", "backend-lora", True),
    ],
)
async def test_base_video_strategy_routes_image_to_video_modes_by_lora_name(
    monkeypatch, mode, lora_name, expected_backend_task_id, use_lora_endpoint
):
    strategy = StrategyFactory.get_strategy(mode)
    submit_lora_mock = AsyncMock(return_value="backend-lora")
    submit_edit_mock = AsyncMock(return_value="backend-edit")
    monkeypatch.setattr(
        "src.core.task_dispatcher.image_service.submit_perfect_video_lora",
        submit_lora_mock,
    )
    monkeypatch.setattr(
        "src.core.task_dispatcher.image_service.submit_perfect_video_edit",
        submit_edit_mock,
    )

    result = await strategy.submit_task(
        "task-1",
        {
            "prompt": "cinematic motion",
            "resolution": "720p",
            "duration": "8s",
            "lora_name": lora_name,
            "saved_input_images": ["demo/input.png"],
        },
        priority=3,
    )

    assert result == expected_backend_task_id
    if use_lora_endpoint:
        submit_lora_mock.assert_awaited_once_with(
            "task-1",
            prompt="cinematic motion",
            image_path="demo/input.png",
            lora_name=lora_name,
            priority=3,
            width=720,
            height=720,
            length=129,
        )
        submit_edit_mock.assert_not_awaited()
    else:
        submit_edit_mock.assert_awaited_once_with(
            "task-1",
            prompt="cinematic motion",
            image_path="demo/input.png",
            priority=3,
            width=720,
            height=720,
            length=129,
        )
        submit_lora_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_base_video_strategy_keeps_special_video_modes_ahead_of_lora_branch(
    monkeypatch,
):
    strategy = StrategyFactory.get_strategy("doggy_style")
    submit_insert_mock = AsyncMock(return_value="backend-insert")
    submit_lora_mock = AsyncMock(return_value="backend-lora")
    monkeypatch.setattr(
        "src.core.task_dispatcher.image_service.submit_perfect_video_insert_task",
        submit_insert_mock,
    )
    monkeypatch.setattr(
        "src.core.task_dispatcher.image_service.submit_perfect_video_lora",
        submit_lora_mock,
    )

    result = await strategy.submit_task(
        "task-1",
        {
            "prompt": "cinematic motion",
            "resolution": "720p",
            "duration": "8s",
            "lora_name": "BreastGrow",
            "saved_input_images": ["demo/input.png"],
        },
        priority=3,
    )

    assert result == "backend-insert"
    submit_insert_mock.assert_awaited_once_with(
        "task-1",
        prompt="cinematic motion",
        image_path="demo/input.png",
        width=720,
        height=720,
        length=129,
        priority=3,
    )
    submit_lora_mock.assert_not_awaited()
