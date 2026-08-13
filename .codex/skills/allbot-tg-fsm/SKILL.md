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

- handler/FSM 负责 Telegram 状态、素材接收、额度提示、消息和清理；输入
  归一、提交计划、payload、历史恢复与扩展链放 application service。
- quick image 计划位于 `quick_image_submission_service.py`；quick video
  位于 `quick_video_submission_service.py`。
- 主 Bot 高级视频计划位于 `advanced_video_submission_service.py`，设置
  view-model/callback 解析位于 `advanced_video_settings_view_service.py`。
- LTX 扩展/拼接历史准备位于 `ltx_video_extension_service.py`；Wan22
  扩展/重生成/拼接位于 `wan22_video_v2_extension_service.py`。
- Telegram `Update` 不进入 core。FSM 把平台输入转换为内部 request/context，
  再调用公开 task application/facade。
- 提交参数由 plan 显式传入 actor/application service，不能借用顶层
  `context.user_data` 作为后台任务隐式参数桥。

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

- 主业务 Bot、QQCC Bot、付费群审核 Bot、客服 Bot 使用不同 token；相同 token
  不能由两个 polling 进程同时使用。
- QQCC 只注册 quick image/video、market 和最小 callback，不导入主 Bot 高级、
  支付或 Gallery handler；私有 Bot 用 webhook。private worker 的官方 token
  只做会员 checker，不启动 `getUpdates`。
- 私有 Bot 申请 token 消息先尽力删除；不得回显、记录或放入审计 metadata。
- 付费群审核 Bot 只处理目标群 join request 与轻量消息治理，不接入生成 FSM
  或复用主 Bot token。
- 普通群管理 Bot 只订阅 `message`，不处理 `chat_join_request`，并隔离 token、
  配置、日志和后台 API。
- 客服 Bot 只收集工单草稿和私有附件，不读取生成维护标记、不提交生成任务，
  也不把未提交草稿写入数据库。
- 主 Bot 旧 QQCC 入口只跳转或提示未配置；callback 兼容由 QQCC Skill 管理。

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

- 全局菜单：任意状态打断、明确回复、END 与临时文件清理。
- callback：注册导入、前缀优先级、正常/拒绝/未知均 answer。
- 并发：同用户不重叠、不同用户可并发、全局上限、取消等待任务后不阻塞
  后续 update。
- 文件：下载成功、超时、异常、半文件和所有退出路径清理。
- service seam：handler 只做 Telegram 编排，payload/设置/历史由对应 service；
  plan 参数显式传递。
- Bot 隔离：token、handler 集、polling/webhook、官方 checker callable。
- 菜单配置与 i18n：默认/归一化、排序分行、显隐、能力 gate、读取失败回退、
  旧文本仍安全路由。
- 任务：提交成功、额度不足、维护、不可取消 continuation、完成/失败展示。
- 交付说明触达 Bot、入口、状态/callback、临时文件、任务/计费影响和 focused
  tests；不把代码或本地测试描述成线上已生效。
