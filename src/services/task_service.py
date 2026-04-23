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
    MODE_FACESWAP_STEP1,
    MODE_MASTURBATION,
    MODE_NAME_MAP,
    MODE_PENETRATION_STEP1,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_UNDRESS,
    MODE_UNDRESS_TONGUE,
    TASK_COSTS,
    TMP_DIR,
    MODE_I2I_PRO,
    MAX_CONCURRENT_TASKS,
    MODE_FACE_VIDEO_STEP1,
    MODE_EDIT,
    MODE_VIDEO_LORA,
    MODE_LTX_VIDEO
)
from src.handlers.utils import MockMessage
from src.logger import UserLogger
from src.services.image_service import image_service
from src.services.permission_service import permission_service
from src.utils import (
    load_prompts,
    robust_delete_message,
    robust_edit_text,
    robust_reply_text,
    robust_send_message,
    robust_send_photo,
    robust_send_video,
)

from src.services.task_registry import TaskRegistry
from src.services.redis_client import redis_client

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
    ):
        from src.core.user_core import get_or_create_user_by_telegram
        from src.core.billing_core import check_concurrency_lock, release_concurrency_lock, check_and_deduct_credits, refund_credits, get_user_priority_and_identity

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.full_name
        
        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        # 1. Check active tasks limit via core
        can_run, lock_msg = await check_concurrency_lock(internal_user_id)
        if not can_run:
            await robust_send_message(context.bot, chat_id, f"⚠️ {lock_msg}")
            if cleanup and image_path:
                TaskService._cleanup_files([image_path])
            return None, None
            
        from src.constants import MODE_LTX_VIDEO, LTX_RESOLUTION_COST, LTX_DURATION_MULTIPLIER
        mode = MODE_LTX_VIDEO
        
        resolution = context.user_data.get('ltx_video_resolution', "1280x704")
        duration = context.user_data.get('ltx_video_duration', "5s")
        
        base_cost = LTX_RESOLUTION_COST.get(resolution, 10)
        multiplier = LTX_DURATION_MULTIPLIER.get(duration, 1.0)
        cost = int(base_cost * multiplier)
        
        duration_frames = {"5s": 5, "10s": 10, "15s": 15, "20s": 20}
        length = duration_frames.get(duration, 10)

        user_logger = UserLogger(internal_user_id, username)

        # Append resolution and duration to prompt for history tracking
        prompt = f"[{resolution}|{duration}] {prompt}"

        saved_input_image = user_logger.save_input_image(image_path)
        notice = await TaskService._get_acceleration_notice(user_id)
        msg_text = f"🚀 正在处理高级图生视频任务 (画质:{resolution}, 时长:{duration}, 消耗{cost}灵石)...{notice}"
        msg = await robust_reply_text(update.effective_message, msg_text)
        registry_task_id = None

        try:
            width, height = map(int, resolution.split('x'))
                
            # 2. 计费 via core
            deduct_success, deduct_msg = await check_and_deduct_credits(internal_user_id, cost, mode, username)
            if not deduct_success:
                await release_concurrency_lock(internal_user_id)
                await robust_delete_message(msg)
                await robust_send_message(context.bot, chat_id, deduct_msg)
                if cleanup and image_path:
                    TaskService._cleanup_files([image_path])
                return None, None
                
            priority, identity_str, user_group = await get_user_priority_and_identity(internal_user_id)

            registry_task_id = await TaskRegistry.add_task(
                internal_user_id, username, cost, mode, chat_id=chat_id, message_id=msg.message_id if msg else None,
                prompt=prompt, saved_input_images=[saved_input_image] if saved_input_image else [], is_video=True, priority=priority
            )
            
            await robust_edit_text(msg, "⏳ 正在生成高级视频，可能需要数分钟，请耐心等待...")

            task_id = await image_service.submit_ltx_video_task(
                prompt, saved_input_image, width=width, height=height, length=length, priority=priority
            )
            
            if registry_task_id and task_id:
                await TaskRegistry.update_backend_task_id(registry_task_id, task_id)

            final_info = await TaskService._monitor_task_progress(
                task_id, msg, is_video=True, monitor_func=image_service.monitor_progress, identity_str=identity_str, user_group=user_group
            )

            if final_info:
                return await TaskService._handle_task_completion(
                    context,
                    chat_id,
                    internal_user_id,
                    prompt,
                    mode,
                    task_id,
                    [saved_input_image] if saved_input_image else [],
                    user_logger,
                    is_video=True,
                    send_result=True,
                    reply_markup=None,
                    status_msg=msg,
                    delete_status=True,
                    caption="✅ 高级图生视频生成完成",
                    allow_contribute=allow_contribute,
                )
            else:
                await refund_credits(internal_user_id, cost, "refund", username)
                await robust_send_message(
                    context.bot, chat_id, "❌ 生成完成但未获取到文件路径，已退还灵石"
                )
                return None, None

        except Exception as e:
            logger.error(
                f"Error in ltx video task for user {internal_user_id}: {e}", exc_info=True
            )
            await refund_credits(internal_user_id, cost, "refund", username)
            await robust_send_message(context.bot, chat_id, f"❌ 出错了：{e}，已退还灵石")
            return None, None
        finally:
            if registry_task_id:
                await TaskRegistry.remove_task(registry_task_id)
            await release_concurrency_lock(internal_user_id)
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
    ):
        from src.core.user_core import get_or_create_user_by_telegram
        from src.core.billing_core import check_concurrency_lock, release_concurrency_lock, check_and_deduct_credits, refund_credits, get_user_priority_and_identity
        from src.core.task_core import core_submit_face_video

        # 1. 身份转换 (TG ID -> 内部 ID)
        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id
        
        # 2. Check active tasks limit via core
        can_run, lock_msg = await check_concurrency_lock(internal_user_id)
        if not can_run:
            await robust_send_message(context.bot, chat_id, f"⚠️ {lock_msg}")
            if cleanup:
                TaskService._cleanup_files([face_image_path, video_path])
            return None, None
            
        mode = MODE_FACE_VIDEO_STEP1
        notice = await TaskService._get_acceleration_notice(user_id)
        msg_text = f"🚀 正在处理视频换脸任务 (画质:{resolution}p, 消耗{cost}灵石)...{notice}"
        
        status_msg = await TaskService._get_or_send_status_msg(
            context, chat_id, message_id, msg_text
        )
        
        try:
            # 3. 计费 via core
            deduct_success, deduct_msg = await check_and_deduct_credits(internal_user_id, cost, mode, username)
            if not deduct_success:
                await release_concurrency_lock(internal_user_id)
                await robust_edit_text(status_msg, deduct_msg)
                if cleanup:
                    TaskService._cleanup_files([face_image_path, video_path])
                return None, None

            priority, identity_str, user_group = await get_user_priority_and_identity(internal_user_id)

            # 4. 调用纯净核心逻辑提交任务
            submit_success, submit_msg, task_id, saved_face_image, saved_video, registry_task_id = await core_submit_face_video(
                internal_user_id, username, face_image_path, video_path, resolution, duration, cost, mode, priority,
                chat_id=chat_id, message_id=status_msg.message_id if status_msg else None
            )

            if not submit_success:
                await refund_credits(internal_user_id, cost, "refund", username)
                await robust_edit_text(status_msg, f"⚠️ {submit_msg}\n已退还灵石。")
                return None, None

            # 5. 监控与完成处理保留原样，但传递正确参数
            user_logger = UserLogger(internal_user_id, username)
            final_info = await TaskService._monitor_task_progress(
                task_id, status_msg, is_video=True, monitor_func=image_service.monitor_progress, identity_str=identity_str, user_group=user_group
            )

            if final_info:
                return await TaskService._handle_task_completion(
                    context,
                    chat_id,
                    internal_user_id, # internal user_id for logging and group refresh
                    "face video",
                    mode,
                    task_id,
                    [saved_face_image, saved_video],
                    user_logger,
                    is_video=True,
                    send_result=True,
                    reply_markup=None,
                    status_msg=status_msg,
                    delete_status=True,
                    caption="✅ 视频换脸完成",
                )
            else:
                await refund_credits(internal_user_id, cost, "refund", username)
                await robust_edit_text(status_msg, "⚠️ 生成失败或超时，已退还灵石。")
                return None, None

        except Exception as e:
            logger.error(f"Error processing face video task for {internal_user_id}: {e}", exc_info=True)
            await refund_credits(internal_user_id, cost, "refund", username)
            await robust_edit_text(status_msg, f"❌ 系统错误：{str(e)}\n已退还灵石。")
            return None, None
        finally:
            if 'registry_task_id' in locals() and registry_task_id:
                await TaskRegistry.remove_task(registry_task_id)
            await release_concurrency_lock(internal_user_id)
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
        allow_contribute: bool = True,
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """Common generation logic for generic tasks."""
        from src.core.user_core import get_or_create_user_by_telegram
        from src.core.billing_core import check_concurrency_lock, release_concurrency_lock, check_and_deduct_credits, refund_credits, get_user_priority_and_identity
        from src.core.task_core import core_submit_generation_task
        from src.constants import DEFAULT_RESOLUTION, DEFAULT_DURATION, RESOLUTION_COST, DURATION_MULTIPLIER, DURATION_FRAMES

        # 1. 身份转换
        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        # 2. Check active tasks limit via core
        can_run, lock_msg = await check_concurrency_lock(internal_user_id)
        if not can_run:
            await robust_send_message(context.bot, chat_id, f"⚠️ {lock_msg}")
            if cleanup:
                TaskService._cleanup_files(images)
            return None, None

        # Determine cost and default task type
        if task_type == "face_swap":
            cost = TASK_COSTS.get(MODE_FACESWAP_STEP1, 1)
        elif task_type == MODE_EDIT or task_type == "edit":
            cost = 6 if len(images) == 2 else 2
        else:
            cost = TASK_COSTS.get(task_type, 6 if is_video else 2)
            
        if not task_type:
            task_type = "video" if is_video else "image"
            
        resolution = 512
        duration = 5
        if is_video and task_type in [MODE_CUSTOM_VIDEO, "video_lora"]:
            res_str = context.user_data.get('custom_video_resolution', DEFAULT_RESOLUTION)
            dur_str = context.user_data.get('custom_video_duration', DEFAULT_DURATION)
            
            if res_str == "1024p" and dur_str == "10s":
                res_str = "720p"
                context.user_data['custom_video_resolution'] = "720p"
                
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

            base_cost = RESOLUTION_COST.get(res_str, 6)
            multiplier = DURATION_MULTIPLIER.get(dur_str, 1.0)
            cost = int(base_cost * multiplier)

        # Load prompts config
        prompts_config = load_prompts()
        negative_prompt = prompts_config.get(
            "negative_prompt",
            "low quality, bad anatomy, ugly, deformed, blurry, watermark, text",
        )

        notice = await TaskService._get_acceleration_notice(user_id)
        msg_text = (
            f"🚀 正在处理视频生成任务 (消耗{cost}灵石)...{notice}"
            if is_video
            else f"🚀 正在处理 {len(images)} 张图片 (消耗{cost}灵石)...{notice}"
        )

        status_msg = await TaskService._get_or_send_status_msg(
            context, chat_id, status_msg_id, msg_text
        )

        media_bytes = None
        full_output_path = None

        try:
            # 3. Deduct Quota via core
            if deduct_quota:
                deduct_success, deduct_msg = await check_and_deduct_credits(internal_user_id, cost, task_type, username)
                if not deduct_success:
                    await release_concurrency_lock(internal_user_id)
                    await robust_edit_text(status_msg, deduct_msg)
                    if cleanup:
                        TaskService._cleanup_files(images)
                    return None, None

            # Determine Priority
            priority, identity_str, user_group = await get_user_priority_and_identity(internal_user_id)

            # 4. Submit Task via core
            submit_success, submit_msg, task_id, saved_input_images, registry_task_id = await core_submit_generation_task(
                internal_user_id, username, prompt, images, is_video, task_type, cost, priority, negative_prompt,
                chat_id=chat_id, message_id=status_msg.message_id if status_msg else None, lora_name=lora_name,
                resolution=resolution, duration=duration
            )

            if not submit_success:
                if deduct_quota:
                    await refund_credits(internal_user_id, cost, "refund", username)
                await robust_edit_text(status_msg, f"⚠️ {submit_msg}\n已退还灵石。")
                return None, None

            # Monitor Progress
            user_logger = UserLogger(internal_user_id, username)
            final_info = await TaskService._monitor_task_progress(
                task_id, status_msg, is_video, image_service.monitor_progress, identity_str=identity_str, user_group=user_group
            )

            if final_info:
                log_prompt = prompt
                if task_type == "video_lora" and lora_name:
                    # 仅为了数据库和历史展示附加 lora 模型信息
                    log_prompt = f"[模型: {lora_name}] {prompt}"
                    
                mode_name = MODE_NAME_MAP.get(task_type, task_type)

                media_bytes, full_output_path = (
                    await TaskService._handle_task_completion(
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
                        caption=f"✅ {mode_name} 生成完成",
                        allow_contribute=allow_contribute,
                    )
                )
            else:
                if deduct_quota:
                    await refund_credits(internal_user_id, cost, "refund", username)
                await robust_send_message(
                    context.bot, chat_id, "❌ 生成完成但未获取到文件路径，已退还灵石"
                )

        except Exception as e:
            logger.error(f"Error in process_generation_task for user {internal_user_id}: {e}", exc_info=True)
            if deduct_quota:
                await refund_credits(internal_user_id, cost, "refund", username)
            await robust_send_message(context.bot, chat_id, f"❌ 出错了：{e}，已退还灵石")

        finally:
            if 'registry_task_id' in locals() and registry_task_id:
                await TaskRegistry.remove_task(registry_task_id)
            await release_concurrency_lock(internal_user_id)
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
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Generic handler for video generation tasks to reduce code duplication.
        """
        from src.core.user_core import get_or_create_user_by_telegram
        from src.core.billing_core import check_concurrency_lock, release_concurrency_lock, check_and_deduct_credits, refund_credits, get_user_priority_and_identity

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.full_name
        
        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        # 1. Check active tasks limit via core
        can_run, lock_msg = await check_concurrency_lock(internal_user_id)
        if not can_run:
            await robust_send_message(context.bot, chat_id, f"⚠️ {lock_msg}")
            if cleanup:
                TaskService._cleanup_files([image_path])
            return None, None
        
        from src.constants import DEFAULT_RESOLUTION, DEFAULT_DURATION, RESOLUTION_COST, DURATION_MULTIPLIER, DURATION_FRAMES

        # Get resolution and duration from user_data
        resolution = context.user_data.get('custom_video_resolution', DEFAULT_RESOLUTION)
        duration = context.user_data.get('custom_video_duration', DEFAULT_DURATION)

        # Fallback safely (1024p + 10s is too heavy)
        if resolution == "1024p" and duration == "10s":
            resolution = "720p"
            context.user_data['custom_video_resolution'] = "720p"
            await robust_reply_text(update.effective_message, "⚠️ 检测到非法配置(1024p+10s)，已自动降级为720p+10s。")

        # Calculate width/height and length
        if resolution == "1024p":
            width, height = 1024, 1024
        elif resolution == "720p":
            width, height = 720, 720
        else:
            width, height = 512, 512
            
        length = DURATION_FRAMES.get(duration, 81)

        # Calculate cost
        base_cost = RESOLUTION_COST.get(resolution, TASK_COSTS.get(mode, 6))
        multiplier = DURATION_MULTIPLIER.get(duration, 1.0)
        cost = int(base_cost * multiplier)
        
        # Calculate width/height and length
        if resolution == "1024p":
            width, height = 1024, 1024
        elif resolution == "720p":
            width, height = 720, 720
        else:
            width, height = 512, 512
            
        length = DURATION_FRAMES.get(duration, 81)

        user_logger = UserLogger(internal_user_id, username)

        # Load prompt
        prompts_config = load_prompts()
        base_prompt = prompts_config.get(default_prompt_key, default_prompt_text)
        prompt = f"[{resolution}|{duration}] {base_prompt}"

        saved_input_image = user_logger.save_input_image(image_path)

        mode_name = MODE_NAME_MAP.get(mode, mode)
        notice = await TaskService._get_acceleration_notice(user_id)
        msg_text = f"🚀 正在处理{mode_name}生成任务 (画质:{resolution}, 时长:{duration}, 消耗{cost}灵石)...{notice}"
        msg = await robust_reply_text(update.effective_message, msg_text)

        media_bytes = None
        full_output_path = None
        registry_task_id = None

        try:
            # 2. 计费 via core
            deduct_success, deduct_msg = await check_and_deduct_credits(internal_user_id, cost, mode, username)
            if not deduct_success:
                await release_concurrency_lock(internal_user_id)
                await robust_delete_message(msg)
                await robust_send_message(context.bot, chat_id, deduct_msg)
                if cleanup:
                    TaskService._cleanup_files([image_path])
                return None, None

            priority, identity_str, user_group = await get_user_priority_and_identity(internal_user_id)

            registry_task_id = await TaskRegistry.add_task(
                internal_user_id, username, cost, mode, chat_id=chat_id, message_id=msg.message_id if msg else None,
                prompt=prompt, saved_input_images=[saved_input_image], is_video=True, priority=priority
            )

            await robust_edit_text(msg, "⏳ 正在生成视频，请耐心等待...")

            # Submit Task
            if mode == MODE_DOGGY_STYLE:
                task_id = await image_service.submit_perfect_video_insert_task(
                    prompt, saved_input_image, width=width, height=height, length=length, priority=priority
                )
            else:
                task_id = await image_service.submit_perfect_video_edit(
                    prompt, saved_input_image, width=width, height=height, length=length, priority=priority
                )
            
            if registry_task_id and task_id:
                await TaskRegistry.update_backend_task_id(registry_task_id, task_id)

            # Monitor Progress
            final_info = await TaskService._monitor_task_progress(
                task_id, msg, is_video=True, monitor_func=image_service.monitor_progress, identity_str=identity_str, user_group=user_group
            )

            if final_info:
                media_bytes, full_output_path = (
                    await TaskService._handle_task_completion(
                        context,
                        chat_id,
                        internal_user_id,
                        prompt,
                        mode,
                        task_id,
                        [saved_input_image] if saved_input_image else [],
                        user_logger,
                        is_video=True,
                        send_result=True,
                        reply_markup=None,
                        status_msg=msg,
                        delete_status=True,
                        caption=f"✅ {mode_name} 生成完成",
                        allow_contribute=allow_contribute,
                    )
                )
            else:
                await refund_credits(internal_user_id, cost, "refund", username)
                await robust_send_message(
                    context.bot, chat_id, "❌ 生成完成但未获取到任务信息，已退还灵石"
                )

        except Exception as e:
            logger.error(f"Error in {mode} task for user {internal_user_id}: {e}", exc_info=True)
            await refund_credits(internal_user_id, cost, "refund", username)
            await robust_send_message(context.bot, chat_id, f"❌ 出错了：{e}，已退还灵石")
        finally:
            if registry_task_id:
                await TaskRegistry.remove_task(registry_task_id)
            await release_concurrency_lock(internal_user_id)
                
            if cleanup:
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
    ):
        from src.core.user_core import get_or_create_user_by_telegram
        from src.core.billing_core import check_concurrency_lock, release_concurrency_lock, check_and_deduct_credits, refund_credits, get_user_priority_and_identity

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.full_name
        
        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        # 1. Check active tasks limit via core
        can_run, lock_msg = await check_concurrency_lock(internal_user_id)
        if not can_run:
            await robust_send_message(context.bot, chat_id, f"⚠️ {lock_msg}")
            if cleanup and image_path:
                TaskService._cleanup_files([image_path])
            return None, None
            
        mode = MODE_CUSTOM_VIDEO
        
        from src.constants import DEFAULT_RESOLUTION, RESOLUTION_COST, DEFAULT_DURATION, DURATION_MULTIPLIER, DURATION_FRAMES
        resolution = context.user_data.get('custom_video_resolution', DEFAULT_RESOLUTION)
        duration = context.user_data.get('custom_video_duration', DEFAULT_DURATION)
        
        if resolution == "1024p" and duration == "10s":
            resolution = "720p" # Fallback safely
            context.user_data['custom_video_resolution'] = "720p"
            await robust_reply_text(update.effective_message, "⚠️ 检测到非法配置(1024p+10s)，已自动降级为720p+10s。")
            
        base_cost = RESOLUTION_COST.get(resolution, TASK_COSTS.get(mode, 6))
        multiplier = DURATION_MULTIPLIER.get(duration, 1.0)
        cost = int(base_cost * multiplier)
        length = DURATION_FRAMES.get(duration, 81)

        user_logger = UserLogger(internal_user_id, username)

        # Append resolution and duration to prompt for history tracking
        prompt = f"[{resolution}|{duration}] {prompt}"

        saved_input_image = user_logger.save_input_image(image_path)
        notice = await TaskService._get_acceleration_notice(user_id)
        msg_text = f"🚀 正在处理自定义视频生成任务 (画质:{resolution}, 时长:{duration}, 消耗{cost}灵石)...{notice}"
        msg = await robust_reply_text(update.effective_message, msg_text)
        registry_task_id = None

        try:
            if resolution == "1024p":
                width, height = 1024, 1024
            elif resolution == "720p":
                width, height = 720, 720
            else:
                width, height = 512, 512
                
            # 2. 计费 via core
            deduct_success, deduct_msg = await check_and_deduct_credits(internal_user_id, cost, mode, username)
            if not deduct_success:
                await release_concurrency_lock(internal_user_id)
                await robust_delete_message(msg)
                await robust_send_message(context.bot, chat_id, deduct_msg)
                if cleanup and image_path:
                    TaskService._cleanup_files([image_path])
                return None, None
                
            priority, identity_str, user_group = await get_user_priority_and_identity(internal_user_id)

            registry_task_id = await TaskRegistry.add_task(
                internal_user_id, username, cost, mode, chat_id=chat_id, message_id=msg.message_id if msg else None,
                prompt=prompt, saved_input_images=[saved_input_image] if saved_input_image else [], is_video=True, priority=priority
            )
            
            await robust_edit_text(msg, "⏳ 正在生成自定义视频，请耐心等待...")

            task_id = await image_service.submit_perfect_video_edit(
                prompt, saved_input_image, width=width, height=height, length=length, priority=priority
            )
            
            if registry_task_id and task_id:
                await TaskRegistry.update_backend_task_id(registry_task_id, task_id)

            final_info = await TaskService._monitor_task_progress(
                task_id, msg, is_video=True, monitor_func=image_service.monitor_progress, identity_str=identity_str, user_group=user_group
            )

            if final_info:
                return await TaskService._handle_task_completion(
                    context,
                    chat_id,
                    internal_user_id,
                    prompt,
                    mode,
                    task_id,
                    [saved_input_image] if saved_input_image else [],
                    user_logger,
                    is_video=True,
                    send_result=True,
                    reply_markup=None,
                    status_msg=msg,
                    delete_status=True,
                    caption="✅ 自定义图生视频生成完成",
                )
            else:
                await refund_credits(internal_user_id, cost, "refund", username)
                await robust_send_message(
                    context.bot, chat_id, "❌ 生成完成但未获取到文件路径，已退还灵石"
                )
                return None, None

        except Exception as e:
            logger.error(
                f"Error in custom video task for user {internal_user_id}: {e}", exc_info=True
            )
            await refund_credits(internal_user_id, cost, "refund", username)
            await robust_send_message(context.bot, chat_id, f"❌ 出错了：{e}，已退还灵石")
            return None, None
        finally:
            if registry_task_id:
                await TaskRegistry.remove_task(registry_task_id)
            await release_concurrency_lock(internal_user_id)
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
    ):
        """Handle MODE_I2I_PRO requests"""
        from src.constants import MODE_I2I_PRO, TASK_COSTS
        from src.core.user_core import get_or_create_user_by_telegram
        from src.core.billing_core import check_concurrency_lock, release_concurrency_lock, check_and_deduct_credits, refund_credits, get_user_priority_and_identity
        
        internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
        internal_user_id = internal_user.id

        # 1. Check active tasks limit
        can_run, lock_msg = await check_concurrency_lock(internal_user_id)
        if not can_run:
            await robust_send_message(context.bot, chat_id, f"⚠️ {lock_msg}")
            TaskService._cleanup_files(images)
            return None, None

        cost = TASK_COSTS.get(MODE_I2I_PRO, 3)
        mode = MODE_I2I_PRO
        user_logger = UserLogger(internal_user_id, username)
        
        # Validate images
        if not images or len(images) == 0:
            await release_concurrency_lock(internal_user_id)
            await robust_send_message(context.bot, chat_id, "❌ 请先发送参考图片。")
            return None, None
            
        image_path = images[0]
        saved_input_image = user_logger.save_input_image(image_path)
        
        import random
        import os
        # Use JS max safe integer (2^53 - 1) to prevent ComfyUI API 400 Bad Request
        seed = random.randint(1, 9007199254740991)

        notice = await TaskService._get_acceleration_notice(user_id)
        msg_text = f"🚀 正在处理幻想换脸任务 (消耗{cost}灵石)...{notice}"
        msg = await robust_send_message(context.bot, chat_id, msg_text)
        registry_task_id = None

        try:
            # 2. 计费
            deduct_success, deduct_msg = await check_and_deduct_credits(internal_user_id, cost, mode, username)
            if not deduct_success:
                await release_concurrency_lock(internal_user_id)
                await robust_delete_message(msg)
                await robust_send_message(context.bot, chat_id, deduct_msg)
                TaskService._cleanup_files(images)
                return None, None

            priority, identity_str, user_group = await get_user_priority_and_identity(internal_user_id)

            registry_task_id = await TaskRegistry.add_task(
                internal_user_id, username, cost, mode, chat_id=chat_id, message_id=msg.message_id if msg else None,
                prompt=prompt, saved_input_images=[saved_input_image], is_video=False, priority=priority
            )

            # Upload image to MinIO
            # saved_input_image is already uploaded to MinIO by user_logger.save_input_image() and it returns the object_name
            minio_object_name = saved_input_image
            
            task_id = await image_service.submit_i2i_pro_task(prompt, minio_object_name, seed, priority=priority)

            if registry_task_id and task_id:
                await TaskRegistry.update_backend_task_id(registry_task_id, task_id)

            final_info = await TaskService._monitor_task_progress(
                task_id, msg, is_video=False, monitor_func=image_service.monitor_progress, identity_str=identity_str, user_group=user_group
            )

            if final_info:
                return await TaskService._handle_task_completion(
                    context, chat_id, internal_user_id, prompt, mode, task_id, [saved_input_image], user_logger,
                    is_video=False, send_result=True, reply_markup=None, status_msg=msg, delete_status=True,
                    caption=f"🌟 幻想换脸生成完成", allow_contribute=allow_contribute
                )
            else:
                await refund_credits(internal_user_id, cost, "refund", username)
                await robust_send_message(context.bot, chat_id, "❌ 生成完成但未获取到文件路径，已退还灵石")
                return None, None

        except Exception as e:
            user_logger.logger.error(f"Error in process_i2i_pro_task for user {internal_user_id}: {e}", exc_info=True)
            await refund_credits(internal_user_id, cost, "refund", username)
            await robust_send_message(context.bot, chat_id, f"❌ 出错了：{e}，已退还灵石")
            return None, None
        finally:
            if registry_task_id:
                await TaskRegistry.remove_task(registry_task_id)
            await release_concurrency_lock(internal_user_id)
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
            return await image_service.submit_perfect_video_edit(prompt, images[0], priority=priority)
        else:
            return await image_service.submit_task(prompt, images, negative_prompt, priority=priority)

    @staticmethod
    async def _monitor_task_progress(task_id, status_msg, is_video, monitor_func, identity_str=None, user_group=None):
        last_progress = 0
        last_status = None
        last_queue_pos = None
        final_info = None

        async def update_status_message(text, **kwargs):
            try:
                await robust_edit_text(status_msg, text, **kwargs)
                return True
            except Exception as exc:
                logger.warning(f"Failed to update status message for task {task_id}: {exc}")
                return False

        # Build VIP/Group suffix if applicable
        vip_suffix = ""
        privileges = []
        if identity_str and identity_str not in ["外门弟子", "凡人", "练气期", "筑基期", "金丹期", "元婴期", "default"]:
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

                logger.debug(f"Task {task_id} pending. Info queue_pos: {raw_pos}, queue_remaining: {info.get('queue_remaining')}")

                if queue_pos is not None:
                    if queue_pos != last_queue_pos or last_status != "pending":
                        if await update_status_message(
                            f"⏳ 排队中... (第 {queue_pos} 位){vip_suffix}", parse_mode="Markdown"
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
                allow_contribute=allow_contribute
            )
            await permission_service.refresh_user_group(internal_user_id)

            if send_result:
                allowed_gallery_types = [MODE_I2I_PRO, MODE_EDIT, MODE_CUSTOM_VIDEO, MODE_VIDEO_LORA, MODE_LTX_VIDEO]
                show_gallery_btn = task_type in allowed_gallery_types and allow_contribute
                
                keyboard = []
                if show_gallery_btn:
                    keyboard.append([InlineKeyboardButton("🚀 一键投稿至广场", callback_data=f"submit_gallery_{task_id}")])
                    
                keyboard.append([
                    InlineKeyboardButton("👍", callback_data="rate_like"),
                    InlineKeyboardButton("👎", callback_data="rate_dislike")
                ])
                
                if ENABLE_PUBLIC_SHARE:
                    keyboard.insert(
                        0,
                        [InlineKeyboardButton("公开", callback_data="public_share_request")]
                    )
                default_markup = InlineKeyboardMarkup(keyboard)
                
                final_markup = reply_markup or default_markup
                if reply_markup and show_gallery_btn:
                    # Inject gallery submit button into custom reply_markup if not present
                    has_gallery = any(
                        btn.callback_data and btn.callback_data.startswith("submit_gallery_")
                        for row in final_markup.inline_keyboard for btn in row
                    )
                    if not has_gallery:
                        new_keyboard = [list(row) for row in final_markup.inline_keyboard]
                        new_keyboard.insert(
                            0,
                            [InlineKeyboardButton("🚀 一键投稿至广场", callback_data=f"submit_gallery_{task_id}")]
                        )
                        final_markup = InlineKeyboardMarkup(new_keyboard)
                        
                sent_msg = await robust_send_video(
                    context.bot,
                    chat_id,
                    video=media_bytes,
                    caption=caption or "✅ 视频生成完成",
                    reply_markup=final_markup
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
                allow_contribute=allow_contribute
            )
            await permission_service.refresh_user_group(internal_user_id)

            if send_result:
                allowed_gallery_types = [MODE_I2I_PRO, MODE_EDIT, MODE_CUSTOM_VIDEO, MODE_VIDEO_LORA, MODE_LTX_VIDEO]
                show_gallery_btn = task_type in allowed_gallery_types and allow_contribute
                
                keyboard = []
                if show_gallery_btn:
                    keyboard.append([InlineKeyboardButton("🚀 一键投稿至广场", callback_data=f"submit_gallery_{task_id}")])
                    
                keyboard.append([
                    InlineKeyboardButton("👍", callback_data="rate_like"),
                    InlineKeyboardButton("👎", callback_data="rate_dislike")
                ])
                
                if ENABLE_PUBLIC_SHARE:
                    keyboard.insert(
                        0,
                        [InlineKeyboardButton("公开", callback_data="public_share_request")]
                    )
                default_markup = InlineKeyboardMarkup(keyboard)
                
                final_markup = reply_markup or default_markup
                if reply_markup and show_gallery_btn:
                    # Inject gallery submit button into custom reply_markup if not present
                    has_gallery = any(
                        btn.callback_data and btn.callback_data.startswith("submit_gallery_")
                        for row in final_markup.inline_keyboard for btn in row
                    )
                    if not has_gallery:
                        new_keyboard = [list(row) for row in final_markup.inline_keyboard]
                        new_keyboard.insert(
                            0,
                            [InlineKeyboardButton("🚀 一键投稿至广场", callback_data=f"submit_gallery_{task_id}")]
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
                try:
                    os.remove(path)
                except OSError:
                    pass

    @staticmethod
    async def _get_acceleration_notice(user_id: int) -> str:
        stats = await permission_service.quota_manager.get_user_stats(user_id)
        if stats.get("generation_count", 0) < 2:
            return "\n✨ [新手特权] 前2次生成享受极速排队通道！"
        return ""


task_service = TaskService()
