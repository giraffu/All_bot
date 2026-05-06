# 图生视频 (Image-to-Video) 业务流与架构分析

本文档详细分析了现有系统中的图生视频（如高级图生视频 LTX-Video、幻想视频、自定义视频等）的业务流程、数据流向以及底层的调度架构。

## 一、 业务流程图 (Business Flow)

```mermaid
sequenceDiagram
    actor User as Telegram 用户
    participant FSM as Bot 交互层 (ltx_video_fsm / custom_video_fsm)
    participant Core as 业务核心层 (task_core)
    participant API as 后端网关 (FastAPI)
    participant Queue as Redis 任务队列
    participant Worker as 调度节点 (Comfy Agent)
    participant ComfyUI as GPU 推理端
    participant MinIO as 对象存储

    User->>FSM: 发送图生视频命令 (menu.ltx_video 等)
    FSM-->>User: 提示上传起始参考图
    User->>FSM: 上传图片 (Image)
    FSM->>FSM: 保存图片至 /tmp/bot_fsm_tmp
    FSM-->>User: 返回视频设置键盘 (画质/时长) 及提示词输入提示
    User->>FSM: 点击修改画质 (Resolution) 与时长 (Duration)
    User->>FSM: 输入提示词 (Prompt)
    
    FSM->>Core: 提交视频核心任务 (process_and_submit_task)
    Core->>Core: 计算时长/画质消耗，扣除灵石 (Billing) & 检查并发锁
    
    Core->>API: 派发任务 (HTTP POST /api/v1/ltx_video)
    API->>Queue: 将任务压入 Redis 队列
    API-->>Core: 返回后端 Task ID
    Core-->>FSM: 返回排队/进度信息
    FSM-->>User: 显示进度 (排队中 / 生成中)
    
    Worker->>Queue: 轮询/订阅获取新任务
    Worker->>Worker: 加载视频 JSON 工作流模板 (如 LTX 2.3 I2V.json)
    Worker->>Worker: 动态注入参数、防缓存 Seed 及清理预览节点 (workflow_patcher)
    Worker->>ComfyUI: 提交推理工作流 (API JSON)
    ComfyUI-->>Worker: WebSocket 推送生成进度
    Worker->>Queue: 更新进度至 Redis
    
    ComfyUI->>Worker: 返回生成的视频流数据 (MP4)
    Worker->>MinIO: 上传生成结果至 Result Bucket
    Worker->>Queue: 标记任务完成 (DONE)，附带 MinIO 视频路径
    
    Core->>Queue: 持续监控任务状态 (monitor_progress)
    Queue-->>Core: 任务完成，返回 MinIO 路径
    Core->>MinIO: 下载视频结果
    Core-->>FSM: 返回生成结果
    FSM->>Core: 释放并发锁
    FSM-->>User: 发送生成的视频文件 (MP4)，展示分享/点赞按钮
```

## 二、 数据流向图 (Data Flow)

描述在图生视频任务执行期间，图片、视频生成参数（画质/时长）和提示词等数据是如何流转的。

```mermaid
graph TD
    subgraph ClientLayer ["用户端"]
        U_IMG["参考图片"]
        U_TXT["提示词"]
        U_CFG["画质/时长 (如 1280x704, 5s)"]
    end

    subgraph BotService ["Bot 服务端"]
        TMP["/tmp 本地临时文件"]
        FSM_CTX["状态机上下文 (ltx_video_data)"]
        FACADE["TaskCore 组装层"]
    end

    subgraph BackendGateway ["后端网关 API"]
        MODEL_REQ["VideoTaskRequest 模型"]
    end

    subgraph MessageQueue ["Redis 消息队列"]
        QUEUE[("任务队列 (comfy_queue:*)")]
        STATUS[("状态字典 (comfy_status:*)")]
    end

    subgraph WorkerNode ["Comfy Agent Worker"]
        PATCHER["workflow_patcher.py"]
        JSON["视频工作流 JSON (LTX)"]
    end

    subgraph Storage ["对象存储"]
        MINIO[("MinIO Result Bucket (MP4)")]
    end

    subgraph GPU ["GPU 节点"]
        COMFY["ComfyUI Server"]
    end

    U_IMG -->|"上传图片"| TMP
    U_TXT -->|"文字/指令"| FSM_CTX
    U_CFG -->|"Inline键盘选择"| FSM_CTX
    
    TMP -->|"传递本地路径"| FACADE
    FSM_CTX -->|"传递分辨率与时长"| FACADE
    
    FACADE -->|"组装 Base64图片/Prompt/Resolution/Duration"| MODEL_REQ
    MODEL_REQ -->|"JSON 化并压栈"| QUEUE
    
    QUEUE -->|"Pop 提取任务"| PATCHER
    PATCHER -->|"读取模板"| JSON
    PATCHER -->|"防爆与防缓存注入 (Seed/Filename)"| JSON
    JSON -->|"POST /prompt"| COMFY
    
    COMFY -->|"生成视频流"| PATCHER
    PATCHER -->|"上传 MP4 文件"| MINIO
    PATCHER -->|"更新路径 (result_path)"| STATUS
    STATUS -->|"TaskCore 轮询读取"| FACADE
```

## 三、 系统架构图 (Architecture Diagram)

图生视频模块的层级架构，展示了其在计费、调度和视频结果回传上的设计。

```mermaid
graph TB
    subgraph "1. 接入层 (Presentation Layer)"
        TG["Telegram API"]
        FSM["视频 FSM 状态机 (ltx_video_fsm.py 等)"]
    end

    subgraph "2. 核心业务层 (Core Domain Layer)"
        TASK_CORE["任务门面 (task_core.py)"]
        BILLING["动态计费引擎 (StrategyFactory)"]
        REGISTRY["任务注册表 (TaskRegistry)"]
    end

    subgraph "3. API 网关与中间件 (Gateway & Middleware)"
        FASTAPI["FastAPI 后端网关 (main.py)"]
        REDIS_Q[("Redis 队列管理器")]
    end

    subgraph "4. 调度与消费层 (Worker Layer)"
        AGENT_1["Comfy Agent (节点 A)"]
        PATCHER["工作流注入器 (Workflow Patcher)"]
    end

    subgraph "5. 底层基础设施 (Infrastructure)"
        COMFYUI_1["ComfyUI 实例 1 (GPU)"]
        MINIO[("MinIO 对象存储 (存 MP4)")]
        DB[("PostgreSQL (历史与日志)")]
    end

    TG <-->|"Webhook / Polling"| FSM
    FSM -->|"请求生成视频"| TASK_CORE
    TASK_CORE -->|"1. 动态乘数计费 (画质×时长)"| BILLING
    TASK_CORE -->|"2. 记录任务"| REGISTRY
    REGISTRY --> DB
    TASK_CORE -->|"3. 发起请求"| FASTAPI
    FASTAPI -->|"入队"| REDIS_Q

    REDIS_Q -->|"出队 (Pop)"| AGENT_1
    AGENT_1 -->|"加载&修改 JSON"| PATCHER
    PATCHER -->|"分发 JSON"| COMFYUI_1

    COMFYUI_1 -->|"回传视频结果"| AGENT_1
    AGENT_1 -->|"上传视频"| MINIO
    AGENT_1 -->|"更新状态"| REDIS_Q
    
    REDIS_Q -.->|"状态同步"| TASK_CORE
    TASK_CORE -.->|"返回 MP4"| FSM
```

## 四、 架构分析说明

图生视频模块在基础三层架构之上，针对视频生成的特殊性（高资源消耗、长耗时、节点缓存问题）进行了多项针对性设计：

### 1. 交互与动态计费层 (FSM + Task Core)
- **状态机流转 (FSM)**: 视频生成（如 `ltx_video_fsm.py`）比生图多了一个“参数选择”环节。在用户上传图片后，系统会弹出 Inline 键盘供用户实时选择**画质 (Resolution)**与**时长 (Duration)**。
- **动态乘数计费**: 视频任务由于算力消耗巨大，灵石扣除不再是固定值，而是通过 `StrategyFactory` 和常量配置（如 `LTX_RESOLUTION_COST` 和 `LTX_DURATION_MULTIPLIER`）计算：`Base Cost * Duration Multiplier`，并在点击确认前预检余额。
- **互斥锁限制**: 对于极高画质（如 >= 1024p）和超长时长（如 >= 10s）的组合，在非特定模式下会触发 `CoreDomainError` 进行拦截，防止显存溢出 (OOM)。

### 2. 网关与调度监控 (Gateway & Monitor)
- **队列管理**: FastAPI 接收到 `ltx_video` 等视频任务请求后压入 Redis 队列。
- **长轮询与锁释放**: 考虑到视频生成时间远长于图片（通常需要数分钟），系统根据请求来源采用双轨制策略：对于 Web UI 请求，挂载 `monitor_task_and_release_lock` 作为独立后台异步任务来监控进度和释放锁；对于 Telegram Bot 流，由 `TaskService` 维持前台长轮询 (`async for`) 实时给用户推送进度，并在 `finally` 块中统一调用 `release_concurrency_lock` 稳妥释放并发锁。两者最终都会调用 `image_service.download_video_result` 下载 `.mp4` 文件。

### 3. 消费推理与防缓存机制 (Worker Patcher)
在视频生成链路中，`workflow_patcher.py` 扮演了关键的“动态补丁”角色，针对视频工作流（如 LTX 2.3）做了大量定制优化：
- **防爆重连与剪枝**: 去除无用的预览节点（如 `Preview Override` 等 UI 调试节点），防止在 API 模式下触发 `AttributeError` 导致任务崩溃。
- **防缓存 (Seed Injection)**: 强制注入随机 Seed 作为 `filename_prefix`（如 `ltx_video_{unique_id}_{node_id}`）。由于 ComfyUI 对视频生成节点 `VHS_VideoCombine` 有缓存机制，若不每次更新输出前缀，会导致生成直接被跳过，无法触发历史记录回传。
- **直连路由**: 对于不需要经过特定复杂处理的连线（例如 LTX 工作流中的 Node 7 直接路由到 Node 8），进行代码层面的强绑定以保证生成的稳定性。

### 4. 视频存储与分发 (Storage & Response)
- **MinIO 存储**: Worker 端获取到 ComfyUI 输出的视频后，将其上传至 MinIO 的 `result_bucket`。
- **Telegram 分发**: Bot 通过 `robust_send_video` 工具函数将 `.mp4` 格式的数据发送给用户，并附带生成参数、画廊分享和点赞功能，完成闭环。
