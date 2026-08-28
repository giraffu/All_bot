from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from observer_bot.report_service import due_report_windows

logger = logging.getLogger(__name__)


async def _is_admin_private(update, runtime_config_provider) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    runtime_config = await runtime_config_provider.get()
    return bool(
        user is not None
        and chat is not None
        and str(chat.type) == "private"
        and int(user.id) in runtime_config.admin_chat_ids
    )


async def handle_start(update, context) -> None:
    if not await _is_admin_private(
        update, context.application.bot_data["runtime_config_provider"]
    ):
        return
    await update.effective_message.reply_text(
        "Observer Bot 已运行。\n/status 查看队列\n/report [daily|weekly|monthly] 生成最近报告"
    )


async def handle_status(update, context) -> None:
    if not await _is_admin_private(
        update, context.application.bot_data["runtime_config_provider"]
    ):
        return
    try:
        snapshot = await context.application.bot_data["queue_client"].fetch()
        await update.effective_message.reply_text(
            "AllBot 队列状态"
            f"\n待处理：{snapshot.queue_size}"
            f"\n最长等待：{snapshot.max_wait_seconds} 秒"
            f"\n可接单 Worker：{snapshot.accepting_workers}"
        )
    except Exception:
        logger.exception("manual observer queue status failed")
        await update.effective_message.reply_text("暂时无法读取 Central 队列状态。")


async def handle_report(update, context) -> None:
    settings = context.application.bot_data["settings"]
    runtime_config_provider = context.application.bot_data["runtime_config_provider"]
    if not await _is_admin_private(update, runtime_config_provider):
        return
    requested = str(context.args[0]).lower() if context.args else "daily"
    windows = {
        item.report_type: item
        for item in due_report_windows(
            datetime.now(timezone.utc),
            timezone_name=settings.timezone,
            report_hour=settings.report_hour,
        )
    }
    if requested not in windows:
        await update.effective_message.reply_text(
            "报告类型只支持 daily、weekly 或 monthly。"
        )
        return
    runtime_config = await runtime_config_provider.get()
    if not runtime_config.report_enabled(requested):
        await update.effective_message.reply_text("该类型报告当前已在管理后台关闭。")
        return

    await update.effective_message.reply_text("已开始生成报告，完成后会发给管理员。")

    async def generate() -> None:
        result = await context.application.bot_data["report_service"].generate(
            windows[requested]
        )
        if result is None:
            await update.effective_message.reply_text("该周期报告已经生成，无需重复执行。")

    context.application.create_task(generate(), update=update)


async def queue_monitor_job(context) -> None:
    runtime_config = await context.application.bot_data[
        "runtime_config_provider"
    ].get()
    if not runtime_config.queue_alerts_enabled:
        return
    try:
        await context.application.bot_data["queue_monitor"].poll()
    except Exception:
        logger.exception("observer queue monitor job failed")


async def report_tick_job(context) -> None:
    settings = context.application.bot_data["settings"]
    windows = due_report_windows(
        datetime.now(timezone.utc),
        timezone_name=settings.timezone,
        report_hour=settings.report_hour,
    )
    runtime_config = await context.application.bot_data[
        "runtime_config_provider"
    ].get()
    for window in windows:
        if not runtime_config.report_enabled(window.report_type):
            continue
        try:
            await context.application.bot_data["report_service"].generate(window)
        except Exception:
            logger.exception("observer report job failed run_key=%s", window.run_key)


async def retention_job(context) -> None:
    settings = context.application.bot_data["settings"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.message_retention_days)
    try:
        deleted = await context.application.bot_data["repository"].delete_messages_before(
            cutoff
        )
        logger.info("observer retention completed deleted=%s", deleted)
    except Exception:
        logger.exception("observer retention job failed")
