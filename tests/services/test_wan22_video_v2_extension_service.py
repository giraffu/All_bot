from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.constants import MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO, MODE_WAN22_VIDEO_V2
from src.services import wan22_video_v2_extension_service as service


@pytest.mark.asyncio
async def test_prepare_wan22_extension_fsm_data_merges_context_and_downloads_tail():
    history = SimpleNamespace(
        type=MODE_WAN22_VIDEO_V2,
        requested_duration=5,
        duration=5,
        extra_outputs={
            "_wan22_context": {
                "wan22_chain_task_ids": ["task-0"],
                "wan22_resolution_preset": "preview",
            }
        },
    )
    load_history = AsyncMock(return_value=history)
    download_last_frame = AsyncMock(return_value="/tmp/tail.png")

    seed = await service.prepare_wan22_extension_fsm_data(
        base_task_id="task-1",
        telegram_user_id=12345,
        username="tester",
        message_meta={
            "wan22_resolution_preset": "hd",
            "wan22_duration_seconds": 8,
            "lora_name": "BreastGrow",
            "lora_strength": 0.75,
        },
        load_history_func=load_history,
        download_last_frame_func=download_last_frame,
    )

    assert seed.base_task_id == "task-1"
    assert seed.history is history
    assert seed.fsm_data == {
        "start_image_path": "/tmp/tail.png",
        "end_image_path": None,
        "use_end_frame": False,
        "resolution_preset": "hd",
        "duration": 8,
        "prompt": "",
        "negative_prompt": "",
        "extension_prev_task_id": "task-1",
        "extension_task_type": MODE_WAN22_VIDEO_V2,
        "lora_name": "BreastGrow",
        "lora_strength": 0.75,
        "chain_task_ids": ["task-0", "task-1"],
    }
    load_history.assert_awaited_once_with(
        task_id="task-1",
        telegram_user_id=12345,
        username="tester",
    )
    download_last_frame.assert_awaited_once_with(history=history)


@pytest.mark.parametrize("task_type", [MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO])
@pytest.mark.asyncio
async def test_prepare_wan22_extension_fsm_data_supports_legacy_wan22_aio_chain(
    task_type,
):
    history = SimpleNamespace(
        type=task_type,
        requested_duration=10,
        duration=10,
        extra_outputs={
            "_wan22_context": {
                "wan22_chain_task_ids": ["legacy-task-0"],
                "wan22_resolution_preset": "standard",
                "lora_name": "BreastGrow" if task_type == MODE_IMAGE_TO_VIDEO else "",
                "lora_strength": 0.9 if task_type == MODE_IMAGE_TO_VIDEO else None,
            }
        },
    )
    load_history = AsyncMock(return_value=history)
    download_last_frame = AsyncMock(return_value="/tmp/legacy-tail.png")

    seed = await service.prepare_wan22_extension_fsm_data(
        base_task_id="legacy-task-1",
        telegram_user_id=12345,
        username="tester",
        message_meta={},
        load_history_func=load_history,
        download_last_frame_func=download_last_frame,
    )

    assert seed.fsm_data["start_image_path"] == "/tmp/legacy-tail.png"
    assert seed.fsm_data["resolution_preset"] == "standard"
    assert seed.fsm_data["duration"] == 10
    assert seed.fsm_data["extension_prev_task_id"] == "legacy-task-1"
    assert seed.fsm_data["extension_task_type"] == task_type
    assert seed.fsm_data["chain_task_ids"] == ["legacy-task-0", "legacy-task-1"]
    if task_type == MODE_IMAGE_TO_VIDEO:
        assert seed.fsm_data["lora_name"] == "BreastGrow"
        assert seed.fsm_data["lora_strength"] == 0.9
    else:
        assert seed.fsm_data["lora_name"] == ""
        assert seed.fsm_data["lora_strength"] is None
    load_history.assert_awaited_once_with(
        task_id="legacy-task-1",
        telegram_user_id=12345,
        username="tester",
    )
    download_last_frame.assert_awaited_once_with(history=history)


@pytest.mark.asyncio
async def test_prepare_wan22_regeneration_fsm_data_reuses_legacy_lora_and_end_frame():
    current_history = SimpleNamespace(
        type=MODE_IMAGE_TO_VIDEO,
        prompt="[standard|5s] [模型: BreastGrow] current prompt",
        requested_duration=5,
        duration=5,
        extra_outputs={},
    )
    prev_history = SimpleNamespace(type=MODE_WAN22_VIDEO_V2)
    load_history = AsyncMock(side_effect=[current_history, prev_history])
    download_last_frame = AsyncMock(return_value="/tmp/start.png")
    download_input_file = AsyncMock(return_value="/tmp/end.png")

    seed = await service.prepare_wan22_regeneration_fsm_data(
        current_task_id="task-3",
        telegram_user_id=12345,
        username="tester",
        message_meta={
            "wan22_prev_task_id": "task-2",
            "wan22_chain_task_ids": ["task-1", "task-2"],
            "wan22_negative_prompt": "neg",
            "wan22_resolution_preset": "standard",
            "wan22_use_end_frame": True,
        },
        load_history_func=load_history,
        download_last_frame_func=download_last_frame,
        download_history_input_file_func=download_input_file,
    )

    assert seed.current_task_id == "task-3"
    assert seed.prev_task_id == "task-2"
    assert seed.current_history is current_history
    assert seed.prev_history is prev_history
    assert seed.fsm_data["start_image_path"] == "/tmp/start.png"
    assert seed.fsm_data["end_image_path"] == "/tmp/end.png"
    assert seed.fsm_data["use_end_frame"] is True
    assert seed.fsm_data["prompt"] == "current prompt"
    assert seed.fsm_data["prefill_prompt"] == "current prompt"
    assert seed.fsm_data["negative_prompt"] == "neg"
    assert seed.fsm_data["extension_prev_task_id"] == "task-2"
    assert seed.fsm_data["extension_task_type"] == MODE_IMAGE_TO_VIDEO
    assert seed.fsm_data["lora_name"] == "BreastGrow"
    assert seed.fsm_data["lora_strength"] == 1.0
    assert seed.fsm_data["chain_task_ids"] == ["task-1", "task-2"]
    assert [call.kwargs["task_id"] for call in load_history.await_args_list] == [
        "task-3",
        "task-2",
    ]
    download_last_frame.assert_awaited_once_with(
        history=prev_history,
        name_hint="wan22_video_v2_regenerate_start",
    )
    download_input_file.assert_awaited_once_with(
        history=current_history,
        index=1,
        name_hint="wan22_video_v2_regenerate_end",
    )


@pytest.mark.asyncio
async def test_prepare_wan22_regeneration_fsm_data_rejects_missing_prev_task():
    current_history = SimpleNamespace(
        type=MODE_WAN22_VIDEO_V2,
        prompt="prompt",
        requested_duration=5,
        extra_outputs={},
    )
    load_history = AsyncMock(return_value=current_history)
    download_last_frame = AsyncMock()

    with pytest.raises(service.Wan22VideoV2MissingPreviousSegmentError):
        await service.prepare_wan22_regeneration_fsm_data(
            current_task_id="task-3",
            telegram_user_id=12345,
            username="tester",
            message_meta={},
            load_history_func=load_history,
            download_last_frame_func=download_last_frame,
        )

    load_history.assert_awaited_once()
    download_last_frame.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_wan22_stitch_plan_recovers_full_chain_in_order():
    current_history = SimpleNamespace(
        task_id="task-3",
        user_id=321,
        extra_outputs={
            "_wan22_context": {
                "wan22_chain_task_ids": ["task-1", "task-2"],
            }
        },
    )
    previous_histories = [
        SimpleNamespace(task_id="task-1", user_id=321),
        SimpleNamespace(task_id="task-2", user_id=321),
    ]
    load_history = AsyncMock(side_effect=[current_history, *previous_histories])

    plan = await service.build_wan22_stitch_plan(
        current_task_id="task-3",
        telegram_user_id=12345,
        username="tester",
        message_meta={},
        load_history_func=load_history,
    )

    assert plan.internal_user_id == 321
    assert plan.source_task_id == "task-3"
    assert plan.full_task_ids == ["task-1", "task-2", "task-3"]
    assert [history.task_id for history in plan.histories] == [
        "task-1",
        "task-2",
        "task-3",
    ]
    assert [call.kwargs["task_id"] for call in load_history.await_args_list] == [
        "task-3",
        "task-1",
        "task-2",
    ]


@pytest.mark.parametrize("task_type", [MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO])
@pytest.mark.asyncio
async def test_build_wan22_stitch_plan_supports_legacy_wan22_aio_chain_in_order(
    task_type,
):
    current_history = SimpleNamespace(
        task_id="legacy-task-3",
        type=task_type,
        user_id=321,
        extra_outputs={
            "_wan22_context": {
                "wan22_chain_task_ids": ["legacy-task-1", "legacy-task-2"],
            }
        },
    )
    previous_histories = [
        SimpleNamespace(task_id="legacy-task-1", type=task_type, user_id=321),
        SimpleNamespace(task_id="legacy-task-2", type=task_type, user_id=321),
    ]
    load_history = AsyncMock(side_effect=[current_history, *previous_histories])

    plan = await service.build_wan22_stitch_plan(
        current_task_id="legacy-task-3",
        telegram_user_id=12345,
        username="tester",
        message_meta={},
        load_history_func=load_history,
    )

    assert plan.internal_user_id == 321
    assert plan.source_task_id == "legacy-task-3"
    assert plan.full_task_ids == [
        "legacy-task-1",
        "legacy-task-2",
        "legacy-task-3",
    ]
    assert [history.task_id for history in plan.histories] == [
        "legacy-task-1",
        "legacy-task-2",
        "legacy-task-3",
    ]
    assert [call.kwargs["task_id"] for call in load_history.await_args_list] == [
        "legacy-task-3",
        "legacy-task-1",
        "legacy-task-2",
    ]


@pytest.mark.asyncio
async def test_build_wan22_stitch_plan_rejects_single_segment():
    current_history = SimpleNamespace(task_id="task-1", user_id=321, extra_outputs={})
    load_history = AsyncMock(return_value=current_history)

    with pytest.raises(service.Wan22VideoV2ExtensionError, match="至少需要两段"):
        await service.build_wan22_stitch_plan(
            current_task_id="task-1",
            telegram_user_id=12345,
            username="tester",
            message_meta={},
            load_history_func=load_history,
        )

    load_history.assert_awaited_once()
