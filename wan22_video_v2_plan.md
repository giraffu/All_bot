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

### 2.1 当前状态总览

- 状态：`wan22_video_v2` 主链已完成并已同步到当前仓库
- 已落地范围：
  - Web 独立入口与独立页面
  - `/api/tasks/generate` 提交主链接入
  - backend 简单任务路由与请求模型
  - worker workflow patch 与 API 工作流接线
  - 主视频 + 尾帧辅助输出聚合
  - `History.extra_outputs` 持久化
  - `/tasks/result` 与历史接口透出 `extra_outputs`
  - Web 详情页与生成结果页显示尾帧

### 2.2 已验证结论

- 当前 API 工作流已经支持并已接入：
  - 正面提示词
  - 负面提示词
  - 起始帧
  - 终止帧
  - I2V / FLF2V 切换
  - color match
  - perfect loop
  - upscale（快速 2x）
  - extract_last_frame
  - 固定 5s
- 原先关于 `upscale` 与 `extract_last_frame` 的两个前置阻塞，现已解除：
  - `upscale` 已确认可由当前 API 工作流稳定控制
  - `extract_last_frame` 已确认可在 API 工作流中稳定产出，并已进入结果聚合链路
- 结果协议已不再是“单主结果”：
  - `workers/comfy_agent/agent_main.py` 已对 `wan22_video_v2` 强制主结果优先选 `videos`
  - `src/database/models.py` 的 `History` 已新增 `extra_outputs`
  - `src/web_api/services/task_result_service.py` 已返回 `extra_outputs`
  - `frontend/src/components/TaskDetailModal.vue` 与 `frontend/src/views/Wan22VideoV2.vue` 已支持尾帧展示 / 下载

### 2.3 与原计划不同的真实实现

- `wan22_video_v2` 在 worker 侧的布尔控制，并非继续依赖 UI 工作流里的 `DaSiWa_NodeStatusSwitch enabled = !bool` 方式。
- 当前真实实现是：
  - 在 `workflow_patcher.py` 中移除一批 UI-only 的 `DaSiWa_NodeStatusSwitch` / preview 节点
  - 直接重连 API 执行图，按用户开关改写最终使用的 frames 分支
  - 对 `extract_last_frame` 直接重建尾帧提取支路，而不是依赖 UI 导出残留 gate
- 因此，下文凡是仍写着“待确认”“接入前验证”“建议 patch enabled = !bool”的地方，都应以“当前真实实现”优先。

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
| `use_end_frame` | `bool` | `false=I2V`，`true=FLF2V` | `2557 -> 2613` | 实际仍写 `2557.inputs.value = !use_end_frame` | 非直觉 | 已落地并有单测；当未提供 `end_image` 时会自动回退 I2V |
| `color_match` | `bool` | 是否启用色彩匹配 | `2614 / 2612` | 实际通过改写下游 `clip_frames` / `video_frames_ref` 引用来切换 | 非直接布尔写入 | 当前实现不再依赖 `2615.enabled`，而是移除 UI-only switch 后直接重连分支 |
| `perfect_loop` | `bool` | 是否启用完美循环 | `2542/2574` 分支 | 实际通过 `video_frames_ref = ["2574", 0] or decoded_frames_ref` 切换 | 非直接布尔写入 | 当前实现不再依赖 `2584.enabled` |
| `upscale` | `bool` | 是否启用“快速 2x” | `2563/2575` 分支 | 实际通过 `final_frames_ref = ["2575", 0] or video_frames_ref` 切换 | 非直接布尔写入 | 已完成 API 实跑验证并落地 |
| `extract_last_frame` | `bool` | 是否同时输出最后一帧图片 | `2700 -> 2503` | `true` 时重建尾帧提取支路，`false` 时移除 `2503/2700` | 已确认 | 当前实现稳定，不再是“待补全” |

### 4.3 功能分支节点

| 功能 | 节点 | 说明 |
| --- | --- | --- |
| 单图视频 | `2545` | `WanImageToVideo` |
| 首尾帧视频 | `2530` | `WanFirstLastFrameToVideo` |
| I2V/FLF2V 切换 | `2613` | `ComfySwitchNode` |
| 色彩匹配 | `2614` | `ColorTransfer` |
| 完美循环链路 | `2542`、`2543`、`2541`、`2558`、`2574` | Loop 预处理、时序分析、插帧、组帧 |
| 主视频输出 | `28` | `VHS_VideoCombine` |
| 尾帧输出 | `2503` | `SaveImage`，现已通过 `2700 -> 2503` 支路稳定接入 |

## 5. 布尔极性红线

### 5.1 原始风险判断

以下节点在 UI 工作流中属于 `DaSiWa_NodeStatusSwitch`：

- `2573`
- `2584`
- `2615`

原始判断没有问题：它们在 UI 导出形态下很可能遵循 `enabled = true => bypass` 的反向语义。

### 5.2 当前真实处理方式

- 当前已落地实现没有继续在 API 运行图里依赖这些 UI-only switch。
- `workflow_patcher.py` 的真实策略是：
  - 直接移除这批 UI-only switch
  - 直接改写最终视频帧引用链
  - 让 `color_match`、`perfect_loop`、`upscale` 变成“分支重连”而不是“反向 enabled patch”
- 因此，这里的红线需要调整为：
  - 若未来再次依赖 UI 导出的 `DaSiWa_NodeStatusSwitch`，必须重新验证其极性
  - 但在当前已提交实现里，主逻辑不再依赖这套极性

### 5.3 当前测试覆盖

- `tests/workers/test_workflow_patcher.py` 已覆盖：
  - `use_end_frame` 切换
  - `color_match` 分支切换
  - `perfect_loop` 分支切换
  - `upscale` 分支切换
  - `extract_last_frame` 开关不会破坏主视频输出

## 6. `extract_last_frame` 的正式要求

### 6.1 产品语义

当 `extract_last_frame=true` 时：

- 主结果仍然是视频
- 同时额外保留一张最后一帧图片
- Web 详情页需要能查看或下载这张尾帧
- 历史、Gallery、投稿主媒体仍以视频为准

### 6.2 当前系统缺口

原始缺口已补齐，当前现状如下：

- `workers/comfy_agent/agent_main.py`
  - 已对 `wan22_video_v2` 强制主结果优先取 `videos`
  - 已新增尾帧辅助输出收集与上传逻辑
- `src/database/models.py`
  - `History` 已新增 `extra_outputs = Column(JSON, nullable=True)`
- `migrations/versions/f2b4c6d8e9f0_add_extra_outputs_to_history.py`
  - Alembic 迁移已存在
- `src/web_api/services/task_result_service.py`
  - 已返回 `extra_outputs`
- `src/web_api/schemas/user_schema.py`
  - `HistoryItem` 已暴露 `extra_outputs`
- `frontend/src/components/TaskDetailModal.vue`
  - 已渲染尾帧预览与下载按钮

### 6.3 当前已采用协议

- `History.output_file`：继续存主视频
- `History.extra_outputs`：保存附加输出
- 当前数据结构与原建议一致，等价于此前提议的 `extra_outputs_json`：

```json
{
  "last_frame": {
    "path": "result/xxx_last_frame.png",
    "media_type": "image"
  }
}
```

### 6.4 当前结果优先级规则

- 对 `wan22_video_v2` 已强制规定：
  - 主结果优先选 `videos`
  - 尾帧作为辅助结果收集进 `extra_outputs`
  - 绝不会因为 `SaveImage` 先被遍历到，就把整次任务识别成图片任务

## 7. `upscale=快速 2x` 的正式要求

本次需求里，`upscale` 的语义固定为：

- 仅对应 UI 原工作流里的 `Upscale 2x simple`
- 不对应：
  - `Upscale 2x with model`
  - `Upscale 2x with RTX SR`

因此本期不要把 `upscale` 设计成枚举，也不要做三选一；先收口成一个简单布尔。

当前状态：

- 上述验证已完成
- 当前提交版本已按 API 图真实可用分支接入
- 现实现不再依赖 `2573.enabled = !upscale` 这种 UI gate patch，而是直接切换最终输出帧链路

## 8. Phase 0：工作流预处理清单

状态：已完成。

当前代码侧已反映以下结果：

- `workers/comfy_agent/workflows/WAN 2.2 i2v -AiO.json` 已作为正式 API 运行文件接入
- `workers/comfy_agent/workflows/mappings.json` 已冻结关键字段映射
- `workflow_patcher.py` 已基于真实 API 可执行图完成 patch 逻辑
- `extract_last_frame` 与 `upscale` 都已有稳定实现与测试覆盖

建议导出后保留一份对照：

- UI 源文件：`workers/comfy_agent/wan2.2/DaSiWa WAN 2.2 i2v FastFidelity C-AiO-80.json`
- API 运行文件：`workers/comfy_agent/workflows/WAN 2.2 i2v -AiO.json`

## 9. wan22_video_v2 详细改造清单

以下按“从 Web 到 worker，再到历史与结果展示”的顺序列出。

### 9.1 前端

#### 必改

- `frontend/src/views/CustomFeatures.vue`
  - 状态：已完成
  - 已新增 `wan22_video_v2` 能力入口
  - 卡片文案已与 `ltx_video` 区分
- `frontend/src/router/index.ts`
  - 状态：已完成
  - 已采用方案 A，新增独立页面路由 `Wan22VideoV2`
- 新增独立页面，建议文件：
  - `frontend/src/views/Wan22VideoV2.vue`
  - 状态：已完成
  - 当前已实际落地为独立页面
- 页面交互要求：
  - 状态：已完成
  - 起始帧上传卡
  - 终止帧上传卡，可选
  - 正面提示词输入
  - 负面提示词输入
  - `use_end_frame` 开关
  - `color_match` 开关
  - `perfect_loop` 开关
  - `upscale` 开关
  - `extract_last_frame` 开关
  - 时长固定展示 `5 秒`

#### 推荐复用或扩展

- `frontend/src/features/generation/buildGenerationTaskPayload.ts`
  - 状态：已完成
  - 已支持 `negativePrompt`
  - 已支持 `extraInputs` 布尔开关透传
  - 已支持 `images` 双图语义
- `frontend/src/features/generation/imageToVideo.ts`
  - 状态：无需强依赖该文件完成主链；当前独立页已直接提交 `wan22_video_v2`
- `frontend/src/composables/useTaskFormat.ts`
  - 状态：已完成
  - 已增加类型标签名
- `frontend/src/utils/galleryTaskTypeFilters.ts`
  - 状态：本次提交未见专项改动，仍属可选优化项
- `frontend/src/components/TaskDetailModal.vue`
  - 状态：已完成
  - 已支持展示与下载辅助尾帧

#### 文案

- `shared/locales/zh.json`
- `shared/locales/en.json`

状态：部分完成。

- 已补：
  - 新功能标题
  - 功能描述文案
  - 类型标签名
- 仍可继续优化：
  - 表单字段名 i18n
  - 开关提示文案 i18n
  - 尾帧说明文案 i18n

### 9.2 Core / 提交编排

#### 必改

- `src/constants.py`
  - 状态：已完成
  - 已新增 `MODE_WAN22_VIDEO_V2 = "wan22_video_v2"`
  - 已补 `MODE_NAME_MAP`
  - 已补 `TASK_COSTS`
  - 已补 `GENERATION_TASK_TYPES`
  - 已补 `VIDEO_TASK_TYPES`
- `src/core/task_dispatcher.py`
  - 状态：已完成
  - 已新增 `Wan22VideoV2Strategy`
  - 已从 `saved_input_images` 拆 `image` / `end_image`
  - 已归一化负面词
  - 已固定 `length = 5`
  - 已透传所有布尔字段
  - 已实现 `end_image` 缺失时自动回退 I2V
- `src/services/image_service.py`
  - 状态：已完成
  - 已新增 `submit_wan22_video_v2_task(...)`
- `src/api_client.py`
  - 状态：已完成
  - 已新增 `submit_wan22_video_v2(...)`
  - 已接入新执行面 endpoint 常量

#### 推荐单测

- `tests/core/test_task_dispatcher.py`
  - 状态：已完成
  - 已覆盖：
    - 双图时 `use_end_frame=true`
    - `end_image` 缺失时自动回退 I2V
    - 固定 `length=5`
    - 所有布尔字段透传正确

### 9.3 Backend 执行面

#### 必改

- `backend/app/models.py`
  - 状态：已完成
  - 已新增：
    - `TaskType.WAN22_VIDEO_V2`
    - `Wan22VideoV2Request`
  - 请求字段已齐全
- `backend/app/main_simple_task_routes.py`
  - 状态：已完成
  - 已新增 `SIMPLE_TASK_TYPE_MAP` 映射
  - 已新增路由 `/api/v1/wan22_video_v2`
- `backend/app/queue_manager.py`
  - 状态：主链已通
  - 当前未见针对 `wan22_video_v2` 的专项分支改动，但由于 queue manager 按通用任务类型入队，现有主链已可正常工作

#### 推荐单测

- `tests/backend/test_queue_manager.py`
  - 状态：未见新增专项覆盖，仍可补充
- `tests/backend/test_main_helpers.py`
  - 状态：已新增路由映射与注册层面的覆盖

### 9.4 Worker / Workflow

#### 必改

- `src/workflow_mapping_validation.py`
  - 状态：已完成
  - 已新增 `"wan22_video_v2": "WAN 2.2 i2v -AiO.json"`
- `workers/comfy_agent/workflows/mappings.json`
  - 状态：已完成
  - 关键直连映射已补齐
  - 布尔复杂逻辑仍由 patcher 接管
- `workers/comfy_agent/workflow_patcher.py`
  - 状态：已完成
  - 已新增 `elif task_type == "wan22_video_v2":`
  - 已实现：
    - prompt / negative prompt 写入
    - 起始帧 / 终止帧写入
    - 固定 `length = 5`
    - `use_end_frame` 切换
    - `color_match` 分支切换
    - `perfect_loop` 分支切换
    - `upscale` 分支切换
    - `extract_last_frame` 支路重建与关闭时裁剪
    - 输出节点唯一 `filename_prefix`
  - 真实实现以“移除 UI-only switch + 直接重连 API 图”为主

#### 强制单测

- `tests/workers/test_workflow_patcher.py`
  - 状态：已完成
  - 已覆盖：
    - I2V / FLF2V 切换
    - color match 分支切换
    - perfect loop 分支切换
    - upscale 分支切换
    - `extract_last_frame` 打开与关闭时的行为
    - 输出文件前缀与尾帧分支裁剪

### 9.5 Worker 结果聚合

这是本需求最容易漏掉的层。

#### 必改

- `workers/comfy_agent/agent_main.py`
  - 状态：已完成
  - 已为 `wan22_video_v2` 增加多输出聚合逻辑
  - 已对 `wan22_video_v2` 设定主结果优先选 `videos`
  - 已将尾帧作为辅助输出上传并回传

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

当前状态：已采用方案 A。

### 9.6 历史持久化与结果协议

#### 必改

- `src/database/models.py`
  - 状态：已完成
  - 实际实现为 `extra_outputs = Column(JSON, nullable=True)`
  - Alembic 迁移已补
- `src/web_api/services/task_result_service.py`
  - 状态：已完成
  - 已返回 `extra_outputs`
- `src/web_api/schemas/task_schema.py`
  - 状态：已完成
  - `TaskResultResponse` 已扩展 `extra_outputs`
- `src/web_api/services/history_response_builder.py`
  - 状态：已完成
  - 已透传辅助输出
- `src/web_api/schemas/user_schema.py`
  - 状态：已完成
  - `HistoryItem` 已新增 `extra_outputs`
- `src/web_api/services/apply_context_service.py`
  - 状态：本次未见专项改动，仍属后续扩展项

#### 推荐单测

- `tests/web_api/test_tasks_result.py`
- `tests/web_api/test_history_response_builder.py`

状态：部分完成。

- `tests/web_api/test_tasks_result.py` 已覆盖：
  - `wan22_video_v2` 主结果是视频
  - 辅助结果包含尾帧图片
- `tests/web_api/test_history_response_builder.py`
  - 当前未在本次同步清单中确认到专项新增覆盖，可继续补强

### 9.7 前端结果与历史展示

#### 必改

- `frontend/src/components/TaskDetailModal.vue`
  - 状态：已完成
  - 已增加“尾帧预览 / 下载”区块
- `frontend/src/views/History.vue`
  - 状态：未完成 / 非主链阻塞
  - 当前未见“含尾帧”列表标签
- `frontend/src/composables/useTaskResult.ts`
  - 状态：已完成
  - 结果数据结构已支持辅助输出
- `frontend/src/stores/taskResultState.ts`
  - 状态：已完成
  - 已支持 `extra_outputs` 结果恢复与轮询收口
- `frontend/src/stores/tasksRuntime.ts`
  - 状态：已完成
  - 已支持 `extraOutputs` 持久化恢复

#### 推荐展示规则

- 详情页默认展示主视频
- 若存在 `extra_outputs.last_frame`：
  - 展示缩略图
  - 提供单独下载按钮
- 不要把尾帧替代主视频封面逻辑，除非未来产品明确要求

当前状态：已按该规则实现。

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

当前状态补充：

- `tests/core/test_task_dispatcher.py`：已覆盖核心提交归一化
- `tests/workers/test_workflow_patcher.py`：已覆盖 worker 关键 patch 行为
- `tests/web_api/test_tasks_result.py`：已覆盖主结果 + 尾帧协议
- 前端状态层相关测试文件已在上次提交中同步，但页面级交互测试仍可继续补

## 12. 实施顺序建议

该实施顺序对应的主线工作已基本完成。

当前剩余更像“收尾优化项”：

1. 补 `History.vue` 的“含尾帧”列表标签（如仍需要）
2. 评估 `apply_context_service.py` 是否要回填 `wan22_video_v2` 专属开关
3. 继续补页面级前端交互测试与 i18n 细化

## 13. 当前最关键阻塞

原先两个关键阻塞均已解除：

- 阻塞 1：`extract_last_frame` 在 API 工作流中的稳定支路与连线，已确认并已落地
- 阻塞 2：`upscale` 对应的“快速 2x”链路，已确认并已落地

当前不再属于“编码前阻塞”，而是“后续可选优化项”：

- 优化 1：历史列表页是否增加“含尾帧”标签
- 优化 2：`apply_context_service.py` 是否支持回填 `wan22_video_v2` 专属参数
- 优化 3：继续补全前端页面级自动化测试与文案国际化
