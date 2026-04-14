# 图生视频 LoRA 注入接口使用指南 (`/perfect_video_lora`)

本文档记录了 `perfect_video_lora` 接口的调用方法、设计原理以及部署使用时的注意事项，供后续功能研发与 Bug 排查参考。

## 1. 接口说明

该接口是在原有 `perfect_video_edit` 基础上扩展而来的，旨在不影响现有服务、不修改现有任务类型的前提下，动态向 ComfyUI 工作流中注入一对 LoRA 模型（高噪与低噪模型）。

*   **API 端点**: `POST /perfect_video_lora`
*   **请求类型**: `application/json`
*   **鉴权方式**: `Authorization: Bearer <your_token>`

### 1.1 请求 Body 参数 (`VideoLoraRequest`)

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| `image` | string | 是 | 无 | 输入图像的文件名（通常是已上传到 MinIO 的 Object Key）。 |
| `prompt` | string | 是 | 无 | 视频生成的正向提示词。 |
| `lora_name` | string | 是 | 无 | **核心参数**：要注入的 LoRA 模型的**基础名称**（不带后缀）。 |
| `width` | integer | 否 | 512 | 生成视频的宽度。 |
| `height` | integer | 否 | 512 | 生成视频的高度。 |
| `length` | integer | 否 | 81 | 生成视频的帧数长度。 |
| `priority` | integer | 否 | 0 | 任务在 Redis 队列中的优先级。 |

### 1.2 请求示例

以调用名为 `Cum` 的 LoRA 模型为例：

```json
POST /perfect_video_lora
Authorization: Bearer my_secret_token
Content-Type: application/json

{
  "image": "user_uploads/img_123.png",
  "prompt": "detailed description of the cum scene...",
  "lora_name": "Cum", 
  "width": 512,
  "height": 512,
  "length": 81,
  "priority": 10
}
```

## 2. 架构设计原理 (核心必读)

为了实现**热更新**与**向后兼容**，该接口采用了**“类型复用 + 启发式注入”**的策略：

1.  **中控 API 侧的伪装**：
    在 `backend/app/main.py` 中，当收到 `/perfect_video_lora` 请求时，API 会将该任务作为 `TaskType.VIDEO_EDIT` 推入 Redis 队列。
2.  **Agent 侧的无缝接单**：
    因为任务被标记为了 `video_edit`，现有的 Worker（例如配置了 `SUPPORTED_TASK_TYPES=video_insert,video_edit` 的 `comfy_agent2`）会像拉取普通任务一样拉取它，**完全不需要修改 Worker 的 `.env` 或重启 Worker。**
3.  **动态节点注入**：
    当 Worker 的 `workflow_patcher.py` 加载 `perfect_video_edit.json` 模板时，它会扫描请求参数。如果发现 `lora_name` 参数，会触发启发式补丁逻辑：
    *   找到 `class_type` 为 `Power Lora Loader (rgthree)` 的节点。
    *   根据预设的 `node_id`（272 为高噪，273 为低噪），自动拼接后缀并注入：
        *   `Node 272` -> `{lora_name}_high_noise.safetensors`
        *   `Node 273` -> `{lora_name}_low_noise.safetensors`

## 3. ComfyUI 服务器部署要求

根据上述注入规则，如果你的 `lora_name` 传的是 `Footjob`，ComfyUI 节点会强制去加载以下两个文件。

**因此，你必须在 ComfyUI 的 `models/loras/` 目录下存放成对的文件：**

1.  `Footjob_high_noise.safetensors`
2.  `Footjob_low_noise.safetensors`

**⚠️ 注意事项：**
*   **大小写敏感**：Linux 系统下文件系统区分大小写，`Footjob` 和 `footjob` 是两个不同的文件。请确保 API 传入的 `lora_name` 与磁盘上的文件名基础部分完全一致。
*   **单模型变通方案**：如果你的 LoRA 模型只有一个单体文件（例如只有一个 `Footjob.safetensors`），为了适配这个双节点加载的工作流，最简单的方法是**将该文件复制一份并重命名**，凑齐 `_high_noise.safetensors` 和 `_low_noise.safetensors` 这两个文件。

## 4. 故障排查指南

| 错误现象 | 可能原因 | 解决策略 |
| :--- | :--- | :--- |
| **调用 API 后，任务立即变成 `error` 状态** | ComfyUI 拦截了不合法的参数，最常见的是找不到对应的 LoRA 模型。 | 通过 `/status/{task_id}` 查询任务状态，查看 `error` 字段。如果报错类似于 `Prompt failed validation: lora Cum_high_noise.safetensors not found`，请检查 ComfyUI 服务器 `models/loras/` 目录下的文件名是否拼写错误或缺失。 |
| **生成的视频没有 LoRA 的风格特征** | 工作流中的节点 ID 发生了变更，导致启发式注入失效。 | 检查对应的 `perfect_video_edit.json`，确认加载 LoRA 的两个 `Power Lora Loader (rgthree)` 节点的 ID 是否依然是 `272` 和 `273`。如果修改了工作流，需要同步更新 `workflow_patcher.py`。 |
| **任务一直 Pending** | 没有任何 Worker 支持 `video_edit` 任务，或者 Worker 全部离线。 | 检查各个 Worker 的 `.env` 文件，确保至少有一个 Worker 的 `SUPPORTED_TASK_TYPES` 包含 `video_edit` 或为空。检查 Worker 的日志确保它正常连通了主控 API 和 Redis。 |