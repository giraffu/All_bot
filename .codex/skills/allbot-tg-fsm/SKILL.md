---
name: "allbot-tg-fsm"
description: "处理 Telegram FSM、全局菜单黑盒退出、callback 路由注册、临时文件下载清理与语言切换同步。开发或修改 Bot 对话流和文件处理时必须调用本技能。"
---

# AllBot Telegram 交互状态机 (TG FSM)

本技能定义 Telegram Bot 特有的复杂交互逻辑，覆盖多步 FSM、主菜单打断、callback 注册路由、文件下载/清理与语言切换的运行时约束。

## 1. 模块功能描述
- **多语言精准路由**：FSM 入口仍可使用 `I18nFilter`，但全局菜单识别已扩展为 `prompt_router + GLOBAL_REVERSE_MAP + is_global_menu_command(...)` 组合。
- **FSM 黑盒退出机制**：在任何文字接收入口，优先用 `is_global_menu_command(...)` 判断是否应退出当前流程，而不是散落硬编码菜单判断。
- **Callback 注册路由**：回调处理依赖 `register_callback` 前缀注册、长度降序匹配与统一 `safe_answer_query` 兜底，修改 callback 拆分时必须维护这套契约。
- **临时文件生命周期**：常规 FSM 文件流已优先收口到 `fsm_temp_file_service.py`，负责目录创建、下载与清理；大文件 Monkey Patch 不是唯一主路径。
- **语言切换同步**：语言切换不只是菜单文案变化，还涉及 DB + Redis 双缓存同步。
- **独立付费群审核 Bot**：`paid_group_guard_bot/` 使用独立 token，只订阅 `chat_join_request`，按订单资格审核付费群入群申请；不要把它接入主业务 FSM 或复用主业务 `BOT_TOKEN`。

## 2. 输入输出规范
### FSM 状态流转
- **入口**：优先使用 `I18nFilter(...)` 或统一菜单路由，而不是硬编码中文正则。
- **状态处理**：文字输入分支必须优先经过 `is_global_menu_command(...)` 黑盒退出判断。
- **超时**：当前主 FSM 通常以 `300` 秒 `conversation_timeout` 为基线；若改动超时值，必须同步文档与测试。
- **退出**：显式返回 `ConversationHandler.END`，并清理 `user_data` / 临时文件。

### Callback Query
- **输入**：注册前缀、query data、上下文状态
- **输出**：对应 handler 返回值与必要的 `query.answer()` / `safe_answer_query(...)`
- **红线**：任何 callback handler 都不能遗漏应答，否则客户端会持续转圈。

## 3. 使用示例 (最佳实践)
```python
async def receive_prompt(update, context):
    text = (update.message.text or "").strip()
    if is_global_menu_command(text):
        return await unexpected_input(update, context)

    # 继续处理正常输入
    ...


def build_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[MessageHandler(I18nFilter("menu.custom_video"), start_fsm)],
        states={
            WAITING_PROMPT: [
                MessageHandler((filters.TEXT | filters.COMMAND), receive_prompt),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,
    )
```

## 4. 核心红线
- Web API 严禁直接消费 Telegram 表示层逻辑；Bot 任务提交通常走 `bot_task_service` / 各 FSM entrypoint / `run_bot_task_application(...)`。
- 付费群审核 Bot 必须和主业务 Bot token 隔离；同一个 token 不得同时被两个 polling 进程使用。
- FSM 内不得依赖硬编码菜单词做全局退出判断，必须走统一菜单路由。
- 临时文件、下载目录和清理逻辑应优先下沉到服务层，避免各 FSM 重复拼装。
- callback 路由拆分时必须确保主入口导入子模块触发注册，不能因加载顺序拿到空路由表。
- SCAIL-2 Bot 的“视频生视频”二级菜单支持测试 Bot 与正式 Bot，但正式展示必须跟随 SCAIL-2 正式 runtime 发布闸门；`scail2_video_fsm` 收集参考图、驱动视频、正向提示词和 5s/8s 时长，负面提示词使用默认值，驱动视频上限 40MB，原“视频换脸”FSM 只移动到该二级菜单内并保持原业务逻辑。正式发布维护窗口内，Bot 生成 FSM 应尊重 `/app/GENERATION_MAINTENANCE` 或全局 `/app/MAINTENANCE`，提示维护并停止新提交。

## 5. 边界条件处理
- **`user_data` 残留**：FSM 正常结束、异常退出、超时三种场景都要清理临时状态。
- **主菜单打断**：若用户在 FSM 中点击主菜单，应退出当前流程并返回明确提示，避免卡死。
- **大文件处理**：若仍使用 Local API / Monkey Patch 路径，需保证 HTTP 下载失败时有清晰错误日志与用户提示。
- **PTB Warning**：`ConversationHandler` 参数若会触发框架级 warning，应先确认是否属于既有契约，再决定改运行时配置还是测试显式处理预期 warning。

## 6. 测试要求
- 覆盖 FSM 意外菜单拦截与超时退出。
- 覆盖 callback 路由注册与未命中前缀的统一兜底。
- 覆盖临时文件下载/清理服务的行为契约。
- 覆盖 `paid_group_guard_bot` 的资格命中、未命中保留待审/拒绝、目标群过滤与 dry-run 行为。
- 当 FSM 使用 PTB 已知 warning 配置时，测试应显式说明该 warning 是否属于预期行为。
