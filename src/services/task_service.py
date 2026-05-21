"""
🚨 架构红线警告 (ARCHITECTURE REDLINE) 🚨
本文件 `task_service.py` 已经被明确定义为 Telegram Bot 专属的表示层 (Presentation Layer) / Handler 层。
严禁在任何 Web API Router (如 src/web_api/routers/*.py) 中导入或调用此文件中的逻辑。
Web API 应直接调用 `src/core/task_core.py` 提供的业务门面 (Facade)。
"""

import logging
import os
from dataclasses import replace
from typing import Callable, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.constants import (
    DEFAULT_DURATION,
    DEFAULT_RESOLUTION,
    MODE_BLOWJOB,
    MODE_CLOSEUP_BLOWJOB,
    MODE_DOGGY_STYLE,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_UNDRESS_TONGUE,
    TMP_DIR,
)
from src.handlers.utils import MockMessage
from src.logger import UserLogger
from src.services.image_service import image_service
from src.services.permission_service import permission_service
from src.services.task_registry import TaskRegistry
from src.services.task_service_completion import (
    download_and_log_task_output,
    handle_task_completion,
)
from src.services.task_service_entrypoints import (
    process_custom_video_task as process_custom_video_task_entrypoint,
    process_face_video_task as process_face_video_task_entrypoint,
    process_generation_task as process_generation_task_entrypoint,
    process_i2i_pro_task as process_i2i_pro_task_entrypoint,
    process_ltx_video_task as process_ltx_video_task_entrypoint,
    process_video_task_template as process_video_task_template_entrypoint,
)
from src.services.task_service_finalize import (
    build_bot_cancellation_message,
    cleanup_runtime_state_if_needed,
    send_bot_domain_error,
    send_bot_warning,
)
from src.services.task_service_flow import (
    mark_task_submission_succeeded,
    prepare_and_submit_bot_task,
    run_bot_task_flow,
    submit_bot_task,
)
from src.services.task_service_types import BotTaskMessageSpec, BotTaskRuntimeState
from src.services.tg_task_runtime import (
    build_vip_suffix,
    build_result_reply_markup,
    cleanup_completion_status_message,
    record_result_message_meta,
    resolve_result_mode_name,
    send_result_media,
)
from src.utils import robust_edit_text, robust_reply_text, robust_send_message

logger = logging.getLogger(__name__)

# Compatibility exports for older tests and monkeypatch targets.
_COMPAT_TEST_EXPORTS = (UserLogger, image_service, TaskRegistry)


class TaskService:
    @staticmethod
    def _create_runtime_state(**kwargs) -> BotTaskRuntimeState:
        return BotTaskRuntimeState(**kwargs)

    @staticmethod
    def _normalize_custom_video_resolution_value(resolution: str) -> int:
        if resolution == "1024p":
            return 1024
        if resolution == "720p":
            return 720
        return 512

    @staticmethod
    def _normalize_custom_video_duration_value(duration: str) -> int:
        if duration == "10s":
            return 10
        if duration == "8s":
            return 8
        return 5

    @staticmethod
    async def _resolve_custom_video_settings(
        context,
        *,
        update: Optional[Update] = None,
        warn_invalid_combo: bool = False,
    ) -> Tuple[str, str, int, int]:
        resolution = context.user_data.get("custom_video_resolution", DEFAULT_RESOLUTION)
        duration = context.user_data.get("custom_video_duration", DEFAULT_DURATION)

        if resolution == "1024p" and duration == "10s":
            resolution = "720p"
            context.user_data["custom_video_resolution"] = resolution
            if warn_invalid_combo and update is not None:
                await robust_reply_text(
                    update.effective_message,
                    "⚠️ 检测到非法配置(1024p+10s)，已自动降级为720p+10s。",
                )

        return (
            resolution,
            duration,
            TaskService._normalize_custom_video_resolution_value(resolution),
            TaskService._normalize_custom_video_duration_value(duration),
        )

    @staticmethod
    def _build_message_spec(
        *,
        initial_status_text: str,
        submitted_status_text: Optional[str] = None,
        progress_wait_text: Optional[str] = None,
        completion_caption: Optional[str] = None,
        missing_output_message: str = "生成完成但未获取到文件路径，已退还灵石",
        cancellation_message_template: str = "任务已撤销，预扣的 {cost} 灵石已全额退回。",
    ) -> BotTaskMessageSpec:
        return BotTaskMessageSpec(
            initial_status_text=initial_status_text,
            submitted_status_text=submitted_status_text,
            progress_wait_text=progress_wait_text,
            completion_caption=completion_caption,
            missing_output_message=missing_output_message,
            cancellation_message_template=cancellation_message_template,
        )

    @staticmethod
    def _with_submitted_status(
        spec: BotTaskMessageSpec, submitted_status_text: str
    ) -> BotTaskMessageSpec:
        return replace(spec, submitted_status_text=submitted_status_text)

    @staticmethod
    def _with_completion_caption(
        spec: BotTaskMessageSpec, completion_caption: str
    ) -> BotTaskMessageSpec:
        return replace(spec, completion_caption=completion_caption)

    @staticmethod
    def _build_result_reply_markup(task_type, task_id, allow_contribute, reply_markup):
        return build_result_reply_markup(
            task_type=task_type,
            task_id=task_id,
            allow_contribute=allow_contribute,
            reply_markup=reply_markup,
        )

    @staticmethod
    def _resolve_result_mode_name(task_type):
        return resolve_result_mode_name(task_type)

    @staticmethod
    def _record_result_message_meta(context, sent_msg, task_type, prompt, task_id):
        record_result_message_meta(context, sent_msg, task_type, prompt, task_id)

    @staticmethod
    async def _send_result_media(
        *,
        context,
        chat_id,
        media_bytes,
        is_video,
        caption,
        task_type,
        task_id,
        allow_contribute,
        reply_markup,
        prompt,
    ):
        return await send_result_media(
            context=context,
            chat_id=chat_id,
            media_bytes=media_bytes,
            is_video=is_video,
            caption=caption,
            task_type=task_type,
            task_id=task_id,
            allow_contribute=allow_contribute,
            reply_markup=reply_markup,
            prompt=prompt,
        )

    @staticmethod
    async def _cleanup_completion_status_message(*, status_msg, delete_status, send_result):
        await cleanup_completion_status_message(
            status_msg=status_msg,
            delete_status=delete_status,
            send_result=send_result,
        )

    @staticmethod
    async def _finalize_cancelled_task_for_bot(
        *,
        status_msg,
        internal_user_id,
        username,
        cost,
        task_submitted,
        registry_task_id,
        explicit_user_message,
    ):
        from src.core.task_core import finalize_task_cancellation

        cancellation_result = await finalize_task_cancellation(
            internal_user_id=internal_user_id,
            username=username,
            cost=cost,
            task_submitted=task_submitted,
            registry_task_id=registry_task_id,
            explicit_user_message=explicit_user_message,
        )
        if status_msg:
            await robust_edit_text(status_msg, f"✅ {cancellation_result.user_message}")
        return cancellation_result

    @staticmethod
    async def _finalize_failed_task_for_bot(
        *,
        context,
        chat_id,
        status_msg,
        internal_user_id,
        username,
        cost,
        should_refund,
        registry_task_id,
        release_lock,
        message_prefix="❌",
        prefer_edit_status=False,
        fallback_to_send_message=True,
        explicit_user_message=None,
        error=None,
        generic_error_prefix=None,
        refund_suffix_mode="if_refunded",
    ):
        from src.core.task_core import finalize_task_failure

        failure_result = await finalize_task_failure(
            internal_user_id=internal_user_id,
            username=username,
            cost=cost,
            should_refund=should_refund,
            registry_task_id=registry_task_id,
            release_lock=release_lock,
            explicit_user_message=explicit_user_message,
            error=error,
            generic_error_prefix=generic_error_prefix,
            refund_suffix_mode=refund_suffix_mode,
        )
        if prefer_edit_status and status_msg:
            await robust_edit_text(status_msg, f"{message_prefix} {failure_result.user_message}")
        elif fallback_to_send_message:
            await robust_send_message(
                context.bot,
                chat_id,
                f"{message_prefix} {failure_result.user_message}",
            )
        return failure_result

    @staticmethod
    async def _send_bot_warning(context, chat_id, error):
        await send_bot_warning(context, chat_id, error)

    @staticmethod
    async def _send_bot_domain_error(context, chat_id, error):
        await send_bot_domain_error(context, chat_id, error)

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

    @staticmethod
    async def _cleanup_runtime_state_if_needed(
        *,
        internal_user_id,
        registry_task_id,
        release_lock,
        terminal_state_finalized,
    ):
        await cleanup_runtime_state_if_needed(
            internal_user_id=internal_user_id,
            registry_task_id=registry_task_id,
            release_lock=release_lock,
            terminal_state_finalized=terminal_state_finalized,
        )

    @staticmethod
    def _mark_task_submission_succeeded(runtime_state, result: dict) -> list[str]:
        return mark_task_submission_succeeded(runtime_state, result)

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
    ) -> tuple[str, list[str]]:
        return await submit_bot_task(
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            task_type=task_type,
            inputs=inputs,
            source_post_id=source_post_id,
            deduct_quota=deduct_quota,
        )

    @staticmethod
    def _build_bot_cancellation_message(cost: int, spec: BotTaskMessageSpec) -> str:
        return build_bot_cancellation_message(cost, spec)

    @staticmethod
    async def _send_initial_task_status(
        *,
        context,
        update,
        chat_id,
        status_msg_id,
        message_spec: BotTaskMessageSpec,
    ):
        if update is not None:
            return await robust_reply_text(
                update.effective_message, message_spec.initial_status_text
            )
        return await TaskService._get_or_send_status_msg(
            context, chat_id, status_msg_id, message_spec.initial_status_text
        )

    @staticmethod
    async def _update_submitted_task_status(*, status_msg, message_spec: BotTaskMessageSpec):
        if message_spec.submitted_status_text:
            await robust_edit_text(status_msg, message_spec.submitted_status_text)
        elif message_spec.progress_wait_text:
            await robust_edit_text(status_msg, message_spec.progress_wait_text)

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
        return await prepare_and_submit_bot_task(
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
        from src.core.billing_core import get_user_priority_and_identity

        _priority, identity_str, user_group = await get_user_priority_and_identity(
            internal_user_id
        )
        return await TaskService._monitor_task_progress(
            task_id,
            status_msg,
            is_video=is_video,
            monitor_func=monitor_func,
            identity_str=identity_str,
            user_group=user_group,
        )

    @staticmethod
    async def _complete_monitored_bot_task(
        *,
        context,
        chat_id,
        status_msg,
        runtime_state,
        internal_user_id,
        username,
        prompt,
        task_type,
        task_id,
        saved_input_images,
        user_logger,
        final_info,
        is_video,
        send_result=True,
        reply_markup=None,
        delete_status=True,
        caption=None,
        allow_contribute=True,
        billing_resolution: Optional[str] = None,
        requested_duration: Optional[int] = None,
        message_spec: BotTaskMessageSpec,
        missing_output_should_refund: bool = True,
    ) -> Tuple[Optional[bytes], Optional[str]]:
        if final_info:
            return await TaskService._handle_task_completion(
                context,
                chat_id,
                internal_user_id,
                prompt,
                task_type,
                task_id,
                saved_input_images,
                user_logger,
                is_video=is_video,
                send_result=send_result,
                reply_markup=reply_markup,
                status_msg=status_msg,
                delete_status=delete_status,
                caption=caption or message_spec.completion_caption,
                allow_contribute=allow_contribute,
                billing_resolution=billing_resolution,
                requested_duration=requested_duration,
            )

        await TaskService._finalize_failed_task_for_bot(
            context=context,
            chat_id=chat_id,
            status_msg=None,
            internal_user_id=internal_user_id,
            username=username,
            cost=runtime_state.actual_cost,
            should_refund=missing_output_should_refund,
            registry_task_id=runtime_state.registry_task_id,
            release_lock=runtime_state.task_submitted,
            explicit_user_message=message_spec.missing_output_message,
        )
        runtime_state.terminal_state_finalized = True
        return None, None

    @staticmethod
    async def _download_and_log_task_output(
        *,
        internal_user_id,
        username,
        prompt,
        task_type,
        task_id,
        saved_input_images,
        is_video,
        allow_contribute,
        billing_resolution: Optional[str],
        requested_duration: Optional[int],
    ):
        return await download_and_log_task_output(
            internal_user_id=internal_user_id,
            username=username,
            prompt=prompt,
            task_type=task_type,
            task_id=task_id,
            saved_input_images=saved_input_images,
            is_video=is_video,
            allow_contribute=allow_contribute,
            billing_resolution=billing_resolution,
            requested_duration=requested_duration,
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

    @staticmethod
    async def _get_or_send_status_msg(context, chat_id, status_msg_id, text):
        if status_msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=status_msg_id, text=text
                )
                return MockMessage(context.bot, chat_id, status_msg_id)
            except Exception:
                pass
        return await robust_send_message(context.bot, chat_id, text)

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
        from src.core.task_core import CoreDomainError

        def _raise_cancelled():
            raise CoreDomainError("cancelled")

        last_progress = 0
        last_status = None
        last_queue_pos = None
        final_info = None
        cancel_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ 撤销任务", callback_data=f"cancel_task_{task_id}")]]
        )

        async def update_status_message(text, **kwargs):
            if not status_msg:
                return False
            try:
                kwargs["reply_markup"] = cancel_markup if "排队中" in text else None
                await robust_edit_text(status_msg, text, **kwargs)
                return True
            except Exception as exc:
                logger.warning(
                    "Failed to update status message for task %s: %s", task_id, exc
                )
                return False

        vip_suffix = build_vip_suffix(
            identity_str=identity_str, user_group=user_group
        )

        async for info in monitor_func(task_id, is_video=is_video):
            status = info.get("status")
            progress = info.get("progress", 0)

            if status == "done":
                final_info = info
                if not is_video and last_progress != 100:
                    await update_status_message("⏳ 生成中... 100%")
                break

            if status in ["error", "failed", "cancelled"]:
                if status == "cancelled":
                    logger.warning("Task %s was cancelled.", task_id)
                    _raise_cancelled()
                raise RuntimeError(info.get("error", "Unknown error"))

            if status == "pending":
                raw_pos = info.get("queue_pos")
                queue_pos = None
                if raw_pos is not None:
                    try:
                        queue_pos = int(raw_pos) + 1
                    except (ValueError, TypeError):
                        queue_pos = raw_pos
                else:
                    queue_pos = info.get("queue_remaining")

                if queue_pos is not None:
                    if queue_pos != last_queue_pos or last_status != "pending":
                        if await update_status_message(
                            f"⏳ 排队中... (第 {queue_pos} 位){vip_suffix}",
                            parse_mode="Markdown",
                        ):
                            last_queue_pos = queue_pos
                            last_status = "pending"
                else:
                    if last_status != "pending":
                        if await update_status_message(
                            f"⏳ 排队中...{vip_suffix}", parse_mode="Markdown"
                        ):
                            last_status = "pending"
                continue

            if progress != last_progress or last_status == "pending":
                text = "⏳ 正在生成视频..." if is_video else f"⏳ 生成中... {progress}%"
                if await update_status_message(text):
                    last_progress = progress
                    last_status = status

        if final_info is None:
            raise CoreDomainError("cancelled")
        return final_info

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
    ):
        return await handle_task_completion(
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
            send_result_media_func=TaskService._send_result_media,
            cleanup_completion_status_message_func=TaskService._cleanup_completion_status_message,
        )

    @staticmethod
    def _cleanup_files(paths: List[str]):
        for path in paths:
            if path.startswith(TMP_DIR) and os.path.exists(path):
                with contextlib.suppress(OSError):
                    os.remove(path)

    @staticmethod
    async def _get_acceleration_notice(user_id: int) -> str:
        stats = await permission_service.quota_manager.get_user_stats(user_id)
        if stats.get("generation_count", 0) < 2:
            return "\n✨ [新手特权] 前2次生成享受极速排队通道！"
        return ""


task_service = TaskService()
