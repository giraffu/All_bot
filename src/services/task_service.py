"""
🚨 架构红线警告 (ARCHITECTURE REDLINE) 🚨
本文件 `task_service.py` 已经被明确定义为 Telegram Bot 专属的表示层 (Presentation Layer) / Handler 层。
严禁在任何 Web API Router (如 src/web_api/routers/*.py) 中导入或调用此文件中的逻辑。
Web API 应直接调用 `src/core/task_core.py` 提供的业务门面 (Facade)。
"""

import logging
import os
from typing import List, Optional, Tuple

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.core.video_billing import (
    normalize_requested_billing_resolution,
    normalize_requested_duration_seconds,
)
from src.constants import (
    MODE_BLOWJOB,
    MODE_CLOSEUP_BLOWJOB,
    MODE_CUSTOM_VIDEO,
    MODE_DOGGY_STYLE,
    MODE_FACE_VIDEO_STEP1,
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


class TaskService:
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
        import uuid

        from asgi_correlation_id import correlation_id

        from src.core.billing_core import (
            get_user_priority_and_identity,
        )
        from src.core.task_core import (
            ConcurrencyLimitError,
            CoreDomainError,
            InsufficientCreditsError,
            process_and_submit_task,
        )
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

        registry_task_id = None
        cost = 0
        task_submitted = False
        terminal_state_finalized = False

        try:
            task_id = str(uuid.uuid4())
            correlation_id.set(task_id)

            inputs = {
                "prompt": prompt,
                "images": [image_path] if image_path else [],
                "resolution": resolution,
                "duration": duration,
            }

            result = await process_and_submit_task(
                user_id=internal_user_id,
                username=username,
                task_type=mode,
                inputs=inputs,
                task_id=task_id,
                client_type="bot",
                source_post_id=source_post_id,
            )

            task_submitted = True
            cost = result["cost"]
            registry_task_id = result["registry_task_id"]
            saved_inputs = result["saved_inputs"]

            notice = await TaskService._get_acceleration_notice(user_id)
            msg_text = f"🚀 正在处理高级图生视频任务 (画质:{resolution}, 时长:{duration}, 消耗{cost}灵石)...{notice}"
            msg = await robust_reply_text(update.effective_message, msg_text)
            await robust_edit_text(
                msg, "⏳ 正在生成高级视频，可能需要数分钟，请耐心等待..."
            )

            _priority, identity_str, user_group = await get_user_priority_and_identity(
                internal_user_id
            )
            final_info = await TaskService._monitor_task_progress(
                task_id,
                msg,
                is_video=True,
                monitor_func=image_service.monitor_progress,
                identity_str=identity_str,
                user_group=user_group,
            )

            if final_info:
                return await TaskService._handle_task_completion(
                    context,
                    chat_id,
                    internal_user_id,
                    prompt,
                    mode,
                    task_id,
                    saved_inputs,
                    UserLogger(internal_user_id, username),
                    is_video=True,
                    send_result=True,
                    reply_markup=None,
                    status_msg=msg,
                    delete_status=True,
                    caption="✅ 高级图生视频生成完成",
                    allow_contribute=allow_contribute,
                    billing_resolution=normalize_requested_billing_resolution(
                        resolution, mode
                    ),
                    requested_duration=normalize_requested_duration_seconds(duration),
                )
            else:
                failure_result = await finalize_task_failure(
                    internal_user_id=internal_user_id,
                    username=username,
                    cost=cost,
                    should_refund=True,
                    registry_task_id=registry_task_id,
                    release_lock=task_submitted,
                    explicit_user_message="生成完成但未获取到文件路径，已退还灵石",
                )
                terminal_state_finalized = True
                await robust_send_message(
                    context.bot, chat_id, f"❌ {failure_result.user_message}"
                )
                return None, None

        except ConcurrencyLimitError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except InsufficientCreditsError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except CoreDomainError as e:
            if str(e) == "cancelled":
                cancellation_result = await finalize_task_cancellation(
                    internal_user_id=internal_user_id,
                    username=username,
                    cost=cost,
                    task_submitted=task_submitted,
                    registry_task_id=registry_task_id,
                    release_lock=task_submitted,
                    explicit_user_message=f"任务已撤销，预扣的 {cost} 灵石已全额退回。",
                )
                terminal_state_finalized = True
                await robust_edit_text(msg, f"✅ {cancellation_result.user_message}")
                return None, None
            await robust_send_message(context.bot, chat_id, f"❌ {e}")
            return None, None
        except Exception as e:
            logger.error(
                f"Error in ltx video task for user {internal_user_id}: {e}",
                exc_info=True,
            )
            failure_result = await finalize_task_failure(
                internal_user_id=internal_user_id,
                username=username,
                cost=cost,
                should_refund=task_submitted and cost > 0,
                registry_task_id=registry_task_id,
                release_lock=task_submitted,
                error=e,
                generic_error_prefix="出错了",
            )
            terminal_state_finalized = True

            await robust_send_message(
                context.bot, chat_id, f"❌ {failure_result.user_message}"
            )
            return None, None
        finally:
            if not terminal_state_finalized and (task_submitted or registry_task_id):
                await asyncio.shield(
                    cleanup_task_runtime_state(
                        internal_user_id=internal_user_id,
                        registry_task_id=registry_task_id,
                        release_lock=task_submitted,
                    )
                )
            if cleanup and image_path:
                TaskService._cleanup_files([image_path])

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
        import asyncio
        import uuid

        from asgi_correlation_id import correlation_id

        from src.core.billing_core import (
            get_user_priority_and_identity,
        )
        from src.core.task_core import (
            ConcurrencyLimitError,
            CoreDomainError,
            InsufficientCreditsError,
            process_and_submit_task,
        )
        from src.core.user_core import get_or_create_user_by_telegram

        # 1. 身份转换 (TG ID -> 内部 ID)
        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        mode = MODE_FACE_VIDEO_STEP1
        registry_task_id = None
        task_submitted = False
        actual_cost = cost
        terminal_state_finalized = False

        try:
            task_id = str(uuid.uuid4())
            correlation_id.set(task_id)

            inputs = {
                "prompt": "Video Face Swap",
                "images": [face_image_path, video_path]
                if face_image_path and video_path
                else [],
                "resolution": resolution,
                "duration": duration,
            }

            result = await process_and_submit_task(
                user_id=internal_user_id,
                username=username,
                task_type=mode,
                inputs=inputs,
                task_id=task_id,
                client_type="bot",
                source_post_id=source_post_id,
            )

            task_submitted = True
            actual_cost = result["cost"]
            registry_task_id = result["registry_task_id"]
            saved_inputs = result["saved_inputs"]

            notice = await TaskService._get_acceleration_notice(user_id)
            msg_text = f"🚀 正在处理视频换脸任务 (画质:{resolution}p, 消耗{actual_cost}灵石)...{notice}"
            status_msg = await TaskService._get_or_send_status_msg(
                context, chat_id, message_id, msg_text
            )

            _priority, identity_str, user_group = await get_user_priority_and_identity(
                internal_user_id
            )
            final_info = await TaskService._monitor_task_progress(
                task_id,
                status_msg,
                is_video=True,
                monitor_func=image_service.monitor_progress,
                identity_str=identity_str,
                user_group=user_group,
            )

            if final_info:
                return await TaskService._handle_task_completion(
                    context,
                    chat_id,
                    internal_user_id,
                    "face video",
                    mode,
                    task_id,
                    saved_inputs,
                    UserLogger(internal_user_id, username),
                    is_video=True,
                    send_result=True,
                    reply_markup=None,
                    status_msg=status_msg,
                    delete_status=True,
                    caption="✅ 视频换脸完成",
                    billing_resolution=normalize_requested_billing_resolution(
                        resolution, mode
                    ),
                )
            else:
                failure_result = await finalize_task_failure(
                    internal_user_id=internal_user_id,
                    username=username,
                    cost=actual_cost,
                    should_refund=True,
                    registry_task_id=registry_task_id,
                    release_lock=task_submitted,
                    explicit_user_message="生成失败或超时，已退还灵石。",
                )
                terminal_state_finalized = True
                await robust_edit_text(status_msg, f"⚠️ {failure_result.user_message}")
                return None, None

        except ConcurrencyLimitError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except InsufficientCreditsError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except CoreDomainError as e:
            if str(e) == "cancelled":
                cancellation_result = await finalize_task_cancellation(
                    internal_user_id=internal_user_id,
                    username=username,
                    cost=actual_cost,
                    task_submitted=task_submitted,
                    registry_task_id=registry_task_id,
                    release_lock=task_submitted,
                    explicit_user_message=f"任务已撤销，预扣的 {actual_cost} 灵石已全额退回。",
                )
                terminal_state_finalized = True
                if "status_msg" in locals():
                    await robust_edit_text(
                        status_msg, f"✅ {cancellation_result.user_message}"
                    )
                return None, None
            await robust_send_message(context.bot, chat_id, f"❌ {e}")
            return None, None
        except Exception as e:
            logger.error(
                f"Error processing face video task for {internal_user_id}: {e}",
                exc_info=True,
            )
            failure_result = await finalize_task_failure(
                internal_user_id=internal_user_id,
                username=username,
                cost=actual_cost,
                should_refund=task_submitted and actual_cost > 0,
                registry_task_id=registry_task_id,
                release_lock=task_submitted,
                error=e,
                generic_error_prefix="系统错误",
            )
            terminal_state_finalized = True

            # status_msg might not be defined if exception occurs early
            if "status_msg" in locals():
                await robust_edit_text(status_msg, f"❌ {failure_result.user_message}")
            else:
                await robust_send_message(
                    context.bot, chat_id, f"❌ {failure_result.user_message}"
                )
            return None, None
        finally:
            if not terminal_state_finalized and (task_submitted or registry_task_id):
                await asyncio.shield(
                    cleanup_task_runtime_state(
                        internal_user_id=internal_user_id,
                        registry_task_id=registry_task_id,
                        release_lock=task_submitted,
                    )
                )
            if cleanup:
                TaskService._cleanup_files([face_image_path, video_path])

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
        import uuid

        from asgi_correlation_id import correlation_id

        from src.constants import DEFAULT_DURATION, DEFAULT_RESOLUTION
        from src.core.billing_core import (
            get_user_priority_and_identity,
        )
        from src.core.task_core import (
            ConcurrencyLimitError,
            CoreDomainError,
            InsufficientCreditsError,
            process_and_submit_task,
        )
        from src.core.user_core import get_or_create_user_by_telegram

        # 1. 身份转换
        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        if not task_type:
            task_type = "video" if is_video else "image"

        resolution = 512
        duration = 5
        from src.constants import (
            MODE_CUSTOM_VIDEO,
            MODE_IMG2IMG_LORA,
        )

        if is_video and task_type in [MODE_CUSTOM_VIDEO, "video_lora"]:
            res_str = context.user_data.get(
                "custom_video_resolution", DEFAULT_RESOLUTION
            )
            dur_str = context.user_data.get("custom_video_duration", DEFAULT_DURATION)

            if res_str == "1024p" and dur_str == "10s":
                res_str = "720p"
                context.user_data["custom_video_resolution"] = "720p"

            if res_str == "1024p":
                resolution = 1024
            elif res_str == "720p":
                resolution = 720
            else:
                resolution = 512

            if dur_str == "8s":
                duration = 8
            elif dur_str == "10s":
                duration = 10
            else:
                duration = 5

        notice = await TaskService._get_acceleration_notice(user_id)

        msg_text = (
            f"🚀 正在处理视频生成任务...{notice}"
            if is_video
            else f"🚀 正在处理 {len(images)} 张图片...{notice}"
        )

        status_msg = await TaskService._get_or_send_status_msg(
            context, chat_id, status_msg_id, msg_text
        )

        media_bytes = None
        full_output_path = None
        registry_task_id = None
        task_submitted = False
        actual_cost = 0
        terminal_state_finalized = False

        try:
            task_id = str(uuid.uuid4())
            correlation_id.set(task_id)

            inputs = {
                "prompt": prompt,
                "images": images,
                "resolution": resolution,
                "duration": duration,
                "lora_name": lora_name,
                "lora_strength": lora_strength,
            }

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

            task_submitted = True
            actual_cost = result["cost"]
            registry_task_id = result["registry_task_id"]
            saved_input_images = result["saved_inputs"]

            # Update msg with actual cost
            updated_msg_text = (
                f"🚀 正在处理视频生成任务 (消耗{actual_cost}灵石)...{notice}"
                if is_video
                else f"🚀 正在处理 {len(images)} 张图片 (消耗{actual_cost}灵石)...{notice}"
            )
            await robust_edit_text(status_msg, updated_msg_text)

            _priority, identity_str, user_group = await get_user_priority_and_identity(
                internal_user_id
            )
            user_logger = UserLogger(internal_user_id, username)

            final_info = await TaskService._monitor_task_progress(
                task_id,
                status_msg,
                is_video,
                image_service.monitor_progress,
                identity_str=identity_str,
                user_group=user_group,
            )

            if final_info:
                log_prompt = prompt
                if task_type in ("video_lora", MODE_IMG2IMG_LORA) and lora_name:
                    log_prompt = f"[模型: {lora_name}] {prompt}"

                from src.constants import MODE_NAME_MAP

                mode_name = MODE_NAME_MAP.get(task_type, task_type)
                display_mode_name = (
                    context.t(mode_name) if hasattr(context, "t") else mode_name
                )

                (
                    media_bytes,
                    full_output_path,
                ) = await TaskService._handle_task_completion(
                    context,
                    chat_id,
                    internal_user_id,
                    log_prompt,
                    task_type,
                    task_id,
                    saved_input_images,
                    user_logger,
                    is_video,
                    send_result,
                    reply_markup,
                    status_msg,
                    delete_status,
                    caption=f"✅ {display_mode_name} 生成完成",
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
                )
            else:
                await TaskService._finalize_failed_task_for_bot(
                    context=context,
                    chat_id=chat_id,
                    status_msg=None,
                    internal_user_id=internal_user_id,
                    username=username,
                    cost=actual_cost,
                    should_refund=deduct_quota,
                    registry_task_id=registry_task_id,
                    release_lock=task_submitted,
                    explicit_user_message="生成完成但未获取到文件路径，已退还灵石",
                )
                terminal_state_finalized = True

        except ConcurrencyLimitError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
        except InsufficientCreditsError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
        except CoreDomainError as e:
            if str(e) == "cancelled":
                await TaskService._finalize_cancelled_task_for_bot(
                    status_msg=status_msg if "status_msg" in locals() else None,
                    internal_user_id=internal_user_id,
                    username=username,
                    cost=actual_cost,
                    task_submitted=deduct_quota and task_submitted,
                    registry_task_id=registry_task_id,
                    explicit_user_message=f"任务已撤销，预扣的 {actual_cost} 灵石已全额退回。",
                )
                terminal_state_finalized = True
                return None, None
            await robust_send_message(context.bot, chat_id, f"❌ {e}")
        except Exception as e:
            logger.error(
                f"Error in process_generation_task for user {internal_user_id}: {e}",
                exc_info=True,
            )
            await TaskService._finalize_failed_task_for_bot(
                context=context,
                chat_id=chat_id,
                status_msg=None,
                internal_user_id=internal_user_id,
                username=username,
                cost=actual_cost,
                should_refund=deduct_quota and task_submitted,
                registry_task_id=registry_task_id,
                release_lock=task_submitted,
                error=e,
                generic_error_prefix="出错了",
            )
            terminal_state_finalized = True

        finally:
            await TaskService._cleanup_runtime_state_if_needed(
                internal_user_id=internal_user_id,
                registry_task_id=registry_task_id,
                release_lock=task_submitted,
                terminal_state_finalized=terminal_state_finalized,
            )
            if cleanup:
                TaskService._cleanup_files(images)

        return media_bytes, full_output_path

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
        import uuid

        from asgi_correlation_id import correlation_id

        from src.core.billing_core import (
            get_user_priority_and_identity,
        )
        from src.core.task_core import (
            ConcurrencyLimitError,
            CoreDomainError,
            InsufficientCreditsError,
            process_and_submit_task,
        )
        from src.core.user_core import get_or_create_user_by_telegram

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        username = update.effective_user.username

        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        from src.constants import DEFAULT_DURATION, DEFAULT_RESOLUTION

        resolution = context.user_data.get(
            "custom_video_resolution", DEFAULT_RESOLUTION
        )
        duration_str = context.user_data.get("custom_video_duration", DEFAULT_DURATION)

        if resolution == "1024p" and duration_str == "10s":
            resolution = "720p"
            context.user_data["custom_video_resolution"] = "720p"
            await robust_reply_text(
                update.effective_message,
                "⚠️ 检测到非法配置(1024p+10s)，已自动降级为720p+10s。",
            )

        duration = 10 if duration_str == "10s" else (8 if duration_str == "8s" else 5)
        res_val = (
            1024 if resolution == "1024p" else (720 if resolution == "720p" else 512)
        )

        prompts_config = load_prompts()
        base_prompt = prompts_config.get(default_prompt_key, default_prompt_text)

        mode_name = MODE_NAME_MAP.get(mode, mode)
        display_mode_name = context.t(mode_name) if hasattr(context, "t") else mode_name
        registry_task_id = None
        task_submitted = False
        actual_cost = 0
        terminal_state_finalized = False
        media_bytes = None
        full_output_path = None

        try:
            task_id = str(uuid.uuid4())
            correlation_id.set(task_id)

            inputs = {
                "prompt": base_prompt,
                "images": [image_path] if image_path else [],
                "resolution": res_val,
                "duration": duration,
            }

            result = await process_and_submit_task(
                user_id=internal_user_id,
                username=username,
                task_type=mode,
                inputs=inputs,
                task_id=task_id,
                client_type="bot",
                source_post_id=source_post_id,
            )

            task_submitted = True
            actual_cost = result["cost"]
            registry_task_id = result["registry_task_id"]
            saved_inputs = result["saved_inputs"]

            notice = await TaskService._get_acceleration_notice(user_id)
            msg_text = f"🚀 正在处理{display_mode_name}生成任务 (画质:{resolution}, 时长:{duration_str}, 消耗{actual_cost}灵石)...{notice}"
            msg = await robust_reply_text(update.effective_message, msg_text)
            await robust_edit_text(msg, "⏳ 正在生成视频，请耐心等待...")

            _priority, identity_str, user_group = await get_user_priority_and_identity(
                internal_user_id
            )
            final_info = await TaskService._monitor_task_progress(
                task_id,
                msg,
                is_video=True,
                monitor_func=image_service.monitor_progress,
                identity_str=identity_str,
                user_group=user_group,
            )

            if final_info:
                (
                    media_bytes,
                    full_output_path,
                ) = await TaskService._handle_task_completion(
                    context,
                    chat_id,
                    internal_user_id,
                    f"[{resolution}|{duration_str}] {base_prompt}",
                    mode,
                    task_id,
                    saved_inputs,
                    UserLogger(internal_user_id, username),
                    is_video=True,
                    send_result=True,
                    reply_markup=None,
                    status_msg=msg,
                    delete_status=True,
                    caption=f"✅ {display_mode_name} 生成完成",
                    allow_contribute=allow_contribute,
                    billing_resolution=normalize_requested_billing_resolution(
                        resolution, mode
                    ),
                    requested_duration=duration,
                )
            else:
                await TaskService._finalize_failed_task_for_bot(
                    context=context,
                    chat_id=chat_id,
                    status_msg=None,
                    internal_user_id=internal_user_id,
                    username=username,
                    cost=actual_cost,
                    should_refund=True,
                    registry_task_id=registry_task_id,
                    release_lock=task_submitted,
                    explicit_user_message="生成完成但未获取到任务信息，已退还灵石",
                )
                terminal_state_finalized = True

        except ConcurrencyLimitError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
        except InsufficientCreditsError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
        except CoreDomainError as e:
            if str(e) == "cancelled":
                await TaskService._finalize_cancelled_task_for_bot(
                    status_msg=msg if "msg" in locals() else None,
                    internal_user_id=internal_user_id,
                    username=username,
                    cost=actual_cost,
                    task_submitted=task_submitted,
                    registry_task_id=registry_task_id,
                    explicit_user_message=f"任务已撤销，预扣的 {actual_cost} 灵石已全额退回。",
                )
                terminal_state_finalized = True
                return None, None
            await robust_send_message(context.bot, chat_id, f"❌ {e}")
        except Exception as e:
            logger.error(
                f"Error in {mode} task for user {internal_user_id}: {e}", exc_info=True
            )
            await TaskService._finalize_failed_task_for_bot(
                context=context,
                chat_id=chat_id,
                status_msg=None,
                internal_user_id=internal_user_id,
                username=username,
                cost=actual_cost,
                should_refund=task_submitted and actual_cost > 0,
                registry_task_id=registry_task_id,
                release_lock=task_submitted,
                error=e,
                generic_error_prefix="出错了",
            )
            terminal_state_finalized = True
        finally:
            await TaskService._cleanup_runtime_state_if_needed(
                internal_user_id=internal_user_id,
                registry_task_id=registry_task_id,
                release_lock=task_submitted,
                terminal_state_finalized=terminal_state_finalized,
            )
            if cleanup and image_path:
                TaskService._cleanup_files([image_path])

        return media_bytes, full_output_path

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
        import uuid

        from asgi_correlation_id import correlation_id

        from src.core.billing_core import (
            get_user_priority_and_identity,
        )
        from src.core.task_core import (
            ConcurrencyLimitError,
            CoreDomainError,
            InsufficientCreditsError,
            process_and_submit_task,
        )
        from src.core.user_core import get_or_create_user_by_telegram

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        username = update.effective_user.username

        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        mode = MODE_CUSTOM_VIDEO

        from src.constants import DEFAULT_DURATION, DEFAULT_RESOLUTION

        resolution = context.user_data.get(
            "custom_video_resolution", DEFAULT_RESOLUTION
        )
        duration = context.user_data.get("custom_video_duration", DEFAULT_DURATION)

        if resolution == "1024p" and duration == "10s":
            resolution = "720p"  # Fallback safely
            context.user_data["custom_video_resolution"] = "720p"
            await robust_reply_text(
                update.effective_message,
                "⚠️ 检测到非法配置(1024p+10s)，已自动降级为720p+10s。",
            )

        notice = await TaskService._get_acceleration_notice(user_id)
        msg_text = f"🚀 正在处理自定义视频生成任务 (画质:{resolution}, 时长:{duration})...{notice}"
        msg = await robust_reply_text(update.effective_message, msg_text)
        registry_task_id = None
        task_submitted = False
        actual_cost = 0
        terminal_state_finalized = False

        try:
            task_id = str(uuid.uuid4())
            correlation_id.set(task_id)

            inputs = {
                "prompt": prompt,
                "images": [image_path] if image_path else [],
                "resolution": resolution,
                "duration": duration,
            }

            result = await process_and_submit_task(
                user_id=internal_user_id,
                username=username,
                task_type=mode,
                inputs=inputs,
                task_id=task_id,
                client_type="bot",
                source_post_id=source_post_id,
            )

            task_submitted = True
            actual_cost = result["cost"]
            registry_task_id = result["registry_task_id"]
            saved_inputs = result["saved_inputs"]

            await robust_edit_text(
                msg,
                f"🚀 正在处理自定义视频生成任务 (画质:{resolution}, 时长:{duration}, 消耗{actual_cost}灵石)...{notice}\n⏳ 正在生成自定义视频，请耐心等待...",
            )

            _priority, identity_str, user_group = await get_user_priority_and_identity(
                internal_user_id
            )
            user_logger = UserLogger(internal_user_id, username)

            final_info = await TaskService._monitor_task_progress(
                task_id,
                msg,
                is_video=True,
                monitor_func=image_service.monitor_progress,
                identity_str=identity_str,
                user_group=user_group,
            )

            if final_info:
                return await TaskService._handle_task_completion(
                    context,
                    chat_id,
                    internal_user_id,
                    f"[{resolution}|{duration}] {prompt}",
                    mode,
                    task_id,
                    saved_inputs,
                    user_logger,
                    is_video=True,
                    send_result=True,
                    reply_markup=None,
                    status_msg=msg,
                    delete_status=True,
                    caption="✅ 自定义图生视频生成完成",
                    billing_resolution=normalize_requested_billing_resolution(
                        resolution, mode
                    ),
                    requested_duration=normalize_requested_duration_seconds(duration),
                )
            else:
                await TaskService._finalize_failed_task_for_bot(
                    context=context,
                    chat_id=chat_id,
                    status_msg=None,
                    internal_user_id=internal_user_id,
                    username=username,
                    cost=actual_cost,
                    should_refund=True,
                    registry_task_id=registry_task_id,
                    release_lock=task_submitted,
                    explicit_user_message="生成完成但未获取到文件路径，已退还灵石",
                )
                terminal_state_finalized = True
                return None, None

        except ConcurrencyLimitError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except InsufficientCreditsError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except CoreDomainError as e:
            if str(e) == "cancelled":
                await TaskService._finalize_cancelled_task_for_bot(
                    status_msg=msg if "msg" in locals() else None,
                    internal_user_id=internal_user_id,
                    username=username,
                    cost=actual_cost,
                    task_submitted=task_submitted,
                    registry_task_id=registry_task_id,
                    explicit_user_message=f"任务已撤销，预扣的 {actual_cost} 灵石已全额退回。",
                )
                terminal_state_finalized = True
                return None, None
            await robust_send_message(context.bot, chat_id, f"❌ {e}")
            return None, None
        except Exception as e:
            logger.error(
                f"Error in custom video task for user {internal_user_id}: {e}",
                exc_info=True,
            )
            await TaskService._finalize_failed_task_for_bot(
                context=context,
                chat_id=chat_id,
                status_msg=None,
                internal_user_id=internal_user_id,
                username=username,
                cost=actual_cost,
                should_refund=task_submitted,
                registry_task_id=registry_task_id,
                release_lock=task_submitted,
                error=e,
                generic_error_prefix="出错了",
                refund_suffix_mode="never",
            )
            terminal_state_finalized = True
            return None, None
        finally:
            await TaskService._cleanup_runtime_state_if_needed(
                internal_user_id=internal_user_id,
                registry_task_id=registry_task_id,
                release_lock=task_submitted,
                terminal_state_finalized=terminal_state_finalized,
            )
            if cleanup and image_path:
                TaskService._cleanup_files([image_path])

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
        import uuid

        from asgi_correlation_id import correlation_id

        from src.constants import MODE_I2I_PRO
        from src.core.billing_core import (
            get_user_priority_and_identity,
        )
        from src.core.task_core import (
            ConcurrencyLimitError,
            CoreDomainError,
            InsufficientCreditsError,
            process_and_submit_task,
        )
        from src.core.user_core import get_or_create_user_by_telegram

        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        mode = MODE_I2I_PRO

        # Validate images
        if not images or len(images) == 0:
            await robust_send_message(context.bot, chat_id, "❌ 请先发送参考图片。")
            return None, None

        image_path = images[0]

        notice = await TaskService._get_acceleration_notice(user_id)
        msg_text = f"🚀 正在处理幻想换脸任务...{notice}"
        msg = await robust_send_message(context.bot, chat_id, msg_text)
        registry_task_id = None
        task_submitted = False
        actual_cost = 0

        try:
            task_id = str(uuid.uuid4())
            correlation_id.set(task_id)

            inputs = {
                "prompt": prompt,
                "images": [image_path],
                "resolution": 512,
                "duration": 5,
            }

            result = await process_and_submit_task(
                user_id=internal_user_id,
                username=username,
                task_type=mode,
                inputs=inputs,
                task_id=task_id,
                client_type="bot",
                source_post_id=source_post_id,
            )

            task_submitted = True
            actual_cost = result["cost"]
            registry_task_id = result["registry_task_id"]
            saved_inputs = result["saved_inputs"]

            await robust_edit_text(
                msg, f"🚀 正在处理幻想换脸任务 (消耗{actual_cost}灵石)...{notice}"
            )

            _priority, identity_str, user_group = await get_user_priority_and_identity(
                internal_user_id
            )
            user_logger = UserLogger(internal_user_id, username)

            final_info = await TaskService._monitor_task_progress(
                task_id,
                msg,
                is_video=False,
                monitor_func=image_service.monitor_progress,
                identity_str=identity_str,
                user_group=user_group,
            )

            if final_info:
                return await TaskService._handle_task_completion(
                    context,
                    chat_id,
                    internal_user_id,
                    prompt,
                    mode,
                    task_id,
                    saved_inputs,
                    user_logger,
                    is_video=False,
                    send_result=True,
                    reply_markup=None,
                    status_msg=msg,
                    delete_status=True,
                    caption="🌟 幻想换脸生成完成",
                    allow_contribute=allow_contribute,
                )
            else:
                await TaskService._finalize_failed_task_for_bot(
                    context=context,
                    chat_id=chat_id,
                    status_msg=None,
                    internal_user_id=internal_user_id,
                    username=username,
                    cost=actual_cost,
                    should_refund=True,
                    registry_task_id=registry_task_id,
                    release_lock=task_submitted,
                    explicit_user_message="生成完成但未获取到文件路径，已退还灵石",
                )
                terminal_state_finalized = True
                return None, None

        except ConcurrencyLimitError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except InsufficientCreditsError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except CoreDomainError as e:
            if str(e) == "cancelled":
                await TaskService._finalize_cancelled_task_for_bot(
                    status_msg=msg if "msg" in locals() else None,
                    internal_user_id=internal_user_id,
                    username=username,
                    cost=actual_cost,
                    task_submitted=task_submitted,
                    registry_task_id=registry_task_id,
                    explicit_user_message=f"任务已撤销，预扣的 {actual_cost} 灵石已全额退回。",
                )
                terminal_state_finalized = True
                return None, None
            await robust_send_message(context.bot, chat_id, f"❌ {e}")
            return None, None
        except Exception as e:
            logger.error(
                f"Error in process_i2i_pro_task for user {internal_user_id}: {e}",
                exc_info=True,
            )
            await TaskService._finalize_failed_task_for_bot(
                context=context,
                chat_id=chat_id,
                status_msg=None,
                internal_user_id=internal_user_id,
                username=username,
                cost=actual_cost,
                should_refund=task_submitted,
                registry_task_id=registry_task_id,
                release_lock=task_submitted,
                error=e,
                generic_error_prefix="出错了",
                refund_suffix_mode="always",
            )
            terminal_state_finalized = True
            return None, None
        finally:
            await TaskService._cleanup_runtime_state_if_needed(
                internal_user_id=internal_user_id,
                registry_task_id=registry_task_id,
                release_lock=task_submitted,
                terminal_state_finalized=terminal_state_finalized,
            )
            TaskService._cleanup_files(images)

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
