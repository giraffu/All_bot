# 子模块: 附加模型部署与配置指南 (ComfyUI Add-on Models)

本指南汇总了在现有分层解耦架构（Bot 交互 -> Backend 队列 -> Comfy Agent 调度）下，新增各种附加模型（如 LoRA、ControlNet 等）的实施方案。

整个过程主要是一个**配置驱动**的过程，无需重构核心逻辑。下面分别介绍“图生图”与“图生视频”附加模型的具体配置路径。

---

## 0. workflow 资产事实源红线

- `workers/comfy_agent/workflows` 是唯一 workflow 资产事实源；`backend/workflows` 已退出，Central API 不再挂载、COPY 或启动校验 workflow 目录。
- 新增或修改 workflow JSON、`mappings.json`、`workflow_patcher.py`、`workflow_task_patchers.py` 时，只更新 Worker 目录，并确认目标 Worker 的 `SUPPORTED_TASK_TYPES` 覆盖该 task type。
- Worker 启动时会基于 `workers/comfy_agent/workflows/mappings.json` 校验映射节点与输入名；Central API 只负责参数网关和队列入队，不再用 workflow 文件做启动门禁。
- 重导 workflow 后必须复核硬编码节点 ID、`mappings.json` 节点输入名、`TASK_TYPE_WORKFLOW_FILENAMES` 绑定和 Worker `SUPPORTED_TASK_TYPES`，避免 Worker 校验通过但执行面读到旧文件。

---

## 一、 新增图生图附加模型（LoRA/ControlNet）实施方案

### 1. 模型文件部署 (Deployment)
- 将新模型的 `.safetensors` 或 `.pt` 文件放置到 ComfyUI 宿主机映射的对应模型目录中（例如 `models/loras/` 或 `models/controlnet/`）。
- 确保文件名拼写正确且全系统唯一，因为后续的路由完全依赖此文件路径。

### 2. Bot 层：更新用户交互菜单 (UI & FSM)
- **文件定位**：`src/handlers/fsm/edit_image_fsm.py`（或相关的状态机配置）。
- **实施步骤**：
  - 找到存储模型映射的常量字典（如 `LORA_MODELS`）。
  - 在字典中追加新模型配置：将**模型实际相对路径**（如 `"qwen/illustration_v2.safetensors"`）作为键，映射到用户可见的**中文按钮标签**（如 `"插画风"`）。**注意路径必须严格包含在宿主机目录下的相对路径前缀**。
  - **权重配置（重要）**：若新模型需要特定的默认权重（非 `1.0`），必须在同文件下的 `get_lora_default_strength` 函数中增加对应的条件分支。
  - 若引入的是全新类别（如增加 ControlNet 专属选单），需在状态机流转中插入一个新的等待节点（State）以收集该参数。

### 3. Backend 层：参数网关透传 (API Routing)
- **文件定位**：`backend/app/models.py` 和 `backend/app/main.py`。
- **实施步骤**：
  - 检查用于验证图生图请求的 Pydantic 模型（如 `Img2ImgLoraRequest`）。
  - 如果新模型复用现有的 `lora_name` 或 `lora_strength` 参数，则本层**无需任何修改**。
  - 如果新增了独立维度的参数（如 `controlnet_image` 或 `controlnet_weight`），需在对应模型中声明这些可选字段，确保后端 API 能将参数安全写入 Redis 队列。

### 4. Worker 层：工作流映射与动态注入 (Workflow Patcher)
- **文件定位**：`workers/comfy_agent/workflows/mappings.json`、`workers/comfy_agent/workflows/Qwen-Rapid-AIO.json` 及 `workers/comfy_agent/workflow_patcher.py`。
- **实施步骤**：
  - **更新模板**：在 ComfyUI 本地调试好包含新节点的工作流，导出 API 格式的 JSON（非 UI 格式）覆盖现有模板。记录新附加模型节点（如 `Load LoRA`）的节点 ID。
  - **配置映射**：在 `mappings.json` 中，声明 Backend 参数键与 ComfyUI 节点 ID 的对应关系，若需要特定输入名可通过 `{key}_input` 指定（例如：`"lora_name_2": "45", "lora_name_2_input": "lora_name"`）。
  - **启动期校验**：Worker 会在启动时校验 `mappings.json`，至少检查“映射节点 ID 是否存在”“映射输入名是否真实存在于节点 `inputs` 中”。若校验失败，Worker 会 fail fast，避免把错误工作流带到线上运行阶段。
  - **编写动态补丁**：若该模型为**用户可选**（非全局强制加载），需在 `workflow_patcher.py` 中补充防爆逻辑：当检测到任务参数未携带该模型时，通过脚本动态**删除该节点**并**重新缝合**工作流上下文连线（如将 Checkpoint 的连线绕过该节点直接连向下游）。
    > ⚠️ **节点硬编码警告**：由于当前 `workflow_patcher.py` 中的节点剪枝和重连高度依赖硬编码的节点 ID（例如图生图逻辑中写死了 ID 为 `32` 的节点为 LoRA 节点，ID 为 `2` 的节点为 KSampler），如果在更新模板时节点 ID 发生变化，务必同步修改代码中的防爆硬编码逻辑，否则会导致连线断裂！
    > 💡 **格式排障**：如果在导出 JSON 时误导出了 UI 格式（包含 `"nodes"` 数组），Agent 的日志会输出 `Workflow xxx.json seems to be in UI format` 警告。请确保使用 ComfyUI 的 `Save (API Format)` 按钮导出。

### 5. 验证与发布 (Testing & Restart)
- 遵循部署规范，通过 `docker-compose up -d comfy-agent-1` 等指令平滑重载对应的 Agent 容器以读取新 JSON，并重启 Bot 进程。
- 在 Telegram 中唤起图生图菜单，验证新按钮渲染、参数透传是否成功，并在后台观察 ComfyUI 是否成功加载该 `.safetensors` 文件。

---

## 二、 旧图生视频附加模型（LoRA）实施方案

旧图生视频的用户侧能力仍保留 `custom_video` / `video_lora` 两种历史类型，但执行面已经改为 `image_to_video`，并与 `wan22_video_v2` 共用 `workers/comfy_agent/workflows/Wan22AioV82.json`。两者通过 `src.domain_config.wan22_aio_video` 中的 profile 注入不同主模型：旧入口使用 `legacy_image_to_video`，v2 使用 `wan22_video_v2`。旧 `src.services.wan22_video_v2_config` 与 `src.services.wan22_video_v2_context` 兼容 re-export 已删除，新增逻辑必须直接引用 domain_config 入口。

目前系统主要支持 LTX-2.3 和 Wan2.2/Wan2.1 视频生成工作流。关于 LTX-2.3 工作流的具体 LoRA 使用与提示词规范，请参考项目根目录的 `LTX_LoRA_Guide.md`。

### 0. 当前支持概览
- **普通图生视频 / 自定义图生视频**：上游类型仍是 `custom_video` / `video_lora`，执行面统一入队 `TaskType.IMAGE_TO_VIDEO`，底层 workflow 为 `Wan22AioV82.json`。
- **Wan22 AIO profile 口径**：旧图生视频 `custom_video` / `video_lora` -> execution `image_to_video` -> `legacy_image_to_video` profile；图生视频 v2 `wan22_video_v2` -> execution `wan22_video_v2` -> `wan22_video_v2` profile。两者共享 worker workflow，但不是同一个用户功能。
- **旧 LoRA 图生视频 (`video_lora`)**：继续接收 `lora_name` 前缀，由 `workflow_task_patchers.py` 按高噪/低噪双节点动态补入。`custom_video` 不带 LoRA 时会清空 LoRA 槽；`wan22_video_v2` 始终清空额外 LoRA 槽。
- **规格口径**：旧图生视频支持 `5s/8s/10s`，对应 `81/129/161` 帧，分辨率和计费基数与 v2 对齐为 `preview=6`、`small=12`、`standard=20`、`hd=30`，时长倍率为 `1x/2x/3x`；旧投稿 `512p/720p/1024p` 分别映射为 `preview/standard/hd`，`0.36 MP - Small` 映射为 `small`。
- **高级图生视频 (`ltx_video`)**：现已升级为 `lora_items` 多选协议。Bot FSM、Web 单图视频页、模板应用面板都会提交最多 3 个 LoRA 项，每项独立携带 `name + strength`；旧 `lora_name / lora_strength` 仍保留兼容入口，但不再是主文档口径。

### 1. 模型文件部署 (Deployment)
- **文件命名规范**：根据现有的探针逻辑，图生视频的 LoRA 模型在生成阶段分为高噪和低噪两个环节。新模型**必须**包含两个文件，并严格按照以下格式命名：
  - `{lora_name}_high_noise.safetensors`
  - `{lora_name}_low_noise.safetensors`
  - *(例如：如果你的模型代号叫 `Dance`，则需要提供 `Dance_high_noise.safetensors` 和 `Dance_low_noise.safetensors`)*
- 将上述两个文件放置到 ComfyUI 宿主机映射的对应 LoRA 模型目录中（如 `models/loras/`）。

### 2. Bot 层：更新用户交互菜单 (UI & FSM)
- **文件定位**：`src/handlers/fsm/image_to_video_fsm.py`
- **实施步骤**：
  - 找到存储模型映射的常量字典 `VIDEO_LORA_MODELS`（定义在 `src/lora_catalog.py`，由 `image_to_video_fsm.py` 渲染）。
  - 在字典中追加新模型配置：将**模型前缀名**（即上述的 `{lora_name}`，如 `"Dance"`）作为键，映射到用户可见的**中文按钮标签**（如 `"跳舞"`）。
  - 保存后，Telegram 机器人中的【图生视频】入口会在启动时展示同屏设置面板：第一组为附加模型按钮，第二组为“单图生成/添加终止帧”，第三组为 `preview/small/standard/hd` 分辨率档位，第四组为 `5s/8s/10s` 时长，第五组为确认。
  - 用户确认后再上传图片：单图模式收 1 张起始图，首尾帧模式依次收起始图和终止图，然后发送提示词提交。
  - 旧入口提供 `5s/8s/10s` 三档时长；菜单与 Web 投稿应用都应展示 v2 四档分辨率和三档时长。`/custom_video` 兼容入口应保持无 LoRA，避免把带 LoRA 的任务写成 `custom_video` 历史类型。

### 3. Backend 层：参数网关透传 (API Routing)
- **文件定位**：`backend/app/models.py` 和 `backend/app/main_simple_task_routes.py`。
- **实施状态**：**无需修改**。
  - 后端网关已经定义了 `VideoLoraRequest`。
  - 当前主 simple route 是 `/image_to_video`；兼容入口 `/perfect_video_lora` 仍会接收该请求，并统一**转化为 `TaskType.IMAGE_TO_VIDEO`** 推入 Redis 队列，同时将 `lora_name`、`resolution_preset`、`end_image`、`extract_last_frame=True` 等参数携带给下游 Worker。
  - `video_edit` 仍继续走 `perfect_video_edit.json`，用于其它快捷视频，不应混入旧图生视频 LoRA 逻辑。

### 4. Worker 层：工作流动态注入 (Workflow Patcher)
- **文件定位**：`workers/comfy_agent/workflow_task_patchers.py` 和 `workers/comfy_agent/workflows/Wan22AioV82.json`。
- **实施状态**：**通常无需修改**，但需注意**硬编码防爆红线**。
  - 主模型节点固定为 `2616`（high）和 `2617`（low）。patcher 会根据 `wan22_model_profile` 写入对应 high/low UNet 文件。
  - 旧 LoRA 注入节点固定为 `26`（high noise）和 `18`（low noise）：
    - `26.inputs.lora_1.lora = {lora_name}_high_noise.safetensors`
    - `18.inputs.lora_1.lora = {lora_name}_low_noise.safetensors`
  - 无 LoRA 的 `custom_video` 与 `wan22_video_v2` 必须清空 `26` / `18` 的 LoRA slot，避免 workflow 模板残留旧模型。
  - V82 通过 `265`（`FL_RIFE`，`multiplier=4`）对 `2603` 最终帧序列插帧；`_patch_wan22_aio_workflow(...)` 会在检测到 `265` 后让 `28` 视频输出、`2575` 帧数统计和 `2607` 尾帧提取都读取 `["265", 0]`，避免插帧被绕过或时长变慢。三档时长会写入 `2578.inputs.value`，保持 `5s/8s/10s` 对应 `81/129/161` 源帧。
  - 节点 `2612` 当前 DaSiWa 版本要求同时写入旧口径 `precision_presets` 和新口径 `resolution_preset`，并补齐 `swap_aspect_when_not_image=false`、`aspect_preset_when_not_image="9:16 - Social"`、`custom_aspect_width=16`、`custom_aspect_height=9`；否则 RunPod ComfyUI `/prompt` 会因缺必填输入拒绝工作流。节点 `2607` 的 `ImageFromBatch.batch_index` 必须保持 `4095`，不要改回旧模板里的 `16384`。
  - 扩展生成、分段重生成和整链拼接依赖 `extra_outputs.last_frame`。Worker 会优先读取 Comfy `2503` 尾帧输出；若个别 Comfy 实例只返回主 MP4，`agent_result_materialization.py` 会用 worker 镜像内的 `ffmpeg/ffprobe` 从主视频补抽最后一帧，因此 `workers/Dockerfile` 必须保留 ffmpeg 依赖。
  - > ⚠️ **节点硬编码警告**：如果后续重导 `Wan22AioV82.json`，必须复核 `2616`、`2617`、`26`、`18`、`2612`、`23`、`24`、`2368`、`2371`、`2578`、`2603`、`265`、`2575`、`2607` 是否仍满足当前补丁与 mappings 逻辑，否则主模型、LoRA、分辨率、首尾帧输入、时长、RIFE 插帧或尾帧输出会失效。

### 5. 验证与发布 (Testing & Restart)
- 上传好 `.safetensors` 模型文件后，重启 Bot 进程（以重载 `VIDEO_LORA_MODELS` 字典）。
- 在 Telegram 中唤起【图生视频】菜单，确认新添加的动作按钮出现在首个设置区；选择模型、帧模式和分辨率后点击“确定”。
- 观察 Worker (Agent) 的控制台日志，确认 `workflow_task_patchers.py` 成功将 `{lora_name}_high_noise.safetensors` 和 `{lora_name}_low_noise.safetensors` 注入到了 `26` 和 `18` 节点中，且 ComfyUI 能够正常加载文件并启动推理。
- 同时验证旧投稿一键应用：prompt 恢复、`[模型: xxx]` 能解析为 `lora_name`、`1024p` 映射 `hd`、`5s/8s/10s` 恢复和对应灵石消耗。

---

## 三、 高级图生视频 (`ltx_video`) 附加模型实施方案

### 1. 模型文件部署 (Deployment)
- 将 LTX-2.3 LoRA 文件直接放到 ComfyUI LoRA 目录，并保持与工作流节点中一致的**相对路径**，例如 `ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors`。
- 与普通图生视频不同，`ltx_video` 当前走的是**单文件直接注入**，不再要求 `{name}_high_noise / {name}_low_noise` 双文件命名。

### 2. Bot / Web 层：模型选单
- **文件定位**：`src/lora_catalog.py`、`src/handlers/fsm/ltx_video_fsm.py`、`frontend/src/views/SingleImageToVideo.vue`、`frontend/src/components/template-apply/TemplateImageToVideoPanel.vue`
- **实施步骤**：
  - 在 `src/lora_catalog.py` 的 `LTX_VIDEO_LORA_OPTIONS` 中新增模型条目，维护：
    - `path`：ComfyUI 可识别的相对路径
    - `label_zh` / `label_en`：前后端展示名称
    - `default_strength`：未显式传权重时的默认值
  - Telegram 高级图生视频 FSM 会先进入附加模型选择，再进入上传图片与填写提示词流程；当前允许多选，最多 3 个，并支持逐项调强度。
  - Web `SingleImageToVideo` 与模板应用面板复用同一批 LTX LoRA 选项；提交时主路径统一写入 `inputs.lora_items`，而不是单个 `inputs.lora_name`。

### 3. Backend 层：参数网关透传
- **文件定位**：`backend/app/models.py`
- **实施状态**：当前 `LtxVideoRequest` 已同时支持：
  - `lora_items: list[{name, strength}]`
  - 兼容字段 `lora_name` 与 `lora_strength`
- **说明**：新增 LTX LoRA 时通常无需新增 task type；重点是保持请求模型、前端提交协议与 worker patcher 的节点约定一致。

### 4. Worker 层：工作流动态注入
- **文件定位**：`workers/comfy_agent/workflow_patcher.py`、`workers/comfy_agent/workflows/LTX 2.3 I2V 6.1.json`
- **当前约定**：
  - 可选 LoRA 注入节点固定为 `256`（`Power Lora Loader (rgthree)`）。
  - 当请求带 `lora_items` 时，patcher 会按顺序写入 `lora_1..n = {on, lora, strength}`，并清理节点上残留的旧 slot。
  - 当前最大注入槽位为 3；超出的项不会继续下沉到工作流。
  - 当请求未带 `lora_items` 时，patcher 会回退兼容读取 `lora_name / lora_strength`；若最终仍无有效 LoRA，则直接裁掉节点 `256`，并把 `8.inputs.model` 回接到 `191`，保持原始无附加模型拓扑可运行。
  - 未显式传 `strength` 时，会回落到 `src/lora_catalog.py` 中登记的默认强度。
- > ⚠️ **节点硬编码警告**：若你重导出了 `LTX 2.3 I2V 6.1.json`，必须同步检查 `256`、`191`、`189`、`8` 这些节点 ID 是否仍满足当前补丁逻辑；否则需要同步修改 `workflow_patcher.py`。

### 5. 验证建议
- Telegram：进入【高级图生视频】后应先看到附加模型选择，再要求上传起始图。
- Web：`ltx_video` 页面和模板应用面板都应能提交 `inputs.lora_items`，并正确回显每个模型的当前强度。
- Worker：分别验证“多选 LoRA / 单个兼容字段 / 不选 LoRA”三种场景，确认多项注入成功、旧字段仍兼容、无 LoRA 时节点被裁剪后仍能正常出图出视频。
