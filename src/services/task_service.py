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
    MODE_NAME_MAP,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_UNDRESS_TONGUE,
    TMP_DIR,
)
from src.services.task_service_support import (
    get_acceleration_notice,
    normalize_custom_video_duration_value,
    normalize_custom_video_resolution_value,
    resolve_custom_video_settings,
)
from src.logger import UserLogger
from src.services.image_service import image_service
from src.services.permission_service import permission_service
from src.services.task_registry import TaskRegistry
from src.services.task_service_entrypoints import (
    process_custom_video_task as process_custom_video_task_entrypoint,
    process_face_video_task as process_face_video_task_entrypoint,
    process_generation_task as process_generation_task_entrypoint,
    process_i2i_pro_task as process_i2i_pro_task_entrypoint,
    process_ltx_video_task as process_ltx_video_task_entrypoint,
    process_video_task_template as process_video_task_template_entrypoint,
)
from src.services.task_service_entrypoint_support import (
    build_cleanup_paths,
    build_log_prompt,
    build_task_inputs,
    build_unexpected_error_log_message,
    resolve_video_billing_args,
)
from src.services.task_service_facade_seams import (
    cleanup_completion_status_message_seam,
    cleanup_runtime_state_if_needed_seam,
    complete_monitored_bot_task_seam as complete_monitored_bot_task_facade,
    download_and_log_task_output_seam,
    finalize_cancelled_task_for_bot_seam,
    finalize_failed_task_for_bot_seam,
    monitor_submitted_bot_task_seam,
    monitor_task_progress_seam,
    prepare_and_submit_bot_task_seam,
    run_bot_task_flow_seam,
    send_bot_domain_error_seam,
    send_initial_task_status_seam,
    send_bot_warning_seam,
    send_result_media_seam,
    submit_bot_task_seam,
    handle_task_completion_seam,
    update_submitted_task_status_seam,
)
from src.services.task_service_finalize import (
    build_bot_cancellation_message,
)
from src.services.task_service_message_support import (
    build_message_spec,
    build_cost_status_builder,
    build_status_message,
    resolve_display_mode_name,
    with_completion_caption,
    with_submitted_status,
)
from src.services.task_service_types import BotTaskMessageSpec, BotTaskRuntimeState
from src.services.tg_task_runtime import (
    build_result_reply_markup,
    get_or_send_status_message,
    record_result_message_meta,
    resolve_result_mode_name,
)
from src.utils import robust_edit_text, robust_reply_text, robust_send_message

logger = logging.getLogger(__name__)

# Compatibility exports for older tests and monkeypatch targets.
_COMPAT_TEST_EXPORTS = (UserLogger, image_service, TaskRegistry)
complete_monitored_bot_task = complete_monitored_bot_task_facade


class TaskService:
    _create_runtime_state = staticmethod(BotTaskRuntimeState)
    _normalize_custom_video_resolution_value = staticmethod(
        normalize_custom_video_resolution_value
    )
    _normalize_custom_video_duration_value = staticmethod(
        normalize_custom_video_duration_value
    )

    @staticmethod
    async def _resolve_custom_video_settings(
        context,
        *,
        update: Optional[Update] = None,
        warn_invalid_combo: bool = False,
    ) -> Tuple[str, str, int, int]:
        return await resolve_custom_video_settings(
            context,
            update=update,
            warn_invalid_combo=warn_invalid_combo,
            reply_text_func=robust_reply_text,
        )

    _build_message_spec = staticmethod(build_message_spec)
    _with_submitted_status = staticmethod(with_submitted_status)
    _with_completion_caption = staticmethod(with_completion_caption)

    @staticmethod
    def _resolve_display_mode_name(task_type: str, context) -> str:
        return resolve_display_mode_name(
            task_type,
            context=context,
            mode_name_map=MODE_NAME_MAP,
        )

    @staticmethod
    def _build_status_message(
        headline: str,
        *,
        notice: str = "",
        wait_text: Optional[str] = None,
    ) -> str:
        return build_status_message(
            headline,
            notice=notice,
            wait_text=wait_text,
        )

    @staticmethod
    def _build_cost_status_builder(
        headline_template: str,
        *,
        notice: str = "",
        wait_text: Optional[str] = None,
    ):
        return build_cost_status_builder(
            headline_template,
            notice=notice,
            wait_text=wait_text,
        )

    @staticmethod
    def _build_task_inputs(
        *,
        prompt: str,
        images: list[str],
        resolution,
        duration,
        **extra_fields,
    ):
        return build_task_inputs(
            prompt=prompt,
            images=images,
            resolution=resolution,
            duration=duration,
            **extra_fields,
        )

    @staticmethod
    def _resolve_video_billing_args(
        *,
        is_video: bool,
        resolution,
        task_type: str,
        duration=None,
        include_requested_duration: bool = True,
        allowed_task_types: set[str] | tuple[str, ...] | None = None,
        duration_transform=None,
    ):
        return resolve_video_billing_args(
            is_video=is_video,
            resolution=resolution,
            task_type=task_type,
            duration=duration,
            include_requested_duration=include_requested_duration,
            allowed_task_types=allowed_task_types,
            duration_transform=duration_transform,
        )

    @staticmethod
    def _build_log_prompt(
        prompt: str,
        *,
        resolution=None,
        duration=None,
        lora_name: str | None = None,
        task_type: str | None = None,
        lora_task_types: set[str] | tuple[str, ...] | None = None,
    ) -> str:
        return build_log_prompt(
            prompt,
            resolution=resolution,
            duration=duration,
            lora_name=lora_name,
            task_type=task_type,
            lora_task_types=lora_task_types,
        )

    _build_cleanup_paths = staticmethod(build_cleanup_paths)

    @staticmethod
    def _build_unexpected_error_log_message(task_label: str, *, verb: str = "in") -> str:
        return build_unexpected_error_log_message(task_label, verb=verb)

    @staticmethod
    def _build_result_reply_markup(task_type, task_id, allow_contribute, reply_markup):
        return build_result_reply_markup(
            task_type=task_type,
            task_id=task_id,
            allow_contribute=allow_contribute,
            reply_markup=reply_markup,
        )

    _resolve_result_mode_name = staticmethod(resolve_result_mode_name)
    _record_result_message_meta = staticmethod(record_result_message_meta)

    _send_result_media = staticmethod(send_result_media_seam)
    _cleanup_completion_status_message = staticmethod(
        cleanup_completion_status_message_seam
    )

    @staticmethod
    async def _finalize_cancelled_task_for_bot(**kwargs):
        return await finalize_cancelled_task_for_bot_seam(
            **kwargs,
            edit_text_func=robust_edit_text,
        )

    @staticmethod
    async def _finalize_failed_task_for_bot(**kwargs):
        return await finalize_failed_task_for_bot_seam(
            **kwargs,
            edit_text_func=robust_edit_text,
            send_message_func=robust_send_message,
        )

    @staticmethod
    async def _send_bot_warning(context, chat_id, error):
        await send_bot_warning_seam(
            context,
            chat_id,
            error,
            send_message_func=robust_send_message,
        )

    @staticmethod
    async def _send_bot_domain_error(context, chat_id, error):
        await send_bot_domain_error_seam(
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
            explicit_user_message=TaskService._build_bot_cancellation_message(
                runtime_state.actual_cost, message_spec
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

    _cleanup_runtime_state_if_needed = staticmethod(
        cleanup_runtime_state_if_needed_seam
    )

    _submit_bot_task = staticmethod(submit_bot_task_seam)

    _build_bot_cancellation_message = staticmethod(build_bot_cancellation_message)

    @staticmethod
    async def _send_initial_task_status(
        *,
        context,
        update,
        chat_id,
        status_msg_id,
        message_spec: BotTaskMessageSpec,
    ):
        return await send_initial_task_status_seam(
            context=context,
            update=update,
            chat_id=chat_id,
            status_msg_id=status_msg_id,
            message_spec=message_spec,
            get_or_send_status_msg_func=TaskService._get_or_send_status_msg,
            reply_text_func=robust_reply_text,
        )

    @staticmethod
    async def _update_submitted_task_status(*, status_msg, message_spec: BotTaskMessageSpec):
        await update_submitted_task_status_seam(
            status_msg=status_msg,
            message_spec=message_spec,
            edit_text_func=robust_edit_text,
        )

    @staticmethod
    async def _prepare_and_submit_bot_task(
        *,
        context,
        update,
        chat_id,
        status_msg_id=None,
        message_spec: BotTaskMessageSpec,
        submitted_status_builder: Optional[Callable[[int], str]] = None,
        runtime_state,
        internal_user_id,
        username,
        task_type,
        inputs,
        source_post_id=None,
        deduct_quota=True,
    ):
        return await prepare_and_submit_bot_task_seam(
            context=context,
            update=update,
            chat_id=chat_id,
            status_msg_id=status_msg_id,
            message_spec=message_spec,
            submitted_status_builder=submitted_status_builder,
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            task_type=task_type,
            inputs=inputs,
            source_post_id=source_post_id,
            deduct_quota=deduct_quota,
            with_submitted_status_func=TaskService._with_submitted_status,
            get_or_send_status_msg_func=TaskService._get_or_send_status_msg,
            send_initial_task_status_func=TaskService._send_initial_task_status,
            submit_bot_task_func=TaskService._submit_bot_task,
            update_submitted_task_status_func=TaskService._update_submitted_task_status,
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
        return await run_bot_task_flow_seam(
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
            with_submitted_status_func=TaskService._with_submitted_status,
            get_or_send_status_msg_func=TaskService._get_or_send_status_msg,
            send_result_media_func=TaskService._send_result_media,
            cleanup_completion_status_message_func=TaskService._cleanup_completion_status_message,
            cleanup_files_func=TaskService._cleanup_files,
            prepare_and_submit_bot_task_func=TaskService._prepare_and_submit_bot_task,
            monitor_submitted_bot_task_func=TaskService._monitor_submitted_bot_task,
            complete_monitored_bot_task_func=TaskService._complete_monitored_bot_task,
            send_bot_warning_func=TaskService._send_bot_warning,
            send_bot_domain_error_func=TaskService._send_bot_domain_error,
            handle_bot_cancelled_exception_func=TaskService._handle_bot_cancelled_exception,
            handle_bot_unexpected_exception_func=TaskService._handle_bot_unexpected_exception,
            cleanup_runtime_state_if_needed_func=TaskService._cleanup_runtime_state_if_needed,
        )

    @staticmethod
    async def _monitor_submitted_bot_task(
        *,
        task_id,
        status_msg,
        is_video,
        internal_user_id,
        monitor_func,
    ):
        return await monitor_submitted_bot_task_seam(
            task_id=task_id,
            status_msg=status_msg,
            is_video=is_video,
            internal_user_id=internal_user_id,
            monitor_func=monitor_func,
            monitor_bot_task_progress_func=TaskService._monitor_task_progress,
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
            TaskService._handle_task_completion,
        )
        kwargs.setdefault(
            "finalize_failed_task_for_bot_func",
            TaskService._finalize_failed_task_for_bot,
        )
        return await complete_monitored_bot_task(
            **kwargs,
        )

    _download_and_log_task_output = staticmethod(download_and_log_task_output_seam)

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
    async def monitor_task_progress(
        task_id, status_msg, is_video, monitor_func, identity_str=None, user_group=None
    ):
        return await TaskService._monitor_task_progress(
            task_id,
            status_msg,
            is_video,
            monitor_func,
            identity_str=identity_str,
            user_group=user_group,
        )

    @staticmethod
    async def _monitor_task_progress(
        task_id, status_msg, is_video, monitor_func, identity_str=None, user_group=None
    ):
        return await monitor_task_progress_seam(
            task_id,
            status_msg,
            is_video=is_video,
            monitor_func=monitor_func,
            identity_str=identity_str,
            user_group=user_group,
            edit_status_text_func=robust_edit_text,
        )

    @staticmethod
    async def handle_task_completion(
        context,
        chat_id,
        internal_user_id,
        prompt,
        task_type,
        task_id,
        saved_input_images,
        user_logger,
        is_video,
        send_result,
        reply_markup,
        status_msg,
        delete_status,
        caption=None,
        allow_contribute=True,
        billing_resolution: Optional[str] = None,
        requested_duration: Optional[int] = None,
        send_result_media_func=None,
        cleanup_completion_status_message_func=None,
        download_and_log_task_output_func=None,
    ):
        return await TaskService._handle_task_completion(
            context=context,
            chat_id=chat_id,
            internal_user_id=internal_user_id,
            prompt=prompt,
            task_type=task_type,
            task_id=task_id,
            saved_input_images=saved_input_images,
            user_logger=user_logger,
            is_video=is_video,
            send_result=send_result,
            reply_markup=reply_markup,
            status_msg=status_msg,
            delete_status=delete_status,
            caption=caption,
            allow_contribute=allow_contribute,
            billing_resolution=billing_resolution,
            requested_duration=requested_duration,
            send_result_media_func=send_result_media_func,
            cleanup_completion_status_message_func=cleanup_completion_status_message_func,
            download_and_log_task_output_func=download_and_log_task_output_func,
        )

    @staticmethod
    async def _handle_task_completion(
        context,
        chat_id,
        internal_user_id,
        prompt,
        task_type,
        task_id,
        saved_input_images,
        user_logger,
        is_video,
        send_result,
        reply_markup,
        status_msg,
        delete_status,
        caption=None,
        allow_contribute=True,
        billing_resolution: Optional[str] = None,
        requested_duration: Optional[int] = None,
        send_result_media_func=None,
        cleanup_completion_status_message_func=None,
        download_and_log_task_output_func=None,
    ):
        send_result_media_func = send_result_media_func or TaskService._send_result_media
        cleanup_completion_status_message_func = (
            cleanup_completion_status_message_func
            or TaskService._cleanup_completion_status_message
        )
        download_and_log_task_output_func = (
            download_and_log_task_output_func
            or TaskService._download_and_log_task_output
        )
        return await handle_task_completion_seam(
            context=context,
            chat_id=chat_id,
            internal_user_id=internal_user_id,
            prompt=prompt,
            task_type=task_type,
            task_id=task_id,
            saved_input_images=saved_input_images,
            user_logger=user_logger,
            is_video=is_video,
            send_result=send_result,
            reply_markup=reply_markup,
            status_msg=status_msg,
            delete_status=delete_status,
            caption=caption,
            allow_contribute=allow_contribute,
            billing_resolution=billing_resolution,
            requested_duration=requested_duration,
            send_result_media_func=send_result_media_func,
            cleanup_completion_status_message_func=cleanup_completion_status_message_func,
            download_and_log_task_output_func=download_and_log_task_output_func,
        )

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
