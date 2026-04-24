# 自由P图与图生图（附加模型）功能分析报告

本文档对系统中的“自由P图”（`edit` / `img2img`）与“图生图（附加模型）”（`img2img_lora`）两大功能进行详细梳理，涵盖用户操作流程、任务流、数据流以及系统架构图。

## 1. 系统架构图 (System Architecture Diagram)

这两个功能共享同一套底层生成链路（均使用 `Qwen-Rapid-AIO.json` 工作流），区别在于前置 FSM（状态机）交互与 LoRA 节点的动态路由控制。

```mermaid
graph TD
    subgraph Client
        User[Telegram 用户]
    end

    subgraph "Core Bot Service (Telegram Bot)"
        FSM[FSM 状态机机制]
        EditFSM[edit_image_fsm<br/>自由P图]
        LoraFSM[img2img_lora_fsm<br/>图生图附加模型]
        TaskService[TaskService<br/>任务调度与鉴权]
        Billing[Billing Core<br/>扣费与并发锁]
    end

    subgraph "Databases & Storage"
        PG[(PostgreSQL<br/>用户/流水/任务)]
        Redis[(Redis<br/>队列/锁/PubSub)]
        MinIO[(MinIO<br/>对象存储)]
    end

    subgraph "Central API Backend"
        API_Img2Img[POST /api/img2img]
        API_Lora[POST /api/img2img_lora]
        QueueMgr[Queue Manager]
    end

    subgraph "ComfyUI Worker (comfy_agent)"
        Worker[Agent Poller]
        Patcher[Workflow Patcher<br/>动态修改 JSON]
        Comfy[本地 ComfyUI 服务]
    end

    User -->|发送指令/图片/文本| FSM
    FSM --> EditFSM
    FSM --> LoraFSM
    EditFSM --> TaskService
    LoraFSM --> TaskService

    TaskService <-->|检查并扣费| Billing
    Billing <--> PG
    Billing <--> Redis
    TaskService -->|上传输入图片| MinIO
    
    TaskService -->|提交任务| API_Img2Img
    TaskService -->|提交任务| API_Lora
    
    API_Img2Img --> QueueMgr
    API_Lora --> QueueMgr
    QueueMgr -->|入队| Redis

    Worker -->|轮询取任务| Redis
    Worker -->|下载图片| MinIO
    Worker -->|配置注入| Patcher
    Patcher -->|Qwen-Rapid-AIO.json| Comfy
    Comfy -->|输出图片| Worker
    Worker -->|上传结果| MinIO
    Worker -->|完成回调| QueueMgr
    QueueMgr -->|Pub/Sub 广播| Redis
    TaskService -->|监听完成事件| Redis
    TaskService -->|下载并发送| User
```

## 2. 用户操作流程 (User Operation Flow)

用户在 Telegram 端与 Bot 交互时的界面操作流向。

### 2.1 自由P图 (Free Edit)
```mermaid
stateDiagram-v2
    [*] --> 触发功能: 点击"🎨 自由P图" 或发送文字
    触发功能 --> WAIT_REFERENCE_IMAGES: Bot提示请发送参考图
    
    WAIT_REFERENCE_IMAGES --> WAIT_PROMPT: 用户发送第1张图片
    WAIT_PROMPT --> WAIT_PROMPT: 用户发送第2张图片(双图融合, 费用增至6)
    
    WAIT_PROMPT --> 提交任务: 用户发送提示词(Text)
    提交任务 --> [*]: 校验余额，进入后台生成，发送预计消耗
```

### 2.2 图生图附加模型 (Img2Img with LoRA)
```mermaid
stateDiagram-v2
    [*] --> 触发功能: 点击"🖼️ 图生图(附加模型)" 或发送文字
    触发功能 --> WAIT_LORA_SELECTION: Bot展示LoRA选项键盘
    
    WAIT_LORA_SELECTION --> WAIT_IMAGE: 用户点击选择LoRA(如"无", "逼真")
    WAIT_IMAGE --> WAIT_PROMPT: 用户发送1张参考图
    
    WAIT_PROMPT --> 提交任务: 用户发送提示词(Text)
    提交任务 --> [*]: 校验余额，进入后台生成，发送预计消耗
```

## 3. 任务流 (Task Flow)

从任务产生到销毁的全生命周期运转流程。

```mermaid
sequenceDiagram
    participant User as 用户
    participant Bot as TG Bot (TaskService)
    participant DB as PostgreSQL
    participant Redis as Redis (Locks/Queue)
    participant MinIO as MinIO Storage
    participant API as Central API
    participant Worker as Comfy Worker

    User->>Bot: 完成FSM交互(图片+提示词+模型配置)
    Bot->>DB: 查询用户身份并创建/更新 (UserCore)
    Bot->>Redis: 检查单用户并发锁 (check_concurrency_lock)
    Bot->>DB: 扣除对应的灵石并生成 user_logs (预扣费)
    Bot->>MinIO: 将本地 `/tmp` 下的图片上传，获得 Object Key
    Bot->>DB: 注册任务 (TaskRegistry)
    
    alt 是自由P图
        Bot->>API: POST /api/img2img (携带多图Key和提示词)
    else 是图生图附加模型
        Bot->>API: POST /api/img2img_lora (额外携带 lora_name)
    end
    
    API->>Redis: 将任务包裹后压入 comfy:queue:pending
    Worker->>Redis: 轮询取出待处理任务
    Worker->>MinIO: 下载 Object Key 对应的原图
    Worker->>Worker: WorkflowPatcher 加载 Qwen-Rapid-AIO.json
    
    alt 包含有效 lora_name
        Worker->>Worker: 注入 LoRA 节点 (ID:32), 设置名称与强度(0.3)
    else 无 lora_name (自由P图)
        Worker->>Worker: 移除节点 32，将 KSampler(2) 直连 Checkpoint(1)
    end
    
    Worker->>Worker: 注入提示词(ID:3)、图片(ID:8/20/30)和宽高
    Worker->>Worker: 清理冗余节点(如未传入image2/3则断开连线)
    Worker->>ComfyUI: 提交最终 JSON 执行推理
    ComfyUI-->>Worker: 返回生成的图片
    Worker->>MinIO: 上传生成结果，获得新 Object Key
    Worker->>API: HTTP 回调任务完成 (TaskStatus.COMPLETED)
    API->>Redis: 触发 Pub/Sub 广播 (comfy:task_events)
    
    Bot->>Redis: 监听到任务完成，释放用户并发锁
    Bot->>DB: 更新 TaskRegistry 状态
    Bot->>MinIO: 根据输出的 Object Key 下载结果图
    Bot->>User: 发送最终图片并提示耗时
```

## 4. 数据流 (Data Flow)

说明在各个服务间流转的数据实体及变化机制。

1. **输入媒体流（Input Media Flow）**：
   - **Telegram Client** -> 上传至 Telegram 服务器 -> **VPS Local API** 暴露本地绝对路径 (`/var/lib/telegram-bot-api/...`)。
   - **Bot (FSM)** -> 通过 `httpx` 下载至本地 `/tmp/bot_fsm_tmp/`。
   - **TaskService** -> 将本地文件异步上传至 **MinIO**（通常为 `comfyui-input` 桶），将其转化为轻量级的 `Object Key`（如 `comfyui-input/abc.png`）。此后内部系统**不再直接传输二进制流**，大幅节省内网带宽。
   - **Worker** -> 接收到 JSON 任务后，根据 `Object Key` 从 MinIO 拉取文件供 ComfyUI 使用。

2. **参数配置流（Configuration Flow）**：
   - **Bot 组装**：通过 FSM 收集到 `prompt`, `image_paths` (List), `lora_name`, `lora_strength`。
   - **API 传递**：封装在 `Img2ImgRequest` / `Img2ImgLoraRequest` 的 JSON body 中转发给 Redis 队列。
   - **Worker 动态修补 (Workflow Patcher)**：
     - 基础文件为 `Qwen-Rapid-AIO.json`。
     - **自由P图 (`task_type="img2img"`)**：因为没有传入 `lora_name`，Patcher 会将 JSON 中 ID 为 `32` 的 LoRA 节点强行删除，并重新修正节点连线（将采样器直接连到大模型）。
     - **图生图附加模型 (`task_type="img2img_lora"`)**：如果指定了 LoRA（如 `qwen/YARN_1.0.safetensors`），Patcher 会在 ID 为 `32` 的节点中动态写入模型名，并将强度 `strength_model` 设为 `0.3`。
     - **多图融合容错**：如果不满足 2 张或 3 张图片，Patcher 会自动断开 `TextEncodeQwenImageEditPlus` 节点中多余的图片输入连线，避免 ComfyUI 报 400 格式错误。

3. **输出媒体流（Output Media Flow）**：
   - **ComfyUI** -> 输出至本地 `output` 文件夹。
   - **Worker** -> 上传至 **MinIO**（`comfyui-temp` 或 `bot-data` 桶），获得生成的 `Object Key`。
   - **Bot** -> 接收到包含新 `Object Key` 的完成事件，从 MinIO 下载流。
   - **Bot** -> 调用 Telegram Local API (`send_photo` / `send_document`) 发送给用户终端。

## 5. 关键业务红线与特点
- **隔离与解耦**：Bot 端不关心具体的节点 ID 和连线，只需负责调用 API 传入高维度的参数（图片、提示词、LoRA名）。底层 JSON 解析脏活全由 `workers/comfy_agent/workflow_patcher.py` 负责。
- **动态图处理**：无论是单图、双图（消耗 6 灵石）还是指定 LoRA 模型，底层共用同一个全能工作流模板 `Qwen-Rapid-AIO.json`，极大地降低了维护多套 JSON 的成本。
- **防内存溢出**：利用 `is_maintenance_mode()` 与 `check_concurrency_lock` 实现防并发与队列压垮机制；图片以 `to_thread` 形式异步上传，防止阻塞主协程。
