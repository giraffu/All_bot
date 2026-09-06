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
- `src/bot_main.py` 只作 composition root；handler 顺序集中在
  `main_bot_handler_registry.py`，所有 ConversationHandler 先于全局 callback fallback。
- 主 Bot 更新通过 `PerUserUpdateProcessor` 保证同用户严格串行、不同用户
  有界并发；禁止退回 PTB 全局单通道或无键 `concurrent_updates(True)`。
  QQCC 官方 Bot 的并发边界按其专项技能执行。
- 主 Bot 后台协程经 `main_bot_task_supervisor.py` 持有；shutdown 先 cancel/await，
  再关闭 Redis。
- 语言切换同时更新数据库和 Redis 缓存，不能只替换当前键盘文案。

## 3. FSM 与 service 分层

- handler/FSM 只负责 Telegram 状态、素材、消息与清理；归一、提交计划、payload、
  历史和扩展链放 application service，具体入口按专项文档定位。
- Quick Video：entry service 管入口规则，entry view 管展示，FSM 传 I/O。
- `Update` 不进入 core；FSM 转为内部 request/context 后调用公开 facade。
- plan 参数显式传给后台 actor/service，不借顶层 `context.user_data` 隐式传递。
- 视频档位权限由 `telegram_video_permission_service.py` 解析为不可变快照。

## 4. 对话与文件不变量

- FSM 入口优先使用 `I18nFilter` 或统一菜单路由；FSM-only key、特殊翻译和
  旧键盘 alias 维护在 `menu_route_registry.py`；状态显式返回下一态或 END，常用
  timeout 为 300 秒，变更时同步测试和专项文档。
- 主菜单可从任意 FSM 打断；结束、失败、取消或超时均清理状态和临时文件，下载
  失败保留安全重试态，大文件不阻塞 update handler。
- callback 的正常、拒绝、过期和未知分支都先 answer；长任务进入受控后台 task，
  后台失败仍清理并通知用户。
- 菜单显隐只改变新键盘，不删除兼容 route/callback 或 fail-closed 入口。

## 5. Bot 隔离

- 各 Bot 隔离进程、handler、配置和日志，同 token 不双 polling；QQCC、审核群、
  普通群、客服与 Observer 入口以各专项文档为准，不跨入口导入。
- token 不回显或记录；通知 token 仅作已授权 outbound，旧入口只安全跳转/拒绝。

## 6. 维护与运行时红线

- Bot 生成入口在维护 marker 生效时停止新提交并提示用户；不自行清除 marker。
- 频道同步使用 `REQUIRED_CHANNEL_ID`，缺失时 fail closed；展示链接不能替代
  `getChatMember` ID。callback/ConversationHandler 顺序是公开契约，前缀不得冲突。
- FSM 不复制计费、任务类型、workflow、R2 或数据库事务；新 seam 先做职责判断。
- 历史按钮只兼容路由或明确拒绝，不代表继续开放能力，也不静默改投其它任务。

## 7. 最小验证

- 菜单/FSM：任意状态退出、明确回复、END、i18n/旧文本安全路由与文件清理。
- callback：注册、前缀优先级，正常/拒绝/未知都 answer。
- 并发：同用户串行、不同用户有界并发，取消后不阻塞后续 update。
- 装配/生命周期：registry 顺序、后台 task 完成移除、shutdown cancel/await。
- service/任务：显式 plan seam；成功、额度不足、维护、取消限制和终态展示。
- Bot 隔离：token、handler、polling/webhook；交付列出 focused tests 和环境状态。
