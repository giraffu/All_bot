---
name: "allbot-tg-fsm"
description: "处理 Telegram FSM、全局菜单退出、callback 注册、更新并发、临时文件、语言同步与独立 Bot 边界。"
---

# AllBot Telegram FSM

修改 Bot 对话流、callback、菜单、文件下载/清理、polling runtime 或语言切换
时必须加载本技能。卡死/转圈/下载失败叠加 `allbot-diagnosing-bugs`，行为
改动叠加 `allbot-tdd`，QQCC 叠加 `allbot-qqcc-lazy-bot`。

## 1. 按需阅读

| 场景 | 必读事实源 |
| --- | --- |
| 主 Bot FSM、菜单、callback、文件 | `docs/子模块_交互状态机_fsm_handlers.md` |
| Telegram Local API/file endpoint | `docs/子模块_Telegram本地API与文件代理_tg_local_api.md` |
| QQCC 官方/私有 Bot | `allbot-qqcc-lazy-bot` |
| 付费群审核 Bot | `docs/子模块_付费群审核Bot_paid_group_guard_bot.md` |
| 独立普通群管理 Bot | `docs/子模块_独立群管理Bot_standalone_group_manage_bot.md` |
| 独立客服 Bot、工单草稿与附件 | `docs/子模块_客服Bot_support_bot.md` |
| Observer Bot、授权群采集与管理员命令 | `allbot-observer-bot` |
| 任务提交与 continuation | `allbot-task-engine` |

具体功能按钮、历史 callback、模型和任务类型枚举只保留在专项文档及代码路由，
不复制成长 Skill。

## 2. 稳定 seam

- 全局菜单识别由 `menu_route_registry`、prompt router、reverse map 和
  `is_global_menu_command(...)` 组合完成。任何文字接收状态先经过统一黑盒
  退出判断，不能散落硬编码中文菜单。
- callback 使用前缀注册、长度降序匹配与统一 `safe_answer_query(...)`
  兜底。拆分模块时主入口必须导入注册子模块；每个 callback 都要应答。
- 临时文件统一通过 `src/services/fsm_temp_file_service.py` 下载和清理；
  `cleanup_fsm_user_data(...)` 覆盖嵌套路径、顶层缓存、正常结束、取消、
  超时和异常。
- Telegram Local API/Poll/旧 payload 兼容与语言注入集中在
  `src/services/telegram_runtime_bootstrap.py`，主 Bot 与 QQCC 共用 bootstrap，
  但不共用 handler 集。
- 主 Bot 更新通过 `PerUserUpdateProcessor` 保证同用户严格串行、不同用户
  有界并发；禁止退回 PTB 全局单通道或无键 `concurrent_updates(True)`。
  QQCC 官方 Bot 的并发边界按其专项技能执行。
- 语言切换同时更新数据库和 Redis 缓存，不能只替换当前键盘文案。

## 3. FSM 与 service 分层

- handler/FSM 只负责 Telegram 状态、素材、消息与清理；归一、提交计划、payload、
  历史和扩展链放 application service，具体入口按专项文档定位。
- `Update` 不进入 core；FSM 转为内部 request/context 后调用公开 facade。
- plan 参数显式传给后台 actor/service，不借顶层 `context.user_data` 隐式传递。

## 4. 对话与文件不变量

- FSM 入口优先使用 `I18nFilter` 或统一菜单路由；FSM-only key、特殊翻译和
  旧键盘 alias 维护在 `menu_route_registry.py`。
- 每个状态显式返回下一状态或 `ConversationHandler.END`。当前常用 timeout
  基线是 300 秒；改变时同步测试和专项文档。
- 主菜单在任意 FSM 内都能安全打断，并给出明确回复；退出必须清理 `user_data`
  和已下载文件。
- callback 即使拒绝、过期或未知也必须快速 answer，避免客户端持续转圈。
- 文件下载失败、取消或超时时清理已写入的半文件，并保留可安全重试的状态。
  大文件不得长时间阻塞 update handler。
- 长时间生成/监视通过受控 background task 脱离 Telegram update；后台失败
  仍要清理临时文件并通知用户，不能在 media handler 同步等终态。
- 菜单显隐只影响展示，不能删除仍需兼容的 prompt route、旧消息 callback
  或安全 fail-closed 入口。

## 5. Bot 隔离

- 各 Bot 隔离 token、进程、handler、配置和日志；同一 token 不得双 polling。
- QQCC handler/webhook、付费群 join request、普通群 `message`、客服工单和
  Observer 采集边界分别以专项 Skill/文档为准，不互相导入入口。
- token 不回显、不记录；旧入口只安全跳转/拒绝，兼容由所属 Skill 管理。

## 6. 维护与运行时红线

- Bot 生成入口在维护 marker 生效时停止新提交并提示用户；不自行清除 marker。
- 主 Bot 频道成员同步必须使用 `REQUIRED_CHANNEL_ID`，展示链接不能替代
  `getChatMember` 所需 ID；缺配置由发布契约 fail closed。
- callback/ConversationHandler 顺序是公开契约；新增前缀先检查冲突。
- 不在 FSM 中复制计费、任务类型、workflow、R2 或数据库事务逻辑；需要新
  seam 时先用 `allbot-codebase-design` 判断职责位置。
- 不把历史按钮兼容理解为继续开放产品能力。旧入口应兼容路由或明确拒绝，
  不能静默提交不同任务。

## 7. 最小验证

- 菜单/FSM：任意状态退出、明确回复、END、i18n/旧文本安全路由与文件清理。
- callback：注册、前缀优先级，正常/拒绝/未知都 answer。
- 并发：同用户串行、不同用户有界并发，取消后不阻塞后续 update。
- service/任务：显式 plan seam；成功、额度不足、维护、取消限制和终态展示。
- Bot 隔离：token、handler、polling/webhook；交付列出 focused tests 和环境状态。
