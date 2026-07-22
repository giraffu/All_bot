# 独立客服 Bot

入口为 `support_bot.main`，正式运行服务为 `support-bot`，只使用 `SUPPORT_BOT_TOKEN`。它是独立 Telegram polling 服务：不得与任何其他进程共用 Token，也不读取生成维护标记、不提交生成任务。

用户可选择“充值问题、Bug反馈、意见反馈、商业合作”四类工单；点击分类只准备或切换当前工单并返回针对性的内容提示，不写入空白用户消息。用户也可直接发送未分类留言。消息写入 `support_tickets` 与 `support_messages`；图片和文件通过 Telegram Local API 的独立文件服务下载，再写入私有 R2 `support/<telegram-user-id>/<message-id>/...` 路径。对象地址不公开，仅由已认证的 Dashboard 生成短时访问链接；图片在工单时间线显示为可点击预览，其他文件显示下载链接。管理员可在该页处理、备注和回复。

首次正式更新使用显式组合模块 `support-platform`，只包含 `dashboard-backend`、`dashboard-frontend` 与 `support-bot`。`e7f8a9b0c1d2` 仅创建两张新表及其索引/约束；`f8a9b0c1d2e3` 只扩展工单分类约束以允许 `business`，升级不改写现有工单，降级时才把 `business` 归为 `uncategorized`。发布器只在候选 main 中这些迁移内容与 `deploy/release-policy.yml` 的精确 SHA256 相符时，才允许 `promote --modules support-platform --no-maintenance --confirm-db-upgrade --confirm-prod` 在备份和单 Alembic head 检查后执行在线升级。任何其它迁移或内容漂移继续 fail closed。

该组合不部署测试环境、不进入前向维护窗口，滚动替换 Dashboard 前后端并首次启动客服 Bot；事务会核对全部非目标正式容器的 image 与启动时间不变。`SUPPORT_BOT_TOKEN` 同时投影给客服 Bot 与 Dashboard Backend，仅配置在受控正式环境中，绝不写入仓库或发布状态。
