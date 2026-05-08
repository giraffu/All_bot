# Web端“局部重绘”功能实施方案

基于现有的系统架构与提供的 `I2I_draw.json` 工作流，为了将“局部重绘”作为全新模式集成到 Web 端（练功房）且不影响 Telegram Bot 端，需要在“前端 - 网关 - 队列 - 调度节点”四层结构中进行相应的扩展。

以下是详细的实施方案：

## 1. 核心定义层 (Constants & Core)
首先需要在核心层定义新的任务类型，以保证计费、锁并发和路由的一致性。

*   **新增任务类型**：在 `src/constants.py` 或公共模型定义中，为“局部重绘”新增一个枚举值，例如 `TaskType.WEB_INPAINT` 或 `TaskType.I2I_DRAW`。
*   **配置权限与计费**：在 `task_core.py` 或 `billing_core.py` 中，为该任务类型配置默认的灵石消耗量（如 1 个灵石）以及最大并发数限制（当前系统默认为 `MAX_CONCURRENT_TASKS = 3`）。

## 2. 后端网关 API (FastAPI)
在 `backend/app/main.py` 及 `backend/app/models.py` 中新增处理 Web 端请求的接口和数据结构。

*   **定义请求模型 (Pydantic)**：
    ```python
    class I2IDrawRequest(BaseModel):
        image: str  # Base64 格式的参考图
        prompt: str
        negative_prompt: Optional[str] = ""
        lora_name: Optional[str] = None
        # 可选扩展参数，如 seed, denoise 等
    ```
*   **新增路由接口**：
    新增 `POST /api/generate/i2i-draw`。该接口需：
    1.  校验 JWT 权限（获取 `internal_user_id`）。
    2.  调用 `task_core.check_and_deduct_credits` 扣除灵石，及检查 `check_concurrency_lock`。
    3.  将图片 Base64、提示词等参数组装为 Task Payload，并附带 `TaskType.I2I_DRAW`。
    4.  通过 `QueueManager` 推入 Redis 任务队列，并立即返回生成的 `task_id`。

## 3. 调度与工作节点 (Comfy Agent)
Agent 层是动态注入的核心，需适配 `I2I_draw.json` 的具体节点逻辑。

*   **部署工作流**：将 `I2I_draw.json` 放入 `workers/comfy_agent/workflows/` 目录下。
*   **更新映射字典 (`mappings.json`)**：
    根据 `I2I_draw.json` 的节点结构，在 `mappings.json` 中添加针对新模式的映射关系：
    ```json
    "I2I_DRAW": {
        "image": "167",               // LoadImage 节点
        "prompt": "108",              // CLIPTextEncode (Positive)
        "negative_prompt": "109",     // CLIPTextEncode (Negative)
        "lora_name": "144",           // LoraLoaderModelOnly
        "seed": "138"                 // KSampler
    }
    ```
*   **完善动态补丁 (`workflow_patcher.py`)**：
    *   **LoRA 节点防爆隔离**：`I2I_draw.json` 中的 LoRA 节点为 `144`。如果前端用户未选择 LoRA（即 `lora_name` 为空），必须在代码中动态执行“剪枝重连”——跳过 `144` 节点，将 `106` (UNETLoader) 直接连接到下游节点（在此工作流中为 `138` KSampler），否则 ComfyUI 会因找不到模型报错。
    *   **图片落盘机制**：Agent 取到 Base64 图片后，会自动落盘并替换 `167` 节点中的 `image` 参数值。

## 4. Web端练功房 (Vue3 Frontend)
前端需新增入口，并复用或扩展原有的生图组件（遵循 Vue3 Composition API 和 TS 规范）。

*   **扩展菜单栏**：在生成页面的 Tab 切换区（如 `ImageAndPrompt.vue` 或外部组件），新增“局部重绘 (Inpaint)”的标签页。
*   **表单与布局**：
    *   **图片上传器**：限制 `maxImages = 1`。由于不同任务共用组件，应根据 `taskType === 'i2i_draw'` 动态计算 `maxImages`（依据知识库记忆）。
    *   **参数配置区**：提供提示词 (Prompt)、反向提示词的文本框。提供 LoRA 模型下拉框（调用后端的 `/api/models/lora` 接口获取）。
*   **状态与请求**：
    *   提交表单时，将图片转为 Base64，调用新建的 `/api/generate/i2i-draw` 接口。
    *   拿到 `task_id` 后，复用全局的任务 SSE 流（SSE Task Stream）获取排队/生成进度，结合现有的 Floating Action Button (FAB) 显示 `第 X 位` 或 `进度 X%`，完成后回显图片并展示于图库/历史。

## 5. 潜在问题与确认项 (风险提示)
在实际开发前，请务必确认以下工作流相关的疑点：
1.  **硬编码节点 ID 预警**：目前 Agent 的防爆逻辑高度依赖节点 ID。由于 `I2I_draw.json` 的 LoRA ID 为 `144`，不同于原图生图的 `32`，修改 `workflow_patcher.py` 时要特别注意做条件分支隔离，不要影响原有的业务流。