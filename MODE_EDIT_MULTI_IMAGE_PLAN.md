# “自由P图”模式多参考图融合（1-3张）全链路改造方案

## 1. 业务目标与核心策略
**目标**：允许用户在 Telegram Bot 的“自由P图”（`MODE_EDIT`）模式下，发送 1-3 张图片作为参考图，最终融合生成图片。
**核心策略**：采用 **策略 B（动态剪裁 JSON）**。在 ComfyUI 工作流 JSON 中预埋 3 个 `LoadImage` 及其缩放节点，但在向 ComfyUI 提交任务前，Python 层的 `WorkflowPatcher` 会根据用户实际上传的图片数量，**动态删除**多余的输入连线和未使用的节点，确保模型不会收到空输入或占位图的干扰，保持生图质量。

---

## 2. 改造步骤与代码分析

### 2.1 工作流 JSON 改造 (ComfyUI 端)
**目标文件**：`workers/comfy_agentX/workflows/Qwen-Rapid-AIO.json`
*   **当前状态**：`TextEncodeQwenImageEditPlus`（节点 3）只有 `image1` 输入，连接到节点 10（等比缩放），节点 10 连接到节点 8（`LoadImage`）。
*   **修改动作**：
    1.  在 JSON 中复制两套类似节点 8 和 10 的结构，作为图 2 和图 3 的输入链路。
        *   例如：新增节点 `20` (`LoadImage` -> `image2`) 和节点 `21` (`ImageScaleToTotalPixels`)。
        *   新增节点 `30` (`LoadImage` -> `image3`) 和节点 `31` (`ImageScaleToTotalPixels`)。
    2.  将节点 `3` (`TextEncodeQwenImageEditPlus`) 的输入扩展，增加 `image2` 和 `image3`，分别连线到节点 21 和 31 的输出。

### 2.2 Bot 交互层改造 (Telegram Bot)
**目标文件**：`src/handlers/message_handler.py`
*   **当前状态**：`_handle_photo_edit` 会提示用户只能发一张图；`handle_prompt` 会强制截取 `valid_images = [valid_images[-1]]`。
*   **修改动作**：
    1.  **交互提示修改**：在 `_handle_photo_edit` 中，当 `pending_count` 为 1 时，提示：“📥 已收到第 1 张参考图。您可以继续发送（最多 3 张），或直接发送提示词 (Text) 开始生成。” 当数量达到 3 时，提示：“✅ 已达到 3 张上限。请直接发送提示词 (Text) 开始生成。”
    2.  **移除强制截断**：在 `handle_prompt` 的执行生成逻辑中，将 `valid_images = [valid_images[-1]]` 修改为保留最多 3 张：`valid_images = valid_images[-3:]`。
    3.  **参数透传**：`task_service.process_generation_task` 接口已支持 `images: list[str]`，无需修改其签名，只需将包含 1-3 个路径的 `valid_images` 传入即可。

### 2.3 API 网关与中控层改造 (FastAPI)
**目标文件**：
*   `backend/app/models.py` (API 端请求模型)
*   `src/api_client.py` (Bot 端请求)
*   **当前状态**：API 端不再接收物理文件流上传，而是接收包含 MinIO `Object Key` 的 JSON Payload。当前 `Img2ImgRequest` 模型硬编码了 `image: str` 和 `image2: Optional[str] = None`。
*   **修改动作**：
    1.  **API 端请求模型更新**：将 `backend/app/models.py` 中的 `Img2ImgRequest` 更新为支持多图列表，例如新增 `images: Optional[List[str]] = None`（为了向后兼容其他旧端，可保留原有的 `image` 字段）。
    2.  **Bot 端提交逻辑**：修改 `src/api_client.py` 中的 `submit_img2img`，不再手动分离 `image` 和 `image2`，而是直接将包含 1-3 个路径的 `image_paths` 列表封装在 JSON Payload 的 `images` 字段中发送给中控 API。
    3.  **调度层透传**：`backend/app/main.py` 接收到 JSON 后直接转为字典存入 Redis 任务队列，此部分调度逻辑无需改动。

### 2.4 Agent 节点与动态补丁改造 (Worker)
**目标文件**：
*   `workers/comfy_agentX/agent_main.py`
*   `workers/comfy_agentX/workflow_patcher.py`
*   **当前状态**：`agent_main.py` 目前是针对 `image` 和 `image2` 字段进行硬编码串行下载。`workflow_patcher.py` 已支持 `mappings.json` 精确映射，但缺乏针对孤立节点的动态剪裁能力。
*   **修改动作**：
    1.  **Agent 端并发下载**：在 `agent_main.py` 的 `process_task` 中，检查 `params.get("images", [])` 列表，使用 `asyncio.gather` 并发从 MinIO 下载所有参考图。下载并上传到 ComfyUI 后，将本地文件名按顺序赋值给 `params["image"]`, `params["image2"]`, `params["image3"]`，以便无缝兼容底层现有的扁平映射结构。
    2.  **智能 Patcher 逻辑（核心策略 B 的实现）**：
        在 `workflow_patcher.py` 的 `patch_workflow` 中，针对 `img2img` 任务增加特定防御性清理逻辑：
        *   依赖 `mappings.json` 显式定义 `image1_node_id`, `image2_node_id`, `image3_node_id`。
        *   **动态剪裁**：判断实际传入的图片数量。如果只传入了 1 张：
            1. 从 `TextEncodeQwenImageEditPlus`（节点 3）的 `inputs` 字典中强行 `pop("image2")` 和 `pop("image3")`。
            2. （可选但强烈推荐）从整个工作流的 `nodes` 字典中彻底删除多余的 `LoadImage` 节点（如节点 20, 30）和对应的缩放节点（如节点 21, 31），保持工作流纯净，杜绝报错。

---

## 3. 风险评估与注意事项
1.  **兼容性风险**：API 接口签名从单文件改为多文件列表时，可能会影响系统中其他调用该接口的遗留逻辑。建议在 API 层做好向后兼容（例如既支持 `image` 也支持 `images`）。
2.  **内存与显存消耗**：同时编码 3 张参考图会成倍增加 CLIP Vision 的计算量，可能会导致显存峰值升高。需要在测试服压测 3 图融合时的显存占用情况。
3.  **Patcher 的健壮性**：动态删除 JSON 节点时，必须确保完全清理干净（包括 `inputs` 连线和节点定义本身），否则 ComfyUI 解析时会报“找不到节点”的错误。建议优先删除 `TextEncodeQwenImageEditPlus` 上的输入键，ComfyUI 通常会自动忽略未连接的孤立节点。