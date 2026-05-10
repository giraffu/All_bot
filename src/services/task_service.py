"""
🚨 架构红线警告 (ARCHITECTURE REDLINE) 🚨
本文件 `task_service.py` 已经被明确定义为 Telegram Bot 专属的表示层 (Presentation Layer) / Handler 层。
严禁在任何 Web API Router (如 src/web_api/routers/*.py) 中导入或调用此文件中的逻辑。
Web API 应直接调用 `src/core/task_core.py` 提供的业务门面 (Facade)。
"""

import logging
import os
from typing import List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ENABLE_PUBLIC_SHARE
from src.constants import (
    MODE_BLOWJOB,
    MODE_CLOSEUP_BLOWJOB,
    MODE_CUSTOM_VIDEO,
    MODE_DOGGY_STYLE,
    MODE_EDIT,
    MODE_FACE_VIDEO_STEP1,
    MODE_FACESWAP_STEP1,
    MODE_I2I_PRO,
    MODE_LTX_VIDEO,
    MODE_MASTURBATION,
    MODE_NAME_MAP,
    MODE_PENETRATION_STEP1,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_UNDRESS,
    MODE_UNDRESS_TONGUE,
    MODE_VIDEO_LORA,
    TMP_DIR,
)
from src.handlers.utils import MockMessage
from src.logger import UserLogger
from src.services.image_service import image_service
from src.services.permission_service import permission_service
from src.services.task_registry import TaskRegistry
from src.utils import (
    load_prompts,
    robust_delete_message,
    robust_edit_text,
    robust_reply_text,
    robust_send_message,
    robust_send_photo,
    robust_send_video,
)
import contextlib

logger = logging.getLogger(__name__)


class TaskService:
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
        import asyncio
        import uuid

        from asgi_correlation_id import correlation_id

        from src.core.billing_core import (
            get_user_priority_and_identity,
            refund_credits,
            release_concurrency_lock,
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

            priority, identity_str, user_group = await get_user_priority_and_identity(
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
                )
            else:
                await asyncio.shield(
                    refund_credits(internal_user_id, cost, "refund", username)
                )
                await robust_send_message(
                    context.bot, chat_id, "❌ 生成完成但未获取到文件路径，已退还灵石"
                )
                return None, None

        except ConcurrencyLimitError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except InsufficientCreditsError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except CoreDomainError as e:
            await robust_send_message(context.bot, chat_id, f"❌ {e}")
            return None, None
        except Exception as e:
            logger.error(
                f"Error in ltx video task for user {internal_user_id}: {e}",
                exc_info=True,
            )
            error_msg = str(e)
            if any(
                kw in error_msg
                for kw in [
                    "Circuit is open",
                    "All connection attempts failed",
                    "Connection refused",
                    "timeout",
                    "ConnectError",
                ]
            ) or "CircuitBreaker" in str(type(e)):
                user_msg = "当前服务器繁忙，请稍后再试"
            else:
                user_msg = f"出错了：{error_msg}"

            if task_submitted and cost > 0:
                await asyncio.shield(
                    refund_credits(internal_user_id, cost, "refund", username)
                )
                user_msg += "，已退还灵石"

            await robust_send_message(context.bot, chat_id, f"❌ {user_msg}")
            return None, None
        finally:
            if registry_task_id:
                await asyncio.shield(TaskRegistry.remove_task(registry_task_id))
            if task_submitted:
                await asyncio.shield(release_concurrency_lock(internal_user_id))
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
            refund_credits,
            release_concurrency_lock,
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

            priority, identity_str, user_group = await get_user_priority_and_identity(
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
                )
            else:
                await asyncio.shield(
                    refund_credits(internal_user_id, actual_cost, "refund", username)
                )
                await robust_edit_text(status_msg, "⚠️ 生成失败或超时，已退还灵石。")
                return None, None

        except ConcurrencyLimitError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except InsufficientCreditsError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except CoreDomainError as e:
            await robust_send_message(context.bot, chat_id, f"❌ {e}")
            return None, None
        except Exception as e:
            logger.error(
                f"Error processing face video task for {internal_user_id}: {e}",
                exc_info=True,
            )
            error_msg = str(e)
            if any(
                kw in error_msg
                for kw in [
                    "Circuit is open",
                    "All connection attempts failed",
                    "Connection refused",
                    "timeout",
                    "ConnectError",
                ]
            ) or "CircuitBreaker" in str(type(e)):
                user_msg = "当前服务器繁忙，请稍后再试"
            else:
                user_msg = f"系统错误：{error_msg}"

            if task_submitted and actual_cost > 0:
                await asyncio.shield(
                    refund_credits(internal_user_id, actual_cost, "refund", username)
                )
                user_msg += "，已退还灵石"

            # status_msg might not be defined if exception occurs early
            if "status_msg" in locals():
                await robust_edit_text(status_msg, f"❌ {user_msg}")
            else:
                await robust_send_message(context.bot, chat_id, f"❌ {user_msg}")
            return None, None
        finally:
            if registry_task_id:
                await asyncio.shield(TaskRegistry.remove_task(registry_task_id))
            if task_submitted:
                await asyncio.shield(release_concurrency_lock(internal_user_id))
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
        import asyncio
        import uuid

        from asgi_correlation_id import correlation_id

        from src.constants import DEFAULT_DURATION, DEFAULT_RESOLUTION
        from src.core.billing_core import (
            get_user_priority_and_identity,
            refund_credits,
            release_concurrency_lock,
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

            priority, identity_str, user_group = await get_user_priority_and_identity(
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
                )
            else:
                if deduct_quota:
                    await asyncio.shield(
                        refund_credits(
                            internal_user_id, actual_cost, "refund", username
                        )
                    )
                await robust_send_message(
                    context.bot, chat_id, "❌ 生成完成但未获取到文件路径，已退还灵石"
                )

        except ConcurrencyLimitError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
        except InsufficientCreditsError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
        except CoreDomainError as e:
            await robust_send_message(context.bot, chat_id, f"❌ {e}")
        except Exception as e:
            logger.error(
                f"Error in process_generation_task for user {internal_user_id}: {e}",
                exc_info=True,
            )
            error_msg = str(e)
            if any(
                kw in error_msg
                for kw in [
                    "Circuit is open",
                    "All connection attempts failed",
                    "Connection refused",
                    "timeout",
                    "ConnectError",
                ]
            ) or "CircuitBreaker" in str(type(e)):
                user_msg = "当前服务器繁忙，请稍后再试"
            else:
                user_msg = f"出错了：{error_msg}"

            if deduct_quota and task_submitted:
                await asyncio.shield(
                    refund_credits(internal_user_id, actual_cost, "refund", username)
                )
            await robust_send_message(context.bot, chat_id, f"❌ {user_msg}")

        finally:
            if registry_task_id:
                await asyncio.shield(TaskRegistry.remove_task(registry_task_id))
            if task_submitted:
                await asyncio.shield(release_concurrency_lock(internal_user_id))
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
        import asyncio
        import uuid

        from asgi_correlation_id import correlation_id

        from src.core.billing_core import (
            get_user_priority_and_identity,
            refund_credits,
            release_concurrency_lock,
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

            priority, identity_str, user_group = await get_user_priority_and_identity(
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
                )
            else:
                await asyncio.shield(
                    refund_credits(internal_user_id, actual_cost, "refund", username)
                )
                await robust_send_message(
                    context.bot, chat_id, "❌ 生成完成但未获取到任务信息，已退还灵石"
                )

        except ConcurrencyLimitError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
        except InsufficientCreditsError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
        except CoreDomainError as e:
            await robust_send_message(context.bot, chat_id, f"❌ {e}")
        except Exception as e:
            logger.error(
                f"Error in {mode} task for user {internal_user_id}: {e}", exc_info=True
            )
            error_msg = str(e)
            if any(
                kw in error_msg
                for kw in [
                    "Circuit is open",
                    "All connection attempts failed",
                    "Connection refused",
                    "timeout",
                    "ConnectError",
                ]
            ) or "CircuitBreaker" in str(type(e)):
                user_msg = "当前服务器繁忙，请稍后再试"
            else:
                user_msg = f"出错了：{error_msg}"

            if task_submitted and actual_cost > 0:
                await asyncio.shield(
                    refund_credits(internal_user_id, actual_cost, "refund", username)
                )
                user_msg += "，已退还灵石"

            await robust_send_message(context.bot, chat_id, f"❌ {user_msg}")
        finally:
            if registry_task_id:
                await asyncio.shield(TaskRegistry.remove_task(registry_task_id))
            if task_submitted:
                await asyncio.shield(release_concurrency_lock(internal_user_id))
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
        import asyncio
        import uuid

        from asgi_correlation_id import correlation_id

        from src.core.billing_core import (
            get_user_priority_and_identity,
            refund_credits,
            release_concurrency_lock,
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

            priority, identity_str, user_group = await get_user_priority_and_identity(
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
                )
            else:
                await asyncio.shield(
                    refund_credits(internal_user_id, actual_cost, "refund", username)
                )
                await robust_send_message(
                    context.bot, chat_id, "❌ 生成完成但未获取到文件路径，已退还灵石"
                )
                return None, None

        except ConcurrencyLimitError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except InsufficientCreditsError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except CoreDomainError as e:
            await robust_send_message(context.bot, chat_id, f"❌ {e}")
            return None, None
        except Exception as e:
            logger.error(
                f"Error in custom video task for user {internal_user_id}: {e}",
                exc_info=True,
            )
            if task_submitted:
                await asyncio.shield(
                    refund_credits(internal_user_id, actual_cost, "refund", username)
                )
            error_msg = str(e)
            if any(
                kw in error_msg
                for kw in [
                    "Circuit is open",
                    "All connection attempts failed",
                    "Connection refused",
                    "timeout",
                    "ConnectError",
                ]
            ) or "CircuitBreaker" in str(type(e)):
                user_msg = "当前服务器繁忙，请稍后再试"
            else:
                user_msg = f"出错了：{error_msg}"
            await robust_send_message(context.bot, chat_id, f"❌ {user_msg}")
            return None, None
        finally:
            if registry_task_id:
                await asyncio.shield(TaskRegistry.remove_task(registry_task_id))
            if task_submitted:
                await asyncio.shield(release_concurrency_lock(internal_user_id))
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
        import asyncio
        import uuid

        from asgi_correlation_id import correlation_id

        from src.constants import MODE_I2I_PRO
        from src.core.billing_core import (
            get_user_priority_and_identity,
            refund_credits,
            release_concurrency_lock,
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

            priority, identity_str, user_group = await get_user_priority_and_identity(
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
                await asyncio.shield(
                    refund_credits(internal_user_id, actual_cost, "refund", username)
                )
                await robust_send_message(
                    context.bot, chat_id, "❌ 生成完成但未获取到文件路径，已退还灵石"
                )
                return None, None

        except ConcurrencyLimitError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except InsufficientCreditsError as e:
            await robust_send_message(context.bot, chat_id, f"⚠️ {e}")
            return None, None
        except CoreDomainError as e:
            await robust_send_message(context.bot, chat_id, f"❌ {e}")
            return None, None
        except Exception as e:
            logger.error(
                f"Error in process_i2i_pro_task for user {internal_user_id}: {e}",
                exc_info=True,
            )
            if task_submitted:
                await asyncio.shield(
                    refund_credits(internal_user_id, actual_cost, "refund", username)
                )
            error_msg = str(e)
            if any(
                kw in error_msg
                for kw in [
                    "Circuit is open",
                    "All connection attempts failed",
                    "Connection refused",
                    "timeout",
                    "ConnectError",
                ]
            ) or "CircuitBreaker" in str(type(e)):
                user_msg = "当前服务器繁忙，请稍后再试"
            else:
                user_msg = f"出错了：{error_msg}"
            await robust_send_message(
                context.bot, chat_id, f"❌ {user_msg}，已退还灵石"
            )
            return None, None
        finally:
            if registry_task_id:
                await asyncio.shield(TaskRegistry.remove_task(registry_task_id))
            if task_submitted:
                await asyncio.shield(release_concurrency_lock(internal_user_id))
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
    async def _submit_generic_task(
        task_type, prompt, images, negative_prompt, is_video, priority=0
    ):
        if task_type == "face_swap" and len(images) >= 2:
            return await image_service.submit_face_swap_task(
                face_image_path=images[1], body_image_path=images[0], priority=priority
            )
        elif is_video:
            return await image_service.submit_perfect_video_edit(
                prompt, images[0], priority=priority
            )
        else:
            return await image_service.submit_task(
                prompt, images, negative_prompt, priority=priority
            )

    @staticmethod
    async def _monitor_task_progress(
        task_id, status_msg, is_video, monitor_func, identity_str=None, user_group=None
    ):
        last_progress = 0
        last_status = None
        last_queue_pos = None
        final_info = None

        async def update_status_message(text, **kwargs):
            try:
                await robust_edit_text(status_msg, text, **kwargs)
                return True
            except Exception as exc:
                logger.warning(
                    f"Failed to update status message for task {task_id}: {exc}"
                )
                return False

        # Build VIP/Group suffix if applicable
        vip_suffix = ""
        privileges = []
        if identity_str and identity_str not in [
            "外门弟子",
            "凡人",
            "练气期",
            "筑基期",
            "金丹期",
            "元婴期",
            "default",
        ]:
            privileges.append(identity_str)
        if user_group and user_group in ["元婴期", "金丹期", "筑基期"]:
            privileges.append(user_group)

        if privileges:
            privilege_str = " + ".join(privileges)
            vip_suffix = f"\n🚀 _已为您开启 [{privilege_str}] 极速通道_"

        async for info in monitor_func(task_id, is_video=is_video):
            status = info.get("status")
            progress = info.get("progress", 0)

            if status == "done":
                final_info = info
                if not is_video and last_progress != 100:
                    await update_status_message("⏳ 生成中... 100%")
                break

            if status == "error":
                raise RuntimeError(info.get("error", "generation failed"))

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

                logger.debug(
                    f"Task {task_id} pending. Info queue_pos: {raw_pos}, queue_remaining: {info.get('queue_remaining')}"
                )

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
                msg = "⏳ 正在生成视频..." if is_video else f"⏳ 生成中... {progress}%"
                if await update_status_message(msg):
                    last_progress = progress
                    last_status = status

        return final_info

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
    ):
        full_output_path = None
        media_bytes = None

        if is_video:
            media_bytes = await image_service.download_video_result(task_id)
            saved_output_image = user_logger.save_output_image(
                media_bytes, task_id, extension="mp4"
            )
            full_output_path = saved_output_image
            await user_logger.log_task(
                prompt,
                saved_input_images,
                saved_output_image,
                task_id=task_id,
                type=task_type,
                allow_contribute=allow_contribute,
            )
            await permission_service.refresh_user_group(internal_user_id)

            if send_result:
                from src.constants import MODE_IMG2IMG_LORA

                allowed_gallery_types = [
                    MODE_I2I_PRO,
                    MODE_EDIT,
                    MODE_CUSTOM_VIDEO,
                    MODE_VIDEO_LORA,
                    MODE_LTX_VIDEO,
                    MODE_IMG2IMG_LORA,
                ]
                show_gallery_btn = (
                    task_type in allowed_gallery_types and allow_contribute
                )

                keyboard = []
                if show_gallery_btn:
                    keyboard.append(
                        [
                            InlineKeyboardButton(
                                "🚀 一键投稿至广场",
                                callback_data=f"submit_gallery_{task_id}",
                            )
                        ]
                    )

                keyboard.append(
                    [
                        InlineKeyboardButton("👍", callback_data="rate_like"),
                        InlineKeyboardButton("👎", callback_data="rate_dislike"),
                    ]
                )

                if ENABLE_PUBLIC_SHARE:
                    keyboard.insert(
                        0,
                        [
                            InlineKeyboardButton(
                                "公开", callback_data="public_share_request"
                            )
                        ],
                    )
                default_markup = InlineKeyboardMarkup(keyboard)

                final_markup = reply_markup or default_markup
                if reply_markup and show_gallery_btn:
                    # Inject gallery submit button into custom reply_markup if not present
                    has_gallery = any(
                        btn.callback_data
                        and btn.callback_data.startswith("submit_gallery_")
                        for row in final_markup.inline_keyboard
                        for btn in row
                    )
                    if not has_gallery:
                        new_keyboard = [
                            list(row) for row in final_markup.inline_keyboard
                        ]
                        new_keyboard.insert(
                            0,
                            [
                                InlineKeyboardButton(
                                    "🚀 一键投稿至广场",
                                    callback_data=f"submit_gallery_{task_id}",
                                )
                            ],
                        )
                        final_markup = InlineKeyboardMarkup(new_keyboard)

                sent_msg = await robust_send_video(
                    context.bot,
                    chat_id,
                    video=media_bytes,
                    caption=caption or "✅ 视频生成完成",
                    reply_markup=final_markup,
                )
                if sent_msg:
                    mode_name = MODE_NAME_MAP.get(task_type, task_type)
                    context.bot_data[f"msg_meta_{sent_msg.message_id}"] = {
                        "mode_name": mode_name,
                        "prompt": prompt,
                        "task_id": task_id,
                    }
        else:
            media_bytes = await image_service.download_result(task_id)
            saved_output_image = user_logger.save_output_image(media_bytes, task_id)
            full_output_path = saved_output_image
            await user_logger.log_task(
                prompt,
                saved_input_images,
                saved_output_image,
                task_id=task_id,
                type=task_type,
                allow_contribute=allow_contribute,
            )
            await permission_service.refresh_user_group(internal_user_id)

            if send_result:
                from src.constants import MODE_IMG2IMG_LORA

                allowed_gallery_types = [
                    MODE_I2I_PRO,
                    MODE_EDIT,
                    MODE_CUSTOM_VIDEO,
                    MODE_VIDEO_LORA,
                    MODE_LTX_VIDEO,
                    MODE_IMG2IMG_LORA,
                ]
                show_gallery_btn = (
                    task_type in allowed_gallery_types and allow_contribute
                )

                keyboard = []
                if show_gallery_btn:
                    keyboard.append(
                        [
                            InlineKeyboardButton(
                                "🚀 一键投稿至广场",
                                callback_data=f"submit_gallery_{task_id}",
                            )
                        ]
                    )

                keyboard.append(
                    [
                        InlineKeyboardButton("👍", callback_data="rate_like"),
                        InlineKeyboardButton("👎", callback_data="rate_dislike"),
                    ]
                )

                if ENABLE_PUBLIC_SHARE:
                    keyboard.insert(
                        0,
                        [
                            InlineKeyboardButton(
                                "公开", callback_data="public_share_request"
                            )
                        ],
                    )
                default_markup = InlineKeyboardMarkup(keyboard)

                final_markup = reply_markup or default_markup
                if reply_markup and show_gallery_btn:
                    # Inject gallery submit button into custom reply_markup if not present
                    has_gallery = any(
                        btn.callback_data
                        and btn.callback_data.startswith("submit_gallery_")
                        for row in final_markup.inline_keyboard
                        for btn in row
                    )
                    if not has_gallery:
                        new_keyboard = [
                            list(row) for row in final_markup.inline_keyboard
                        ]
                        new_keyboard.insert(
                            0,
                            [
                                InlineKeyboardButton(
                                    "🚀 一键投稿至广场",
                                    callback_data=f"submit_gallery_{task_id}",
                                )
                            ],
                        )
                        final_markup = InlineKeyboardMarkup(new_keyboard)

                sent_msg = await robust_send_photo(
                    context.bot,
                    chat_id,
                    photo=media_bytes,
                    caption=caption or "✅ 图片生成完成",
                    reply_markup=final_markup,
                )
                if sent_msg:
                    mode_name = MODE_NAME_MAP.get(task_type, task_type)
                    if task_type == "face_swap":
                        mode_name = MODE_NAME_MAP.get(MODE_FACESWAP_STEP1)
                    elif task_type == "penetration":
                        mode_name = MODE_NAME_MAP.get(MODE_PENETRATION_STEP1)
                    elif task_type == "undress":
                        mode_name = MODE_NAME_MAP.get(MODE_UNDRESS)
                    elif task_type == "masturbation":
                        mode_name = MODE_NAME_MAP.get(MODE_MASTURBATION)

                    context.bot_data[f"msg_meta_{sent_msg.message_id}"] = {
                        "mode_name": mode_name,
                        "prompt": prompt,
                        "task_id": task_id,
                    }

        try:
            if delete_status and send_result:
                await robust_delete_message(status_msg)
        except Exception:
            pass

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
