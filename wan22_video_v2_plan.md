# WAN22 Video V2 字段映射与改造清单

## 1. 目标范围

- 新增一个仅 Web 端可用的全新任务类型：`wan22_video_v2`
- 采用工作流：`workers/comfy_agent/workflows/WAN 2.2 i2v -AiO.json`
- 功能范围：
  - 正面提示词
  - 负面提示词
  - 1 张起始帧，或 2 张首尾帧
  - `use_end_frame` 控制 `I2V` / `FLF2V`
  - `color_match`
  - `perfect_loop`
  - `upscale`，语义固定为“快速 2x”
  - `extract_last_frame`，语义固定为“同时保留主视频和最后一帧图片”
  - 固定只支持 `5s`

## 2. 先决结论

- 当前 API 工作流已经明确支持：
  - 正面提示词
  - 负面提示词
  - 起始帧
  - 终止帧
  - I2V / FLF2V 切换
  - color match
  - perfect loop
  - 固定 5s
- 当前 API 工作流对 `upscale=快速2x` 的支持，按节点拓扑判断可接，但必须在接入前做一次 API 实跑验证。
- 当前 API 工作流对 `extract_last_frame` 不能直接判定为“已可接入”。
  - UI 原工作流有该开关。
  - 当前 API 导出文件里只看到 `SaveImage` 节点，没有看到稳定、完整的尾帧开关与连线语义。
  - 因此必须先做一轮工作流重导出或节点确认，再进入编码。
- 即使工作流最终能同时产出 `mp4 + png`，现有系统结果链路也只支持“单主结果”：
  - `workers/comfy_agent/agent_main.py` 当前只选第一个输出资源
  - `src/database/models.py` 的 `History` 只有 `output_file`
  - `src/web_api/services/task_result_service.py` 当前只返回一个 `result_url`
  - 因此 `extract_last_frame=true` 不能只改 workflow，必须同时改结果聚合和历史展示协议

## 3. 推荐对外契约

### 3.1 Web 提交契约

建议 Web 仍沿用统一 `/api/tasks/generate` 主链，但新增独立 `task_type`：

```json
{
  "task_type": "wan22_video_v2",
  "inputs": {
    "images": [
      "bot-data/web_uploads/start.png",
      "bot-data/web_uploads/end.png"
    ],
    "prompt": "positive prompt",
    "negative_prompt": "negative prompt",
    "use_end_frame": true,
    "color_match": true,
    "perfect_loop": false,
    "upscale": true,
    "extract_last_frame": true,
    "duration": 5
  },
  "priority": 0
}
```

说明：

- `images[0]` 是起始帧，必填
- `images[1]` 是终止帧，可选
- `use_end_frame=false` 时走单图 `I2V`
- `use_end_frame=true` 时走双图 `FLF2V`
- `duration` 在前端固定写死为 `5`，不暴露给用户修改

### 3.2 Dispatcher 归一化契约

`task_dispatcher` 内部建议归一化为：

```json
{
  "image": "start.png",
  "end_image": "end.png",
  "prompt": "...",
  "negative_prompt": "...",
  "use_end_frame": true,
  "color_match": true,
  "perfect_loop": false,
  "upscale": true,
  "extract_last_frame": true,
  "length": 5
}
```

说明：

- Web 层继续保留 `inputs.images`
- Dispatcher 负责拆出 `image` 和 `end_image`
- Worker 侧不要再依赖“猜第二张图是不是尾帧”，而是使用显式字段

## 4. 字段到节点正式对照表

下表按“推荐 worker 入参 -> 当前 API 工作流节点”的口径整理。

### 4.1 高置信映射

| 字段 | 推荐类型 | 语义 | 当前 API 节点 | 输入名 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `prompt` | `string` | 正面提示词 | `2368` | `value` | 节点标题为 `WAN22 Video prompt positive` |
| `negative_prompt` | `string` | 负面提示词 | `2371` | `value` | 节点标题为 `WAN22 Video prompt negative` |
| `image` | `string` | 起始帧 object key | `23` | `image` | `LoadImage`，下游进入 `2561` 缩放 |
| `end_image` | `string?` | 终止帧 object key | `24` | `image` | `LoadImage`，下游进入 `2529` 缩放 |
| `length` | `int` | 固定视频时长秒数 | `2586` | `value` | 当前固定为 `5`，前端不开放 |

### 4.2 布尔控制映射

| 字段 | 推荐类型 | 用户语义 | 当前 API 节点 | 建议 patch 点 | 极性说明 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| `use_end_frame` | `bool` | `false=I2V`，`true=FLF2V` | `2557 -> 2613` | 写 `2557.inputs.value = !use_end_frame` | 非直觉 | `2557` 当前默认 `true`，而 `2613` 标题为 `I2V - FLF2V switch` |
| `color_match` | `bool` | 是否启用色彩匹配 | `2615 -> 2614` | 写 `2615.inputs.enabled = !color_match` | 反向 | `2615` 是 `DaSiWa_NodeStatusSwitch`，当前导出呈现为“默认旁路关闭功能” |
| `perfect_loop` | `bool` | 是否启用完美循环 | `2584 -> 2542/2543/2541/2558/2574` | 写 `2584.inputs.enabled = !perfect_loop` | 反向 | 控制 loop 裁剪、补帧、拼装分支 |
| `upscale` | `bool` | 是否启用“快速 2x” | `2573 -> 2563/2564/2565/2575` | 写 `2573.inputs.enabled = !upscale` | 反向 | 按拓扑判断该组节点即“快速 2x”链路，接入前要实跑验证 |
| `extract_last_frame` | `bool` | 是否同时输出最后一帧图片 | `待补全` | `待补全` | `待确认` | UI 原工作流有该功能，但当前 API 导出未保留为稳定可接形态 |

### 4.3 功能分支节点

| 功能 | 节点 | 说明 |
| --- | --- | --- |
| 单图视频 | `2545` | `WanImageToVideo` |
| 首尾帧视频 | `2530` | `WanFirstLastFrameToVideo` |
| I2V/FLF2V 切换 | `2613` | `ComfySwitchNode` |
| 色彩匹配 | `2614` | `ColorTransfer` |
| 完美循环链路 | `2542`、`2543`、`2541`、`2558`、`2574` | Loop 预处理、时序分析、插帧、组帧 |
| 主视频输出 | `28` | `VHS_VideoCombine` |
| 尾帧输出 | `2503` | `SaveImage`，但当前 API 文件内连线不可信，需重导出确认 |

## 5. 布尔极性红线

以下节点不是普通布尔开关，而是 `DaSiWa_NodeStatusSwitch`：

- `2573`
- `2584`
- `2615`

当前 API 导出表现是：

- `enabled = true`
- `trigger_on = "true → active"`
- `action = "bypass"`

这意味着它们极大概率遵循以下语义：

- `enabled = true`：触发 bypass，功能关闭
- `enabled = false`：不 bypass，功能开启

所以 worker patch 层不能把用户布尔值原样写入，必须做反向转换：

```text
node.inputs.enabled = !user_bool
```

这部分必须加单测，不能靠肉眼判断。

## 6. `extract_last_frame` 的正式要求

### 6.1 产品语义

当 `extract_last_frame=true` 时：

- 主结果仍然是视频
- 同时额外保留一张最后一帧图片
- Web 详情页需要能查看或下载这张尾帧
- 历史、Gallery、投稿主媒体仍以视频为准

### 6.2 当前系统缺口

现状是单输出协议：

- `workers/comfy_agent/agent_main.py`
  - `RESULT_ASSET_KEYS = ("images", "gifs", "videos")`
  - `_pick_first_output_asset(...)` 只取第一个资源
- `src/database/models.py`
  - `History` 只有 `output_file`
- `src/web_api/services/task_result_service.py`
  - 仅返回单个 `result_url`
- `src/web_api/schemas/user_schema.py`
  - `HistoryItem` 仅暴露 `output_file` / `output_file_url`
- `frontend/src/components/TaskDetailModal.vue`
  - 仅渲染单个视频或单张图片

### 6.3 推荐协议

建议新增“附加输出”字段，而不是覆盖主视频：

- `History.output_file`：继续存主视频
- 新增 `History.extra_outputs_json` 或等价字段
- 内容建议：

```json
{
  "last_frame": {
    "path": "result/xxx_last_frame.png",
    "media_type": "image"
  }
}
```

### 6.4 结果优先级规则

对 `wan22_video_v2` 强制规定：

- 主结果优先选 `videos`
- 尾帧作为辅助结果收集进 `extra_outputs_json`
- 绝对不能因为 `SaveImage` 比 `VideoCombine` 先被遍历到，就把整次任务识别成图片任务

## 7. `upscale=快速 2x` 的正式要求

本次需求里，`upscale` 的语义固定为：

- 仅对应 UI 原工作流里的 `Upscale 2x simple`
- 不对应：
  - `Upscale 2x with model`
  - `Upscale 2x with RTX SR`

因此本期不要把 `upscale` 设计成枚举，也不要做三选一；先收口成一个简单布尔。

但编码前必须完成以下验证：

- 在 ComfyUI 本地用当前 API 工作流实跑一次
- 验证 `2573` 这一组目标节点是否真的控制了快速 2x
- 若验证失败，必须重新导出 API 工作流，确保快速 2x 的 gate 在 API 文件中可稳定访问

## 8. Phase 0：工作流预处理清单

在进入代码开发前，先完成以下工作流层面的清理：

- 重新导出 `WAN 2.2 i2v -AiO.json`，确保是 API Format，而不是 UI Format
- 清空模板里残留的示例图片名
- 清空模板里残留的示例正负提示词
- 确认 `extract_last_frame` 的 gate 在 API 文件中存在且可 patch
- 确认 `upscale fast 2x` 的 gate 在 API 文件中存在且可 patch
- 记录所有最终节点 ID，冻结为实现契约

建议导出后保留一份对照：

- UI 源文件：`workers/comfy_agent/wan2.2/DaSiWa WAN 2.2 i2v FastFidelity C-AiO-80.json`
- API 运行文件：`workers/comfy_agent/workflows/WAN 2.2 i2v -AiO.json`

## 9. wan22_video_v2 详细改造清单

以下按“从 Web 到 worker，再到历史与结果展示”的顺序列出。

### 9.1 前端

#### 必改

- `frontend/src/views/CustomFeatures.vue`
  - 新增 `wan22_video_v2` 能力入口
  - 卡片文案建议与 `ltx_video` 区分，避免用户误解
- `frontend/src/router/index.ts`
  - 方案 A：新增独立页面路由，例如 `Wan22VideoV2`
  - 方案 B：复用现有 `SingleImageToVideo`，但会导致页面逻辑过于分叉，不推荐
- 新增独立页面，建议文件：
  - `frontend/src/views/Wan22VideoV2.vue`
  - 理由：当前 `SingleImageToVideo.vue` 只支持单图上传，不适合硬塞双图、负面词和多开关
- 页面交互要求：
  - 起始帧上传卡
  - 终止帧上传卡，可选
  - 正面提示词输入
  - 负面提示词输入
  - `use_end_frame` 开关
  - `color_match` 开关
  - `perfect_loop` 开关
  - `upscale` 开关
  - `extract_last_frame` 开关
  - 时长只展示固定 `5 秒`，不允许修改

#### 推荐复用或扩展

- `frontend/src/features/generation/buildGenerationTaskPayload.ts`
  - 如继续复用统一 payload builder，需要扩充：
    - `negativePrompt`
    - `boolean toggles`
    - `images` 支持 2 张语义
- `frontend/src/features/generation/imageToVideo.ts`
  - 新增任务类型识别
  - 不要把 `wan22_video_v2` 折叠成 `custom_video`
- `frontend/src/composables/useTaskFormat.ts`
  - 增加类型标签中文名
- `frontend/src/utils/galleryTaskTypeFilters.ts`
  - 若希望归到图生视频分组，需要增加 grouped alias
- `frontend/src/components/TaskDetailModal.vue`
  - 支持展示辅助尾帧入口

#### 文案

- `shared/locales/zh.json`
- `shared/locales/en.json`

至少补：

- 新功能标题
- 描述文案
- 表单字段名
- 开关提示文案
- 尾帧说明文案

### 9.2 Core / 提交编排

#### 必改

- `src/constants.py`
  - 新增 `MODE_WAN22_VIDEO_V2 = "wan22_video_v2"`
  - 补 `MODE_NAME_MAP`
  - 补 `TASK_COSTS`
  - 补 `GENERATION_TASK_TYPES`
  - 补 `VIDEO_TASK_TYPES`
- `src/core/task_dispatcher.py`
  - 新增 `Wan22VideoV2Strategy`
  - 负责：
    - 从 `inputs.images` 拆 `image` / `end_image`
    - 归一化负面词
    - 固定 `length = 5`
    - 把布尔字段透传到执行面
- `src/services/image_service.py`
  - 新增 `submit_wan22_video_v2_task(...)`
- `src/api_client.py`
  - 新增 `submit_wan22_video_v2(...)`
  - 新增新执行面 endpoint 常量

#### 推荐单测

- `tests/core/test_task_dispatcher.py`
  - 覆盖：
    - 单图时 `use_end_frame=false`
    - 双图时 `use_end_frame=true`
    - `end_image` 缺失时自动回退 I2V
    - 固定 `length=5`
    - 所有布尔字段透传正确

### 9.3 Backend 执行面

#### 必改

- `backend/app/models.py`
  - 新增：
    - `TaskType.WAN22_VIDEO_V2`
    - `Wan22VideoV2Request`
  - 字段至少包括：
    - `task_id`
    - `image`
    - `end_image: Optional[str]`
    - `prompt`
    - `negative_prompt: Optional[str]`
    - `use_end_frame: bool`
    - `color_match: bool`
    - `perfect_loop: bool`
    - `upscale: bool`
    - `extract_last_frame: bool`
    - `length: int = 5`
    - `priority: int = 0`
- `backend/app/main_simple_task_routes.py`
  - 新增 `SIMPLE_TASK_TYPE_MAP` 映射
  - 新增路由，例如：
    - `/api/v1/wan22_video_v2`
- `backend/app/queue_manager.py`
  - 确认新 `TaskType` 能正常入队、出队和统计

#### 推荐单测

- `tests/backend/test_queue_manager.py`
  - 覆盖新任务类型排队与分发

### 9.4 Worker / Workflow

#### 必改

- `src/workflow_mapping_validation.py`
  - 新增：
    - `"wan22_video_v2": "WAN 2.2 i2v -AiO.json"`
- `workers/comfy_agent/workflows/mappings.json`
  - 补直连映射：
    - `image -> 23.image`
    - `end_image -> 24.image`
    - `prompt -> 2368.value`
    - `negative_prompt -> 2371.value`
    - `length -> 2586.value`
  - 不建议把布尔复杂逻辑全部塞进纯 mapping，布尔仍由 patcher 接管
- `workers/comfy_agent/workflow_patcher.py`
  - 新增 `elif task_type == "wan22_video_v2":`
  - 负责：
    - 写 prompt / negative prompt
    - 写起始帧 / 终止帧
    - 固定 `length = 5`
    - `use_end_frame -> 2557.value = !use_end_frame`
    - `color_match -> 2615.enabled = !color_match`
    - `perfect_loop -> 2584.enabled = !perfect_loop`
    - `upscale -> 2573.enabled = !upscale`
    - `extract_last_frame` 的最终节点 patch，前提是完成 API 重导出确认
    - 为输出节点写唯一 `filename_prefix`

#### 强制单测

- `tests/workers/test_workflow_patcher.py`
  - 覆盖：
    - I2V / FLF2V 切换
    - color match 极性
    - perfect loop 极性
    - upscale 极性
    - `extract_last_frame` 打开时不会破坏主视频输出

### 9.5 Worker 结果聚合

这是本需求最容易漏掉的层。

#### 必改

- `workers/comfy_agent/agent_main.py`
  - 为 `wan22_video_v2` 增加“多输出聚合”逻辑
  - 不能继续复用 `_pick_first_output_asset(...)` 的单结果策略
  - 新逻辑建议：
    - 主结果优先取 `videos`
    - 如果存在尾帧图片，则作为辅助输出一起上传
    - 上传后返回：
      - 主视频路径
      - 尾帧路径

#### 推荐实现方式

- 方案 A，推荐：
  - 扩展完成上报协议，向后端回传：

```json
{
  "result": "main_video.mp4",
  "extra_outputs": {
    "last_frame": "last_frame.png"
  }
}
```

- 方案 B，不推荐：
  - 只上报主视频，把尾帧直接丢弃
  - 这会违背本期需求

### 9.6 历史持久化与结果协议

#### 必改

- `src/database/models.py`
  - `History` 需新增可选字段，例如：
    - `extra_outputs_json = Column(Text, nullable=True)`
  - 需要 Alembic 迁移
- `src/web_api/services/task_result_service.py`
  - 返回值需补：
    - `extra_outputs`
- `src/web_api/schemas/task_schema.py`
  - `TaskResultResponse` 需扩展：
    - `extra_outputs: Optional[dict]`
- `src/web_api/services/history_response_builder.py`
  - `HistoryItem` 需透传辅助输出
- `src/web_api/schemas/user_schema.py`
  - `HistoryItem` 新增：
    - `extra_outputs`
- `src/web_api/services/apply_context_service.py`
  - 若未来允许模板应用该能力，需要定义是否将 `use_end_frame/color_match/perfect_loop/upscale` 一起回填

#### 推荐单测

- `tests/web_api/test_tasks_result.py`
- `tests/web_api/test_history_response_builder.py`

重点覆盖：

- `wan22_video_v2` 主结果是视频
- 辅助结果包含尾帧图片
- 无尾帧时 `extra_outputs` 为空

### 9.7 前端结果与历史展示

#### 必改

- `frontend/src/components/TaskDetailModal.vue`
  - 在主视频预览之外，增加“尾帧预览 / 下载”区块
- `frontend/src/views/History.vue`
  - 如需要在列表卡片上标识“含尾帧”，可新增小标签
- `frontend/src/composables/useTaskResult.ts`
  - 扩展结果数据结构，支持辅助输出

#### 推荐展示规则

- 详情页默认展示主视频
- 若存在 `extra_outputs.last_frame`：
  - 展示缩略图
  - 提供单独下载按钮
- 不要把尾帧替代主视频封面逻辑，除非未来产品明确要求

## 10. 必改文件 Top 20

按优先级排序：

1. `workers/comfy_agent/workflows/WAN 2.2 i2v -AiO.json`
2. `workers/comfy_agent/workflows/mappings.json`
3. `workers/comfy_agent/workflow_patcher.py`
4. `workers/comfy_agent/agent_main.py`
5. `src/workflow_mapping_validation.py`
6. `src/constants.py`
7. `src/core/task_dispatcher.py`
8. `src/services/image_service.py`
9. `src/api_client.py`
10. `backend/app/models.py`
11. `backend/app/main_simple_task_routes.py`
12. `src/database/models.py`
13. `src/web_api/services/task_result_service.py`
14. `src/web_api/schemas/task_schema.py`
15. `src/web_api/services/history_response_builder.py`
16. `src/web_api/schemas/user_schema.py`
17. `frontend/src/views/CustomFeatures.vue`
18. `frontend/src/router/index.ts`
19. `frontend/src/views/Wan22VideoV2.vue`
20. `frontend/src/components/TaskDetailModal.vue`

## 11. 测试建议

### 11.1 Worker 侧

- `wan22_video_v2` 单图 + `use_end_frame=false`
- `wan22_video_v2` 双图 + `use_end_frame=true`
- `color_match=true/false`
- `perfect_loop=true/false`
- `upscale=true/false`
- `extract_last_frame=true` 时主视频仍优先

### 11.2 Web API 侧

- `/api/tasks/generate` 接受 `wan22_video_v2`
- 历史返回主视频和辅助尾帧
- `/tasks/result` 返回 `extra_outputs`

### 11.3 前端

- 表单双图模式切换
- 负面提示词透传
- 开关 payload 正确
- 详情页正确展示主视频和尾帧

## 12. 实施顺序建议

按风险从高到低建议分 6 步：

1. 先重导出并冻结 `WAN 2.2` API 工作流
2. 完成 worker patch 与本地单测
3. 完成执行面和 task_dispatcher 接线
4. 完成结果聚合与历史协议扩展
5. 完成前端页面与结果展示
6. 补回归测试和文案

## 13. 当前最关键阻塞

在真正编码前，必须先解决这两个阻塞：

- 阻塞 1：确认 `extract_last_frame` 在 API 工作流中的稳定 gate 和连线
- 阻塞 2：确认 `upscale` 对应的 API 节点确实是“快速 2x”而不是别的缩放链

如果这两个阻塞没有解决，直接编码会导致：

- 开关逻辑反向
- 尾帧开关失效
- 主视频被尾帧覆盖
- 结果页拿错资源
