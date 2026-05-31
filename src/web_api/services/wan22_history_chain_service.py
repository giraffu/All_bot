import uuid

from fastapi import HTTPException

from src.database.models import History
from src.services.storage import storage
from src.services.wan22_video_v2_extension_service import (
    Wan22VideoV2ExtensionError,
    build_wan22_chain_prompt_summary,
    build_full_chain_task_ids,
    build_wan22_stitched_extra_outputs,
    extract_wan22_history_context,
    load_owned_wan22_history_for_internal_user,
    stitch_history_videos,
)
from src.web_api.schemas.user_schema import HistoryItem
from src.web_api.schemas.user_schema import Wan22HistoryChainResponse
from src.web_api.services.history_query_service import (
    fetch_active_public_gallery_task_ids,
    fetch_owned_histories_by_task_ids,
)
from src.web_api.services.history_response_builder import build_user_history_payload


async def _load_current_wan22_history(*, task_id: str, current_user) -> object:
    try:
        return await load_owned_wan22_history_for_internal_user(
            task_id=task_id,
            internal_user_id=current_user.id,
        )
    except Wan22VideoV2ExtensionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _resolve_chain_task_ids(history) -> list[str]:
    context = extract_wan22_history_context(getattr(history, "extra_outputs", None))
    current_task_id = str(getattr(history, "task_id", "") or "").strip()
    return build_full_chain_task_ids(
        chain_task_ids=context.get("wan22_chain_task_ids") or [],
        current_task_id=current_task_id,
    )


async def get_wan22_history_chain_payload(
    *,
    task_id: str,
    current_user,
    db,
) -> Wan22HistoryChainResponse:
    current_history = await _load_current_wan22_history(
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
        raise HTTPException(status_code=404, detail="未找到对应的链式视频记录")
    active_task_ids = await fetch_active_public_gallery_task_ids(
        db=db,
        task_ids=chain_task_ids,
    )
    items = await build_user_history_payload(
        histories=ordered_histories,
        gallery_task_ids=active_task_ids,
    )
    return Wan22HistoryChainResponse(current_task_id=task_id, items=items)


async def stitch_wan22_history_chain_response(
    *,
    task_id: str,
    current_user,
    db,
) -> HistoryItem:
    chain_payload = await get_wan22_history_chain_payload(
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
        stitched_video = await stitch_history_videos(ordered_histories)
    except Wan22VideoV2ExtensionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stitched_task_id = f"wan22_chain_{uuid.uuid4().hex[:24]}"
    output_object_name = f"{current_user.id}/output_images/{stitched_task_id}.mp4"
    output_file = storage.upload_bytes(
        stitched_video,
        output_object_name,
        content_type="video/mp4",
    )
    if not output_file:
        raise HTTPException(status_code=500, detail="拼接视频上传失败，请稍后再试")

    stitched_history = History(
        user_id=current_user.id,
        task_id=stitched_task_id,
        type="wan22_video_v2",
        prompt=build_wan22_chain_prompt_summary(ordered_histories),
        output_file=output_file,
        extra_outputs=build_wan22_stitched_extra_outputs(
            chain_task_ids=[item.task_id for item in chain_payload.items if item.task_id],
            source_task_id=task_id,
        ),
        billing_resolution=next(
            (
                getattr(history, "billing_resolution", None)
                for history in reversed(ordered_histories)
                if getattr(history, "billing_resolution", None)
            ),
            None,
        ),
        width=next(
            (
                getattr(history, "width", None)
                for history in reversed(ordered_histories)
                if getattr(history, "width", None) is not None
            ),
            None,
        ),
        height=next(
            (
                getattr(history, "height", None)
                for history in reversed(ordered_histories)
                if getattr(history, "height", None) is not None
            ),
            None,
        ),
        duration=sum(int(getattr(history, "duration", 0) or 0) for history in ordered_histories)
        or None,
        requested_duration=sum(
            int(getattr(history, "requested_duration", 0) or 0) for history in ordered_histories
        )
        or None,
        allow_contribute=all(
            getattr(history, "allow_contribute", True) is not False
            for history in ordered_histories
        ),
        source="web",
    )
    db.add(stitched_history)
    await db.commit()
    await db.refresh(stitched_history)

    payload_items = await build_user_history_payload(
        histories=[stitched_history],
        gallery_task_ids=set(),
    )
    if not payload_items:
        raise HTTPException(status_code=500, detail="拼接记录写入成功，但返回详情失败")
    return payload_items[0]
