import contextlib
import logging

from src.constants import MODE_NAME_MAP
from src.core.billing_core import get_user_priority_and_identity
from src.core.task_status_mapper import BACKEND_STATUS_DONE, normalize_backend_status
from src.domain_config.scail2_video import normalize_scail2_negative_prompt
from src.services.image_service import image_service
from src.services.permission_service import permission_service
from src.services.task_service_message_support import (
    build_message_spec,
    resolve_display_mode_name,
    translate_context_text,
)
from src.services.task_service_completion import (
    complete_monitored_bot_task,
)
from src.services.task_service_types import (
    BotTaskCompletionContext,
    BotTaskMessageSpec,
    BotTaskRuntimeState,
)
from src.services.private_qqcc_bot_service import parse_private_bot_client_type
from src.services.task_recovery_contract import (
    build_bot_task_recovery_contract,
    normalize_bot_task_recovery_contract,
)
from src.services.task_registry import TaskRegistry
from src.services.scail2_face_swap_pipeline_service import (
    BOT_SCAIL2_FACE_SWAP_CONTINUATION_KEY,
    build_bot_scail2_stage2_task_id,
    cleanup_scail2_face_swap_first_frame,
)
from src.services.private_qqcc_continuation_service import (
    activate_private_qqcc_continuation_task,
    normalize_private_qqcc_continuation_task_ref,
    record_private_qqcc_continuation_task_result,
)
from src.services.tg_task_runtime import (
    TelegramBotContextAdapter,
    TelegramMessageAdapter,
    monitor_task_progress,
)

logger = logging.getLogger(__name__)


def _resolve_recovered_task_language(task_data: dict) -> str:
    metadata = task_data.get("metadata") or {}
    recovery_contract = normalize_bot_task_recovery_contract(metadata) or {}
    return (
        task_data.get("language_code")
        or task_data.get("lang")
        or metadata.get("language_code")
        or metadata.get("lang")
        or recovery_contract.get("language_code")
        or "zh"
    )


def _build_recovered_message_spec(*, context, task_type: str) -> BotTaskMessageSpec:
    display_mode_name = resolve_display_mode_name(
        task_type,
        context=context,
        mode_name_map=MODE_NAME_MAP,
    )
    return build_message_spec(
        initial_status_text="",
        completion_caption=translate_context_text(
            context,
            "task.status_completion_mode",
            mode_name=display_mode_name,
        ),
        missing_output_message=translate_context_text(
            context,
            "task.status_missing_output_refunded",
        ),
        cancellation_message_template=translate_context_text(
            context,
            "task.status_cancelled_refunded",
            cost="{cost}",
        ),
    )


async def _monitor_recovered_task_progress(
    *,
    task_id,
    status_msg,
    is_video,
    identity_str=None,
    user_group=None,
    show_queue_status=True,
):
    return await monitor_task_progress(
        task_id=task_id,
        status_msg=status_msg,
        is_video=is_video,
        monitor_func=image_service.monitor_progress,
        identity_str=identity_str,
        user_group=user_group,
        show_queue_status=show_queue_status,
    )


def _build_recovered_completion_context(
    *,
    context,
    chat_id,
    internal_user_id,
    username,
    prompt,
    task_type,
    registry_task_id,
    backend_task_id,
    saved_input_images,
    is_video,
    send_result,
    reply_markup,
    status_msg,
    delete_status,
    allow_contribute,
    billing_resolution,
    requested_duration,
    caption=None,
    result_meta=None,
    final_info,
    record_history=True,
):
    task_runtime = BotTaskRuntimeState(
        registry_task_id=registry_task_id,
        backend_task_id=backend_task_id,
        task_submitted=True,
    )
    return BotTaskCompletionContext(
        context=context,
        chat_id=chat_id,
        status_msg=status_msg,
        runtime_state=task_runtime,
        internal_user_id=internal_user_id,
        username=username,
        prompt=prompt,
        task_type=task_type,
        registry_task_id=registry_task_id,
        backend_task_id=backend_task_id,
        saved_input_images=saved_input_images,
        final_info=final_info,
        is_video=is_video,
        message_spec=_build_recovered_message_spec(
            context=context,
            task_type=task_type,
        ),
        send_result=send_result,
        reply_markup=reply_markup,
        delete_status=delete_status,
        caption=caption,
        allow_contribute=allow_contribute,
        record_history=record_history,
        result_meta=result_meta,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
    )


async def _handle_recovered_task_completion(*, completion: BotTaskCompletionContext):
    return await complete_monitored_bot_task(completion=completion)


def _get_bot_scail2_face_swap_continuation(
    recovery_contract: dict | None,
) -> dict | None:
    if not isinstance(recovery_contract, dict):
        return None
    result_meta = recovery_contract.get("result_meta")
    if not isinstance(result_meta, dict):
        return None
    continuation = result_meta.get(BOT_SCAIL2_FACE_SWAP_CONTINUATION_KEY)
    if not isinstance(continuation, dict) or continuation.get("version") != 1:
        return None
    return continuation


async def _resume_recovered_bot_scail2_face_swap(
    *,
    registry_task_id: str,
    task_data: dict,
    recovery_contract: dict,
    continuation: dict,
    final_info: dict,
) -> dict | None:
    if normalize_backend_status(final_info.get("status")) != BACKEND_STATUS_DONE:
        return None
    swapped_reference = final_info.get("result_path") or final_info.get("output")
    saved_inputs = list(task_data.get("saved_input_images") or [])
    reference_index = int(continuation.get("reference_input_index", 1))
    motion_index = int(continuation.get("motion_video_input_index", 2))
    if (
        not swapped_reference
        or reference_index >= len(saved_inputs)
        or motion_index >= len(saved_inputs)
    ):
        return None

    original_reference = saved_inputs[reference_index]
    motion_video = saved_inputs[motion_index]
    duration = int(continuation.get("duration") or 5)
    prompt = str(continuation.get("prompt") or task_data.get("prompt") or "")
    base_priority = int(continuation.get("normal_priority") or 0)
    user_priority, _identity, _group = await get_user_priority_and_identity(
        int(task_data["user_id"])
    )
    final_priority = min(base_priority + int(user_priority), 100)
    stage2_backend_task_id = build_bot_scail2_stage2_task_id(registry_task_id)
    final_metadata = build_bot_task_recovery_contract(
        send_result=True,
        delete_status=True,
        allow_contribute=bool(task_data.get("allow_contribute", True)),
        record_history=True,
        result_task_type="scail2_face_swap_v2",
        result_prompt=prompt,
        completion_caption=recovery_contract.get("completion_caption"),
        language_code=recovery_contract.get("language_code"),
        show_queue_status=True,
    )
    await TaskRegistry.transition_backend_task(
        registry_task_id,
        backend_task_id=stage2_backend_task_id,
        task_type="scail2_face_swap_v2",
        saved_input_images=[original_reference, motion_video],
        allow_contribute=bool(task_data.get("allow_contribute", True)),
        user_cancel_allowed=False,
        status="pending",
        task_updates={
            "is_video": True,
            "prompt": prompt,
            "billing_resolution": "512x896",
            "requested_duration": duration,
            "metadata": final_metadata,
        },
    )
    existing_stage2 = await image_service.get_task_status(stage2_backend_task_id)
    if existing_stage2 is None:
        submitted_id = await image_service.submit_scail2_video_task(
            stage2_backend_task_id,
            task_type="scail2_face_swap_v2",
            reference_image_path=swapped_reference,
            motion_video_path=motion_video,
            prompt=prompt,
            negative_prompt=normalize_scail2_negative_prompt(None),
            length=duration,
            priority=final_priority,
            reference_preprocessed=True,
        )
        if submitted_id != stage2_backend_task_id:
            raise RuntimeError("SCAIL-2 backend changed the deterministic task ID")
    await cleanup_scail2_face_swap_first_frame(saved_inputs[0])

    updated = dict(task_data)
    updated.update(
        {
            "backend_task_id": stage2_backend_task_id,
            "task_type": "scail2_face_swap_v2",
            "saved_input_images": [original_reference, motion_video],
            "is_video": True,
            "prompt": prompt,
            "billing_resolution": "512x896",
            "requested_duration": duration,
            "user_cancel_allowed": False,
            "status": "pending",
            "metadata": final_metadata,
        }
    )
    return updated


async def run_recovered_task(*, registry_task_id: str, task_data: dict, application) -> bool:
    bot = application.bot
    user_id = task_data.get("user_id")
    username = task_data.get("username")
    backend_task_id = task_data.get("backend_task_id")
    chat_id = task_data.get("chat_id")
    message_id = task_data.get("message_id")
    task_type = task_data.get("task_type")
    prompt = task_data.get("prompt", "")
    saved_input_images = task_data.get("saved_input_images", [])
    is_video = task_data.get("is_video", False)
    allow_contribute = task_data.get("allow_contribute", True)
    metadata = task_data.get("metadata") or {}
    recovery_contract = normalize_bot_task_recovery_contract(metadata)
    continuation_ref = normalize_private_qqcc_continuation_task_ref(metadata)
    private_bot_id = parse_private_bot_client_type(task_data.get("client_type"))
    billing_resolution = task_data.get("billing_resolution") or metadata.get(
        "billing_resolution"
    )
    requested_duration = task_data.get("requested_duration") or metadata.get(
        "requested_duration"
    )

    if not registry_task_id or not backend_task_id:
        return False

    runtime_context = TelegramBotContextAdapter(application)
    runtime_context.lang = _resolve_recovered_task_language(task_data)
    status_msg = (
        TelegramMessageAdapter(bot, chat_id, message_id)
        if chat_id and message_id
        else None
    )

    identity_str = await permission_service.get_user_identity(user_id)
    user_group = await permission_service.get_user_group(user_id)

    final_info = await _monitor_recovered_task_progress(
        task_id=backend_task_id,
        status_msg=status_msg,
        is_video=is_video,
        identity_str=identity_str,
        user_group=user_group,
        show_queue_status=(
            recovery_contract.get("show_queue_status") is not False
            if recovery_contract is not None
            else True
        ),
    )
    if not final_info:
        return False

    scail2_continuation = _get_bot_scail2_face_swap_continuation(
        recovery_contract
    )
    if scail2_continuation is not None:
        resumed_task_data = await _resume_recovered_bot_scail2_face_swap(
            registry_task_id=registry_task_id,
            task_data=task_data,
            recovery_contract=recovery_contract,
            continuation=scail2_continuation,
            final_info=final_info,
        )
        if resumed_task_data is not None:
            return await run_recovered_task(
                registry_task_id=registry_task_id,
                task_data=resumed_task_data,
                application=application,
            )

    if private_bot_id is not None and (
        recovery_contract is None
        or (
            recovery_contract.get("requires_continuation") is True
            and continuation_ref is None
        )
    ):
        logger.error(
            "Private QQCC task %s for tenant %s has no durable final-result "
            "recovery contract; refusing to expose an intermediate output.",
            registry_task_id,
            private_bot_id,
        )
        return False

    recovered_task_type = task_type
    recovered_prompt = prompt
    recovered_saved_inputs = list(saved_input_images or [])
    send_result = bool(chat_id)
    delete_status = bool(status_msg)
    result_meta = None
    record_history = True
    caption = None
    if recovery_contract is not None:
        recovered_task_type = recovery_contract.get("result_task_type") or task_type
        recovered_prompt = recovery_contract.get("result_prompt") or prompt
        input_indices = recovery_contract.get("result_input_image_indices")
        if isinstance(input_indices, list):
            selected_inputs = [
                recovered_saved_inputs[index]
                for index in input_indices
                if isinstance(index, int)
                and 0 <= index < len(recovered_saved_inputs)
            ]
            if selected_inputs:
                recovered_saved_inputs = selected_inputs
        send_result = bool(recovery_contract.get("send_result")) and bool(chat_id)
        delete_status = bool(recovery_contract.get("delete_status")) and bool(
            status_msg
        )
        allow_contribute = bool(recovery_contract.get("allow_contribute"))
        record_history = recovery_contract.get("record_history") is not False
        result_meta = recovery_contract.get("result_meta")
        caption = recovery_contract.get("completion_caption")

    completion = _build_recovered_completion_context(
        context=runtime_context,
        chat_id=chat_id,
        internal_user_id=user_id,
        username=username,
        prompt=recovered_prompt,
        task_type=recovered_task_type,
        registry_task_id=registry_task_id,
        backend_task_id=backend_task_id,
        saved_input_images=recovered_saved_inputs,
        is_video=is_video,
        send_result=send_result,
        reply_markup=None,
        status_msg=status_msg,
        delete_status=delete_status,
        allow_contribute=allow_contribute,
        record_history=record_history,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        caption=caption,
        result_meta=result_meta,
        final_info=final_info,
    )
    continuation_scope = (
        activate_private_qqcc_continuation_task(continuation_ref)
        if continuation_ref is not None
        else contextlib.nullcontext()
    )
    with continuation_scope:
        completion_result = await _handle_recovered_task_completion(
            completion=completion
        )
    if continuation_ref is not None:
        output_file = (
            completion_result[1]
            if isinstance(completion_result, tuple) and len(completion_result) > 1
            else None
        )
        await record_private_qqcc_continuation_task_result(
            registry_metadata=metadata,
            registry_task_id=registry_task_id,
            saved_inputs=recovered_saved_inputs,
            output_file=output_file,
        )
    return True
