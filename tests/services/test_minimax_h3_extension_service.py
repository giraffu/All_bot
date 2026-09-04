from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services import minimax_h3_extension_service as service


def _history(
    *,
    task_id="segment-1",
    task_type="minimax_h3_ref2v",
    context=None,
    last_frame="task-results/segment-1/last_frame.png",
    allow_contribute=True,
    width=None,
    height=None,
):
    return SimpleNamespace(
        task_id=task_id,
        user_id=7,
        type=task_type,
        extra_outputs={
            "_minimax_h3_context": context
            or {
                "version": 2,
                "mode": task_type.removeprefix("minimax_h3_"),
                "requested_duration": 5,
                "resolution_preset": "preview",
                "aspect_ratio": "16:9" if task_type.endswith("ref2v") else "source",
                "lora_items": [],
            },
            "last_frame": {"path": last_frame},
        },
        allow_contribute=allow_contribute,
        output_file=f"task-results/{task_id}/primary.mp4",
        prompt=f"prompt {task_id}",
        duration=5,
        requested_duration=5,
        width=width,
        height=height,
    )


@pytest.mark.asyncio
async def test_web_extension_anchors_owned_tail_frame_and_builds_canonical_chain(
    monkeypatch,
):
    parent = _history(allow_contribute=False)
    monkeypatch.setattr(
        service,
        "load_owned_minimax_h3_history_for_internal_user",
        AsyncMock(return_value=parent),
    )

    prepared = await service.prepare_minimax_h3_web_extension(
        prev_task_id="segment-1",
        internal_user_id=7,
        target_task_type="minimax_h3_ref2v",
        client_images=[],
    )

    assert prepared.images == ("task-results/segment-1/last_frame.png",)
    assert prepared.reference_video is None
    assert prepared.execution_task_type == "minimax_h3_i2v"
    assert prepared.aspect_ratio == "16:9"
    assert prepared.metadata == {
        "minimax_h3_prev_task_id": "segment-1",
        "minimax_h3_chain_task_ids": ["segment-1"],
    }
    assert prepared.allow_contribute is False


@pytest.mark.asyncio
async def test_web_extension_rejects_client_supplied_i2v_start_frame():
    with pytest.raises(service.MiniMaxH3ExtensionError, match="不能上传首帧"):
        await service.prepare_minimax_h3_web_extension(
            prev_task_id="segment-1",
            internal_user_id=7,
            target_task_type="minimax_h3_ref2v",
            client_images=["forged.png"],
        )


@pytest.mark.asyncio
async def test_web_extension_keeps_tail_frame_path_for_optional_end_frame(monkeypatch):
    parent = _history()
    monkeypatch.setattr(
        service,
        "load_owned_minimax_h3_history_for_internal_user",
        AsyncMock(return_value=parent),
    )
    validate = AsyncMock()

    prepared = await service.prepare_minimax_h3_web_extension(
        prev_task_id="segment-1",
        internal_user_id=7,
        target_task_type="minimax_h3_flf2v",
        client_images=["web_uploads/7/end.png"],
        frame_aspect_validator=validate,
    )

    assert prepared.images == (
        "task-results/segment-1/last_frame.png",
        "web_uploads/7/end.png",
    )
    assert prepared.reference_video is None
    assert prepared.aspect_ratio is None


@pytest.mark.asyncio
async def test_bot_extension_downloads_only_tail_frame_for_i2v_anchor(
    monkeypatch, tmp_path
):
    parent = _history()
    monkeypatch.setattr(service, "FSM_TEMP_DIR", tmp_path)
    monkeypatch.setattr(
        service.user_core,
        "get_or_create_user_by_telegram",
        AsyncMock(return_value=(SimpleNamespace(id=7), False)),
    )
    monkeypatch.setattr(
        service,
        "load_owned_minimax_h3_history_for_internal_user",
        AsyncMock(return_value=parent),
    )
    download = MagicMock()
    monkeypatch.setattr(service.storage, "download_file", download)

    seed = await service.prepare_minimax_h3_extension_fsm_data(
        prev_task_id="segment-1",
        telegram_user_id=99,
        username="alice",
    )

    assert len(seed.fsm_data["images"]) == 1
    assert seed.fsm_data["images"][0] == seed.fsm_data["extension_start_frame"]
    assert seed.fsm_data["reference_video"] is None
    assert seed.fsm_data["minimax_h3_execution_task_type"] == "minimax_h3_i2v"
    assert download.call_count == 1


def test_video_extension_uses_nearest_supported_parent_aspect():
    history = _history(task_type="minimax_h3_i2v", width=720, height=1280)

    assert service.resolve_minimax_h3_extension_aspect_ratio(history) == "9:16"


def test_h3_stitched_record_has_no_segment_index_and_cannot_extend():
    extra_outputs = service.build_minimax_h3_stitched_extra_outputs(
        chain_task_ids=["segment-1", "segment-2"],
        source_task_id="segment-2",
    )
    history = _history()
    history.extra_outputs = extra_outputs

    assert service.is_minimax_h3_stitched_result(extra_outputs) is True
    assert service.resolve_minimax_h3_segment_index(extra_outputs) is None
    with pytest.raises(service.MiniMaxH3ExtensionError, match="拼接结果不能"):
        service.resolve_minimax_h3_last_frame_output_file(history)


def test_h3_chain_context_rejects_disconnected_parent():
    history = _history(
        task_id="segment-3",
        task_type="minimax_h3_i2v",
        context={
            "version": 2,
            "mode": "i2v",
            "requested_duration": 5,
            "resolution_preset": "preview",
            "aspect_ratio": "source",
            "lora_items": [],
            "prev_task_id": "segment-x",
            "chain_task_ids": ["segment-1", "segment-2"],
        },
    )

    with pytest.raises(service.MiniMaxH3ExtensionError, match="有效的生成上下文"):
        service.build_minimax_h3_full_chain_task_ids(history)


@pytest.mark.asyncio
async def test_h3_stitch_downloads_segments_in_order_before_media_normalization(
    monkeypatch,
):
    first = _history(task_id="segment-1")
    second = _history(task_id="segment-2")
    get_bytes = MagicMock(side_effect=[b"first", b"second"])
    normalize = AsyncMock(return_value=b"stitched")
    monkeypatch.setattr(service.storage, "get_file_bytes", get_bytes)
    monkeypatch.setattr(service, "stitch_qqcc_video_segments", normalize)

    result = await service.stitch_minimax_h3_history_videos([first, second])

    assert result == b"stitched"
    assert [call.args[0] for call in get_bytes.call_args_list] == [
        "task-results/segment-1/primary.mp4",
        "task-results/segment-2/primary.mp4",
    ]
    normalize.assert_awaited_once_with([b"first", b"second"])


@pytest.mark.asyncio
async def test_h3_stitch_is_idempotent_when_deterministic_history_exists(monkeypatch):
    first = _history(task_id="segment-1", task_type="minimax_h3_i2v")
    second = _history(
        task_id="segment-2",
        task_type="minimax_h3_i2v",
        context={
            "version": 2,
            "mode": "i2v",
            "requested_duration": 5,
            "resolution_preset": "preview",
            "aspect_ratio": "source",
            "lora_items": [],
            "prev_task_id": "segment-1",
            "chain_task_ids": ["segment-1"],
        },
    )
    existing = SimpleNamespace(output_file="task-results/existing/primary.mp4")

    class _Result:
        def scalar_one_or_none(self):
            return existing

    class _Session:
        async def execute(self, _statement):
            return _Result()

    get_bytes = MagicMock(return_value=b"already-stitched")
    stitch = AsyncMock(return_value=b"must-not-run")
    monkeypatch.setattr(service.storage, "get_file_bytes", get_bytes)

    result = await service.stitch_minimax_h3_histories_and_create_history(
        histories=[first, second],
        user_id=7,
        source_task_id="segment-2",
        source="web",
        session=_Session(),
        stitch_func=stitch,
    )

    assert result.video_bytes == b"already-stitched"
    assert result.history is existing
    stitch.assert_not_awaited()


@pytest.mark.asyncio
async def test_h3_storage_frame_validation_rejects_mismatched_aspect(monkeypatch):
    from io import BytesIO

    from PIL import Image

    def _image(width: int, height: int) -> bytes:
        output = BytesIO()
        Image.new("RGB", (width, height)).save(output, format="PNG")
        return output.getvalue()

    monkeypatch.setattr(
        service.storage,
        "get_file_bytes",
        MagicMock(side_effect=[_image(1280, 720), _image(720, 1280)]),
    )

    with pytest.raises(service.MiniMaxH3ExtensionError, match="比例需与上一段尾帧一致"):
        await service.validate_minimax_h3_storage_frame_aspects(
            ["task-results/parent/last.png", "web_uploads/7/end.png"]
        )
