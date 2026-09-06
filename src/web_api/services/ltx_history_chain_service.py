from fastapi import HTTPException

from src.services.ltx_video_extension_service import (
    LtxVideoExtensionError,
    LtxVideoPersistenceError,
    build_ltx_full_chain_task_ids,
    extract_ltx_history_context,
    load_owned_ltx_history_for_internal_user,
    stitch_ltx_histories_and_create_history,
)
from src.web_api.schemas.user_schema import HistoryItem, LtxHistoryChainResponse
from src.web_api.services.history_query_service import (
    fetch_active_public_gallery_task_ids,
    fetch_owned_histories_by_task_ids,
)
from src.web_api.services.history_response_builder import build_user_history_payload


async def _load_current_ltx_history(*, task_id: str, current_user) -> object:
    try:
        return await load_owned_ltx_history_for_internal_user(
            task_id=task_id,
            internal_user_id=current_user.id,
        )
    except LtxVideoExtensionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _resolve_chain_task_ids(history) -> list[str]:
    context = extract_ltx_history_context(getattr(history, "extra_outputs", None))
    current_task_id = str(getattr(history, "task_id", "") or "").strip()
    chain_task_ids = context.get("ltx_chain_task_ids") or []
    if not chain_task_ids:
        prev_task_id = str(context.get("ltx_prev_task_id") or "").strip()
        chain_task_ids = [prev_task_id] if prev_task_id else []
    return build_ltx_full_chain_task_ids(
        chain_task_ids=chain_task_ids,
        current_task_id=current_task_id,
    )


async def get_ltx_history_chain_payload(
    *,
    task_id: str,
    current_user,
    db,
) -> LtxHistoryChainResponse:
    current_history = await _load_current_ltx_history(
        task_id=task_id,
        current_user=current_user,
    )
    chain_task_ids = _resolve_chain_task_ids(current_history)
    histories = await fetch_owned_histories_by_task_ids(
        db=db,
        task_ids=chain_task_ids,
        current_user_id=current_user.id,
    )
    histories_by_task_id = {
        str(getattr(history, "task_id", "") or "").strip(): history for history in histories
    }
    ordered_histories = [
        histories_by_task_id[current_task_id]
        for current_task_id in chain_task_ids
        if current_task_id in histories_by_task_id
    ]
    if not ordered_histories:
        raise HTTPException(status_code=404, detail="未找到对应的 LTX 链式视频记录")
    active_task_ids = await fetch_active_public_gallery_task_ids(
        db=db,
        task_ids=chain_task_ids,
        current_user_id=current_user.id,
    )
    items = await build_user_history_payload(
        histories=ordered_histories,
        gallery_task_ids=active_task_ids,
    )
    return LtxHistoryChainResponse(current_task_id=task_id, items=items)


async def stitch_ltx_history_chain_response(
    *,
    task_id: str,
    current_user,
    db,
) -> HistoryItem:
    chain_payload = await get_ltx_history_chain_payload(
        task_id=task_id,
        current_user=current_user,
        db=db,
    )
    if len(chain_payload.items) < 2:
        raise HTTPException(status_code=400, detail="至少需要两段视频才能执行拼接")
    histories = await fetch_owned_histories_by_task_ids(
        db=db,
        task_ids=[item.task_id for item in chain_payload.items if item.task_id],
        current_user_id=current_user.id,
    )
    histories_by_task_id = {
        str(getattr(history, "task_id", "") or "").strip(): history for history in histories
    }
    ordered_histories = [
        histories_by_task_id[item.task_id]
        for item in chain_payload.items
        if item.task_id in histories_by_task_id
    ]
    try:
        stitched_result = await stitch_ltx_histories_and_create_history(
            histories=ordered_histories,
            user_id=current_user.id,
            source_task_id=task_id,
            source="web",
            session=db,
        )
    except LtxVideoPersistenceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except LtxVideoExtensionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload_items = await build_user_history_payload(
        histories=[stitched_result.history],
        gallery_task_ids=set(),
    )
    if not payload_items:
        raise HTTPException(status_code=500, detail="拼接记录写入成功，但返回详情失败")
    return payload_items[0]
