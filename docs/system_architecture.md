# 修仙主题 AI 创作工作台 - 系统架构与数据流说明书

本文档基于项目的最新重构与功能迭代（涵盖多模块分布式架构、三大支付体系并入等），通过 Graph 架构图和数据流图，全面梳理系统的核心组成部分及其流转机制。

---

## 1. 核心系统架构图 (System Architecture Graph)

系统采用分布式多节点架构，从前端入口、统一业务逻辑、到底层基础设施与计算节点实现了职责分离。

```mermaid
graph TD
    %% 用户入口层
    subgraph Clients["客户端层 (Client Layer)"]
        TG[Telegram 用户]
        WebUser[Web 浏览器/SPA]
        Admin[Dashboard 管理员]
        PayGateway[第三方支付网关<br/>易支付/RMB]
        TON[TON 钱包]
    end

    %% 服务入口层
    subgraph Gateways["服务接入层 (Gateway & API)"]
        TGBot[Telegram Bot<br/>src/bot_test.py / bot_prod.py]
        WebBFF[Web BFF API<br/>FastAPI: src/web_api/]
        PayAPI[Payment Callback API<br/>src/payment_api_server.py]
        DashFront[Dashboard Frontend<br/>Vue3 SPA]
        DashBack[Dashboard Backend<br/>FastAPI]
    end

    %% 核心业务逻辑层 (Platform-Agnostic)
    subgraph Core["核心业务逻辑层 (Core Logic)"]
        TaskCore[Task Core<br/>src/core/task_core.py]
        UserCore[User & Billing Core<br/>src/core/user_core.py / billing_core.py]
        Fulfillment[支付发货与身份折算<br/>src/services/payment_fulfillment_service.py]
    end

    %% 基础设施层
    subgraph Infra["基础设施 (Infrastructure)"]
        DB[(PostgreSQL<br/>用户/订单/资产流水)]
        RedisDB1[(Redis DB 1<br/>Bot缓存/并发锁/任务追踪)]
        RedisDB2[(Redis DB 2<br/>队列/调度/心跳)]
        MinIO[(MinIO 对象存储<br/>文件/中间产物/模板)]
    end

    %% 底层计算与调度层
    subgraph Computing["底层计算与调度 (Execution Layer)"]
        CentralAPI[Central API Backend<br/>/backend]
        Workers[ComfyUI Workers<br/>/workers/comfy_agent*]
    end

    %% 关联连线
    TG <-->|Telegram API / Local API| TGBot
    WebUser <-->|HTTP REST / SSE| WebBFF
    WebUser -.->|预签名直传| MinIO
    Admin <-->|HTTP| DashFront
    DashFront <--> DashBack
    PayGateway -->|Webhook 回调| PayAPI
    TON <--> TGBot

    TGBot <--> TaskCore & UserCore
    WebBFF <--> TaskCore & UserCore
    PayAPI --> Fulfillment
    Fulfillment --> UserCore

    TaskCore <--> DB & RedisDB1
    UserCore <--> DB
    DashBack <--> DB & RedisDB1 & RedisDB2

    TaskCore -->|派发任务| CentralAPI
    CentralAPI <-->|排队/状态同步| RedisDB2
    CentralAPI -->|分配 JSON Workflow| Workers
    
    Workers <-->|下载输入/上传输出| MinIO
    TGBot <-->|大文件存取| MinIO
```

### 架构模块说明
1. **客户端层**：包含传统的 Telegram Bot 交互端、现代化的 Web SPA（Vue3）前端、管理后台 Dashboard，以及负责接收异步回调的第三方支付网关。
2. **服务接入层**：针对不同客户端提供独立接入点。Bot 端负责 TG 交互状态机，BFF 负责处理 Web 端的 JWT 鉴权与 SSE 状态推送，Payment API 独立负责监听外网 HTTP 支付回调。
3. **核心业务逻辑层**：整个系统的底座，平台无关 (Platform-Agnostic)。统一处理权限鉴定、并发锁机制 (`ActiveTasksTable`)、扣费逻辑与任务封装。
4. **基础设施层**：PostgreSQL 负责资产与订单的绝对持久化；Redis 按库分离（DB1 处理高速缓存与并发控制，DB2 处理底层队列与心跳）；MinIO 负责所有流媒体与图像对象存储，实现文件引用传递（Object Key）。
5. **底层计算层**：Central API 解析工作流，动态注入参数并向后端的 ComfyUI Agents (Workers) 派发计算任务。

---

## 2. 核心业务数据流图 (Data Flow Diagrams)

### 2.1 任务生成流 (Task Generation Flow)

涵盖从用户上传素材、系统鉴权与并发锁判定、直到异步节点完成任务并通过 Pub/Sub 推送状态回前端的全过程。

```mermaid
sequenceDiagram
    autonumber
    participant User as 用户 (TG / Web)
    participant API as 接入层 (Bot / BFF)
    participant Core as 核心逻辑层 (Task Core)
    participant Redis as Redis (PubSub / 锁)
    participant Central as Central API
    participant Worker as ComfyUI Worker
    participant MinIO as MinIO 对象存储

    User->>API: 1. 发起生成请求 (传图/传视频)
    alt Web 大文件上传
        API->>MinIO: 生成 Presigned PUT URL
        API-->>User: 返回直传链接
        User->>MinIO: 直接 PUT 上传文件 (绕过后端)
    else TG Bot 小文件
        API->>MinIO: 下载后存入 bot-data Bucket
    end

    API->>Core: 2. 提交任务 (internal_user_id, task_type, args)
    Core->>Core: 3. 校验权限、余额
    Core->>Redis: 4. 检查并获取并发锁 (MAX_CONCURRENT_TASKS)
    Core->>Redis: 5. 注册活跃任务 (ActiveTasksTable)
    Core->>Central: 6. 发送任务与工作流参数 (仅传 Object Key)
    Central->>Redis: 7. 推送至排队队列 (comfy:queue:pending)
    
    Worker->>Redis: 8. 轮询获取任务
    Worker->>MinIO: 9. 使用 Object Key 下载输入文件
    Worker->>Worker: 10. 执行 ComfyUI 推理 (GPU)
    
    loop 进度流转
        Worker->>Redis: 发布进度事件 (PubSub)
        Redis-->>API: 触发 SSE / TG 消息更新
        API-->>User: 实时推送进度 (如: 45%)
    end

    Worker->>MinIO: 11. 任务完成，上传输出结果至 comfyui-temp
    Worker->>Redis: 12. 广播 Task Complete (包含结果 Object Key)
    Central->>Redis: 更新最终状态为 Done
    
    Redis-->>API: 接收到 Complete 事件
    API->>Core: 13. 释放并发锁、扣除灵石余额
    API->>MinIO: 14. 获取生成文件的预签名下载 URL (或发消息)
    API-->>User: 15. 返回最终生成图像/视频
```

### 2.2 支付与充值数据流 (Payment & Top-up Flow)

系统采用“先预建单，后异步验签发货”的高幂等性安全设计。

```mermaid
sequenceDiagram
    autonumber
    participant User as 用户
    participant Bot as Bot / Web
    participant Core as 订单与支付 Core
    participant DB as PostgreSQL
    participant PayGate as 第三方支付网关
    participant PayAPI as Payment Callback API

    User->>Bot: 选择套餐 (直充/月卡) 并点击支付
    Bot->>Core: 发起支付请求
    Core->>DB: 创建新订单 Order (状态: PENDING)
    Core->>PayGate: 请求生成支付链接 (携带 Order ID)
    PayGate-->>User: 返回 Checkout 页面
    User->>PayGate: 完成付款
    
    PayGate->>PayAPI: 异步 Webhook POST (支付成功通知)
    PayAPI->>PayAPI: 1. 验证签名 (Signature Check)
    PayAPI->>DB: 2. 查询订单状态 (Idempotency Check)
    
    alt 订单已是 SUCCESS
        PayAPI-->>PayGate: HTTP 200 (幂等拦截，防止重复发货)
    else 订单为 PENDING
        PayAPI->>DB: 3. 更新订单状态为 SUCCESS
        PayAPI->>Core: 4. 执行发货逻辑 (Fulfillment)
        Core->>DB: 4a. 月卡跨级折算 / 直充灵石累加
        Core->>DB: 4b. 写入严密流水日志 (user_logs)
        PayAPI-->>PayGate: HTTP 200 (发货成功)
    end
    
    Bot->>User: (通过轮询或主动推送) 支付成功提示
```

### 2.3 异常拦截与僵尸任务自愈机制 (Zombie Task Recovery)

为防止因网络中断、Worker 崩溃等导致用户并发锁被永久锁死（Ghost Locks），系统配备了自愈闭环。

```mermaid
sequenceDiagram
    autonumber
    participant Clean as 自愈协程 (clean_zombies_loop)
    participant Redis as Redis (ActiveTasksTable)
    participant DB as PostgreSQL
    participant Central as Central API
    participant Worker as ComfyUI Worker

    Clean->>Redis: 1. 定期巡检活跃任务表
    Redis-->>Clean: 返回驻留时间超限 (如 > 1小时) 的任务
    Clean->>Redis: 2. 强行清除异常并发锁 (Release Lock)
    Clean->>DB: 3. (可选) 补偿或回退预扣费用的灵石
    Clean->>Central: 4. DELETE /api/tasks/{task_id} (双向剔除)
    Central->>Redis: 5. 从 Pending 队列移除
    alt 任务正在 Worker 执行
        Central->>Worker: 发送 Interrupt 信号打断 GPU 推理
    end
    Clean->>Redis: 6. 广播任务失败/取消通知给前端
```

---

## 3. 核心机制设计红线备忘

根据开发指南 (AGENTS.md)，系统维护和后续迭代中需严格遵守以下架构级红线：

1. **统一用户标识**：不同终端（Telegram / Web）进来的请求，进入 `src/core` 前必须被解析为底层的 `internal_user_id`（对应 DB 的 `users.id`）。绝不允许在 Core 层混用 Telegram ID 或其他平台凭证。
2. **大文件传输绕流**：对于 100MB+ 的视频，坚决贯彻通过 MinIO **预签名直传 (Presigned PUT)** 的模式。Web 流量直接走 MinIO，禁止 BFF 或 Bot 服务器进行文件流的中转，以防耗尽服务器内存与带宽。
3. **并发锁最终一致性**：无论前端用户是否断开 SSE 连接或异常中断，后台的 Background Tasks 或自愈协程都必须确保在任务终态（成功/失败/被取消）时，释放该用户的并发锁。
4. **数据库流水对账**：任何触发资产变更（增减灵石）的操作，必须通过上下文追踪同步写入 `user_logs` 表，杜绝“隐式加钱”。
5. **月卡跨级保护**：高等级身份（如真传弟子）覆盖购买低等级套餐时，不可发生身份降级，系统应将低等级天数按既定比例折算为高等级天数。

> 文档由 AI 助手自动提取汇总，最后更新日期：2026-04-15
