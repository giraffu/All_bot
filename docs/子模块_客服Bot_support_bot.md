# 独立客服 Bot

入口为 `support_bot.main`，正式运行服务为 `support-bot`，只使用 `SUPPORT_BOT_TOKEN`。它是独立 Telegram polling 服务：不得与任何其他进程共用 Token，也不读取生成维护标记、不提交生成任务。

用户消息写入 `support_tickets` 与 `support_messages`；附件写入私有 R2 `support/<telegram-user-id>/<message-id>/...` 路径，仅由已认证的 Dashboard 生成短时访问链接。管理员在 Dashboard 的“客服工单”页处理、备注和回复。

正式更新走 `scripts/release.py promote --modules support-bot --confirm-prod`。该模块不需要测试环境或维护窗口，但仍需 main 可达 SHA、成功 CI、精确镜像及每次生产确认。Token 仅配置在受控环境变量，泄露后立即通过 BotFather 轮换。
