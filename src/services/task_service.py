"""
🚨 架构红线警告 (ARCHITECTURE REDLINE) 🚨
本文件 `task_service.py` 已经被明确定义为 Telegram Bot 专属的表示层 (Presentation Layer) / Handler 层。
严禁在任何 Web API Router (如 src/web_api/routers/*.py) 中导入或调用此文件中的逻辑。
Web API 应直接调用 `src/core/task_core.py` 提供的业务门面 (Facade)。
"""

import logging
import os
from dataclasses import dataclass, replace
from typing import Callable, List, Optional, Tuple

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.core.video_billing import (
    normalize_requested_billing_resolution,
    normalize_requested_duration_seconds,
)
from src.constants import (
    DEFAULT_DURATION,
    DEFAULT_RESOLUTION,
    MODE_BLOWJOB,
    MODE_CLOSEUP_BLOWJOB,
    MODE_CUSTOM_VIDEO,
    MODE_DOGGY_STYLE,
    MODE_FACE_VIDEO_STEP1,
    MODE_IMG2IMG_LORA,
    MODE_NAME_MAP,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_UNDRESS_TONGUE,
    TMP_DIR,
)
from src.handlers.utils import MockMessage
from src.logger import UserLogger
from src.services.image_service import image_service
from src.services.permission_service import permission_service
from src.services.tg_task_runtime import (
    build_result_reply_markup,
    cleanup_completion_status_message,
    monitor_task_progress,
    record_result_message_meta,
    resolve_result_mode_name,
    send_result_media,
)
from src.utils import (
    load_prompts,
    robust_edit_text,
    robust_reply_text,
    robust_send_message,
)

logger = logging.getLogger(__name__)


@dataclass
class BotTaskRuntimeState:
    registry_task_id: Optional[str] = None
    task_submitted: bool = False
    actual_cost: int = 0
    terminal_state_finalized: bool = False


@dataclass(frozen=True)
class BotTaskMessageSpec:
    initial_status_text: str
    submitted_status_text: Optional[str] = None
    progress_wait_text: Optional[str] = None
    completion_caption: Optional[str] = None
    missing_output_message: str = "生成完成但未获取到文件路径，已退还灵石"
    cancellation_message_template: str = "任务已撤销，预扣的 {cost} 灵石已全额退回。"


class TaskService:
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
            release_lock=task_submitted,
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
        await robust_send_message(context.bot, chat_id, f"⚠️ {error}")

    @staticmethod
    async def _send_bot_domain_error(context, chat_id, error):
        await robust_send_message(context.bot, chat_id, f"❌ {error}")

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
        if terminal_state_finalized or not (release_lock or registry_task_id):
            return

        import asyncio

        from src.core.task_core import cleanup_task_runtime_state

        await asyncio.shield(
            cleanup_task_runtime_state(
                internal_user_id=internal_user_id,
                registry_task_id=registry_task_id,
                release_lock=release_lock,
            )
        )

    @staticmethod
    def _mark_task_submission_succeeded(runtime_state, result: dict) -> list[str]:
        runtime_state.task_submitted = True
        runtime_state.actual_cost = result["cost"]
        runtime_state.registry_task_id = result["registry_task_id"]
        return result["saved_inputs"]

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
        import uuid

        from asgi_correlation_id import correlation_id

        from src.core.task_core import process_and_submit_task

        task_id = str(uuid.uuid4())
        correlation_id.set(task_id)

        result = await process_and_submit_task(
            user_id=internal_user_id,
            username=username,
            task_type=task_type,
            inputs=inputs,
            task_id=task_id,
            client_type="bot",
            source_post_id=source_post_id,
            deduct_quota=deduct_quota,
        )
        saved_inputs = TaskService._mark_task_submission_succeeded(runtime_state, result)
        return task_id, saved_inputs

    @staticmethod
    def _build_bot_cancellation_message(cost: int, spec: BotTaskMessageSpec) -> str:
        return spec.cancellation_message_template.format(cost=cost)

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
        status_msg = await TaskService._send_initial_task_status(
            context=context,
            update=update,
            chat_id=chat_id,
            status_msg_id=status_msg_id,
            message_spec=message_spec,
        )
        task_id, saved_inputs = await TaskService._submit_bot_task(
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            task_type=task_type,
            inputs=inputs,
            source_post_id=source_post_id,
            deduct_quota=deduct_quota,
        )
        if submitted_status_builder is not None:
            message_spec = TaskService._with_submitted_status(
                message_spec,
                submitted_status_builder(runtime_state.actual_cost),
            )
        await TaskService._update_submitted_task_status(
            status_msg=status_msg,
            message_spec=message_spec,
        )
        return status_msg, task_id, saved_inputs, message_spec

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
        from src.core.task_core import (
            ConcurrencyLimitError,
            CoreDomainError,
            InsufficientCreditsError,
        )

        media_bytes = None
        full_output_path = None

        try:
            status_msg, task_id, saved_inputs, message_spec = (
                await TaskService._prepare_and_submit_bot_task(
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
                )
            )

            final_info = await TaskService._monitor_submitted_bot_task(
                task_id=task_id,
                status_msg=status_msg,
                is_video=is_video,
                internal_user_id=internal_user_id,
                monitor_func=image_service.monitor_progress,
            )

            media_bytes, full_output_path = await TaskService._complete_monitored_bot_task(
                context=context,
                chat_id=chat_id,
                status_msg=status_msg,
                runtime_state=runtime_state,
                internal_user_id=internal_user_id,
                username=username,
                prompt=prompt,
                task_type=task_type,
                task_id=task_id,
                saved_input_images=saved_inputs,
                user_logger=UserLogger(internal_user_id, username),
                final_info=final_info,
                is_video=is_video,
                send_result=send_result,
                reply_markup=reply_markup,
                delete_status=delete_status,
                allow_contribute=allow_contribute,
                billing_resolution=billing_resolution,
                requested_duration=requested_duration,
                message_spec=message_spec,
                missing_output_should_refund=missing_output_should_refund,
            )

        except ConcurrencyLimitError as e:
            await TaskService._send_bot_warning(context, chat_id, e)
            return None, None
        except InsufficientCreditsError as e:
            await TaskService._send_bot_warning(context, chat_id, e)
            return None, None
        except CoreDomainError as e:
            if str(e) == "cancelled":
                return await TaskService._handle_bot_cancelled_exception(
                    status_msg=locals().get("status_msg"),
                    runtime_state=runtime_state,
                    internal_user_id=internal_user_id,
                    username=username,
                    message_spec=locals().get("message_spec", message_spec),
                    deduct_quota=deduct_quota,
                )
            await TaskService._send_bot_domain_error(context, chat_id, e)
            return None, None
        except Exception as e:
            return await TaskService._handle_bot_unexpected_exception(
                context=context,
                chat_id=chat_id,
                status_msg=locals().get("status_msg") if prefer_edit_status else None,
                runtime_state=runtime_state,
                internal_user_id=internal_user_id,
                username=username,
                error=e,
                log_message=unexpected_error_log_message.format(
                    internal_user_id=internal_user_id,
                    error=e,
                ),
                should_refund=(
                    unexpected_should_refund(runtime_state)
                    if unexpected_should_refund is not None
                    else deduct_quota and runtime_state.task_submitted
                ),
                generic_error_prefix=unexpected_error_prefix,
                prefer_edit_status=prefer_edit_status,
                refund_suffix_mode=refund_suffix_mode,
            )
        finally:
            await TaskService._cleanup_runtime_state_if_needed(
                internal_user_id=internal_user_id,
                registry_task_id=runtime_state.registry_task_id,
                release_lock=runtime_state.task_submitted,
                terminal_state_finalized=runtime_state.terminal_state_finalized,
            )
            if cleanup_enabled and cleanup_paths:
                TaskService._cleanup_files(cleanup_paths)

        return media_bytes, full_output_path

    @staticmethod
    async def _monitor_submitted_bot_task(
        *,
        task_id,
        status_msg,
        is_video,
        internal_user_id,
        monitor_func,
    ):
        from src.core.billing_core import (
            get_user_priority_and_identity,
        )

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
        from src.core.task_core import persist_successful_task_result

        persistence_result = await persist_successful_task_result(
            backend_task_id=task_id,
            registry_task_id=task_id,
            internal_user_id=internal_user_id,
            username=username,
            prompt=prompt,
            task_type=task_type,
            input_images=saved_input_images,
            allow_contribute=allow_contribute,
            is_video=is_video,
            billing_resolution=billing_resolution,
            requested_duration=requested_duration,
            source="bot",
            refresh_user_group_after_log=True,
        )
        return (
            persistence_result.media_bytes,
            persistence_result.output_file,
            persistence_result.width,
            persistence_result.height,
            persistence_result.duration,
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
        from src.core.user_core import get_or_create_user_by_telegram

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        username = update.effective_user.username

        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        from src.constants import MODE_LTX_VIDEO

        mode = MODE_LTX_VIDEO

        resolution = context.user_data.get("ltx_video_resolution", "1280x704")
        duration = context.user_data.get("ltx_video_duration", "5s")

        runtime_state = BotTaskRuntimeState()
        notice = await TaskService._get_acceleration_notice(user_id)
        message_spec = TaskService._build_message_spec(
            initial_status_text=(
                f"🚀 正在处理高级图生视频任务 (画质:{resolution}, 时长:{duration})...{notice}"
            ),
            progress_wait_text="⏳ 正在生成高级视频，可能需要数分钟，请耐心等待...",
            completion_caption="✅ 高级图生视频生成完成",
        )
        inputs = {
            "prompt": prompt,
            "images": [image_path] if image_path else [],
            "resolution": resolution,
            "duration": duration,
        }

        return await TaskService._run_bot_task_flow(
            context=context,
            update=update,
            chat_id=chat_id,
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            task_type=mode,
            inputs=inputs,
            prompt=prompt,
            is_video=True,
            message_spec=message_spec,
            submitted_status_builder=lambda actual_cost: (
                f"🚀 正在处理高级图生视频任务 (画质:{resolution}, 时长:{duration}, 消耗{actual_cost}灵石)...{notice}"
            ),
            source_post_id=source_post_id,
            allow_contribute=allow_contribute,
            billing_resolution=normalize_requested_billing_resolution(
                resolution, mode
            ),
            requested_duration=normalize_requested_duration_seconds(duration),
            unexpected_should_refund=lambda state: state.task_submitted
            and state.actual_cost > 0,
            unexpected_error_log_message="Error in ltx video task for user {internal_user_id}: {error}",
            unexpected_error_prefix="出错了",
            cleanup_paths=[image_path] if image_path else None,
            cleanup_enabled=cleanup,
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
        from src.core.user_core import get_or_create_user_by_telegram

        # 1. 身份转换 (TG ID -> 内部 ID)
        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        mode = MODE_FACE_VIDEO_STEP1
        runtime_state = BotTaskRuntimeState(actual_cost=cost)
        notice = await TaskService._get_acceleration_notice(user_id)
        message_spec = TaskService._build_message_spec(
            initial_status_text=f"🚀 正在处理视频换脸任务 (画质:{resolution}p)...{notice}",
            completion_caption="✅ 视频换脸完成",
            missing_output_message="生成失败或超时，已退还灵石。",
        )
        inputs = {
            "prompt": "Video Face Swap",
            "images": [face_image_path, video_path]
            if face_image_path and video_path
            else [],
            "resolution": resolution,
            "duration": duration,
        }

        return await TaskService._run_bot_task_flow(
            context=context,
            update=None,
            chat_id=chat_id,
            status_msg_id=message_id,
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            task_type=mode,
            inputs=inputs,
            prompt="face video",
            is_video=True,
            message_spec=message_spec,
            submitted_status_builder=lambda actual_cost: (
                f"🚀 正在处理视频换脸任务 (画质:{resolution}p, 消耗{actual_cost}灵石)...{notice}"
            ),
            source_post_id=source_post_id,
            billing_resolution=normalize_requested_billing_resolution(
                resolution, mode
            ),
            prefer_edit_status=True,
            unexpected_should_refund=lambda state: state.task_submitted
            and state.actual_cost > 0,
            unexpected_error_log_message="Error processing face video task for {internal_user_id}: {error}",
            unexpected_error_prefix="系统错误",
            cleanup_paths=[face_image_path, video_path],
            cleanup_enabled=cleanup,
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
        """Common generation logic for generic tasks."""
        from src.core.user_core import get_or_create_user_by_telegram

        # 1. 身份转换
        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        if not task_type:
            task_type = "video" if is_video else "image"

        resolution = 512
        duration = 5

        if is_video and task_type in [MODE_CUSTOM_VIDEO, "video_lora"]:
            _, _, resolution, duration = await TaskService._resolve_custom_video_settings(
                context
            )

        runtime_state = BotTaskRuntimeState()
        notice = await TaskService._get_acceleration_notice(user_id)
        inputs = {
            "prompt": prompt,
            "images": images,
            "resolution": resolution,
            "duration": duration,
            "lora_name": lora_name,
            "lora_strength": lora_strength,
        }
        message_spec = TaskService._build_message_spec(
            initial_status_text=(
                f"🚀 正在处理视频生成任务...{notice}"
                if is_video
                else f"🚀 正在处理 {len(images)} 张图片...{notice}"
            ),
            missing_output_message="生成完成但未获取到文件路径，已退还灵石",
        )

        log_prompt = prompt
        if task_type in ("video_lora", MODE_IMG2IMG_LORA) and lora_name:
            log_prompt = f"[模型: {lora_name}] {prompt}"

        from src.constants import MODE_NAME_MAP

        mode_name = MODE_NAME_MAP.get(task_type, task_type)
        display_mode_name = context.t(mode_name) if hasattr(context, "t") else mode_name
        message_spec = TaskService._with_completion_caption(
            message_spec,
            f"✅ {display_mode_name} 生成完成",
        )

        return await TaskService._run_bot_task_flow(
            context=context,
            update=None,
            chat_id=chat_id,
            status_msg_id=status_msg_id,
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            task_type=task_type,
            inputs=inputs,
            prompt=log_prompt,
            is_video=is_video,
            message_spec=message_spec,
            submitted_status_builder=lambda actual_cost: (
                f"🚀 正在处理视频生成任务 (消耗{actual_cost}灵石)...{notice}"
                if is_video
                else f"🚀 正在处理 {len(images)} 张图片 (消耗{actual_cost}灵石)...{notice}"
            ),
            source_post_id=source_post_id,
            deduct_quota=deduct_quota,
            send_result=send_result,
            reply_markup=reply_markup,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
            billing_resolution=(
                normalize_requested_billing_resolution(resolution, task_type)
                if is_video
                else None
            ),
            requested_duration=(
                duration
                if is_video and task_type in (MODE_CUSTOM_VIDEO, "video_lora")
                else None
            ),
            missing_output_should_refund=deduct_quota,
            unexpected_error_log_message="Error in process_generation_task for user {internal_user_id}: {error}",
            unexpected_error_prefix="出错了",
            cleanup_paths=images,
            cleanup_enabled=cleanup,
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
        """
        Generic handler for video generation tasks to reduce code duplication.
        """
        from src.core.user_core import get_or_create_user_by_telegram

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        username = update.effective_user.username

        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        resolution, duration_str, res_val, duration = (
            await TaskService._resolve_custom_video_settings(
                context,
                update=update,
                warn_invalid_combo=True,
            )
        )

        prompts_config = load_prompts()
        base_prompt = prompts_config.get(default_prompt_key, default_prompt_text)

        mode_name = MODE_NAME_MAP.get(mode, mode)
        display_mode_name = context.t(mode_name) if hasattr(context, "t") else mode_name
        runtime_state = BotTaskRuntimeState()
        notice = await TaskService._get_acceleration_notice(user_id)
        message_spec = TaskService._build_message_spec(
            initial_status_text=(
                f"🚀 正在处理{display_mode_name}生成任务 (画质:{resolution}, 时长:{duration_str})...{notice}"
            ),
            progress_wait_text="⏳ 正在生成视频，请耐心等待...",
            completion_caption=f"✅ {display_mode_name} 生成完成",
            missing_output_message="生成完成但未获取到任务信息，已退还灵石",
        )
        inputs = {
            "prompt": base_prompt,
            "images": [image_path] if image_path else [],
            "resolution": res_val,
            "duration": duration,
        }

        return await TaskService._run_bot_task_flow(
            context=context,
            update=update,
            chat_id=chat_id,
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            task_type=mode,
            inputs=inputs,
            prompt=f"[{resolution}|{duration_str}] {base_prompt}",
            is_video=True,
            message_spec=message_spec,
            submitted_status_builder=lambda actual_cost: (
                f"🚀 正在处理{display_mode_name}生成任务 (画质:{resolution}, 时长:{duration_str}, 消耗{actual_cost}灵石)...{notice}"
            ),
            source_post_id=source_post_id,
            allow_contribute=allow_contribute,
            billing_resolution=normalize_requested_billing_resolution(
                resolution, mode
            ),
            requested_duration=duration,
            unexpected_should_refund=lambda state: state.task_submitted
            and state.actual_cost > 0,
            unexpected_error_log_message="Error in {mode} task for user {internal_user_id}: {error}".replace(
                "{mode}", mode
            ),
            unexpected_error_prefix="出错了",
            cleanup_paths=[image_path] if image_path else None,
            cleanup_enabled=cleanup,
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
        from src.core.user_core import get_or_create_user_by_telegram

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        username = update.effective_user.username

        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        mode = MODE_CUSTOM_VIDEO
        resolution, duration, _res_val, _duration_val = (
            await TaskService._resolve_custom_video_settings(
                context,
                update=update,
                warn_invalid_combo=True,
            )
        )

        runtime_state = BotTaskRuntimeState()
        notice = await TaskService._get_acceleration_notice(user_id)
        message_spec = TaskService._build_message_spec(
            initial_status_text=(
                f"🚀 正在处理自定义视频生成任务 (画质:{resolution}, 时长:{duration})...{notice}"
            ),
            progress_wait_text="⏳ 正在生成自定义视频，请耐心等待...",
            completion_caption="✅ 自定义图生视频生成完成",
        )
        inputs = {
            "prompt": prompt,
            "images": [image_path] if image_path else [],
            "resolution": resolution,
            "duration": duration,
        }

        return await TaskService._run_bot_task_flow(
            context=context,
            update=update,
            chat_id=chat_id,
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            task_type=mode,
            inputs=inputs,
            prompt=f"[{resolution}|{duration}] {prompt}",
            is_video=True,
            message_spec=message_spec,
            submitted_status_builder=lambda actual_cost: (
                f"🚀 正在处理自定义视频生成任务 (画质:{resolution}, 时长:{duration}, 消耗{actual_cost}灵石)...{notice}\n⏳ 正在生成自定义视频，请耐心等待..."
            ),
            source_post_id=source_post_id,
            billing_resolution=normalize_requested_billing_resolution(
                resolution, mode
            ),
            requested_duration=normalize_requested_duration_seconds(duration),
            refund_suffix_mode="never",
            unexpected_should_refund=lambda state: state.task_submitted,
            unexpected_error_log_message="Error in custom video task for user {internal_user_id}: {error}",
            unexpected_error_prefix="出错了",
            cleanup_paths=[image_path] if image_path else None,
            cleanup_enabled=cleanup,
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
        """Handle MODE_I2I_PRO requests"""
        from src.constants import MODE_I2I_PRO
        from src.core.user_core import get_or_create_user_by_telegram

        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        mode = MODE_I2I_PRO

        # Validate images
        if not images or len(images) == 0:
            await robust_send_message(context.bot, chat_id, "❌ 请先发送参考图片。")
            return None, None

        image_path = images[0]

        runtime_state = BotTaskRuntimeState()
        notice = await TaskService._get_acceleration_notice(user_id)
        message_spec = TaskService._build_message_spec(
            initial_status_text=f"🚀 正在处理幻想换脸任务...{notice}",
            completion_caption="🌟 幻想换脸生成完成",
        )
        inputs = {
            "prompt": prompt,
            "images": [image_path],
            "resolution": 512,
            "duration": 5,
        }

        return await TaskService._run_bot_task_flow(
            context=context,
            update=None,
            chat_id=chat_id,
            runtime_state=runtime_state,
            internal_user_id=internal_user_id,
            username=username,
            task_type=mode,
            inputs=inputs,
            prompt=prompt,
            is_video=False,
            message_spec=message_spec,
            submitted_status_builder=lambda actual_cost: (
                f"🚀 正在处理幻想换脸任务 (消耗{actual_cost}灵石)...{notice}"
            ),
            source_post_id=source_post_id,
            allow_contribute=allow_contribute,
            refund_suffix_mode="always",
            unexpected_should_refund=lambda state: state.task_submitted,
            unexpected_error_log_message="Error in process_i2i_pro_task for user {internal_user_id}: {error}",
            unexpected_error_prefix="出错了",
            cleanup_paths=images,
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

        final_info = await monitor_task_progress(
            task_id=task_id,
            status_msg=status_msg,
            is_video=is_video,
            monitor_func=monitor_func,
            identity_str=identity_str,
            user_group=user_group,
            on_cancelled=_raise_cancelled,
        )
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
        media_bytes, full_output_path, _width, _height, _duration = (
            await TaskService._download_and_log_task_output(
                internal_user_id=internal_user_id,
                username=user_logger.username,
                prompt=prompt,
                task_type=task_type,
                task_id=task_id,
                saved_input_images=saved_input_images,
                is_video=is_video,
                allow_contribute=allow_contribute,
                billing_resolution=billing_resolution,
                requested_duration=requested_duration,
            )
        )

        if send_result:
            await TaskService._send_result_media(
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

        await TaskService._cleanup_completion_status_message(
            status_msg=status_msg,
            delete_status=delete_status,
            send_result=send_result,
        )

        return media_bytes, full_output_path

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
