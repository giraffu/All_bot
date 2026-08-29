from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.services.minimax_h3_extension_service import MiniMaxH3ExtensionError
from src.web_api.services import minimax_h3_history_chain_service as service
from src.web_api.schemas.user_schema import HistoryItem


def _item(task_id: str) -> HistoryItem:
    return HistoryItem(
        id=1,
        task_id=task_id,
        type="minimax_h3_i2v",
        prompt="prompt",
        input_file=None,
        output_file=f"task-results/{task_id}/primary.mp4",
        created_at=datetime.now(),
    )


@pytest.mark.asyncio
async def test_chain_payload_uses_owned_ordered_history_and_public_presenter(monkeypatch):
    histories = [
        SimpleNamespace(task_id="h3-a"),
        SimpleNamespace(task_id="h3-b"),
    ]
    items = [_item("h3-a"), _item("h3-b")]
    load = AsyncMock(return_value=histories)
    fetch_public = AsyncMock(return_value={"h3-a"})
    build = AsyncMock(return_value=items)
    monkeypatch.setattr(service, "load_minimax_h3_chain_for_internal_user", load)
    monkeypatch.setattr(service, "fetch_active_public_gallery_task_ids", fetch_public)
    monkeypatch.setattr(service, "build_user_history_payload", build)
    db = object()

    response = await service.get_minimax_h3_history_chain_payload(
        task_id="h3-b",
        current_user=SimpleNamespace(id=7),
        db=db,
    )

    assert response.current_task_id == "h3-b"
    assert response.items == items
    load.assert_awaited_once_with(
        task_id="h3-b",
        internal_user_id=7,
        session=db,
    )
    fetch_public.assert_awaited_once()
    build.assert_awaited_once_with(histories=histories, gallery_task_ids={"h3-a"})


@pytest.mark.asyncio
async def test_chain_payload_translates_ownership_or_chain_errors_to_400(monkeypatch):
    monkeypatch.setattr(
        service,
        "load_minimax_h3_chain_for_internal_user",
        AsyncMock(side_effect=MiniMaxH3ExtensionError("链路不可用")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.get_minimax_h3_history_chain_payload(
            task_id="foreign",
            current_user=SimpleNamespace(id=7),
            db=object(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "链路不可用"


@pytest.mark.asyncio
async def test_stitch_response_returns_the_idempotent_history_payload(monkeypatch):
    histories = [SimpleNamespace(task_id="h3-a"), SimpleNamespace(task_id="h3-b")]
    stitched_history = SimpleNamespace(task_id="h3-chain")
    item = SimpleNamespace(task_id="h3-chain", type="minimax_h3_i2v")
    monkeypatch.setattr(
        service,
        "load_minimax_h3_chain_for_internal_user",
        AsyncMock(return_value=histories),
    )
    stitch = AsyncMock(
        return_value=SimpleNamespace(history=stitched_history, video_bytes=b"video")
    )
    monkeypatch.setattr(service, "stitch_minimax_h3_histories_and_create_history", stitch)
    monkeypatch.setattr(
        service,
        "build_user_history_payload",
        AsyncMock(return_value=[item]),
    )

    result = await service.stitch_minimax_h3_history_chain_response(
        task_id="h3-b",
        current_user=SimpleNamespace(id=7),
        db=object(),
    )

    assert result is item
    stitch.assert_awaited_once()
