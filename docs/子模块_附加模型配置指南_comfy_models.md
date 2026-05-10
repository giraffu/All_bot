# 子模块: 附加模型部署与配置指南 (ComfyUI Add-on Models)

本指南汇总了在现有分层解耦架构（Bot 交互 -> Backend 队列 -> Comfy Agent 调度）下，新增各种附加模型（如 LoRA、ControlNet 等）的实施方案。

整个过程主要是一个**配置驱动**的过程，无需重构核心逻辑。下面分别介绍“图生图”与“图生视频”附加模型的具体配置路径。

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
  - **编写动态补丁**：若该模型为**用户可选**（非全局强制加载），需在 `workflow_patcher.py` 中补充防爆逻辑：当检测到任务参数未携带该模型时，通过脚本动态**删除该节点**并**重新缝合**工作流上下文连线（如将 Checkpoint 的连线绕过该节点直接连向下游）。
    > ⚠️ **节点硬编码警告**：由于当前 `workflow_patcher.py` 中的节点剪枝和重连高度依赖硬编码的节点 ID（例如图生图逻辑中写死了 ID 为 `32` 的节点为 LoRA 节点，ID 为 `2` 的节点为 KSampler），如果在更新模板时节点 ID 发生变化，务必同步修改代码中的防爆硬编码逻辑，否则会导致连线断裂！
    > 💡 **格式排障**：如果在导出 JSON 时误导出了 UI 格式（包含 `"nodes"` 数组），Agent 的日志会输出 `Workflow xxx.json seems to be in UI format` 警告。请确保使用 ComfyUI 的 `Save (API Format)` 按钮导出。

### 5. 验证与发布 (Testing & Restart)
- 遵循部署规范，通过 `docker-compose up -d comfy-agent-1` 等指令平滑重载对应的 Agent 容器以读取新 JSON，并重启 Bot 进程。
- 在 Telegram 中唤起图生图菜单，验证新按钮渲染、参数透传是否成功，并在后台观察 ComfyUI 是否成功加载该 `.safetensors` 文件。

---

## 二、 新增图生视频附加模型（LoRA）实施方案

图生视频底层复用了 `video_edit`（自定义图生视频）的工作流和任务队列，通过动态注入 `lora_name` 参数来实现差异化。
目前系统主要支持 LTX-2.3 和 Wan2.1 视频生成工作流。关于 LTX-2.3 工作流的具体 LoRA 使用与提示词规范，请参考项目根目录的 `LTX_LoRA_Guide.md`。

### 1. 模型文件部署 (Deployment)
- **文件命名规范**：根据现有的探针逻辑，图生视频的 LoRA 模型在生成阶段分为高噪和低噪两个环节。新模型**必须**包含两个文件，并严格按照以下格式命名：
  - `{lora_name}_high_noise.safetensors`
  - `{lora_name}_low_noise.safetensors`
  - *(例如：如果你的模型代号叫 `Dance`，则需要提供 `Dance_high_noise.safetensors` 和 `Dance_low_noise.safetensors`)*
- 将上述两个文件放置到 ComfyUI 宿主机映射的对应 LoRA 模型目录中（如 `models/loras/`）。

### 2. Bot 层：更新用户交互菜单 (UI & FSM)
- **文件定位**：`src/handlers/fsm/video_lora_fsm.py`
- **实施步骤**：
  - 找到存储模型映射的常量字典 `LORA_MODELS`。
  - 在字典中追加新模型配置：将**模型前缀名**（即上述的 `{lora_name}`，如 `"Dance"`）作为键，映射到用户可见的**中文按钮标签**（如 `"跳舞"`）。
  - 保存后，Telegram 机器人中的【图生视频(附加模型)】菜单会自动渲染出这个新按钮。

### 3. Backend 层：参数网关透传 (API Routing)
- **文件定位**：`backend/app/models.py` 和 `backend/app/main.py`。
- **实施状态**：**无需修改**。
  - 后端网关已经定义了 `VideoLoraRequest`。
  - 在 `main.py` 中，接口 `/perfect_video_lora` 会接收该请求，并**将其转化为 `TaskType.VIDEO_EDIT`** 推入 Redis 队列，同时将 `lora_name` 携带在参数中透传给下游 Worker。

### 4. Worker 层：工作流动态注入 (Workflow Patcher)
- **文件定位**：`workers/comfy_agent/workflow_patcher.py` 和 `workers/comfy_agent/workflows/perfect_video_edit.json`。
- **实施状态**：**通常无需修改**，但需注意**硬编码防爆红线**。
  - **原理解析**：在 `workflow_patcher.py` 的 `heuristic_patch` 方法中，系统会根据传入的 `lora_name` 动态寻找类型为 `Power Lora Loader (rgthree)` 的节点：
    - 若节点 ID 为 `272`，则动态注入 `{lora_name}_high_noise.safetensors`。
    - 若节点 ID 为 `273`，则动态注入 `{lora_name}_low_noise.safetensors`。
  - > ⚠️ **节点硬编码警告**：如果你后续在 ComfyUI 本地调试并更新了图生视频的基础工作流模板（`perfect_video_edit.json`），**绝对不能改变这两个 LoRA 加载节点（rgthree）的 ID（必须保持为 272 和 273）**。一旦节点 ID 发生改变，Python 代码将无法找到对应的注入点，导致附加动作模型彻底失效！

### 5. 验证与发布 (Testing & Restart)
- 上传好 `.safetensors` 模型文件后，重启 Bot 进程（以重载 `LORA_MODELS` 字典）。
- 在 Telegram 中唤起【图生视频(附加模型)】菜单，点击新添加的动作按钮。
- 观察 Worker (Agent) 的控制台日志，确认 `workflow_patcher.py` 成功将 `{lora_name}_high_noise.safetensors` 和 `{lora_name}_low_noise.safetensors` 注入到了 `272` 和 `273` 节点中，且 ComfyUI 能够正常加载文件并启动推理。
