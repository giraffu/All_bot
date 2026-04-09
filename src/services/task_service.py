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
    MODE_I2I_PRO
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
        # 1. Check active tasks limit
        active_tasks = await redis_client.increment_user_concurrency(user_id)
        from src.constants import MAX_CONCURRENT_TASKS, MODE_FACE_VIDEO_STEP1
        if active_tasks > MAX_CONCURRENT_TASKS:
            await redis_client.decrement_user_concurrency(user_id)
            await robust_send_message(context.bot, chat_id, f"⚠️ 您当前已有 {MAX_CONCURRENT_TASKS} 个任务正在处理中，请等待其中一个完成后再试！")
            if cleanup:
                TaskService._cleanup_files([face_image_path, video_path])
            return None, None
            
        mode = MODE_FACE_VIDEO_STEP1
        user_logger = UserLogger(user_id, username)
        
        saved_face_image = user_logger.save_input_image(face_image_path)
        saved_video = user_logger.save_input_image(video_path) # save_input_image works for video too
        
        notice = await TaskService._get_acceleration_notice(user_id)
        msg_text = f"🚀 正在处理视频换脸任务 (画质:{resolution}p, 消耗{cost}灵石)...{notice}"
        
        status_msg = await TaskService._get_or_send_status_msg(
            context, chat_id, message_id, msg_text
        )
        registry_task_id = None
        
        try:
            priority = await permission_service.calculate_user_priority(user_id)
            identity_str = await permission_service.get_user_identity(user_id)
            user_group = await permission_service.get_user_group(user_id)

            await permission_service.increment_quota(user_id, cost=cost, username=username, task_type=mode)
            registry_task_id = await TaskRegistry.add_task(
                user_id, username, cost, mode, chat_id=chat_id, message_id=status_msg.message_id if status_msg else None,
                prompt="face video", saved_input_images=[saved_face_image, saved_video], is_video=True, priority=priority
            )
            
            task_id = await image_service.submit_face_video(
                saved_face_image, saved_video, resolution=resolution, duration=duration, priority=priority
            )
            
            if registry_task_id and task_id:
                await TaskRegistry.update_backend_task_id(registry_task_id, task_id)

            final_info = await TaskService._monitor_task_progress(
                task_id, status_msg, is_video=True, monitor_func=image_service.monitor_progress, identity_str=identity_str, user_group=user_group
            )

            if final_info:
                return await TaskService._handle_task_completion(
                    context,
                    chat_id,
                    user_id,
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
                if registry_task_id:
                    try:
                        await TaskRegistry.mark_task_status(registry_task_id, "failed")
                    except AttributeError:
                        pass
                await permission_service.increment_quota(user_id, cost=-cost, username=username, task_type="refund")
                await robust_edit_text(status_msg, "⚠️ 生成失败或超时，已退还灵石。")
                return None, None

        except Exception as e:
            logger.error(f"Error processing face video task for {user_id}: {e}", exc_info=True)
            if registry_task_id:
                try:
                    await TaskRegistry.mark_task_status(registry_task_id, "failed")
                except AttributeError:
                    # In case mark_task_status doesn't exist
                    pass
            await permission_service.increment_quota(user_id, cost=-cost, username=username, task_type="refund")
            await robust_edit_text(status_msg, f"❌ 系统错误：{str(e)}\n已退还灵石。")
            return None, None
        finally:
            await redis_client.decrement_user_concurrency(user_id)
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
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """Common generation logic for generic tasks."""

        # 1. Check active tasks limit
        active_tasks = await redis_client.increment_user_concurrency(user_id)
        from src.constants import MAX_CONCURRENT_TASKS
        if active_tasks > MAX_CONCURRENT_TASKS:
            await redis_client.decrement_user_concurrency(user_id)
            await robust_send_message(context.bot, chat_id, f"⚠️ 您当前已有 {MAX_CONCURRENT_TASKS} 个任务正在处理中，请等待其中一个完成后再试！")
            if cleanup:
                TaskService._cleanup_files(images)
            return None, None

        # Determine cost and default task type
        # For faceswap tasks, map the generic "face_swap" string back to constants for cost lookup
        from src.constants import MODE_FACESWAP_STEP1, MODE_EDIT
        if task_type == "face_swap":
            # Both fast faceswap and random faceswap cost 1 credit now
            cost = TASK_COSTS.get(MODE_FACESWAP_STEP1, 1)
        elif task_type == MODE_EDIT or task_type == "edit":
            cost = 2
        else:
            cost = TASK_COSTS.get(task_type, 6 if is_video else 2)
            
        if not task_type:
            task_type = "video" if is_video else "image"

        # Load prompts config
        prompts_config = load_prompts()
        negative_prompt = prompts_config.get(
            "negative_prompt",
            "low quality, bad anatomy, ugly, deformed, blurry, watermark, text",
        )

        # Logger & Save Input
        user_logger = UserLogger(user_id, username)
        saved_input_images = []
        for img_path in images:
            if img_path.startswith("template:"):
                # Pass template path directly without saving
                saved_input_images.append(img_path)
            else:
                saved_name = user_logger.save_input_image(img_path)
                if saved_name:
                    saved_input_images.append(saved_name)

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
        registry_task_id = None

        try:
            # Determine Priority
            priority = await permission_service.calculate_user_priority(user_id)
            identity_str = await permission_service.get_user_identity(user_id)
            user_group = await permission_service.get_user_group(user_id)

            # Deduct Quota (Credits) first
            if deduct_quota:
                await permission_service.increment_quota(user_id, cost=cost, username=username, task_type=task_type)
                registry_task_id = await TaskRegistry.add_task(
                    user_id, username, cost, task_type, chat_id=chat_id, message_id=status_msg.message_id if status_msg else None,
                    prompt=prompt, saved_input_images=saved_input_images, is_video=is_video, priority=priority
                )

            # Submit Task
            task_id = await TaskService._submit_generic_task(
                task_type, prompt, saved_input_images, negative_prompt, is_video, priority
            )
            if registry_task_id and task_id:
                await TaskRegistry.update_backend_task_id(registry_task_id, task_id)

            # Monitor Progress
            final_info = await TaskService._monitor_task_progress(
                task_id, status_msg, is_video, image_service.monitor_progress, identity_str=identity_str, user_group=user_group
            )

            if final_info:
                media_bytes, full_output_path = (
                    await TaskService._handle_task_completion(
                        context,
                        chat_id,
                        user_id,
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
                    )
                )
            else:
                if deduct_quota:
                    await permission_service.increment_quota(user_id, cost=-cost, username=username, task_type="refund")
                await robust_send_message(
                    context.bot, chat_id, "❌ 生成完成但未获取到文件路径，已退还灵石"
                )

        except Exception as e:
            user_logger.logger.error(
                f"Error in process_generation_task for user {user_id}: {e}",
                exc_info=True,
            )
            if deduct_quota:
                await permission_service.increment_quota(user_id, cost=-cost, username=username, task_type="refund")
            await robust_send_message(context.bot, chat_id, f"❌ 出错了：{e}，已退还灵石")

        finally:
            if registry_task_id:
                await TaskRegistry.remove_task(registry_task_id)
            await redis_client.decrement_user_concurrency(user_id)
                
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
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Generic handler for video generation tasks to reduce code duplication.
        """
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.full_name
        
        # 1. Check active tasks limit
        active_tasks = await redis_client.increment_user_concurrency(user_id)
        from src.constants import MAX_CONCURRENT_TASKS
        if active_tasks > MAX_CONCURRENT_TASKS:
            await redis_client.decrement_user_concurrency(user_id)
            await robust_send_message(context.bot, chat_id, f"⚠️ 您当前已有 {MAX_CONCURRENT_TASKS} 个任务正在处理中，请等待其中一个完成后再试！")
            if cleanup:
                TaskService._cleanup_files([image_path])
            return None, None
        
        user_group = await permission_service.get_user_group(user_id)
        identity_str = await permission_service.get_user_identity(user_id)
        
        from src.constants import DEFAULT_RESOLUTION, DEFAULT_DURATION, RESOLUTION_COST, DURATION_MULTIPLIER, DURATION_FRAMES

        # Get resolution and duration from user_data
        resolution = context.user_data.get('custom_video_resolution', DEFAULT_RESOLUTION)
        duration = context.user_data.get('custom_video_duration', DEFAULT_DURATION)

        # Fallback safely (1024p + 10s is too heavy)
        if resolution == "1024p" and duration == "10s":
            resolution = "720p"
            context.user_data['custom_video_resolution'] = "720p"
            await robust_reply_text(update.effective_message, "⚠️ 检测到非法配置(1024p+10s)，已自动降级为720p+10s。")

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

        user_logger = UserLogger(user_id, username)

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
            # Pre-flight check removed as backend can upscale
            if not await permission_service.check_quota(update, context, cost=cost):
                await robust_delete_message(msg)
                return None, None

            priority = await permission_service.calculate_user_priority(user_id)

            await permission_service.increment_quota(user_id, cost=cost, username=username, task_type=mode)
            registry_task_id = await TaskRegistry.add_task(
                user_id, username, cost, mode, chat_id=chat_id, message_id=msg.message_id if msg else None,
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
                        user_id,
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
                        caption=f"✅ {mode_name}生成完成",
                    )
                )
            else:
                await permission_service.increment_quota(user_id, cost=-cost, username=username, task_type="refund")
                await robust_send_message(
                    context.bot, chat_id, "❌ 生成完成但未获取到任务信息，已退还灵石"
                )

        except Exception as e:
            logger.error(f"Error in {mode} task for user {user_id}: {e}", exc_info=True)
            await permission_service.increment_quota(user_id, cost=-cost, username=username, task_type="refund")
            await robust_send_message(context.bot, chat_id, f"❌ 出错了：{e}，已退还灵石")
        finally:
            if registry_task_id:
                await TaskRegistry.remove_task(registry_task_id)
            await redis_client.decrement_user_concurrency(user_id)
                
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
    ):
        return await TaskService._process_video_task_template(
            update,
            context,
            image_path,
            MODE_BLOWJOB,
            "blowjob",
            "undress blowjob",
            cleanup,
        )

    @staticmethod
    async def process_undress_tongue_task(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        image_path: str,
        cleanup: bool = True,
    ):
        return await TaskService._process_video_task_template(
            update,
            context,
            image_path,
            MODE_UNDRESS_TONGUE,
            "undress_tongue",
            "undress and show tongue",
            cleanup,
        )

    @staticmethod
    async def process_doggy_style_task(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        image_path: str,
        cleanup: bool = True,
    ):
        return await TaskService._process_video_task_template(
            update,
            context,
            image_path,
            MODE_DOGGY_STYLE,
            "doggy_style",
            "doggy style sex",
            cleanup,
        )

    @staticmethod
    async def process_closeup_blowjob_task(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        image_path: str,
        cleanup: bool = True,
    ):
        return await TaskService._process_video_task_template(
            update,
            context,
            image_path,
            MODE_CLOSEUP_BLOWJOB,
            "closeup_blowjob",
            "closeup blowjob sex",
            cleanup,
        )

    @staticmethod
    async def process_perfect_video_insert_task(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        image_path: str,
        cleanup: bool = True,
    ):
        return await TaskService._process_video_task_template(
            update,
            context,
            image_path,
            MODE_PERFECT_VIDEO_INSERT,
            "perfect_video_insert",
            "missionary sex",
            cleanup,
        )

    @staticmethod
    async def process_custom_video_task(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        prompt: str,
        image_path: str,
        cleanup: bool = True,
    ):
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        # 1. Check active tasks limit
        active_tasks = await redis_client.increment_user_concurrency(user_id)
        from src.constants import MAX_CONCURRENT_TASKS
        if active_tasks > MAX_CONCURRENT_TASKS:
            await redis_client.decrement_user_concurrency(user_id)
            await robust_send_message(context.bot, chat_id, f"⚠️ 您当前已有 {MAX_CONCURRENT_TASKS} 个任务正在处理中，请等待其中一个完成后再试！")
            if cleanup and image_path:
                TaskService._cleanup_files([image_path])
            return None, None
            
        username = update.effective_user.username or update.effective_user.full_name
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

        user_logger = UserLogger(user_id, username)

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
                
            # Pre-flight check removed as backend can upscale
            if not await permission_service.check_quota(update, context, cost=cost):
                await robust_delete_message(msg)
                return None, None

            priority = await permission_service.calculate_user_priority(user_id)
            identity_str = await permission_service.get_user_identity(user_id)
            user_group = await permission_service.get_user_group(user_id)

            await permission_service.increment_quota(user_id, cost=cost, username=username, task_type=mode)
            registry_task_id = await TaskRegistry.add_task(
                user_id, username, cost, mode, chat_id=chat_id, message_id=msg.message_id if msg else None,
                prompt=prompt, saved_input_images=[saved_input_image], is_video=True, priority=priority
            )
            await robust_edit_text(msg, "⏳ 正在生成视频，请耐心等待...")

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
                    user_id,
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
                    caption="✅ 自定义视频生成完成",
                )
            else:
                await permission_service.increment_quota(user_id, cost=-cost, username=username, task_type="refund")
                await robust_send_message(
                    context.bot, chat_id, "❌ 生成完成但未获取到任务信息，已退还灵石"
                )
                return None, None
        except Exception as e:
            logger.error(
                f"Error in custom video task for user {user_id}: {e}", exc_info=True
            )
            await permission_service.increment_quota(user_id, cost=-cost, username=username, task_type="refund")
            await robust_send_message(context.bot, chat_id, f"❌ 出错了：{e}，已退还灵石")
            return None, None
        finally:
            if registry_task_id:
                await TaskRegistry.remove_task(registry_task_id)
            await redis_client.decrement_user_concurrency(user_id)
            if cleanup:
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
    ):
        """Handle MODE_I2I_PRO requests"""
        from src.constants import MAX_CONCURRENT_TASKS, MODE_I2I_PRO, TASK_COSTS
        
        # 1. Check active tasks limit
        active_tasks = await redis_client.increment_user_concurrency(user_id)
        if active_tasks > MAX_CONCURRENT_TASKS:
            await redis_client.decrement_user_concurrency(user_id)
            await robust_send_message(context.bot, chat_id, f"⚠️ 您当前已有 {MAX_CONCURRENT_TASKS} 个任务正在处理中，请等待其中一个完成后再试！")
            return

        cost = TASK_COSTS.get(MODE_I2I_PRO, 3)
        mode = MODE_I2I_PRO
        user_logger = UserLogger(user_id, username)
        
        # Validate images
        if not images or len(images) == 0:
            await redis_client.decrement_user_concurrency(user_id)
            await robust_send_message(context.bot, chat_id, "❌ 请先发送参考图片。")
            return
            
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
            priority = await permission_service.calculate_user_priority(user_id)
            identity_str = await permission_service.get_user_identity(user_id)
            user_group = await permission_service.get_user_group(user_id)

            await permission_service.increment_quota(user_id, cost=cost, username=username, task_type=mode)
            registry_task_id = await TaskRegistry.add_task(
                user_id, username, cost, mode, chat_id=chat_id, message_id=msg.message_id if msg else None,
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
                    context, chat_id, user_id, prompt, mode, task_id, [saved_input_image], user_logger,
                    is_video=False, send_result=True, reply_markup=None, status_msg=msg, delete_status=True,
                    caption=f"🌟 幻想换脸生成完成\n提示词：{prompt[:100]}..."
                )
            else:
                await permission_service.increment_quota(user_id, cost=-cost, username=username, task_type="refund")
                await robust_send_message(context.bot, chat_id, "❌ 生成完成但未获取到文件路径，已退还灵石")

        except Exception as e:
            user_logger.logger.error(f"Error in process_i2i_pro_task for user {user_id}: {e}", exc_info=True)
            await permission_service.increment_quota(user_id, cost=-cost, username=username, task_type="refund")
            await robust_send_message(context.bot, chat_id, f"❌ 出错了：{e}，已退还灵石")
        finally:
            if registry_task_id:
                await TaskRegistry.remove_task(registry_task_id)
            await redis_client.decrement_user_concurrency(user_id)
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
        user_id,
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
            )
            await permission_service.refresh_user_group(user_id)

            if send_result:
                keyboard = [
                    [
                        InlineKeyboardButton("👍", callback_data="rate_like"),
                        InlineKeyboardButton("👎", callback_data="rate_dislike")
                    ]
                ]
                if ENABLE_PUBLIC_SHARE:
                    keyboard.insert(
                        0,
                        [InlineKeyboardButton("公开", callback_data="public_share_request")]
                    )
                default_markup = InlineKeyboardMarkup(keyboard)
                sent_msg = await robust_send_video(
                    context.bot,
                    chat_id,
                    video=media_bytes,
                    caption=caption or "✅ 视频生成完成",
                    reply_markup=reply_markup or default_markup,
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
            )
            await permission_service.refresh_user_group(user_id)

            if send_result:
                keyboard = [
                    [
                        InlineKeyboardButton("👍", callback_data="rate_like"),
                        InlineKeyboardButton("👎", callback_data="rate_dislike")
                    ]
                ]
                if ENABLE_PUBLIC_SHARE:
                    keyboard.insert(
                        0,
                        [InlineKeyboardButton("公开", callback_data="public_share_request")]
                    )
                default_markup = InlineKeyboardMarkup(keyboard)
                sent_msg = await robust_send_photo(
                    context.bot,
                    chat_id,
                    photo=media_bytes,
                    caption=caption or "✅ 用户生成内容投稿",
                    reply_markup=reply_markup or default_markup,
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
