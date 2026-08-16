# 子模块: 交互状态机与回调路由 (FSM & Callback Handlers)

主菜单的历史 `menu.ltx_video` 键当前展示为“高级图生视频pro”，实际注册
`advanced_video_pro_fsm.py`。入口选择 H3 三个公开模式、时长、画质档位与比例，再按模式
收集 0/1/2 张图片；提交计划由
`advanced_video_pro_submission_service.py` 校验并通过公共 Bot task facade 入队。
用户输入原始提示词后先进入 `WAIT_CONFIRMATION`：可直接生成，或在测试环境按独立
开关发起 1 灵石优化。优化使用用户/会话/模式/时长/原文派生的确定性请求
ID，成功只回显并保存优化文案，不自动提交视频，同时提供“使用优化提示词生成”和
“恢复原提示词”；失败保留原文并显示账本确认的退款状态。Bot 临时图片先复制到当前
用户专属 staging key，任务终态后清理。优化后台任务必须先通过
`get_or_create_user_by_telegram` 把 Telegram 平台 ID 映射为内部用户 ID；计费、结果
归属和 staging key 一律使用内部用户 ID，禁止把平台 ID 直接传入共享优化服务。
历史 LTX 设置 callback 只提示过期，不得静默改投新任务；旧 History/扩展 callback
仍维持历史记录兼容。
该入口画质统一为极速/清晰/标准/高清四档。首帧与首尾帧模式隐藏固定比例按钮并
展示“跟随首帧”；第二张图片与首帧比例差异超过 1% 时保留首帧和会话状态、删除
无效尾帧并要求重传。文生视频仍展示固定画面比例。
高级图生视频pro 的设置摘要明确显示固定 10Eros Beta2 + LightX2V 8-step 基础链，
并提供六个可多选 LoRA、全选和清空。附件默认全部关闭，Bot 不让用户输入自由强度，
而是把选中项转换为目录建议强度后交给 `advanced_video_pro_submission_service.py`。

## 1. 目标与范围

本模块包含所有通过 Python-Telegram-Bot (PTB) 实现的有限状态机逻辑，以及基于装饰器注册的 callback 路由体系。

当前职责边界：

- FSM 负责分步收集图片、视频设置、提示词与确认信息。
- 全局菜单打断依赖统一黑盒路由，而不是散落的硬编码菜单判断。
- callback 路由负责把充值、广场、杂项等回调拆分到独立模块。
- 充值菜单同时提供 USDT-TON 身份套餐、USDT-TON 灵石直充、原生 TON、
  Telegram Stars 与人民币入口。USDT 两个按钮都进入主 Vue `/billing`，
  分别携带 `method=usdt-ton&kind=membership|credits`；旧原生 TON 深链保持
  `method=ton&kind=membership`，不得把两种链上资产混成同一按钮。
- 文件下载、临时目录创建与清理由服务层承接，不应在各 FSM 内重复实现。
- 主 Bot 返佣面板提供 USDT-TON 人工兑换申请：金额、主网钱包地址、确认三步，
  最低 5 USDT，300 秒超时并支持全局菜单打断；冻结统一进入
  `affiliate_usdt_redeem_service`，FSM 不直接写账本。

## 2. 当前架构图

```mermaid
stateDiagram-v2
    [*] --> START : 点击某个 FSM 入口
    START --> WAITING_IMAGE : 发送图片要求
    WAITING_IMAGE --> WAITING_SETTINGS : 上传图片
    WAITING_IMAGE --> CANCEL : 主菜单打断 / /cancel
    WAITING_SETTINGS --> WAITING_PROMPT : 选择分辨率/时长/模型
    WAITING_SETTINGS --> CANCEL : 主菜单打断 / 超时
    WAITING_PROMPT --> WAITING_CONFIRMATION : 输入提示词 / 优化提示词
    WAITING_PROMPT --> CANCEL : 主菜单打断 / 超时
    WAITING_CONFIRMATION --> SUBMIT : 确认生成
    WAITING_CONFIRMATION --> CANCEL : 放弃生成
    SUBMIT --> [*] : 释放 FSM，移交 Bot task flow
    CANCEL --> [*] : 清理 user_data 与临时文件
```

## 3. 当前主链路

### 3.1 FSM 到 Bot 任务流

当前主链为：

- FSM / message handler
- 分域 entrypoints
- `task_service_entrypoints_generation.py`
- `task_service_entrypoints_specialized.py`
- `task_service_entrypoints_video.py`
- `run_bot_task_application(...)`

Bot flow 当前采用五段式上下文：

- `request`
- `presentation`
- `billing`
- `failure`
- `cleanup`

取消态使用 `BotTaskCancelled`，不再使用字符串 sentinel。

### 3.2 全局菜单黑盒退出

FSM 入口与过程中，当前推荐组合为：

- `I18nFilter(...)`
- `menu_route_registry.py`
- `GLOBAL_REVERSE_MAP`
- `is_global_menu_command(...)`

在任意文字输入 handler 内，应优先判断 `is_global_menu_command(...)`，决定是否强制退出当前 FSM。

- 若多个 FSM 共享同一类取消/超时/意外输入退出逻辑，优先复用 `fsm_shared.py`，不要在各文件继续复制 `_t/cancel/timeout/unexpected_input` 样板。
- `menu_route_registry.py` 是反向菜单路由事实源：FSM-only menu keys、QQCC 特殊翻译覆盖、`menu.video_lora` 优先级和旧键盘文案 alias 都在这里分区维护；`prompt_router.build_global_menu_filter()` 只负责把这些 key 翻译成 `GLOBAL_REVERSE_MAP`。

### 3.3 主 Bot 与 QQCC 重复入口收口

主 Bot 的 Reply Keyboard 支持运行时展示配置。事实源为 `src/services/main_bot_menu_config_service.py` 与 `runtime_checkpoints` 中的 `main_bot_menu_config:v1`；Dashboard 通过认证接口 `/api/main-bot/menu-config` 管理主菜单排序、每行 1–4 个按钮，以及主菜单和“图片换脸”“视频生视频”二级菜单的显隐。配置不引入数据库迁移；读取失败时必须回退完整默认菜单，避免故障期间误隐藏入口。

`/start`、`/cancel`、返回主菜单、语言切换、未知输入兜底、空闲图片提示和两个二级菜单入口都在发送新键盘前加载最新配置。Telegram 已经发出的旧键盘不会主动撤回；隐藏只影响后续 Reply Keyboard 展示，不停用 route、FSM、旧按钮或手工文本入口。二级菜单的“返回主菜单”固定可见，`QQCC_LAZY_BOT_ENABLED` 等既有安全/能力闸门仍优先，展示配置只能进一步隐藏。

主业务 Bot 底部菜单不再展示旧 `修仙市集` 和 `视频创作` 入口；旧 `修仙市集` 文案与新 `懒人bot` 菜单都只回复前往 QQCC 懒人 Bot 的 inline URL 按钮，跳转目标由 `QQCC_LAZY_BOT_URL` 或 `QQCC_LAZY_BOT_USERNAME` 提供。`图片换脸` 二级菜单只保留双图 `快速换脸` 与单图 `随机换脸`。

旧 `快速脱衣`、`快速自慰`、`menu.video_edit_*`、旧 `AI绘图` / `AI滤镜` / `AI动图` / `快速换脸` 文本入口和主 Bot 上的 `qvid_*` callback 必须回复前往 QQCC 懒人 Bot 的 inline URL 按钮或入口未配置提示，不得进入任务提交。QQCC Bot 仍保留 `AI绘图` / `AI滤镜` / `AI动图` 动态场景入口、`qdraw_scene:*`、`qfilter_scene:*`、`qvid_scene:*` 与旧 `qvid_mode:*` 已发按钮兼容。

主 Bot `src/bot_main.py` 与 QQCC Bot `qqcc_bot/main.py` 共享 `src/services/telegram_runtime_bootstrap.py`，统一 Local Bot API URL、HTTPXRequest、Telegram File/Poll patch 和语言/i18n middleware。共享 bootstrap 不改变注册边界：主 Bot 仍注册完整 FSM/支付/恢复，QQCC 仍只注册 quick image/video、QQCC market 和最小 callback，并继续用 `bot:qqcc` 过滤恢复任务。

主 Bot 和 QQCC Bot 都注册 PTB `ConversationHandler`，入口构建不得开启无键全局并发 `concurrent_updates(True)`。主 Bot 使用 `src/services/telegram_update_processor.py` 的 `PerUserUpdateProcessor`：以 `effective_user.id` 为串行键，同一用户的 Update 严格按顺序执行，不同用户最多并发处理 `MAIN_BOT_MAX_CONCURRENT_UPDATES` 个（默认 32，上限 256）；无用户 Update 回退到 chat 键，无 user/chat 的系统 Update 共用保守串行键。处理器为每个 Update 记录 `telegram_update_timing`，包含 `queue_wait_ms` 与 `handler_duration_ms`，用于日志侧计算排队和执行耗时分位数。主 Bot long polling 的 `poll_interval` 为 0，避免原先额外 0～2 秒轮询抖动。QQCC 官方 Bot 当前仍保持单通道；`paid_group_guard_bot` 不注册生成 FSM，仍允许保持全局并发处理群审核与消息删除。

主 Bot 全局 callback router 在用户数据库/缓存同步前先调用 `safe_answer_query(...)`，避免同步和路由 I/O 延长客户端转圈；路由模块和高频 FSM callback 的应答也必须使用该 helper，使过期 callback 只记录告警而不终止业务动作。

#### QQCC 私有 Bot 申请 FSM

`qqcc_bot/private_bot_fsm.py` 的 `私有bot` 入口只注册在官方 QQCC。首次点击说明 `@BotFather` + `/newbot` 申请步骤；文本状态收到 token 后必须先尽力删除原 Telegram 消息，禁止在回复、日志、异常或审计 metadata 中回显。验证有效后无需审核直接注册 webhook；同一 owner 已有绑定时只返回管理入口。全局菜单打断、`/cancel` 和 300 秒超时都结束 token 接收状态。

私有 QQCC Application 由 webhook worker 装配，不注册申请入口、不启动 polling，并继续复用 quick image/video FSM。worker 为每个 private Bot 使用独立顺序队列，防止同一 Bot 的 ConversationHandler update 交错；不同 Bot 才通过全局并发门限并行。详细凭据/worker/Host 契约见 `docs/子模块_QQCC用户私有Bot平台_qqcc_private_bot_platform.md`。

Quick Video 的提交与设置归一已收口到 `src/services/quick_video_submission_service.py`：`quick_video_fsm.py` 只负责 Telegram 状态、设置面板展示、额度检查、用户回复和上下文清理；service 负责构造提交计划、QQCC 场景 engine 分支、尾帧绘图链成本、执行 payload，以及 `set_res_*` / `set_dur_*` callback 对分辨率/时长状态的归一。提交旧图生视频时，plan 会把 `resolution` / `duration` 显式传给 `process_video_task_template(...)`，不再通过 `context.user_data["custom_video_resolution"]` / `custom_video_duration` / `mode` 作为桥接状态。后续改 `AI动图` 提交或设置语义时优先覆盖 service focused tests，再保留 FSM 黑盒回归。

Quick Image 的提交阶段已收口到 `src/services/quick_image_submission_service.py`：`quick_image_fsm.py` 和 `random_faceswap_again` callback 只负责 Telegram 状态/按钮、图片路径读取、额度检查、用户回复和上下文清理；service 负责构造提交计划、随机换脸模板过滤、QQCC AI绘图/AI滤镜场景、`draw -> draw...` / `draw -> filter` / 单步 `filter` 链成本与执行 payload，并在重生成 metadata 中写入 `scene_kind=draw|filter`。旧 `WAIT_UNDRESS_METHOD` 选择态和旧脱衣方式 callback 已移除，`i2i_draw` 提交 payload 仅保留 service 兼容。

主 Bot 高级视频提交阶段已收口到 `src/services/advanced_video_submission_service.py`：`image_to_video_fsm.py`、`wan22_video_v2_fsm.py`、`ltx_video_fsm.py` 仍负责 Telegram 状态、素材接收、额度检查、用户回复和清理；service 负责旧图生视频/Wan22 v2/LTX 的提交计划、分辨率与时长归一、首尾帧 payload、LTX LoRA 多选与扩展链上下文。LTX 提交时，`resolution`、`duration` 和 `ltx_mode` 由 plan 显式传给 `process_ltx_video_task(...)`；主 Bot 与 QQCC 市集 apply 都不得再通过 `context.user_data` 顶层 `ltx_video_*` 键桥接后台任务参数。该 service 不新增 task type、workflow、RunPod profile 或 QQCC 能力；旧 setup confirm callback 仍只作为已发消息兼容。

主 Bot 高级视频设置面板已收口到 `src/services/advanced_video_settings_view_service.py`：旧图生视频、Wan22 v2 与 LTX 的同屏设置 view-model/keyboards、费用展示、LTX 扩展直接续写/添加终止帧提示，以及对应 settings callback data 到 `fsm_data` 的解析回写都由 service 承接；FSM wrapper 只处理 callback 状态并发送或编辑 Telegram 消息。后续修改高级视频按钮布局、设置文案或设置 callback 语义时，应优先覆盖 service focused tests，再保留 handler 黑盒回归。

LTX Bot 侧当前只保留单首帧与首尾帧：`ltx_video_fsm.py` 不再注册 `ltx_mode_v2v_audio` callback、`WAIT_VIDEO` 状态或视频上传 handler。底层 `ltx_video_v2v_audio` 仍作为历史/队列兼容执行面由 service/core/worker 负责 reject 或执行兼容，不能从 Bot FSM 重新暴露。

LTX 扩展/拼接回调准备阶段已收口到 `src/services/ltx_video_extension_service.py`：`ltx_video_fsm.py` 的扩展入口只负责解析 callback task id、会话冲突、写入 seed 后展示设置面板；`ltx_video_callbacks.py` 的完成拼接 callback 只负责 Telegram 进度提示、调用 stitch、发送结果、记录 message meta 和置灰原按钮。历史归属校验、`_ltx_context` 合并、尾帧下载、扩展 FSM 初始数据和完整链路 histories 加载都由该 service 负责。

Wan22 AIO 链路扩展/重生成/拼接回调准备阶段已收口到 `src/services/wan22_video_v2_extension_service.py`，覆盖旧图生视频 `custom_video` / `video_lora` 与图生视频 v2：`wan22_video_v2_fsm.py` 的扩展/重生成入口只负责解析 callback task id、会话冲突、写入 seed 后继续 FSM；`wan22_video_v2_callbacks.py` 的重生成 callback 只负责发送提交中提示并调用提交 service，完成拼接 callback 只负责进度提示、调用 stitch、发送结果、记录 message meta 和置灰原按钮。历史归属校验、`_wan22_context` 合并、上一段尾帧下载、当前段输入图复用、FSM seed 和完整链路 histories 加载都由该 service 负责。

### 3.4 Callback 路由

当前 callback 体系依赖：

- `@register_callback("prefix")` 前缀注册
- 按前缀长度降序匹配
- 主入口导入子模块以触发注册
- 主 Bot / QQCC Bot 在 callback handler import 阶段调用 `validate_callback_routes(...)` 校验关键 prefix manifest，防止拆模块后漏导入
- 未命中时统一 `safe_answer_query(...)` 兜底

### 3.5 SCAIL-2 视频生视频 FSM

正式 Bot 与测试 Bot 的主菜单中，原“视频换脸”位置已进入“视频生视频”二级菜单。二级菜单顺序固定为：

- 视频换人
- 动作迁移
- 视频换脸
- 返回主菜单

`视频换人`、`动作迁移` 和 SCAIL-2 `视频换脸` 由
`src/handlers/fsm/scail2_video_fsm.py` 处理，状态流为：

- `WAIT_REFERENCE_IMAGE`：只接收参考图片
- `WAIT_MOTION_VIDEO`：接收 Telegram video 或 video document，驱动视频上限 40MB
- `WAIT_PROMPT`：接收正向提示词，或通过 inline button 跳过并使用 task type 默认提示词；空文本会提示用户点击跳过
- `WAIT_DURATION`：inline keyboard 只允许 `5秒 · 40灵石` 或 `8秒 · 80灵石`

该 FSM 不询问负面提示词，统一使用 `SCAIL2_DEFAULT_NEGATIVE_PROMPT`。提交时通过
`process_scail2_video_task(...)` 进入 Bot task flow，inputs 与 Web 保持一致：
`images=[reference_image_local_path, motion_video_local_path]`、`prompt`（可为空，服务层会补默认值）、`negative_prompt`、
`duration`、`resolution=512x896`。正常结束、取消、超时、非法文件、全局菜单打断或下载后发现超限时，
都必须清理临时文件和 `user_data["scail2_video_data"]`。旧 `src/handlers/fsm/face_video_fsm.py` 已从 Bot 层删除，`FaceVideoState` 也不再保留；“视频换脸”菜单与 `/video_swap` 现在都由 SCAIL-2 视频生视频 FSM 接管。非 Bot 层的 `face_video` 历史任务类型、Gallery 历史展示与 worker/workflow 兼容仍按历史数据保留。

## 4. 关键实现约束

### 4.1 FSM 超时

当前主 FSM 普遍采用：

- `conversation_timeout=300`

若后续调整超时值，必须同步更新：

- FSM 文档
- 相关 focused tests
- 若有对应 skill 文档，也需同步更新

### 4.2 临时文件服务

常规 FSM 文件下载与清理应优先复用 `fsm_temp_file_service.py`，避免各 FSM 自己拼装。
`cleanup_fsm_user_data(user_data)` 是全局兜底清理入口：它会收集所有 `*_data` 中的 `image_path`、`end_image_path`、`video_path`、`images` 等临时路径，也会收集随机换脸“再来一张”使用的顶层 `last_face_image` 临时缓存；只删除 `TMP_DIR` 下文件，并清理 `in_conversation`、`*_data` 与这些顶层临时缓存，保留 `language_code` 等偏好。主 Bot `/cancel`、QQCC `/cancel` 与 `global_error_handler` 都应走该 helper；单个 FSM 的正常提交/超时仍可保留自己的局部 cleanup，但路径规则需与该 helper 一致。

### 4.3 语言切换

语言切换当前不只是菜单文案变更，还涉及：

- 数据库语言字段更新
- Redis 缓存同步
- translator 运行时状态刷新

## 5. 测试要求

- 覆盖 FSM 超时与主菜单打断
- 覆盖完整参数收集后进入对应 Bot entrypoint 或 `run_bot_task_application(...)`
- 覆盖 callback prefix 路由与统一兜底
- 覆盖主 Bot 同用户 Update 不重叠、不同用户可并发、全局并发上限、等待任务取消释放，以及 callback 在用户同步前安全应答
- 覆盖 SCAIL-2 入口 task type 映射、40MB 视频拦截、5s/8s 时长按钮、默认负面词和临时文件清理；测试环境还需覆盖 `scail2_face_swap_v2`。
- 若 PTB 某些配置会触发已知 warning，测试需显式说明它是“预期行为”还是“应修复行为”
