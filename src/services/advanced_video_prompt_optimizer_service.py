from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from config import MINIO_BUCKET
from src.logger import UserLogger
from src.quota import QuotaManager
from src.services.storage import storage
from src.web_api.schemas.prompt_optimization_schema import PromptOptimizationTaskRequest
from src.web_api.services.prompt_optimization_service import submit_prompt_optimization
from src.web_api.services.prompt_result_store import get_owned_prompt_result

_MODE_TARGETS = {
    "t2v": "minimax_h3_t2v",
    "i2v": "minimax_h3_i2v",
    "flf2v": "minimax_h3_flf2v",
}


async def _call_maybe_async(func: Callable, *args):
    value = func(*args)
    return await value if inspect.isawaitable(value) else value


async def _default_remove_object(object_key: str) -> None:
    await asyncio.to_thread(storage.client.remove_object, MINIO_BUCKET, object_key)


async def optimize_advanced_video_prompt(
    *,
    internal_user_id: int,
    username: str | None,
    mode: str,
    prompt: str,
    images: list[str],
    duration_seconds: int,
    client_request_id: str,
    upload_image: Callable[[str], str] | None = None,
    submit_func=submit_prompt_optimization,
    get_result_func=get_owned_prompt_result,
    remove_object_func: Callable[[str], Any] = _default_remove_object,
    sleep_func=asyncio.sleep,
    get_balance=None,
    max_polls: int = 200,
    poll_interval_seconds: float = 1.2,
) -> str:
    target_task_type = _MODE_TARGETS.get(str(mode))
    if target_task_type is None:
        raise ValueError("unsupported MiniMax H3 prompt optimization mode")
    expected_images = {"t2v": 0, "i2v": 1, "flf2v": 2}[mode]
    if len(images) != expected_images:
        raise ValueError("MiniMax H3 optimizer media contract mismatch")

    uploader = upload_image or UserLogger(
        internal_user_id,
        username or "unknown",
    ).save_input_image
    object_keys: list[str] = []
    should_cleanup = True
    try:
        for path in images:
            object_key = str(await asyncio.to_thread(uploader, path) or "").strip()
            if not object_key:
                raise RuntimeError("优化素材上传失败")
            object_keys.append(object_key)

        request = PromptOptimizationTaskRequest.model_validate(
            {
                "client_request_id": client_request_id,
                "target_task_type": target_task_type,
                "template": {"id": "minimax_h3_10eros_naughtytimes", "version": 4},
                "prompt": prompt,
                "context": {"duration_seconds": duration_seconds},
                "media": [
                    {
                        "role": "start_image" if index == 0 else "end_image",
                        "object_key": object_key,
                    }
                    for index, object_key in enumerate(object_keys)
                ],
            }
        )
        quota = QuotaManager()
        submission = await submit_func(
            request=request,
            current_user=SimpleNamespace(id=int(internal_user_id), username=username),
            get_balance=get_balance or quota.get_credits,
        )
        task_id = str(submission["task_id"])
        should_cleanup = False
        for _ in range(max_polls):
            result = await get_result_func(task_id, int(internal_user_id))
            if result and str(result.get("result_text") or "").strip():
                should_cleanup = True
                return str(result["result_text"]).strip()
            if result and result.get("status") == "failed":
                should_cleanup = True
                refund = str(result.get("refund_status") or "pending")
                raise RuntimeError(f"提示词优化失败，退款状态：{refund}")
            await sleep_func(poll_interval_seconds)
        raise TimeoutError("提示词优化等待超时，任务仍可能继续运行")
    finally:
        if should_cleanup:
            for object_key in object_keys:
                try:
                    await _call_maybe_async(remove_object_func, object_key)
                except Exception:
                    pass
