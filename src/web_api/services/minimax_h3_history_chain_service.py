from fastapi import HTTPException

from src.services.minimax_h3_extension_service import (
    MiniMaxH3ExtensionError,
    MiniMaxH3PersistenceError,
    load_minimax_h3_chain_for_internal_user,
    stitch_minimax_h3_histories_and_create_history,
)
from src.web_api.schemas.user_schema import (
    HistoryItem,
    MiniMaxH3HistoryChainResponse,
)
from src.web_api.services.history_query_service import (
    fetch_active_public_gallery_task_ids,
)
from src.web_api.services.history_response_builder import build_user_history_payload


async def get_minimax_h3_history_chain_payload(
    *, task_id: str, current_user, db
) -> MiniMaxH3HistoryChainResponse:
    try:
        histories = await load_minimax_h3_chain_for_internal_user(
            task_id=task_id,
            internal_user_id=current_user.id,
            session=db,
        )
    except MiniMaxH3ExtensionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    active_task_ids = await fetch_active_public_gallery_task_ids(
        db=db,
        task_ids=[str(history.task_id or "") for history in histories],
    )
    items = await build_user_history_payload(
        histories=histories,
        gallery_task_ids=active_task_ids,
    )
    return MiniMaxH3HistoryChainResponse(current_task_id=task_id, items=items)


async def stitch_minimax_h3_history_chain_response(
    *, task_id: str, current_user, db
) -> HistoryItem:
    try:
        histories = await load_minimax_h3_chain_for_internal_user(
            task_id=task_id,
            internal_user_id=current_user.id,
            session=db,
        )
        stitched = await stitch_minimax_h3_histories_and_create_history(
            histories=histories,
            user_id=current_user.id,
            source_task_id=task_id,
            source="web",
            session=db,
        )
    except MiniMaxH3PersistenceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except MiniMaxH3ExtensionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    items = await build_user_history_payload(
        histories=[stitched.history],
        gallery_task_ids=set(),
    )
    if not items:
        raise HTTPException(status_code=500, detail="拼接记录写入成功，但返回详情失败")
    return items[0]
