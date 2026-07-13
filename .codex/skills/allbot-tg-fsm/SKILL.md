---
name: "allbot-tg-fsm"
description: "处理 Telegram FSM、全局菜单黑盒退出、callback 路由注册、临时文件下载清理与语言切换同步。开发或修改 Bot 对话流和文件处理时必须调用本技能。"
---

# AllBot Telegram 交互状态机 (TG FSM)

本技能定义 Telegram Bot 特有的复杂交互逻辑，覆盖多步 FSM、主菜单打断、callback 注册路由、文件下载/清理与语言切换的运行时约束。

涉及 FSM 卡死、callback 转圈、文件下载失败或语言路由异常时，叠加 `allbot-diagnosing-bugs`；新增对话流或修复回归时，叠加 `allbot-tdd` 通过 handler / callback focused tests 锁定行为。

## 1. 模块功能描述
- **多语言精准路由**：FSM 入口仍可使用 `I18nFilter`，但全局菜单识别已扩展为 `menu_route_registry + prompt_router + GLOBAL_REVERSE_MAP + is_global_menu_command(...)` 组合。
- **FSM 黑盒退出机制**：在任何文字接收入口，优先用 `is_global_menu_command(...)` 判断是否应退出当前流程，而不是散落硬编码菜单判断。
- **Callback 注册路由**：回调处理依赖 `register_callback` 前缀注册、长度降序匹配与统一 `safe_answer_query` 兜底，修改 callback 拆分时必须维护这套契约。
- **临时文件生命周期**：常规 FSM 文件流已优先收口到 `fsm_temp_file_service.py`，负责目录创建、下载与清理；`cleanup_fsm_user_data(...)` 除了清理 `*_data` 内路径，也会清理随机换脸“再来一张”使用的顶层 `last_face_image` 临时缓存；Telegram Local API / Poll 兼容 / 语言注入由 `telegram_runtime_bootstrap.py` 统一安装，避免主 Bot 与 QQCC Bot 重复补丁。
- **语言切换同步**：语言切换不只是菜单文案变化，还涉及 DB + Redis 双缓存同步。
- **独立付费群审核 Bot**：`paid_group_guard_bot/` 使用独立 token，订阅目标群 `chat_join_request` 与普通 `message` update；入群资格只读查订单/修为，普通消息只做轻量群管理（非管理员链接、违禁词、结构化日志），不要把它接入主业务 FSM 或复用主业务 `BOT_TOKEN`。
- **QQCC 懒人 Bot**：`qqcc_bot/` 是独立简化 polling 服务，只注册 quick image/video FSM 和最小菜单；修改它时必须叠加 `allbot-qqcc-lazy-bot`。
- **QQCC 私有 Bot 申请**：`qqcc_bot/private_bot_fsm.py` 只注册在官方 QQCC。收到 token 后必须先尽力删除原消息，禁止回显、日志或审计 metadata；验证成功即自动开通，无审核，一个 owner 只能绑定一个 Telegram Bot。私有 Application 不展示申请入口。
- **QQCC 私有 Bot 会员检查**：租户 Application 不得用自己的 Bot 查询官方 QQCC 频道；private worker 注入进程共享的官方 QQCC membership checker，只做成员查询、不启动 polling，进程内对同用户 singleflight，Redis 在租户间共享正向 60 秒、负向 5 秒缓存。
- **QQCC 场景示范媒体**：`qdraw_scene:*` / `qfilter_scene:*` / `qvid_scene:*` 进入 FSM 时，先调用 `qqcc_demo_media_service` 发送场景输入/输出示范媒体，再发送上传素材文字提示。发送优先使用与当前 Bot ID 对应的 Telegram `file_id`；无缓存或缓存失效时使用 R2 短签并回写新 file_id。示范发送失败只能降级为文字提示，不得卡住 callback 或阻断 FSM。
- **已迁移主 Bot 旧懒人入口**：主 Bot 不得恢复旧懒人入口任务提交；旧 `menu.video_edit` / `menu.video_edit_*`、`qqcc.menu.ai_draw`、`qqcc.menu.ai_filter`、`qqcc.menu.quick_faceswap`、`快速脱衣` / `快速自慰` 和主 Bot `qvid_*` 残留入口只能回复 QQCC 懒人 Bot inline 跳转或入口未配置提示。QQCC Bot 自身 `qdraw_scene:*`、`qfilter_scene:*`、`qvid_scene:*` 和旧 `qvid_mode:*` 兼容不受影响。
- **Quick Image 提交 service**：`quick_image_fsm.py` 与 `random_faceswap_again` callback 只负责 Telegram 状态流转、图片路径读取、额度检查、用户回复和清理；quick image 的提交计划、随机换脸模板过滤、QQCC AI绘图/AI滤镜场景 engine 分支、`draw -> draw...` / `draw -> filter` / 单步 `filter` 链与执行 payload 统一放在 `src/services/quick_image_submission_service.py`。旧 `WAIT_UNDRESS_METHOD` / 旧脱衣方式 callback 已清理，`i2i_draw` 只作为兼容 payload 保留。
- **Quick Video 提交 / 设置 seam**：`quick_video_fsm.py` 只负责 Telegram 状态流转、设置面板展示、额度检查、用户回复和清理；quick video 的提交计划、QQCC 场景 engine 分支、尾帧绘图链、执行 payload 以及 `set_res_*` / `set_dur_*` callback 状态归一统一放在 `src/services/quick_video_submission_service.py`。旧图生视频提交时由 plan 显式向 `process_video_task_template(...)` 传入 `resolution` / `duration`，不要再通过 `context.user_data["custom_video_resolution"]` / `custom_video_duration` / `mode` 做桥接。后续改 AI动图提交或设置逻辑应优先改该 service 并补 service focused tests。
- **高级视频提交 service**：主 Bot `image_to_video_fsm.py`、`wan22_video_v2_fsm.py`、`ltx_video_fsm.py` 只负责 Telegram 状态流转、素材接收、额度检查、用户回复和清理；旧图生视频/Wan22 v2/LTX 的提交计划、首尾帧 payload、分辨率/时长归一、LTX LoRA 多选和扩展链上下文统一放在 `src/services/advanced_video_submission_service.py`。LTX 提交必须由 plan 显式向 `process_ltx_video_task(...)` 传入 `resolution` / `duration` / `ltx_mode`，不要再通过 `context.user_data["ltx_video_resolution"]` / `ltx_video_duration` / `ltx_video_mode` 做后台任务参数桥接。该 service 不新增 task type、workflow 或 QQCC 能力。
- **高级视频设置 view service**：主 Bot 旧图生视频、Wan22 v2 与 LTX 的同屏设置面板 view-model/keyboards 和 settings callback data 到 `fsm_data` 的解析回写统一放在 `src/services/advanced_video_settings_view_service.py`；FSM wrapper 只处理 callback 状态并发送或编辑 Telegram 消息。修改设置按钮、费用展示、设置 callback 语义或 LTX 扩展直接续写提示时优先改该 service 并补 focused tests，不在 handler 里复制键盘拼装。
- **LTX 扩展/拼接 service**：`ltx_video_fsm.py` 的扩展入口和 `handlers/callbacks/ltx_video_callbacks.py` 的完成拼接 callback 只负责 Telegram 层交互；历史归属校验、`_ltx_context` 合并、尾帧下载、扩展 FSM seed 与完整拼接链 histories 加载统一放在 `src/services/ltx_video_extension_service.py`。
- **Wan22 AIO 链路扩展/重生成/拼接 service**：旧图生视频 `custom_video` / `video_lora` 与图生视频 v2 共用这套 Bot 链路。`wan22_video_v2_fsm.py` 的扩展/重生成入口和 `handlers/callbacks/wan22_video_v2_callbacks.py` 的重生成/完成拼接 callback 只负责 Telegram 层交互与任务启动；历史归属校验、`_wan22_context` 合并、上一段尾帧/当前段输入图下载、FSM seed 与完整拼接链 histories 加载统一放在 `src/services/wan22_video_v2_extension_service.py`。

## 2. 输入输出规范
### FSM 状态流转
- **入口**：优先使用 `I18nFilter(...)` 或统一菜单路由，而不是硬编码中文正则；FSM-only 菜单 key、特殊翻译覆盖和旧键盘文案 alias 必须维护在 `src/handlers/menu_route_registry.py`。
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
- QQCC Bot 必须和主业务 Bot token 隔离，且不能导入 `src.bot_main` 或注册主 Bot 的高级/支付/gallery handler。
- 用户私有 Bot 必须使用 Telegram webhook；不能用相同 token 启动 polling。Webhook update 由 Web API 快速入 Redis stream，再由 private worker 将 update 交给对应 QQCC Application；同一 Bot update 顺序处理。
- private worker 读取环境对应 `QQCC_BOT_TOKEN` / `QQCC_BOT_TOKEN_TEST` 只授权统一频道会员查询，不能因此注册官方 handler 或启动第二个 `getUpdates`；租户只接收 checker callable，不能拿到官方 token/Bot 对象。
- FSM 内不得依赖硬编码菜单词做全局退出判断，必须走统一菜单路由。
- 临时文件、下载目录和清理逻辑应优先下沉到服务层，避免各 FSM 重复拼装。
- 主 Bot 与 QQCC Bot 共享 `src/services/telegram_runtime_bootstrap.py`，但 QQCC 仍只注册 quick image/video、QQCC market 和最小 callback；不要为了复用 bootstrap 引入主 Bot handler 集。
- callback 路由拆分时必须确保主入口导入子模块触发注册，不能因加载顺序拿到空路由表。
- 主 Bot 和 QQCC Bot 注册 ConversationHandler 时不得启用 PTB 无键全局并发 `concurrent_updates(True)`。主 Bot 必须通过 `src/services/telegram_update_processor.py` 的 `PerUserUpdateProcessor` 保证同一 Telegram 用户严格串行、不同用户有界并发；QQCC 官方 Bot 当前仍保持单通道。付费群审核 Bot 不注册 FSM，可继续保持全局并发。
- SCAIL-2 Bot 的“视频生视频”二级菜单支持测试 Bot 与正式 Bot，但正式展示必须跟随 SCAIL-2 正式 runtime 发布闸门；`scail2_video_fsm` 收集参考图、驱动视频、可选正向提示词和 5s/8s 时长，正向提示词可通过 inline button 跳过并由 domain config 默认值补齐，负面提示词使用默认值，驱动视频上限 40MB。旧 `face_video_fsm.py` 已退出 Bot 层并被删除；主 Bot 的 `视频换脸` 菜单和 `/video_swap` 均由 `scail2_video_fsm` 接管，非 Bot 层 `face_video` 历史任务类型、Gallery 展示和 worker 兼容不因此删除。正式发布维护窗口内，Bot 生成 FSM 应尊重 `/app/GENERATION_MAINTENANCE` 或全局 `/app/MAINTENANCE`，提示维护并停止新提交。
- 旧图生视频与图生视频 v2 的普通入口设置面板不再展示“确定/确认上传”按钮。`image_to_video_fsm.py` 在附加模型/帧模式/分辨率/时长面板直接接收起始图片，发送图片即确认设置；首尾帧模式随后收终止图片。`wan22_video_v2_fsm.py` 在单图/首尾帧、分辨率和时长面板同样直接接收起始帧图片；旧 `i2v_setup_confirm` / `wan22v2_setup_confirm` callback 仅保留兼容已发出的旧消息。
- LTX 高级图生视频 FSM 当前用户侧只开放两种模式：单首帧、首尾帧。普通入口先选最多 3 个 LoRA，然后在同屏设置面板选择 `ltx_mode`、清晰度和时长；该面板不再展示“确定，上传素材”按钮，用户直接发送起始帧图片即确认当前设置并进入素材步骤。单首帧收 1 张起始图后要求提示词，首尾帧收 `image_path` 后继续收 `end_image_path` 并提交 `ltx_mode=flf2v`；素材收完后直接要求发送提示词，不再二次展示清晰度/时长按钮。历史/底层兼容仍可识别或拒绝 `ltx_mode=v2v_audio`，但 Bot 层不再注册 `ltx_mode_v2v_audio` callback、`WAIT_VIDEO` 状态或视频上传 handler；旧已发按钮会走全局未知 callback 兜底。结果消息存在 `extra_outputs.last_frame` 预期时展示“扩展生成”按钮，callback 前缀为 `ltx_extend`；点击后必须校验历史归属、下载尾帧到 FSM 临时目录，并作为下一段 LTX 起始帧进入扩展设置面板。扩展设置面板不展示确认按钮：直接续写时用户发送提示词进入提示词确认，添加终止帧时用户发送图片即写入 `end_image_path` 并提交 `ltx_mode=flf2v`；旧 `ltx_setup_confirm` callback 仅保留兼容已发出的旧消息。续段必须携带 `ltx_prev_task_id` / `ltx_chain_task_ids`，由 Bot 完成落库写入 `extra_outputs._ltx_context`。Bot 结果从第二段起必须展示“完成拼接”按钮，callback 前缀为 `ltx_stitch_chain`，由全局 callback router 校验历史归属并拼接整条链；拼接结果只作为整链结果，不再展示扩展按钮。退出、超时、提交结束、`/cancel` 和全局异常兜底必须经 `cleanup_fsm_user_data(...)` / FSM cleanup 清理 `image_path`、`end_image_path`、`images` 等临时文件。

## 5. 边界条件处理
- **`user_data` 残留**：FSM 正常结束、异常退出、超时三种场景都要清理临时状态。
- **主菜单打断**：若用户在 FSM 中点击主菜单，应退出当前流程并返回明确提示，避免卡死。
- **大文件处理**：若仍使用 Local API / Monkey Patch 路径，需保证 HTTP 下载失败时有清晰错误日志与用户提示。
- **PTB Warning**：`ConversationHandler` 参数若会触发框架级 warning，应先确认是否属于既有契约，再决定改运行时配置还是测试显式处理预期 warning。

## 6. 测试要求
- 覆盖 FSM 意外菜单拦截与超时退出。
- 覆盖 callback 路由注册与未命中前缀的统一兜底。
- 主 Bot Update Processor 回归必须覆盖同用户不重叠、不同用户可并发、全局并发上限和等待任务取消后不阻塞后续 Update；入口测试必须禁止退回 `concurrent_updates(True)` 或 PTB 默认单通道。
- 覆盖临时文件下载/清理服务的行为契约。
- 覆盖 `paid_group_guard_bot` 的资格命中、未命中保留待审/拒绝、目标群过滤、消息删除 dry-run、管理员豁免、链接白名单和违禁词行为。
- 当 FSM 使用 PTB 已知 warning 配置时，测试应显式说明该 warning 是否属于预期行为。
- 私有 Application 回归必须证明频道资格查询来自官方 checker、租户 Bot 不被调用，并覆盖正/负缓存与并发 singleflight。
