# 图生视频 (Image-to-Video) 业务流与架构分析

本文档描述当前系统中的图生视频链路，包括 `ltx_video`、`wan22_video_v2`、自定义视频、快捷视频与相关 Telegram / Web 任务流。

## 一、 当前业务主链

```mermaid
sequenceDiagram
    actor User as Telegram 用户
    participant FSM as Bot 交互层
    participant Entry as Bot entrypoints
    participant Flow as run_bot_task_application
    participant Core as task_core facade
    participant Backend as Central API / Queue / Worker
    participant Store as MinIO

    User->>FSM: 发送图生视频命令
    FSM-->>User: 提示上传图片、选择设置、输入提示词
    FSM->>Entry: 进入视频 entrypoint
    Entry->>Flow: 组装 BotTaskFlowContext 五段式上下文
    Flow->>Core: process_and_submit_task(...)
    Core->>Backend: 派发 registry_task_id / backend_task_id
    Flow-->>User: 前台进度通知 / 排队状态
    Backend->>Store: 上传视频结果
    Flow->>Store: 下载/发送视频结果
    Flow-->>User: 返回 MP4 与分享/交互按钮
```

### 当前关键事实
- FSM 不再直接长轮询 `task_core`；真实主链是 `entrypoint -> run_bot_task_application(...) -> task_core facade`。
- Bot 视频主链的取消态当前通过 `BotTaskCancelled` 收口，而不是字符串 sentinel。
- `quick_video_fsm.py` 已不再通过构造假的 `Update/Message` 适配旧接口。
- `ltx_video` 当前主协议是 `lora_items` 多选链路，最多 3 个 LoRA，旧 `lora_name / lora_strength` 只保留兼容。
- `wan22_video_v2` 已进入统一视频主链；除主视频外，还可能通过 `extra_outputs.last_frame` 回传尾帧图片。
- 旧图生视频 `custom_video` / `video_lora` 在执行面新增为 `image_to_video`，与 `wan22_video_v2` 共用 `Wan22AioV81.json`；历史、投稿和展示类型仍保留 `custom_video` / `video_lora`，不改写成 v2。
- Wan22 AIO 视频配置事实源是 `src.domain_config.wan22_aio_video`：旧图生视频 `custom_video` / `video_lora` -> execution `image_to_video` -> `legacy_image_to_video` profile；图生视频 v2 `wan22_video_v2` -> execution `wan22_video_v2` -> `wan22_video_v2` profile。两者共享 worker workflow，但不是同一个用户功能。
- 旧图生视频固定 5 秒，分辨率与计费对齐 v2 三档：`preview` / `standard` / `hd`。历史投稿中的 `512p` / `720p` / `1024p` 会分别映射到这三档，旧 duration 一律忽略为 5 秒。
- `image_to_video` 和 `wan22_video_v2` 通过 `wan22_model_profile` 区分主模型：旧入口使用 legacy high/low 主模型，v2 使用 snatchkiss high/low 主模型。`video_lora` 仍保留旧 LoRA 前缀选择，`custom_video` 与 v2 会清空额外 LoRA 槽。
- Web `wan22_video_v2`、`custom_video`、`video_lora` 已支持与 Bot 对齐的多段链：历史与 `/api/tasks/{task_id}/result` 会返回 `last_frame` 与 `result_meta`，并新增 `/api/users/history/{task_id}/wan22-chain`、`/api/users/history/{task_id}/wan22-chain/stitch` 供练功房继续扩展、分段重生成和整链拼接；其中整链拼接现在会把拼接后 MP4 上传存储，并新增一条 `History` 记录返回给前端，而不是只回下载流。

## 二、 数据流向

```mermaid
graph TD
    subgraph ClientLayer [用户端]
        U_IMG[参考图片]
        U_TXT[提示词]
        U_CFG[分辨率/时长/模式]
    end

    subgraph BotLayer [Bot 侧]
        TMP[临时文件服务]
        FSM_CTX[FSM 上下文]
        ENTRY[视频 entrypoint]
        FLOW[Bot task flow]
    end

    subgraph CoreLayer [Core]
        FACADE[task_core facade]
        DEPS[provider / dependencies]
    end

    subgraph Backend [后端执行]
        CENTRAL[Central API]
        WORKER[Comfy Workers]
        STATUS[运行态事件 / 状态]
    end

    subgraph Storage [存储]
        MINIO[MinIO 结果桶]
    end

    U_IMG --> TMP
    U_TXT --> FSM_CTX
    U_CFG --> FSM_CTX
    TMP --> ENTRY
    FSM_CTX --> ENTRY
    ENTRY --> FLOW
    FLOW --> FACADE
    FACADE --> DEPS
    DEPS --> CENTRAL --> WORKER
    WORKER --> MINIO
    WORKER --> STATUS
    STATUS --> FLOW
    FLOW --> MINIO
```

## 三、 分层说明
### 3.1 交互层
- `ltx_video_fsm.py`、`wan22_video_v2_fsm.py`、`image_to_video_fsm.py`、`quick_video_fsm.py` 等负责分步收集参数。
- 全局菜单打断通过 `is_global_menu_command(...)` 统一识别。
- 当前主 FSM 普遍使用 `conversation_timeout=300`。
- `wan22_video_v2_fsm.py` 现已收口为“起始帧 + 可选终止帧 + prompt/negative prompt”输入；是否启用首尾帧由是否上传第二张图自动判断，尾帧提取固定开启且仅作存储，不再开放 `color_match`、`perfect_loop`、`upscale`、`extract_last_frame` 给用户。

### 3.2 Bot 任务流层
- 视频任务入口主要位于：
  - `task_service_entrypoints_video.py`
  - `task_service_entrypoints_specialized.py`
  - `task_service_entrypoints_generation.py`
- 这些入口负责构造 `BotTaskFlowContext`，再进入 `run_bot_task_application(...)`。
- 其中 generation 侧已继续按任务族拆分到：
  - `task_service_generation_image.py`
  - `task_service_generation_video.py`
  - `task_service_generation_wan22.py`
- Wan22 AIO 图生视频 Bot 生成服务已收口到 `src/services/wan22_aio_video_generation.py`；`task_service_generation_video.py` 与 `task_service_generation_wan22.py` 保留薄 wrapper，前端/Bot 交互语义不随底层合并而改名。
- 内部调用当前应优先直接进入分域 entrypoints；历史 `bot_task_service.py` compat 壳已删除，不再作为调用入口。
- `process_wan22_video_v2_task(...)` 位于 generation entrypoints，`process_ltx_video_task(...)` 位于 specialized entrypoints；两者都已走统一提交与前台监控主链。

### 3.3 Core 提交与监控层
- `task_core.py` 负责统一提交语义。
- `task_dispatcher.py` 基于 strategy 生成 workflow / payload。
- Web 任务完成后由 `src/services/task_web_side_effects.py`、`task_web_lifecycle_monitor.py`、`task_web_terminal_finalization.py` 协同承接 side effect 与终态收口；Bot 则由 `run_bot_task_application(...)` 负责前台监控与展示。
- Wan22 图生视频链式上下文（`wan22_prev_task_id`、`wan22_chain_task_ids`、分辨率、负面提示词、是否使用终止帧、主模型 profile、旧 LoRA 信息）现由 dispatcher metadata 写入提交，再由 Web terminal finalization 合并进历史 `extra_outputs._wan22_context`，供 Bot/Web 共用历史链恢复。适用类型包括 `wan22_video_v2`、`custom_video`、`video_lora`。

### 3.4 Web 练功房与历史链
- `wan22_video_v2` 主入口已并入练功房 `frontend/src/views/CustomFeatures.vue`；独立 `frontend/src/views/Wan22VideoV2.vue` 仅作为兼容入口保留。旧 `custom_video` / `video_lora` 也复用同一套 Wan22 多段编辑能力。
- 练功房结果区不再提供语义含混的“继续生成”，而是为 Wan22 图生视频显示“扩展生成 / 重新生成”；第二段及以后基于 `wan22_prev_task_id` 额外显示“拼接”。
- 扩展生成会把当前段 `extra_outputs.last_frame` 作为锁定起始帧，清空本段正向 prompt，并提交 `wan22_prev_task_id = 当前段` 与包含当前段在内的 `wan22_chain_task_ids`。
- 重新生成第一段只清空表单并保持 `wan22_video_v2` 模式，不自动复用原始素材或参数；第二段及以后会复用上一段尾帧、当前段 prompt/负面 prompt/分辨率和可选终止帧，且只继承当前段之前的链路上下文。
- 历史详情 `TaskDetailModal.vue` 已为 `wan22_video_v2`、`custom_video`、`video_lora` 提供“扩展下一段 / 重新生成本段 / 完成整链拼接”入口；编辑入口会携带 `type=<来源类型>&wan22_mode=extend|regenerate&wan22_task_id=...` 回到练功房。点击“完成整链拼接”后，前端会直接打开新生成的拼接历史记录，提示词按“第 N 段”分段汇总各子片段 prompt，拼接历史类型保持来源链路类型。
- Gallery 一键应用只支持 Wan22 单段记录：旧 `custom_video` / `video_lora` 继续恢复 prompt、旧 LoRA 与分辨率档位，`wan22_video_v2` 单段恢复 prompt、negative prompt、分辨率档位和固定 5 秒；所有 stitched 拼接记录都禁用一键应用，apply-context 服务端返回 400。
- Telegram Bot 第二段及以后点击“重新生成”会进入可编辑 FSM：锁定上一段尾帧，继承当前段终止帧、负面提示词、分辨率和旧 LoRA 上下文，并展示原 prompt；用户可以发送新 prompt，或点击“使用原提示词”继续。
- Telegram Bot 结果按钮不能只依赖 `context.bot_data["msg_meta_<message_id>"]` 里的内存元数据；`扩展生成 / 重新生成 / 完成拼接` callback 需携带当前 `task_id`，旧消息则允许从同条消息的 `submit_gallery_<task_id>` 按钮兜底恢复，再从历史 `extra_outputs._wan22_context` 补齐分辨率、上一段、负面提示词、LoRA 和拼接链路上下文。若仍无法恢复，必须回一条明确失效提示，避免只显示“任务初始化中”。
- Telegram Bot 点击“完成拼接”后也会把拼接 MP4 上传存储并新增一条 `source=bot` 的历史记录；结果消息使用新 `task_id` 注入“投稿至广场”按钮，继续复用 `submit_gallery_<task_id>` 投稿链路。

## 四、 计费与资源约束
- 视频任务计费是动态的，通常由分辨率与时长组合决定。
- Wan22 AIO 视频的分辨率档位统一维护在 `src.domain_config.wan22_aio_video`，Bot / Web / dispatcher / worker patcher 共享同一语义；当前 5 秒固定时长下展示三档：`preview` = 极速 / 约 512p / `0.26 MP - Preview` / 6 灵石（默认且最低价），`standard` = 标准 / 约 720p / `0.52 MP - SD` / 20 灵石，`hd` = 高清 / 约 810p / `0.65 MP - Balanced` / 30 灵石。旧 `fast` / `0.36 MP - Small` 仅作为兼容别名归一到 `preview`，不再作为可选档位展示。Worker 会把档位写入 `Wan22AioV81.json` 的 `DaSiWa_ResolutionScaleCalculator` 节点 `2612.inputs.precision_presets`。
- `custom_video` / `video_lora` 现在完全对齐上述 v2 计费口径：固定 5 秒，`preview=6`、`standard=20`、`hd=30`。投稿一键应用恢复旧 `1024p` 时应自动选择 `hd`，提交消耗 30 灵石。
- 过高画质与过长时长组合仍可能触发 guardrail，避免显存溢出或节点拥塞。
- 任何取消/失败路径都必须与并发锁释放和必要退款一并考虑。

## 五、 结果发送与清理
- Bot 完成后会发送 MP4、caption、reply markup 与后续交互入口。
- `wan22_video_v2` 与执行面 `image_to_video` 都会额外保存 `extra_outputs.last_frame` 对应的尾帧图片，用于扩展生成、分段重生成和整链拼接。Worker 优先读取 Comfy `2503` 尾帧输出；如果某个 Comfy 实例只返回主 MP4，`agent_result_materialization.py` 会用 `ffmpeg/ffprobe` 从主视频补抽最后一帧，因此 worker 镜像必须保留 ffmpeg 依赖。
- 运行结束后需清理：
  - status message
  - 本地临时文件
  - runtime state / registry
  - 必要的锁与终态消息

## 六、 测试要求
- 覆盖参数收集、菜单打断、超时退出。
- 覆盖视频 entrypoint 到 `run_bot_task_application(...)` 的上下文装配。
- 覆盖取消、失败、成功三条主分支。
- 若修改 `wan22_video_v2`，需覆盖“单起始帧 / 双帧模式 / 尾帧开关”三类布尔门控与结果发送语义。
- 若修改 Wan22 Web 链式编辑，需额外覆盖 `wan22_video_v2`、`custom_video`、`video_lora` 三类历史的 `result_meta`、历史链查询、结果区按钮、练功房路由恢复、整链拼接、首段重生成清空、以及“后续段重生成只继承前序链路”的提交上下文截断语义。
- 若修改 Wan22 尾帧物化逻辑，需覆盖 Comfy 返回 `2503` 和只返回主 MP4 的兜底抽帧两类路径，确保旧图生视频生成后仍可扩展和拼接。
- 若修改旧图生视频投稿一键应用，需覆盖 prompt、`[模型: xxx]` LoRA 解析、旧分辨率到 `preview/standard/hd` 映射、固定 5 秒和 v2 灵石消耗。
- 若修改 Wan22 Gallery 一键应用，需覆盖 v2 单段 `negative_prompt` / `wan22_resolution_preset` 回填，以及旧/v2 stitched 拼接记录列表禁用与 apply-context 400 拒绝。
- 若修改 `ltx_video`，需覆盖 `lora_items` 多选、单项兼容字段与无 LoRA 回退三类协议。
- 若修改视频成本计算、requested_duration 或结果发送语义，需同步回归 focused tests 与黄金路径集。
