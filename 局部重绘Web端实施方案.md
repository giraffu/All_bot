# Web端“局部重绘”功能实施方案

基于现有的系统架构与提供的 `I2I_draw.json` 工作流，为了将“局部重绘”作为全新模式集成到 Web 端（练功房）且不影响 Telegram Bot 端，需要在“前端 - Web API - 内部网关 - 调度节点”四层结构中进行相应的扩展。

在审查系统代码后，纠正了之前方案中关于“前后端接口职责混淆”、“计费配置位置”、“API请求封装链路”以及“Linux文件大小写敏感”等核心问题，并针对画廊分享报错与 Worker 崩溃隐患进行了深度修正。以下是经过修正的**分阶段落地方案**：

## 🚨 核心架构纠错说明
1. **前后端接口职责边界**：
   - Web 用户的真实网关接口位于 `src/web_api/routers/tasks.py` (`POST /api/tasks/generate`)。
   - `backend/app/main.py` 仅作为内部 Worker 的通信网关，**不负责**处理 JWT 校验和用户计费。
2. **计费与常量配置**：
   - 所有的模式枚举、计费额度和任务分类都集中管理在 `src/constants.py` 文件中。配置字典键时必须使用声明的常量（如 `MODE_I2I_DRAW`）而非硬编码字符串。
3. **调度动态分发与网络请求**：
   - 新增任务需要通过 `src/core/task_dispatcher.py` 路由。
   - **注意图片与参数提取**：在派发层，前端传来的 `images` 数组已被处理并上传至 MinIO，真正的图片路径存放在 `inputs["saved_input_images"]` 列表中。
   - 真实的 HTTP 请求、断路器及 `X-Trace-ID` 注入由 `src/api_client.py` 负责，`src/services/image_service.py` 仅作外层封装。

---

## 📋 分阶段详细实施方案

### 阶段一：核心常量、服务派发与 Web 接口 (Core, Dispatcher & Web API)

1. **定义常量 (`src/constants.py`)**：
   - 增加模式声明：`MODE_I2I_DRAW = "i2i_draw"`。
   - 在 `TASK_COSTS` 字典中添加：`MODE_I2I_DRAW: 3`（设定消耗 3 灵石，注意使用常量作为 Key）。
   - 将 `MODE_I2I_DRAW` 加入 `GENERATION_TASK_TYPES` 列表，确保其计入每日生成限额。
   - **新增补充**：在 `MODE_NAME_MAP` 中添加映射 `MODE_I2I_DRAW: "task.mode_i2i_draw"`，防止在日志或特定 UI 查询时出现 KeyError。

2. **新增内部请求链路 (`config.py`, `src/api_client.py` & `src/services/image_service.py`)**：
   - **配置端** (`config.py`)：新增 `I2I_DRAW_ENDPOINT = f"{API_BASE}/i2i_draw"`。
   - **请求端** (`src/api_client.py`)：新增 `async def submit_i2i_draw(...)` 方法，使用 `self._request("POST", I2I_DRAW_ENDPOINT, json=data)` 发起带断路器与重试机制的请求。
   - **服务层** (`src/services/image_service.py`)：引入并暴露 `submit_i2i_draw` 方法。

3. **适配路由分发 (`src/core/task_dispatcher.py`)**：
   - 在 `DefaultImageStrategy.submit_task` 方法中增加条件分支：当 `self.mode in ["i2i_draw", MODE_I2I_DRAW]` 时，提取参数并调用 `image_service.submit_i2i_draw`（注意兼容字符串与常量传递）。
   - **关键细节**：
     - 提取图片路径必须使用 `inputs.get("saved_input_images", [])[0] if inputs.get("saved_input_images") else ""`。
     - **务必注意导入**：在文件头部 `from src.constants import (...)` 列表中补充导入 `MODE_I2I_DRAW`，避免使用该常量时引发 `NameError`。

### 阶段二：内部队列调度层 (Backend Worker API)

1. **定义请求结构 (`backend/app/models.py`)**：
   - 在 `TaskType` 枚举中新增：`I2I_DRAW = "i2i_draw"`。
   - 增加请求校验模型 `class I2IDrawRequest(BaseModel)`。该模式只需图片和提示词（注：也可直接复用现有的 `I2IProRequest`，因为字段完全一致）：
     ```python
     class I2IDrawRequest(BaseModel):
         task_id: str
         image: str
         prompt: str
         seed: Optional[int] = None
         priority: int = 0
     ```

2. **新增内部路由 (`backend/app/main.py`)**：
   - 新增 `@app.post("/i2i_draw", response_model=TaskResponse)` 接口。
   - 依赖注入 `queue_manager` 和内部 `token` 验证，提取参数后调用 `await queue_manager.enqueue_task(TaskType.I2I_DRAW, params, priority, task_id)` 将任务推入 Redis 队列。

### 阶段三：Comfy 节点动态注入层 (Agent Node)

1. **工作流确认与防范大小写敏感 (`workers/comfy_agent/workflow_patcher.py`)**：
   - 包含 LoRA 和 KSampler 等节点的 API 格式工作流文件 `I2I_draw.json` 已正确放置于 `workers/comfy_agent/workflows/` 目录下。
   - **⚠️ 核心修正**：在 `load_workflow` 函数中，必须显式添加映射：`elif task_type == "i2i_draw": filename = "I2I_draw.json"`。否则在 Linux 宿主机上会因为大小写敏感导致文件未找到。

2. **配置节点映射 (`workers/comfy_agent/workflows/mappings.json`)**：
   - 添加键 `"i2i_draw"`（需与上游队列传入的 `TaskType` 保持一致），并将后端传来的参数名映射到 `I2I_draw.json` 中的对应节点 ID。由于不需要反向提示词和 LoRA，只映射图片、提示词和种子：
     ```json
     "i2i_draw": {
         "image": "167",               // LoadImage 节点
         "prompt": "108",              // CLIPTextEncode (Positive)
         "prompt_input": "text",
         "seed": "138",                // KSampler
         "seed_input": "seed"
     }
     ```

3. **编写防爆补丁 (`workers/comfy_agent/workflow_patcher.py`)**：
   - 在 `patch_workflow` 函数中拦截 `i2i_draw` 任务类型。
   - **硬编码反向提示词**：因为前端不传负面提示词，需在代码中硬编码兜底。例如，直接给节点 109 的 text 赋值一个空格串 `" "`。
   - **LoRA 节点隔离与彻底删除**：该模式不允许选择附加 LoRA。必须在代码中固定执行“剪枝重连”——跳过 `144` 节点，将 `106` (UNETLoader) 的输出直接连接到下游节点（如 `138` KSampler），**并且必须显式安全删除该孤立节点（使用 `wf.pop("144", None)` 而非危险的 `del wf["144"]` 以防 Worker 崩溃）**。
   - **图片落盘与赋值验证**：Agent 取到图片后会自动落盘并替换节点参数，需要确保 `167` 节点的 `image` 参数值被正确覆盖。

### 阶段四：Web前端练功房 (Vue3 UI)

1. **拓展菜单选项**：
   - 在前端页面（如 `ImageAndPrompt.vue`），在任务类型切换区增加 `i2i_draw`（局部重绘）标签页。

2. **动态渲染极简表单**：
   - 当 `taskType === 'i2i_draw'` 时，控制上传组件严格限制 **仅能上传 1 张图片** (`maxImages = 1`)。
   - 仅渲染**正向提示词**输入框。
   - **移除** 反向提示词输入框和 LoRA 模型选择下拉框。

3. **发起请求与进度流**：
   - 点击生成后，组装参数并调用现有的通用 Web 接口 `POST /api/tasks/generate`，Body 形如：
     ```json
     {
       "task_type": "i2i_draw",
       "inputs": {
         "prompt": "用户输入的提示词",
         "images": ["base64_or_path"]
       }
     }
     ```
   - 请求成功拿到 `task_id` 后，系统原有的 SSE 流（Task Stream）与悬浮按钮（FAB）逻辑会自动接管排队查询与图片回显，无需修改即可直接展示“排队中”、“进度 X%”并在完成后加入图库历史，同时消耗 3 灵石。

### 阶段五：画廊发布白名单配置 (Gallery Publishing)

1. **允许作品发布到广场 (`src/web_api/routers/gallery.py` & `src/core/gallery_core.py`)**：
   - **核心问题**：若不配置白名单，用户在前端点击“发布到广场”时会被系统拦截并抛出 `CoreDomainError`。
   - **修复动作**：必须在这两个文件的 `ALLOWED_WEB_SUBMIT_TYPES` 集合/列表中，补充注入 `MODE_I2I_DRAW` 模式，确保局部重绘的作品能够正常分享。

2. **同步配置过滤下拉框暴露 (`src/web_api/routers/gallery.py`)**：
   - 在 `get_gallery_config` 接口返回的 `allowed_types` 列表中增加 `{"id": MODE_I2I_DRAW, "name": MODE_NAME_MAP.get(MODE_I2I_DRAW, "task.mode_i2i_draw")}`。
   - 确保前端画廊大厅的筛选器能够正确显示并支持按“局部重绘”类型进行检索过滤。