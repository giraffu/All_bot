"""
🚨 架构红线警告 (ARCHITECTURE REDLINE) 🚨
本文件 `task_service.py` 已经被明确定义为 Telegram Bot 专属的表示层 (Presentation Layer) / Handler 层。
严禁在任何 Web API Router (如 src/web_api/routers/*.py) 中导入或调用此文件中的逻辑。
Web API 应直接调用 `src/core/task_core.py` 提供的业务门面 (Facade)。
"""

import contextlib
import logging
import os
from typing import Callable, List, Optional, Tuple

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.constants import (
    MODE_BLOWJOB,
    MODE_CLOSEUP_BLOWJOB,
    MODE_DOGGY_STYLE,
    MODE_IMAGE_TO_VIDEO,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_UNDRESS_TONGUE,
    TMP_DIR,
)
from src.services import task_service_completion as task_service_completion_helpers
from src.services.task_service_support import (
    get_acceleration_notice,
    resolve_custom_video_settings,
)
from src.services.permission_service import permission_service
from src.services.task_service_entrypoints import (
    process_custom_video_task as process_custom_video_task_entrypoint,
    process_face_video_task as process_face_video_task_entrypoint,
    process_generation_task as process_generation_task_entrypoint,
    process_image_to_video_task as process_image_to_video_task_entrypoint,
    process_i2i_pro_task as process_i2i_pro_task_entrypoint,
    process_ltx_video_task as process_ltx_video_task_entrypoint,
    process_video_task_template as process_video_task_template_entrypoint,
)
from src.services.task_service_finalize import (
    build_bot_cancellation_message,
    cleanup_runtime_state_if_needed,
    finalize_cancelled_task_for_bot,
    finalize_failed_task_for_bot,
    send_bot_domain_error,
    send_bot_warning,
)
from src.services.task_service_flow import (
    prepare_and_submit_bot_task,
    run_bot_task_flow,
    send_initial_task_status,
    submit_bot_task,
    update_submitted_task_status,
)
from src.services.task_service_message_support import (
    with_submitted_status,
)
from src.services.task_service_types import BotTaskMessageSpec, BotTaskRuntimeState
from src.services.tg_task_runtime import (
    cleanup_completion_status_message,
    get_or_send_status_message,
    send_result_media,
)
from src.utils import robust_edit_text, robust_reply_text, robust_send_message

logger = logging.getLogger(__name__)


class TaskService:
    @staticmethod
    async def _resolve_custom_video_settings(
        context,
        *,
        update: Optional[Update] = None,
        warn_invalid_combo: bool = False,
        resolution=None,
        duration=None,
    ) -> Tuple[str, str, int, int]:
        return await resolve_custom_video_settings(
            context,
            update=update,
            warn_invalid_combo=warn_invalid_combo,
            reply_text_func=robust_reply_text,
            resolution=resolution,
            duration=duration,
        )

    _with_submitted_status = staticmethod(with_submitted_status)
    _send_result_media = staticmethod(send_result_media)
    _cleanup_completion_status_message = staticmethod(cleanup_completion_status_message)

    @staticmethod
    async def _finalize_cancelled_task_for_bot(**kwargs):
        return await finalize_cancelled_task_for_bot(
            **kwargs,
            edit_text_func=robust_edit_text,
        )

    @staticmethod
    async def _finalize_failed_task_for_bot(**kwargs):
        return await finalize_failed_task_for_bot(
            **kwargs,
            edit_text_func=robust_edit_text,
            send_message_func=robust_send_message,
        )

    @staticmethod
    async def _send_bot_warning(context, chat_id, error):
        await send_bot_warning(
            context,
            chat_id,
            error,
            send_message_func=robust_send_message,
        )

    @staticmethod
    async def _send_bot_domain_error(context, chat_id, error):
        await send_bot_domain_error(
            context,
            chat_id,
            error,
            send_message_func=robust_send_message,
        )

    @staticmethod
    async def _handle_bot_cancelled_exception(
        *,
        status_msg,
        runtime_state,
        internal_user_id,
        username,
        message_spec,
        deduct_quota=True,
    ):
        await TaskService._finalize_cancelled_task_for_bot(
            status_msg=status_msg,
            internal_user_id=internal_user_id,
            username=username,
            cost=runtime_state.actual_cost,
            task_submitted=deduct_quota and runtime_state.task_submitted,
            registry_task_id=runtime_state.registry_task_id,
            explicit_user_message=build_bot_cancellation_message(
                runtime_state.actual_cost,
                message_spec,
            ),
        )
        runtime_state.terminal_state_finalized = True
        return None, None

    @staticmethod
    async def _handle_bot_unexpected_exception(
        *,
        context,
        chat_id,
        status_msg,
        runtime_state,
        internal_user_id,
        username,
        error,
        log_message,
        should_refund,
        generic_error_prefix,
        prefer_edit_status=False,
        refund_suffix_mode="if_refunded",
    ):
        logger.error(log_message, exc_info=True)
        await TaskService._finalize_failed_task_for_bot(
            context=context,
            chat_id=chat_id,
            status_msg=status_msg,
            internal_user_id=internal_user_id,
            username=username,
            cost=runtime_state.actual_cost,
            should_refund=should_refund,
            registry_task_id=runtime_state.registry_task_id,
            release_lock=runtime_state.task_submitted,
            error=error,
            generic_error_prefix=generic_error_prefix,
            prefer_edit_status=prefer_edit_status,
            refund_suffix_mode=refund_suffix_mode,
        )
        runtime_state.terminal_state_finalized = True
        return None, None

    _cleanup_runtime_state_if_needed = staticmethod(cleanup_runtime_state_if_needed)

    @staticmethod
    async def _submit_bot_task(
        *,
        runtime_state,
        internal_user_id,
        username,
        task_type,
        inputs,
        source_post_id=None,
        deduct_quota=True,
    ):
        from src.core.task_core import process_and_submit_task

        return await submit_bot_task(
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            task_type=task_type,
            inputs=inputs,
            source_post_id=source_post_id,
            deduct_quota=deduct_quota,
            process_and_submit_task_func=process_and_submit_task,
        )

    @staticmethod
    async def _run_bot_task_flow(
        *,
        context,
        chat_id,
        runtime_state,
        internal_user_id,
        username,
        task_type,
        inputs,
        prompt,
        is_video,
        message_spec: BotTaskMessageSpec,
        update=None,
        status_msg_id=None,
        submitted_status_builder: Optional[Callable[[int], str]] = None,
        source_post_id=None,
        deduct_quota=True,
        send_result=True,
        reply_markup=None,
        delete_status=True,
        allow_contribute=True,
        billing_resolution: Optional[str] = None,
        requested_duration: Optional[int] = None,
        missing_output_should_refund: bool = True,
        prefer_edit_status=False,
        refund_suffix_mode="if_refunded",
        unexpected_should_refund: Optional[
            Callable[[BotTaskRuntimeState], bool]
        ] = None,
        unexpected_error_log_message: str,
        unexpected_error_prefix: str,
        cleanup_paths: Optional[list[str]] = None,
        cleanup_enabled: bool = True,
    ) -> Tuple[Optional[bytes], Optional[str]]:
        from src.core.billing_core import get_user_priority_and_identity

        return await run_bot_task_flow(
            context=context,
            chat_id=chat_id,
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            task_type=task_type,
            inputs=inputs,
            prompt=prompt,
            is_video=is_video,
            message_spec=message_spec,
            update=update,
            status_msg_id=status_msg_id,
            submitted_status_builder=submitted_status_builder,
            source_post_id=source_post_id,
            deduct_quota=deduct_quota,
            send_result=send_result,
            reply_markup=reply_markup,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
            billing_resolution=billing_resolution,
            requested_duration=requested_duration,
            missing_output_should_refund=missing_output_should_refund,
            prefer_edit_status=prefer_edit_status,
            refund_suffix_mode=refund_suffix_mode,
            unexpected_should_refund=unexpected_should_refund,
            unexpected_error_log_message=unexpected_error_log_message,
            unexpected_error_prefix=unexpected_error_prefix,
            cleanup_paths=cleanup_paths,
            cleanup_enabled=cleanup_enabled,
            send_result_media_func=TaskService._send_result_media,
            cleanup_completion_status_message_func=TaskService._cleanup_completion_status_message,
            cleanup_files_func=TaskService._cleanup_files,
            prepare_and_submit_bot_task_func=prepare_and_submit_bot_task,
            with_submitted_status_func=TaskService._with_submitted_status,
            get_or_send_status_msg_func=TaskService._get_or_send_status_msg,
            send_initial_task_status_func=send_initial_task_status,
            submit_bot_task_func=TaskService._submit_bot_task,
            update_submitted_task_status_func=update_submitted_task_status,
            reply_text_func=robust_reply_text,
            edit_text_func=robust_edit_text,
            monitor_submitted_bot_task_func=task_service_completion_helpers.monitor_submitted_bot_task,
            get_user_priority_and_identity_func=get_user_priority_and_identity,
            monitor_bot_task_progress_func=task_service_completion_helpers.monitor_bot_task_progress,
            edit_status_text_func=robust_edit_text,
            complete_monitored_bot_task_func=TaskService._complete_monitored_bot_task,
            send_bot_warning_func=TaskService._send_bot_warning,
            send_bot_domain_error_func=TaskService._send_bot_domain_error,
            handle_bot_cancelled_exception_func=TaskService._handle_bot_cancelled_exception,
            handle_bot_unexpected_exception_func=TaskService._handle_bot_unexpected_exception,
            cleanup_runtime_state_if_needed_func=TaskService._cleanup_runtime_state_if_needed,
        )

    @staticmethod
    async def _complete_monitored_bot_task(**kwargs) -> Tuple[Optional[bytes], Optional[str]]:
        kwargs.setdefault("send_result_media_func", TaskService._send_result_media)
        kwargs.setdefault(
            "cleanup_completion_status_message_func",
            TaskService._cleanup_completion_status_message,
        )
        kwargs.setdefault(
            "handle_task_completion_func",
            task_service_completion_helpers.handle_task_completion,
        )
        kwargs.setdefault(
            "finalize_failed_task_for_bot_func",
            TaskService._finalize_failed_task_for_bot,
        )
        return await task_service_completion_helpers.complete_monitored_bot_task(
            **kwargs,
        )

    @staticmethod
    async def process_ltx_video_task(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        prompt: str,
        image_path: str,
        cleanup: bool = True,
        allow_contribute: bool = True,
        source_post_id: Optional[int] = None,
    ):
        return await process_ltx_video_task_entrypoint(
            service=TaskService,
            update=update,
            context=context,
            prompt=prompt,
            image_path=image_path,
            cleanup=cleanup,
            allow_contribute=allow_contribute,
            source_post_id=source_post_id,
        )

    @staticmethod
    async def process_face_video_task(
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        user_id: int,
        username: str,
        face_image_path: str,
        video_path: str,
        resolution: int,
        duration: int,
        cost: int,
        message_id: int = None,
        cleanup: bool = True,
        source_post_id: Optional[int] = None,
    ):
        return await process_face_video_task_entrypoint(
            service=TaskService,
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            face_image_path=face_image_path,
            video_path=video_path,
            resolution=resolution,
            duration=duration,
            cost=cost,
            message_id=message_id,
            cleanup=cleanup,
            source_post_id=source_post_id,
        )

    @staticmethod
    async def process_generation_task(
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        user_id: int,
        username: str,
        prompt: str,
        images: list[str],
        is_video: bool = False,
        status_msg_id: int = None,
        delete_status: bool = True,
        task_type: str = None,
        cleanup: bool = True,
        send_result: bool = True,
        deduct_quota: bool = True,
        reply_markup: InlineKeyboardMarkup = None,
        lora_name: str = None,
        lora_strength: float = 1.0,
        allow_contribute: bool = True,
        source_post_id: Optional[int] = None,
        resolution=None,
        duration=None,
    ) -> Tuple[Optional[bytes], Optional[str]]:
        return await process_generation_task_entrypoint(
            service=TaskService,
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            prompt=prompt,
            images=images,
            is_video=is_video,
            status_msg_id=status_msg_id,
            delete_status=delete_status,
            task_type=task_type,
            cleanup=cleanup,
            send_result=send_result,
            deduct_quota=deduct_quota,
            reply_markup=reply_markup,
            lora_name=lora_name,
            lora_strength=lora_strength,
            allow_contribute=allow_contribute,
            source_post_id=source_post_id,
            resolution=resolution,
            duration=duration,
        )

    @staticmethod
    async def process_image_to_video_task(
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        user_id: int,
        username: str,
        prompt: str,
        images: list[str],
        resolution=None,
        duration=None,
        status_msg_id: int = None,
        delete_status: bool = True,
        task_type: str = MODE_IMAGE_TO_VIDEO,
        cleanup: bool = True,
        send_result: bool = True,
        deduct_quota: bool = True,
        reply_markup: InlineKeyboardMarkup = None,
        lora_name: str = None,
        lora_strength: float = 1.0,
        allow_contribute: bool = True,
        source_post_id: Optional[int] = None,
    ) -> Tuple[Optional[bytes], Optional[str]]:
        return await process_image_to_video_task_entrypoint(
            service=TaskService,
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            prompt=prompt,
            images=images,
            resolution=resolution,
            duration=duration,
            status_msg_id=status_msg_id,
            delete_status=delete_status,
            task_type=task_type,
            cleanup=cleanup,
            send_result=send_result,
            deduct_quota=deduct_quota,
            reply_markup=reply_markup,
            lora_name=lora_name,
            lora_strength=lora_strength,
            allow_contribute=allow_contribute,
            source_post_id=source_post_id,
        )

    @staticmethod
    async def _process_video_task_template(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        image_path: str,
        mode: str,
        default_prompt_key: str,
        default_prompt_text: str,
        cleanup: bool = True,
        allow_contribute: bool = True,
        source_post_id: Optional[int] = None,
    ) -> Tuple[Optional[bytes], Optional[str]]:
        return await process_video_task_template_entrypoint(
            service=TaskService,
            update=update,
            context=context,
            image_path=image_path,
            mode=mode,
            default_prompt_key=default_prompt_key,
            default_prompt_text=default_prompt_text,
            cleanup=cleanup,
            allow_contribute=allow_contribute,
            source_post_id=source_post_id,
        )

    # Public Methods mapped to the generic template

    @staticmethod
    async def process_blowjob_task(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        image_path: str,
        cleanup: bool = True,
        allow_contribute: bool = True,
    ):
        return await TaskService._process_video_task_template(
            update,
            context,
            image_path,
            MODE_BLOWJOB,
            "blowjob",
            "undress blowjob",
            cleanup,
            allow_contribute=allow_contribute,
        )

    @staticmethod
    async def process_undress_tongue_task(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        image_path: str,
        cleanup: bool = True,
        allow_contribute: bool = True,
    ):
        return await TaskService._process_video_task_template(
            update,
            context,
            image_path,
            MODE_UNDRESS_TONGUE,
            "undress_tongue",
            "undress and show tongue",
            cleanup,
            allow_contribute=allow_contribute,
        )

    @staticmethod
    async def process_doggy_style_task(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        image_path: str,
        cleanup: bool = True,
        allow_contribute: bool = True,
    ):
        return await TaskService._process_video_task_template(
            update,
            context,
            image_path,
            MODE_DOGGY_STYLE,
            "doggy_style",
            "doggy style sex",
            cleanup,
            allow_contribute=allow_contribute,
        )

    @staticmethod
    async def process_closeup_blowjob_task(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        image_path: str,
        cleanup: bool = True,
        allow_contribute: bool = True,
    ):
        return await TaskService._process_video_task_template(
            update,
            context,
            image_path,
            MODE_CLOSEUP_BLOWJOB,
            "closeup_blowjob",
            "closeup blowjob sex",
            cleanup,
            allow_contribute=allow_contribute,
        )

    @staticmethod
    async def process_perfect_video_insert_task(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        image_path: str,
        cleanup: bool = True,
        allow_contribute: bool = True,
    ):
        return await TaskService._process_video_task_template(
            update,
            context,
            image_path,
            MODE_PERFECT_VIDEO_INSERT,
            "perfect_video_insert",
            "missionary sex",
            cleanup,
            allow_contribute=allow_contribute,
        )

    @staticmethod
    async def process_custom_video_task(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        prompt: str,
        image_path: str,
        cleanup: bool = True,
        source_post_id: Optional[int] = None,
    ):
        return await process_custom_video_task_entrypoint(
            service=TaskService,
            update=update,
            context=context,
            prompt=prompt,
            image_path=image_path,
            cleanup=cleanup,
            source_post_id=source_post_id,
        )

    # Private Helpers

    @staticmethod
    async def process_i2i_pro_task(
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        user_id: int,
        username: str,
        prompt: str,
        images: list[str],
        allow_contribute: bool = True,
        source_post_id: Optional[int] = None,
    ):
        return await process_i2i_pro_task_entrypoint(
            service=TaskService,
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            prompt=prompt,
            images=images,
            allow_contribute=allow_contribute,
            source_post_id=source_post_id,
        )

    _get_or_send_status_msg = staticmethod(get_or_send_status_message)

    @staticmethod
    def _cleanup_files(paths: List[str]):
        for path in paths:
            if path.startswith(TMP_DIR) and os.path.exists(path):
                with contextlib.suppress(OSError):
                    os.remove(path)

    @staticmethod
    async def _get_acceleration_notice(user_id: int) -> str:
        return await get_acceleration_notice(
            user_id,
            quota_manager=permission_service.quota_manager,
        )


task_service = TaskService()
