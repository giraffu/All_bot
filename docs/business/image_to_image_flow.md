# 图生图 (Image-to-Image) 业务流与架构分析

本文档详细分析了现有系统中的图生图（自由P图 / 幻想换脸 / 附加模型）的业务流程、数据流向以及底层的调度架构。

## 一、 业务流程图 (Business Flow)

```mermaid
sequenceDiagram
    actor User as Telegram 用户
    participant FSM as Bot 交互层 (edit_image_fsm)
    participant Core as 业务核心层 (task_core)
    participant API as 后端网关 (FastAPI)
    participant Queue as Redis 任务队列
    participant Worker as 调度节点 (Comfy Agent)
    participant ComfyUI as GPU 推理端
    participant MinIO as 对象存储

    User->>FSM: 发送图生图命令 (menu.free_edit / i2i_pro)
    FSM-->>User: 提示选择附加模型 (LoRA)
    User->>FSM: 选择模型 / 选择"无"
    FSM-->>User: 提示上传参考图
    User->>FSM: 上传 1-2 张参考图片
    FSM-->>User: 提示输入提示词
    User->>FSM: 输入提示词 (Prompt)
    
    FSM->>Core: 提交生成任务 (process_generation_task)
    Core->>Core: 扣除灵石 (Billing) & 检查并发锁 (Concurrency)
    
    Core->>API: 派发任务 (HTTP POST /comfy_img2img)
    API->>Queue: 将任务压入 Redis 队列
    API-->>Core: 返回后端 Task ID
    Core-->>FSM: 返回排队/进度信息
    FSM-->>User: 显示进度 (排队中 / 生成中)
    
    Worker->>Queue: 轮询/订阅获取新任务
    Worker->>Worker: 动态注入参数与工作流补丁 (workflow_patcher)
    Worker->>ComfyUI: 提交推理工作流 (API JSON)
    ComfyUI-->>Worker: WebSocket 推送生成进度
    Worker->>Queue: 更新进度至 Redis
    
    ComfyUI->>Worker: 返回生成的图片数据
    Worker->>MinIO: 上传生成结果 (图片/视频)
    Worker->>Queue: 标记任务完成 (DONE)，附带 MinIO 路径
    
    Core->>Queue: 持续监控任务状态
    Queue-->>Core: 任务完成，返回 MinIO 路径
    Core->>MinIO: 下载结果
    Core-->>FSM: 返回生成结果
    FSM->>Core: 释放并发锁
    FSM-->>User: 发送生成好的图片，展示分享/点赞按钮
```

## 二、 数据流向图 (Data Flow)

描述在图生图任务执行期间，图片、提示词和模型参数等数据是如何在各个微服务间流转的。

```mermaid
graph TD
    subgraph ClientLayer ["用户端"]
        U_IMG["参考图片"]
        U_TXT["提示词"]
        U_CFG["选择的 LoRA/参数"]
    end

    subgraph BotService ["Bot 服务端"]
        TMP["/tmp 本地临时文件"]
        FSM_CTX["状态机上下文"]
        FACADE["TaskCore 组装层"]
    end

    subgraph BackendGateway ["后端网关 API"]
        MODEL_REQ["Img2ImgRequest 模型"]
    end

    subgraph MessageQueue ["Redis 消息队列"]
        QUEUE[("任务队列 (comfy_queue:*)")]
        STATUS[("状态字典 (comfy_status:*)")]
    end

    subgraph WorkerNode ["Comfy Agent Worker"]
        PATCHER["workflow_patcher.py"]
        JSON["工作流 JSON 模板"]
    end

    subgraph Storage ["对象存储"]
        MINIO[("MinIO Result Bucket")]
    end

    subgraph GPU ["GPU 节点"]
        COMFY["ComfyUI Server"]
    end

    U_IMG -->|"上传图片"| TMP
    U_TXT -->|"文字/指令"| FSM_CTX
    U_CFG -->|"选择配置"| FSM_CTX
    
    TMP -->|"传递本地路径"| FACADE
    FSM_CTX -->|"传递参数"| FACADE
    
    FACADE -->|"组装 Base64图片/Prompt/LoRA"| MODEL_REQ
    MODEL_REQ -->|"JSON 化并压栈"| QUEUE
    
    QUEUE -->|"Pop 提取任务"| PATCHER
    PATCHER -->|"读取模板"| JSON
    PATCHER -->|"映射注入 (节点 ID)"| JSON
    JSON -->|"POST /prompt"| COMFY
    
    COMFY -->|"生成图像流"| PATCHER
    PATCHER -->|"上传文件"| MINIO
    PATCHER -->|"更新路径 (result_path)"| STATUS
    STATUS -->|"TaskCore 轮询读取"| FACADE
```

## 三、 系统架构图 (Architecture Diagram)

图生图模块在系统中的层级架构，展示了从接入层到底层基础设施的分层解耦设计。

```mermaid
graph TB
    subgraph "1. 接入层 (Presentation Layer)"
        TG["Telegram API"]
        FSM["FSM 状态机 (edit_image_fsm.py)"]
    end

    subgraph "2. 核心业务层 (Core Domain Layer)"
        TASK_CORE["任务门面 (task_core.py)"]
        BILLING["计费引擎 (billing_core.py)"]
        REGISTRY["任务注册表 (TaskRegistry)"]
    end

    subgraph "3. API 网关与中间件 (Gateway & Middleware)"
        FASTAPI["FastAPI 后端网关 (main.py)"]
        REDIS_Q[("Redis 队列管理器 (QueueManager)")]
    end

    subgraph "4. 调度与消费层 (Worker Layer)"
        AGENT_1["Comfy Agent (节点 A)"]
        AGENT_2["Comfy Agent (节点 B)"]
        PATCHER["工作流注入器 (Workflow Patcher)"]
    end

    subgraph "5. 底层基础设施 (Infrastructure)"
        COMFYUI_1["ComfyUI 实例 1 (GPU)"]
        COMFYUI_2["ComfyUI 实例 2 (GPU)"]
        MINIO[("MinIO 对象存储")]
        DB[("PostgreSQL (持久化数据)")]
    end

    TG <-->|"Webhook / Polling"| FSM
    FSM -->|"请求生成"| TASK_CORE
    TASK_CORE -->|"1. 扣除灵石"| BILLING
    TASK_CORE -->|"2. 记录任务"| REGISTRY
    REGISTRY --> DB
    TASK_CORE -->|"3. 发起请求"| FASTAPI
    FASTAPI -->|"入队"| REDIS_Q

    REDIS_Q -->|"出队 (Pop)"| AGENT_1
    REDIS_Q -->|"出队 (Pop)"| AGENT_2
    AGENT_1 -->|"加载&修改"| PATCHER
    PATCHER -->|"分发 JSON"| COMFYUI_1
    AGENT_2 -->|"分发 JSON"| COMFYUI_2

    COMFYUI_1 -->|"回传结果"| AGENT_1
    AGENT_1 -->|"上传"| MINIO
    AGENT_1 -->|"更新状态"| REDIS_Q
    
    REDIS_Q -.->|"状态同步"| TASK_CORE
    TASK_CORE -.->|"返回结果"| FSM
```

## 四、 架构分析说明

目前的图生图 (Image-to-Image) 模块采用了**高度解耦的三层架构**，以保障系统在高并发情况下的稳定性和容灾能力：

### 1. 交互与核心层 (Telegram Bot + Task Core)
- **状态机流转 (FSM)**: 图生图的业务入口由 `edit_image_fsm.py` 控制。使用 `ConversationHandler` 严格规范了“选模型 -> 传图 -> 传词”的收集顺序。
- **资源隔离**: 图片首先被下载到 Bot 的本地 `/tmp/bot_fsm_tmp` 目录中。收集完毕后，FSM 调用 `bot_task_service.py` 将控制权移交给系统核心层。
- **计费与并发锁**: 在 `task_core.py` 中，执行 `check_concurrency_lock` 和 `check_and_deduct_credits`，利用 Redis 的原子性保证灵石不被超扣，同时限制用户最大并发数（目前 MAX_CONCURRENT_TASKS = 3）。

### 2. 网关与调度层 (FastAPI + Redis Queue)
- **解耦中转**: Bot 并不直接与 ComfyUI 通信，而是通过 HTTP 调用 `backend/app/main.py` 中的网关接口（如 `/comfy_img2img_lora`）。
- **队列管理**: FastAPI 接收到请求后，将其转化为 `TaskType` 对应的 Pydantic 模型，推入 Redis 的等待队列（由 `QueueManager` 统一管理），随后立刻向 Bot 返回一个 `task_id`。
- **状态监控**: Bot 使用该 `task_id` 轮询后端（或使用 pub/sub），向用户实时反馈“排队中 (第 X 位)”或“生成中 (X%)”的进度。

### 3. 消费与推理层 (Worker + ComfyUI)
- **Worker 轮询**: `workers/comfy_agent/` 独立运行在各个计算节点上。它们不断从 Redis 取出对应任务类型的 Payload。
- **动态补丁 (Workflow Patcher)**: 这是架构中最灵活的部分。
  - Worker 首先读取 `mappings.json`，获知业务参数（如 `prompt`, `image`, `lora_name`）对应在 ComfyUI 工作流中的节点 ID。
  - 读取基础工作流模板（例如 `Qwen-Rapid-AIO.json`）。
  - **防爆重连**: 如果用户没有选择 LoRA（或者某些可选图没有传），Patcher 会执行动态剪枝操作（如绕过 LoRA 节点，直接将 KSampler 连向 Checkpoint），防止 ComfyUI 因为节点参数缺失而崩溃。
- **结果回传**: ComfyUI 推理完毕后，Worker 将图片上传到 MinIO 的 `result_bucket`，并将路径写回 Redis `status` 中，从而闭环整个数据流。

### 4. 附加模型(LoRA)的配置特性
得益于 `allbot-comfy-models` 的技能设计，增加新的图生图 LoRA 模型**无需修改底层代码**。只需：
1. 将 `.safetensors` 文件放至指定目录。
2. 在 `edit_image_fsm.py` 的 `LORA_MODELS` 字典中增加对应的路径和中文名。
3. 系统会自动将其展示给用户，并通过网关将其作为 `lora_name` 参数一路透传到 `workflow_patcher.py` 中进行节点注入。
