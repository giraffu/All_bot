from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.constants import MODE_LTX_VIDEO
from src.services import ltx_video_extension_service as service


def _history(
    task_id: str,
    *,
    user_id: int = 321,
    requested_duration: int | None = 10,
    billing_resolution: str | None = "1280x704",
    extra_outputs: dict | None = None,
    task_type: str = MODE_LTX_VIDEO,
):
    return SimpleNamespace(
        task_id=task_id,
        user_id=user_id,
        type=task_type,
        requested_duration=requested_duration,
        billing_resolution=billing_resolution,
        extra_outputs=extra_outputs or {},
    )


@pytest.mark.asyncio
async def test_prepare_ltx_extension_fsm_data_restores_chain_lora_and_tail_frame():
    history = _history(
        "ltx-task-2",
        requested_duration=None,
        extra_outputs={
            "last_frame": {"path": "history/ltx-task-2/last.png"},
            "_ltx_context": {
                "ltx_duration_seconds": 10,
                "ltx_chain_task_ids": ["ltx-task-1"],
                "lora_items": [
                    {
                        "name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
                        "strength": 0.8,
                    }
                ],
            },
        },
    )
    load_history = AsyncMock(return_value=history)
    download_last_frame = AsyncMock(return_value="/tmp/ltx-tail.png")

    seed = await service.prepare_ltx_extension_fsm_data(
        base_task_id="ltx-task-2",
        telegram_user_id=12345,
        username="tester",
        meta={},
        load_history_func=load_history,
        download_last_frame_func=download_last_frame,
    )

    assert seed.base_task_id == "ltx-task-2"
    assert seed.history is history
    assert seed.fsm_data == {
        "resolution": "1280x704",
        "duration": "10s",
        "ltx_mode": "i2v",
        "image_path": "/tmp/ltx-tail.png",
        "end_image_path": None,
        "video_path": None,
        "lora_items": [
            {
                "name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
                "strength": 0.8,
            }
        ],
        "is_extension": True,
        "extension_prev_task_id": "ltx-task-2",
        "chain_task_ids": ["ltx-task-1", "ltx-task-2"],
    }
    load_history.assert_awaited_once_with(
        task_id="ltx-task-2",
        telegram_user_id=12345,
        username="tester",
    )
    download_last_frame.assert_awaited_once_with(history=history)


@pytest.mark.asyncio
async def test_prepare_ltx_extension_fsm_data_accepts_legacy_lora_fields():
    history = _history(
        "ltx-task-2",
        extra_outputs={"last_frame": {"path": "tail.png"}},
    )
    load_history = AsyncMock(return_value=history)
    download_last_frame = AsyncMock(return_value="/tmp/ltx-tail.png")

    seed = await service.prepare_ltx_extension_fsm_data(
        base_task_id="ltx-task-2",
        telegram_user_id=12345,
        username="tester",
        meta={
            "lora_name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
            "lora_strength": "0.7",
        },
        load_history_func=load_history,
        download_last_frame_func=download_last_frame,
    )

    assert seed.fsm_data["lora_items"] == [
        {
            "name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
            "strength": 0.7,
        }
    ]


@pytest.mark.asyncio
async def test_prepare_ltx_extension_fsm_data_propagates_existing_extension_error():
    load_history = AsyncMock(
        side_effect=service.LtxVideoExtensionError(
            "未找到对应的视频记录，或该记录不属于您。"
        )
    )

    with pytest.raises(service.LtxVideoExtensionError, match="不属于您"):
        await service.prepare_ltx_extension_fsm_data(
            base_task_id="ltx-task-2",
            telegram_user_id=12345,
            username="tester",
            meta={},
            load_history_func=load_history,
            download_last_frame_func=AsyncMock(),
        )


@pytest.mark.asyncio
async def test_prepare_ltx_extension_fsm_data_rejects_missing_last_frame():
    history = _history("ltx-task-2", extra_outputs={})

    with pytest.raises(service.LtxVideoExtensionError, match="尾帧图片"):
        await service.prepare_ltx_extension_fsm_data(
            base_task_id="ltx-task-2",
            telegram_user_id=12345,
            username="tester",
            meta={},
            load_history_func=AsyncMock(return_value=history),
            download_last_frame_func=service.download_ltx_last_frame_to_fsm_temp,
        )


@pytest.mark.asyncio
async def test_build_ltx_stitch_plan_loads_full_chain_in_order_from_history_context():
    histories = {
        "ltx-task-1": _history("ltx-task-1"),
        "ltx-task-2": _history("ltx-task-2"),
        "ltx-task-3": _history(
            "ltx-task-3",
            extra_outputs={
                "_ltx_context": {
                    "ltx_chain_task_ids": ["ltx-task-1", "ltx-task-2"]
                }
            },
        ),
    }
    load_order = []

    async def load_history(**kwargs):
        load_order.append(kwargs["task_id"])
        return histories[kwargs["task_id"]]

    plan = await service.build_ltx_stitch_plan(
        current_task_id="ltx-task-3",
        telegram_user_id=12345,
        username="tester",
        meta={},
        load_history_func=load_history,
    )

    assert plan.full_task_ids == ["ltx-task-1", "ltx-task-2", "ltx-task-3"]
    assert [history.task_id for history in plan.histories] == plan.full_task_ids
    assert plan.internal_user_id == 321
    assert plan.source_task_id == "ltx-task-3"
    assert load_order == ["ltx-task-3", "ltx-task-1", "ltx-task-2"]


@pytest.mark.asyncio
async def test_build_ltx_stitch_plan_rejects_single_segment_chain():
    with pytest.raises(service.LtxVideoExtensionError, match="至少需要两段"):
        await service.build_ltx_stitch_plan(
            current_task_id="ltx-task-1",
            telegram_user_id=12345,
            username="tester",
            meta={},
            load_history_func=AsyncMock(return_value=_history("ltx-task-1")),
        )
