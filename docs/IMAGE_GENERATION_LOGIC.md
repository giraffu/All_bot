# Bot 图生图与图生视频功能技术文档

本文档详细梳理了 Bot 中“图生图” (Image-to-Image) 和“图生视频” (Image-to-Video) 功能的调用逻辑、业务规则及底层架构。

## 1. 架构概览 (Architecture Overview)

Bot 的图像/视频生成功能采用分层架构设计，确保了业务逻辑、任务调度与底层 API 调用的解耦。

*   **Handler 层 (`src/handlers/message_handler.py`)**:
    *   **入口点**: 接收用户发送的图片、视频或命令。
    *   **状态管理**: 维护用户当前的会话模式 (Mode) 和待处理图片队列 (`pending_images`)。
    *   **分发**: 根据当前模式将请求分发给 `TaskService`。

*   **Service 层 (`src/services/`)**:
    *   **`TaskService` (`task_service.py`)**: 核心业务编排者。负责任务提交、配额扣除、进度监控 (Polling)、结果处理 (下载/保存) 以及向用户发送最终结果。
    *   **`ImageService` (`image_service.py`)**: API 调用的外观模式 (Facade) 封装，简化了对 API Client 的调用。

*   **Infrastructure 层 (`src/api_client.py`)**:
    *   **`APIClient`**: 处理与后端推理引擎的 HTTP 通信。
    *   **功能**: 包含文件上传 (支持本地文件及 MinIO 模板路径)、熔断机制 (`CircuitBreaker`)、重试逻辑 (`async_retry`) 和结果轮询。

## 2. 核心流程 (Core Process Flow)

无论是图生图还是图生视频，通过 `process_generation_task` 或特定任务处理函数，遵循以下通用流程：

1.  **接收输入**: 用户发送图片，Bot 将其保存到临时目录 (`TMP_DIR`)。
2.  **模式匹配**: 根据用户当前选择的模式 (如 `MODE_EDIT`, `MODE_CUSTOM_VIDEO`) 确定任务类型。
3.  **配额检查**: 检查用户灵石余额（图片消耗 2，视频消耗 6）。
4.  **任务提交**:
    *   构建请求参数（Prompt, Image, Resolution 等）。
    *   通过 `APIClient` 上传图片并调用对应后端接口。
5.  **异步轮询**: `TaskService` 启动循环，调用 `listen_for_progress` 监听任务状态。
    *   实时更新消息内容（显示排队位置或生成进度百分比）。
6.  **结果处理**:
    *   任务完成后，下载生成的媒体流。
    *   保存到本地及记录日志 (`UserLogger`)。
    *   扣除配额（如果尚未扣除）。
    *   发送结果给用户，并提供“公开/私密”选项。

## 3. 图生图功能 (Image-to-Image)

图生图功能主要通过 `submit_img2img` 和 `submit_face_swap` 接口实现。

### 3.1 功能模式与逻辑

| 模式名称 | 模式代码 | 逻辑描述 | 消耗灵石 |
| :--- | :--- | :--- | :--- |
| **自由P图** | `MODE_EDIT` | 用户发送一张图片 + 提示词。调用标准 img2img 接口。 | 2 |
| **快速脱衣** | `MODE_UNDRESS` | 预设提示词 (从 `prompts.ini` 读取)。用户仅需发送图片。 | 2 |
| **快速自慰** | `MODE_MASTURBATION` | 预设提示词。用户仅需发送图片。 | 2 |
| **快速换脸** | `MODE_FACESWAP` | **两步操作**: 1. 发送人脸图 -> 2. 发送身体图。调用 Face Swap 接口。 | 2 |
| **随机换脸** | `MODE_RANDOM_FACESWAP` | 用户发送人脸图。系统从 MinIO `quick_face/` 桶随机选取一张身体模板。 | 2 |

### 3.2 接口与参数 (`submit_img2img`)

*   **Endpoint**: `POST /img2img`
*   **关键参数**:
    *   `prompt`: 用户输入或预设提示词。
    *   `negative_prompt`: 默认包含质量控制词 (low quality, bad anatomy 等)。
    *   `num_inference_steps`: 固定为 `6`。
    *   `guidance_scale`: 固定为 `1.0`。
    *   `image`: 输入图片文件流。

### 3.3 换脸接口与参数 (`submit_face_swap`)

*   **Endpoint**: `POST /face_swap`
*   **关键参数**:
    *   `face_image`: 提供面部特征的图片。
    *   `body_image`: 提供身体结构的图片。

## 4. 图生视频功能 (Image-to-Video)

图生视频功能基于“首图+提示词”生成短视频，主要涉及 `submit_perfect_video_edit` 和 `submit_perfect_video_insert` 两个接口。

### 4.1 功能模式与逻辑

| 模式名称 | 模式代码 | 接口类型 | 逻辑描述 | 消耗灵石 |
| :--- | :--- | :--- | :--- | :--- |
| **自定义图生视频** | `MODE_CUSTOM_VIDEO` | `Edit` | 用户发送起始图片 + 自定义提示词。生成 5秒 视频。 | 6 |
| **动图传教士** | `MODE_PERFECT_VIDEO_INSERT` | `Insert` | 用户发送图片，使用预设 "missionary sex" 提示词。 | 6 |
| **动图后入** | `MODE_DOGGY_STYLE` | `Insert` | 用户发送图片，使用预设 "doggy style sex" 提示词。 | 6 |
| **口交黑人** | `MODE_BLOWJOB` | `Edit` | 用户发送图片，使用预设 "undress blowjob" 提示词。 | 6 |
| **脱衣吐舌** | `MODE_UNDRESS_TONGUE` | `Edit` | 用户发送图片，使用预设 "undress and show tongue" 提示词。 | 6 |
| **特写口交** | `MODE_CLOSEUP_BLOWJOB` | `Edit` | 用户发送图片，使用预设 "closeup blowjob sex" 提示词。 | 6 |

### 4.2 接口区别

*   **Perfect Video Edit (`submit_perfect_video_edit`)**:
    *   **用途**: 通用视频生成/编辑。适用于大多数基于提示词让图片动起来的场景。
    *   **参数**: `width`, `height` (根据用户等级动态调整), `length=81` (帧数), `prompt`, `image`.

*   **Perfect Video Insert (`submit_perfect_video_insert`)**:
    *   **用途**: 特定场景的视频插入/生成（如传教士、后入等特定体位）。可能涉及更复杂的控制网或特定模型路径。
    *   **参数**: 同上，但后端处理逻辑不同。

## 5. 规则与配置 (Rules & Configuration)

### 5.1 灵石消耗 (Quota)
*   **基础消耗**: 定义在 `src/constants.py` 的 `TASK_COSTS` 中。
    *   图片任务默认: **2 灵石**
    *   视频任务默认: **6 灵石**
*   **扣除时机**: 任务提交成功后扣除。如果任务失败或被拒绝，逻辑上应有回滚或不扣除机制（代码中是在提交后扣除，若配额不足则不提交）。

### 5.2 用户等级权益 (User Groups)
*   **分辨率**: 视频生成的分辨率取决于用户等级 (`VIDEO_RESOLUTIONS`)。
    *   普通用户使用默认分辨率。
    *   高级用户（如筑基期、金丹期）可能配置了更高分辨率。
*   **优先级**: 任务提交时携带 `priority` 参数。
    *   高等级用户拥有更高的任务优先级，在队列中排队更靠前。

### 5.3 文件处理
*   **临时文件**: 用户上传的图片暂存在本地 `TMP_DIR`，任务完成后尝试清理。
*   **模板文件**: 支持 `template:filename` 格式的路径，直接从 MinIO 读取模板文件，无需下载到本地，提高效率（用于随机换脸等功能）。

## 6. 代码索引 (Code Reference)

*   **入口处理**: [`src/handlers/message_handler.py`](../src/handlers/message_handler.py)
*   **任务编排**: [`src/services/task_service.py`](../src/services/task_service.py)
*   **服务外观**: [`src/services/image_service.py`](../src/services/image_service.py)
*   **API 客户端**: [`src/api_client.py`](../src/api_client.py)
*   **常量定义**: [`src/constants.py`](../src/constants.py)
