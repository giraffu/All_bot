# 修仙主题 AI 创作工作台 - 系统架构与业务分析报告

## 目录
1. [系统架构梳理](#1-系统架构梳理)
2. [数据流图分析](#2-数据流图分析)
3. [业务板块划分](#3-业务板块划分)
4. [关键设计决策与技术选型](#4-关键设计决策与技术选型)
5. [架构合理性分析与优化建议](#5-架构合理性分析与优化建议)

---

## 1. 系统架构梳理

系统采用现代化的**多模块、多节点分布式架构**。在物理部署上，系统划分为“海外边缘节点层”与“国内（武汉）算力与数据底座”，通过内网穿透（FRP / Cloudflare Tunnel / Tailscale 等）组建虚拟局域网（VLAN），既突破了网络访问限制，又保障了底层数据和高算力设备的安全。

### 系统架构图

```mermaid
graph TD
    subgraph 客户端层
        A1[Telegram 客户端]
        A2[Web 前端 Vue3 SPA]
        A3[Dashboard 前端看板]
        A4[社群用户 / TON 支付前端]
        A5[易支付 / 支付宝 / 微信回调]
    end

    subgraph 边缘节点与代理穿透层
        V1[海外 VPS - Web 边缘节点<br>Nginx 静态托管 & 接口反代]
        V2[海外 VPS - Telegram 节点<br>Local API & File Server 8081/8082]
        T1[Cloudflare Tunnel / FRP<br>内网穿透与外网暴露]
        T2[Tailscale 虚拟局域网 VLAN<br>底座与节点安全互联]
    end

    subgraph 接入网关层 算力底座
        B1[主 Bot 服务 Tg-Bot]
        B2[Web BFF API FastAPI 8000]
        B3[Dashboard 后端]
        B4[Payment API 回调网关 8021]
        B5[AI 客服大师姐 CS Bot]
    end

    subgraph 核心业务逻辑层 src/core
        C1[任务核心 Task Core]
        C2[任务分发 Task Dispatcher]
        C3[计费核心 Billing Core]
        C4[用户与认证核心 User & Auth]
        C5[画廊存储核心 Gallery Core]
    end

    subgraph 调度与执行层
        D1[中控 API Backend 8003]
        D2[ComfyUI Worker Node 1]
        D3[ComfyUI Worker Node N]
        D4[LM Studio 宿主机推理 1234]
    end

    subgraph 基础设施与分级存储层
        E1[(PostgreSQL 主库 bot_db)]
        E2[(Redis 缓存/队列 DB 1 & DB 2)]
        E3[(MinIO 热数据主桶<br>bot-data / comfyui-temp)]
        E4[(MinIO 冷数据归档桶<br>历史数据降级存储)]
        E5[(Cloudflare R2 边缘存储<br>社区广场加速分发)]
    end

    %% 客户端到边缘层连接
    A1 <--> V2
    A2 <-->|HTTPS/WSS| V1
    A4 <--> V1
    A5 -->|HTTP 回调| T1
    A3 <--> T1

    %% 边缘层到底座网关连接 (通过 VLAN / FRP)
    V1 <-->|Tailscale 路由| B2
    V2 <-->|直连下载/API| B1
    T1 -->|端口转发| B4 & B3

    %% 网关层到核心业务层
    B1 --> C1 & C2 & C3
    B2 --> C1 & C2 & C3
    B3 --> C1 & C2
    B4 --> C3
    B5 --> D4
    
    %% 核心业务到基础设施
    C1 <--> E2
    C2 <--> E1
    C3 <--> E1
    
    %% 调度执行与存储流转
    E2 <--> D1
    D1 --> D2 & D3
    D2 & D3 <--> E3
    E3 -.->|定时/异步生命周期迁移| E4
    E3 -.->|排行榜高频作品同步| E5
    A2 -.->|Web端大文件预签名直传| E3
```

### 架构物理与逻辑层级说明
1. **客户端层**：多端覆盖。包括传统的 Telegram 交互、内嵌的 TON Web App、独立的 Vue3 创作工作台，以及三方支付网关的异步回调发起方。支持多语言 (i18n)，Web 端基于 `vue-i18n`，Telegram 端基于 `I18nFilter` 和 Redis 语言偏好缓存。
2. **边缘节点与代理穿透层 (Edge & Network Layer)**：
   * **Web VPS**：部署 Nginx，负责 Web 前端（Vue3 打包的 `/dist`）的静态文件托管，并将 `/api/` 的动态请求通过内网反向代理（Proxy Pass）给国内底座。
   * **Telegram VPS**：运行官方 Local API 和文件服务器，专门用于突破 Telegram 官方 50MB 视频上传和 20MB 下载限制，将文件通过 HTTP 直链暴露给 Bot 底座提取。
   * **隧道穿透与组网**：使用 Tailscale 组建虚拟局域网打通海内外节点通信；使用 Cloudflare Tunnel 和 FRP 将本地的 Payment API（端口 8021）和 Dashboard 暴露到公网，既能接收外网支付回调，又能隐藏国内真实服务器 IP。
3. **接入网关层**：接收处理解析后的请求。各微服务（主 Bot、Web BFF、支付 API、客服大师姐）互不干扰，独立运作。
4. **核心领域逻辑层 (Core-Driven Architecture)**：业务“中枢”。剥离特定平台依赖，废弃传统的 Service/Repository 三层架构思路，全面拥抱核心领域层架构 (`src/core/`)。使用内部统一的 `internal_user_id` 处理鉴权、通过 Saga 模式进行单轨制计费与分布式退款、并发锁检查及任务派发，完全不知道 HTTP 或 Telegram Bot 的存在。
5. **调度与执行层**：中控 API 作为任务调度器（基于 Redis Pub/Sub 实现无阻塞分发）；ComfyUI 节点执行生图/视频计算；同时宿主机部署 **LM Studio**（监听本地 1234 端口），为 CS Bot（大师姐）提供低成本的本地大模型（如 Qwen）推理能力。
6. **基础设施与分级存储层**：
   * **PostgreSQL / Redis**：提供财务强一致性账本与高速队列锁机制。
   * **冷热分离的 MinIO 存储**：包含一个**热数据主桶**（近期生成作品、ComfyUI 中间件传输）与一个**冷数据归档桶**（定时迁移若干天以上的旧历史文件），有效降低主库 IO 压力。
   * **Cloudflare R2**：专门用于高并发的“社区广场 (Gallery)”模块流媒体加速。

---

## 2. 数据流图分析

以下梳理了系统中完整的“图像/视频生成”及“数据冷热生命周期”的数据流转路径。

### 任务执行与存储降级数据流图

```mermaid
flowchart TD
    U([用户 User]) -->|1. 发起生图/视频请求| V[海外边缘节点 VPS]
    V -->|2. Tailscale / 隧道转发| GW[Bot / Web BFF 接入层]
    
    subgraph 预处理与资源抢占
        GW -->|3. 调用任务调度| CORE[核心业务逻辑层]
        CORE -->|4. 检查单用户并发锁| RD1[(Redis DB 1)]
        CORE -->|5. 扣除灵石 / 记录扣费流水| PG[(PostgreSQL)]
    end
    
    subgraph 异步调度与执行
        CORE -->|6. 下发任务包| RD2[(Redis DB 2 Pending队列)]
        CAPI[中控 API] -->|7. 轮询提取任务| RD2
        CAPI -->|8. 派发工作流指令| WK[ComfyUI Worker 节点]
        WK -->|9. AI 推理生成| WK
        WK -->|10. 产物直传存储| HOT_MINIO[(MinIO 热数据桶)]
    end
    
    subgraph 通知与分发
        WK -->|11. 发布任务完成事件| PUB[(Redis Pub/Sub)]
        PUB -->|12. 触发事件监听器| CORE
        CORE -->|13. 写入历史记录 & 释放锁| PG
        CORE -->|14. 触发 SSE 流 / Tg 消息推送| GW
    end
    
    subgraph 存储生命周期管理
        HOT_MINIO -.->|16a. 异步转存高热度作品| R2[(Cloudflare R2 加速)]
        HOT_MINIO -.->|16b. 脚本定期迁移数天前的旧数据| COLD_MINIO[(MinIO 冷数据归档桶)]
        R2 -->|17. 社区广场高速读取| U
        COLD_MINIO -->|18. 用户回溯历史记录读取| U
    end
    
    GW -->|15. 返回文件预签名链接/直链| U
```

### 数据流转核心设计
* **穿透转发**：所有来自公网的用户流量首先打到海外 VPS 或 CF 边缘节点，通过安全的隧道清洗和反向代理进入国内的计算底座。
* **存储降级与冷热隔离**：产出结果默认写入 MinIO 热桶。随着时间推移，后台任务自动将数天前的用户私人历史数据迁移至**冷数据归档桶**；而推送到广场的热门作品会被主动同步到 **Cloudflare R2** 进行 CDN 加速分发。
* **本地模型数据流**：客服大师姐（CS Bot）捕获群聊文本后，不走 ComfyUI 调度，而是直接请求宿主机的 LM Studio（`127.0.0.1:1234`）进行意图嗅探，并在判断为求助时做出响应。
* **全链路追踪 (End-to-End Tracing)**：为解决分布式异步环境下的日志串包问题，系统实现了跨进程的 TraceID 透传。入口网关（Bot/BFF）生成 TraceID 并通过 `ContextVar` 在当前进程的协程中流转；在跨节点调度时，通过 HTTP Headers (`X-Trace-ID`) 与 Redis 任务 Payload 携带 TraceID，最终在 ComfyUI Worker 节点日志中还原，实现单次请求的全生命周期可观测性。

---

## 3. 业务板块划分

项目在功能模块上通过高内聚原则划分，不仅涵盖了业务核心，还包含了复杂的网络组网与存储运维板块。

### 业务模块与部署拓扑关系图

```mermaid
graph LR
    subgraph 网络暴露与边缘板块
        Net_Nginx[Nginx 反代与静态托管模块]
        Net_Tunnel[CF Tunnel/FRP 穿透模块]
        Net_VLAN[Tailscale 组网模块]
        Net_TgLocal[Telegram 本地 API 突破模块]
    end

    subgraph 交互与接入网关板块
        UI_Bot[Telegram Bot 交互模块]
        UI_Router[装饰器 Callback 路由分发器]
        UI_Web[Web 工作台 BFF 模块]
        UI_Dash[数据看板管控模块]
        UI_Pay[第三方支付回调处理模块]
        UI_CS[社群大模型客服智能体]
    end

    subgraph 核心领域模型板块
        Domain_User[修仙用户等级与折算体系]
        Domain_Bill[单轨制灵石计费与流水体系]
        Domain_Task[并发锁与防死锁剔除机制]
    end

    subgraph 推理引擎与调度板块
        Eng_Schedule[节点队列与中控派发器]
        Eng_Workflow[JSON 工作流动态注入]
        Eng_Comfy[ComfyUI 图像/视频生成阵列]
        Eng_LLM[LM Studio 本地大语言模型]
    end

    subgraph 存储运维与增值板块
        Sup_Gallery[社区广场与一键克隆保护]
        Sup_Storage_Hot[MinIO 热数据高频读写模块]
        Sup_Storage_Cold[MinIO 冷数据生命周期迁移]
        Sup_Storage_CDN[Cloudflare R2 广场边缘分发]
    end

    Net_Nginx --> UI_Web
    Net_TgLocal --> UI_Bot
    Net_Tunnel --> UI_Pay & UI_Dash
    Net_VLAN --> 交互与接入网关板块
    
    UI_Bot --> Domain_User & Domain_Task
    UI_Web --> Domain_User & Domain_Task
    UI_Pay --> Domain_Bill
    UI_CS --> Eng_LLM
    
    Domain_Task --> Eng_Schedule
    Eng_Schedule --> Eng_Workflow
    Eng_Workflow --> Eng_Comfy
    
    Eng_Comfy --> Sup_Storage_Hot
    Domain_Task --> Sup_Gallery
    Sup_Gallery --> Sup_Storage_CDN
    Sup_Storage_Hot -.-> Sup_Storage_Cold
```

### 核心板块职责边界
* **网络暴露与边缘板块**：解决“国内高算力底座无法直接对外提供服务”的痛点。由 VPS、Tunnel、FRP 共同承担抗 DDoD、反代、以及突破 Telegram 官方大文件限制的网络中转重任。
* **推理引擎与调度板块**：包含了执行具体任务的算力集群。不仅有 ComfyUI 生成图片视频，还新增了本地部署的 LM Studio，专为社群客服机器人提供文本推理算力。
* **存储运维板块**：基于 MinIO 构建的冷热分级存储架构。通过脚本自动将早期个人数据移至冷数据桶释放主盘 IO，同时利用 R2 加速公开广场。

---

## 4. 关键设计决策与技术选型

1. **海外双 VPS 与内网穿透架构**：
   * **决策**：为了利用国内便宜的高端显卡算力，同时满足海外用户的 Web 极速访问和 Telegram 服务器的直连，系统设计了物理分离的架构。
   * **技术选型**：使用 Tailscale 组建底层 VLAN 保证内网接口不暴露；使用 Cloudflare Tunnel 和 FRP 将支付回调、Dashboard 面板等特定服务安全映射到公网；使用独立的 Telegram VPS 运行 Local API 规避 50MB 官方限制。
2. **三级存储与数据生命周期 (Storage Tiering)**：
   * **决策**：多媒体 AI 生成极为消耗磁盘空间和 IO。若全放一处会导致主库在重度并发下“假死”（引发 Web 503 宕机）。
   * **技术选型**：热数据桶（MinIO 主桶）负责当前创作；冷数据归档桶（额外 MinIO）负责存放过期历史；Cloudflare R2 负责广场公开资源分发。配合离线 `_region_map` 机制，彻底避免了 MinIO 阻塞引发的 FastAPI 事件循环崩溃。
3. **去中心化推理引擎**：
   * **决策**：不仅图像/视频生成由 ComfyUI 阵列承接，文字推理也下沉到本地。
   * **技术选型**：采用 LM Studio（暴露兼容 OpenAI 的 API）在本地运行大模型（如 Qwen），结合 LangGraph 的长效记忆机制，打造极低成本、可控意图嗅探的“合欢宗大师姐”社群客服。

---

## 5. 架构合理性分析与优化建议

### 架构合理性 (Strengths)
* **网络穿透与安全性极高**：通过边缘节点、VLAN 和 FRP 的组合，将高价值的算力服务器和数据库完全隐藏在 NAT 之后。即使海外节点遭到攻击，核心数据和业务中枢依然安全。
* **存储成本与性能的完美平衡**：冷热数据分离的引入是一个极其出彩的设计。它让热盘始终保持高 IOPS，而把海量历史包袱转移到廉价大容量的冷存储中，辅以 R2 边缘加速，用户体验几乎不受影响。
* **高度模块化的业务底座**：不论是新增 Web 界面、TON 支付、还是基于大模型的 CS Bot，底层的 `src/core` 计费和鉴权系统都无需大改，展现了优秀的领域驱动设计（DDD）能力。

### 持续优化建议 (Recommendations)
1. **穿透服务的单点故障防范**：
    * 目前国内底座与外界通信高度依赖单条 FRP 隧道或 Tailscale 节点。建议配置多条隧道或使用 BGP 协议进行多线负载均衡与容灾，防止单点断网导致系统彻底失联。
2. **冷数据检索与缓存预热优化**：
    * 当用户翻阅非常久远的历史记录时，从“冷数据桶”提取大文件可能会存在延迟。建议在 Web BFF 层针对历史数据读取加入轻量级缓存预热机制（如请求时提前触发异步拉取到内存或热盘）。
3. **算力节点的动态弹性伸缩 (Auto-Scaling)**：
    * ComfyUI Worker 目前为静态多开隔离部署。未来如果接入更多的闲置显卡服务器，可以考虑引入 Kubernetes 或 Nomad，结合 Redis 队列深度，实现算力节点的动态伸缩与休眠。
