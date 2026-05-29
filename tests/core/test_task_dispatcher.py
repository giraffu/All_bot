from unittest.mock import AsyncMock

import pytest

from src.core.task_dispatcher import (
    BaseVideoStrategy,
    DefaultImageStrategy,
    FaceSwapStrategy,
    LtxVideoStrategy,
    StrategyFactory,
    Wan22VideoV2Strategy,
)
from src.constants import (
    MODE_I2I_PRO,
    MODE_IMAGE_TO_VIDEO,
    MODE_IMG2IMG_LORA,
    MODE_TXT2IMG,
    MODE_WAN22_VIDEO_V2,
)


def _patch_dispatch_image_service(monkeypatch, **methods):
    fake_service = type("FakeImageService", (), methods)()
    monkeypatch.setattr(
        "src.core.task_dispatcher._get_dispatch_image_service",
        lambda: fake_service,
    )
    return fake_service


def test_strategy_factory_returns_correct_strategy():
    # Face swap
    strategy = StrategyFactory.get_strategy("face_swap")
    assert isinstance(strategy, FaceSwapStrategy)

    # LTX Video
    strategy = StrategyFactory.get_strategy("ltx_video")
    assert isinstance(strategy, LtxVideoStrategy)

    strategy = StrategyFactory.get_strategy(MODE_WAN22_VIDEO_V2)
    assert isinstance(strategy, Wan22VideoV2Strategy)

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


def test_base_video_strategy_normalizes_legacy_image_to_video_mode():
    strategy = BaseVideoStrategy("MODE_IMAGE_TO_VIDEO")

    assert strategy.mode == MODE_IMAGE_TO_VIDEO


@pytest.mark.parametrize(
    ("strategy", "inputs"),
    [
        (
            DefaultImageStrategy(MODE_IMG2IMG_LORA),
            {
                "saved_input_images": ["demo/input.png"],
                "lora_name": "qwen/YARN_1.0.safetensors",
                "lora_strength": 0.3,
            },
        ),
        (
            BaseVideoStrategy("video_lora"),
            {
                "saved_input_images": ["demo/input.png"],
                "lora_name": "BreastGrow",
                "lora_strength": 0.8,
            },
        ),
    ],
)
def test_strategy_metadata_keeps_lora_context(strategy, inputs):
    metadata = strategy.get_metadata(inputs)

    assert metadata["saved_inputs"] == ["demo/input.png"]
    assert metadata["lora_name"] == inputs["lora_name"]
    assert metadata["lora_strength"] == inputs["lora_strength"]


@pytest.mark.parametrize(
    ("legacy_task_type", "expected_mode"),
    [
        ("MODE_I2I_PRO", MODE_I2I_PRO),
        ("MODE_IMG2IMG_LORA", MODE_IMG2IMG_LORA),
        ("t2i-pornmaster-turbo", MODE_TXT2IMG),
    ],
)
def test_strategy_factory_normalizes_legacy_string_task_types(
    legacy_task_type, expected_mode
):
    strategy = StrategyFactory.get_strategy(legacy_task_type)

    assert isinstance(strategy, DefaultImageStrategy)
    assert strategy.mode == expected_mode


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


def test_base_video_strategy_face_video_upload_paths_accept_step_modes():
    strategy = BaseVideoStrategy("face_video_step1")

    file_paths = strategy.get_file_paths_to_upload(
        {"face_image": "face.png", "target_video": "target.mp4"}
    )

    assert file_paths == ["face.png", "target.mp4"]


@pytest.mark.asyncio
async def test_default_image_strategy_normalizes_legacy_lora_mode_before_submit(
    monkeypatch,
):
    strategy = DefaultImageStrategy("MODE_IMG2IMG_LORA")
    submit_mock = AsyncMock(return_value="backend-task-id")
    _patch_dispatch_image_service(
        monkeypatch,
        submit_img2img_lora_task=submit_mock,
    )

    result = await strategy.submit_task(
        "task-1",
        {
            "prompt": "merge styles",
            "saved_input_images": ["demo/input.png"],
            "lora_name": "test-lora",
        },
        priority=2,
    )

    assert result == "backend-task-id"
    submit_mock.assert_awaited_once_with(
        "task-1",
        prompt="merge styles",
        image_paths=["demo/input.png"],
        lora_name="test-lora",
        negative_prompt=" ",
        priority=2,
        lora_strength=1.0,
    )


@pytest.mark.asyncio
async def test_default_image_strategy_routes_txt2img_to_legacy_t2i_endpoint(
    monkeypatch,
):
    strategy = DefaultImageStrategy(MODE_TXT2IMG)
    submit_mock = AsyncMock(return_value="backend-task-id")
    _patch_dispatch_image_service(
        monkeypatch,
        submit_txt2img_task=submit_mock,
    )

    result = await strategy.submit_task(
        "task-1",
        {
            "prompt": "moonlit courtyard",
            "saved_input_images": [],
        },
        priority=4,
    )

    assert result == "backend-task-id"
    submit_mock.assert_awaited_once_with(
        prompt="moonlit courtyard",
        priority=4,
    )


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
    _patch_dispatch_image_service(
        monkeypatch,
        submit_ltx_video_task=submit_mock,
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
        lora_name=None,
        lora_strength=None,
        lora_items=None,
        width=1280,
        height=704,
        length=expected_length,
        priority=3,
    )


@pytest.mark.asyncio
async def test_ltx_video_submit_task_forwards_optional_lora_context(monkeypatch):
    strategy = StrategyFactory.get_strategy("ltx_video")
    submit_mock = AsyncMock(return_value="backend-task-id")
    _patch_dispatch_image_service(
        monkeypatch,
        submit_ltx_video_task=submit_mock,
    )

    result = await strategy.submit_task(
        "task-1",
        {
            "prompt": "cinematic motion",
            "resolution": "1280x704",
            "duration": "10s",
            "lora_name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
            "lora_strength": 0.8,
            "saved_input_images": ["demo/input.png"],
        },
        priority=5,
    )

    assert result == "backend-task-id"
    submit_mock.assert_awaited_once_with(
        "task-1",
        prompt="cinematic motion",
        image_path="demo/input.png",
        lora_name="ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
        lora_strength=0.8,
        lora_items=None,
        width=1280,
        height=704,
        length=10,
        priority=5,
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
    _patch_dispatch_image_service(
        monkeypatch,
        submit_image_to_video_task=submit_lora_mock,
        submit_perfect_video_edit=submit_edit_mock,
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
    _patch_dispatch_image_service(
        monkeypatch,
        submit_perfect_video_insert_task=submit_insert_mock,
        submit_image_to_video_task=submit_lora_mock,
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


@pytest.mark.asyncio
async def test_wan22_video_v2_submit_task_normalizes_optional_end_frame(monkeypatch):
    strategy = StrategyFactory.get_strategy(MODE_WAN22_VIDEO_V2)
    submit_mock = AsyncMock(return_value="backend-task-id")
    _patch_dispatch_image_service(
        monkeypatch,
        submit_wan22_video_v2_task=submit_mock,
    )

    result = await strategy.submit_task(
        "task-1",
        {
            "prompt": "cinematic motion",
            "negative_prompt": "blurry",
            "saved_input_images": ["demo/start.png", "demo/end.png"],
            "use_end_frame": True,
            "color_match": True,
            "perfect_loop": False,
            "upscale": True,
            "extract_last_frame": True,
        },
        priority=5,
    )

    assert result == "backend-task-id"
    submit_mock.assert_awaited_once_with(
        "task-1",
        prompt="cinematic motion",
        image_path="demo/start.png",
        end_image_path="demo/end.png",
        negative_prompt="blurry",
        use_end_frame=True,
        color_match=True,
        perfect_loop=False,
        upscale=True,
        extract_last_frame=True,
        length=5,
        priority=5,
    )


@pytest.mark.asyncio
async def test_wan22_video_v2_submit_task_falls_back_to_i2v_without_end_frame(monkeypatch):
    strategy = StrategyFactory.get_strategy(MODE_WAN22_VIDEO_V2)
    submit_mock = AsyncMock(return_value="backend-task-id")
    _patch_dispatch_image_service(
        monkeypatch,
        submit_wan22_video_v2_task=submit_mock,
    )

    result = await strategy.submit_task(
        "task-1",
        {
            "prompt": "cinematic motion",
            "saved_input_images": ["demo/start.png"],
            "use_end_frame": True,
        },
        priority=1,
    )

    assert result == "backend-task-id"
    submit_mock.assert_awaited_once_with(
        "task-1",
        prompt="cinematic motion",
        image_path="demo/start.png",
        end_image_path=None,
        negative_prompt=" ",
        use_end_frame=False,
        color_match=False,
        perfect_loop=False,
        upscale=False,
        extract_last_frame=False,
        length=5,
        priority=1,
    )
