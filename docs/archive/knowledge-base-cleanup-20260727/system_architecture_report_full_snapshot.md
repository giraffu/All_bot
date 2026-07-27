# 修仙主题 AI 创作工作台 - 系统架构与业务分析报告（历史完整快照）

## 目录

1. [系统架构总览](#1-系统架构总览)
2. [关键数据流与核心闭环](#2-关键数据流与核心闭环)
3. [业务板块划分](#3-业务板块划分)
4. [关键设计决策](#4-关键设计决策)
5. [当前架构口径与维护约束](#5-当前架构口径与维护约束)

---

## 1. 系统架构总览

AllBot 当前采用“多入口接入 + 核心领域下沉 + 异步任务调度 + 分级存储 + 独立运维边界”的整体架构。系统已经从早期的 Telegram Bot 驱动单体，演进为覆盖 Telegram、Web、Dashboard 与支付的复合平台。

### 1.1 当前架构图

```mermaid
graph TD
    subgraph Client[客户端与外部系统]
        TG[Telegram 用户]
        WEB[Web 工作台]
        DASH[Dashboard]
        LANANA[本地分析平台]
        PAY[RMB 网关 / Telegram Stars / TON]
    end

    subgraph Edge[边缘与网络层]
        CFPAGES[Cloudflare Pages]
        CFTUNNEL[Cloudflare Tunnel]
        TGAPI[Telegram Local API / 文件服务]
        VLAN[Tailscale]
    end

    subgraph Gateway[云正式接入与应用层]
        BOT[cloud-tg-bot-prod]
        QQCC[cloud-qqcc-bot-prod]
        QPWORKER[cloud-qqcc-private-bot-worker-prod / profile]
        PGBOT[paid-group-guard-bot]
        API[cloud-web-api-prod / FastAPI]
        PAYAPI[cloud-payment-api-prod]
        DFRONT[cloud-dashboard-frontend-prod]
        DBACK[cloud-dashboard-backend-prod]
        QCFG[cloud-qqcc-config-frontend/backend-prod]
    end

    subgraph LocalAna[本地只读分析]
        LANA[local_analytics_platform]
        SHADOW[(bot_db_prod_shadow)]
    end

    subgraph Core[核心领域与调度]
        AUTH[Auth / Permission]
        TASK[Task Core Facade]
        TASKSUB[Task Submission / Monitor / Runtime]
        BILL[Billing / Payment Fulfillment]
        AFF[Affiliate / Redeem / Membership]
        GAL[Gallery / Apply Context]
        CENTRAL[Central API]
        WORKERS[ComfyUI Workers]
    end

    subgraph Infra[基础设施]
        PG[(托管 PostgreSQL)]
        REDIS[(托管 Valkey / Redis)]
        SHADOWSTORE[(本地 R2 shadow)]
        R2[(Cloudflare R2 user-data-prod)]
    end

    TG --> TGAPI --> BOT
    TGAPI --> QQCC
    TG -.私有 Bot webhook.-> CFTUNNEL --> API
    WEB --> CFPAGES
    WEB --> CFTUNNEL --> API
    DASH --> VLAN --> DFRONT --> DBACK
    PAY --> CFTUNNEL --> PAYAPI
    LANANA --> LANA --> SHADOW

    BOT --> AUTH
    BOT --> TASK
    QQCC --> AUTH
    QQCC --> TASK
    API --> REDIS --> QPWORKER
    QPWORKER --> AUTH
    QPWORKER --> TASK
    PGBOT --> PG
    API --> AUTH
    API --> TASK
    TASK --> TASKSUB
    API --> GAL
    API --> AFF
    PAYAPI --> BILL
    DBACK --> PG

    TASKSUB --> REDIS
    TASKSUB --> CENTRAL --> VLAN --> WORKERS
    WORKERS --> R2
    GAL --> R2
    AUTH --> PG
    BILL --> PG
    AFF --> PG
    BILL --> AFF
    API --> PG
    BOT --> PG
    QQCC --> PG
    QPWORKER --> PG
```

### 1.2 当前分层说明

- **客户端与外部系统**
  - Telegram 仍是核心入口之一。
  - Web 工作台已成为生成、历史管理、广场浏览与模板应用的主路径。
  - Dashboard 与支付 API 都是独立边界，不再是 Bot 的附属模块。
  - 本地数据分析平台是独立 LAN/本地只读入口，只分析 shadow 数据，不挂载到正式 Dashboard 菜单。
- **接入与应用层**
  - `tg-bot` 负责 Telegram 交互、FSM、结果消息与支付通知。
  - `qqcc_bot` 是独立简化 Telegram polling 入口，开放 `快速换脸`、`AI绘图`、`AI动图`、QQCC 专用轻量 `修仙市集` 与 `前往主bot`，复用同一用户、灵石、任务队列、对象存储与 worker 链路，不承载充值、affiliate 或高级 FSM。主业务 Bot 的旧 `修仙市集` 底部入口已改为 `懒人bot` 跳转，用户点击后通过 inline URL 前往 QQCC 懒人 Bot。
  - QQCC 用户私有 Bot 通过官方 QQCC 的申请 FSM 建立“一 owner 一 Telegram Bot”绑定。私有 Bot 不常驻 polling：Web API 校验 Telegram webhook 并写 Redis stream，独立 `qqcc_private_bot.worker` 按租户装配 QQCC Application，使用 `bot:qqcc-private:<id>` 隔离配置、任务与恢复；访客仍按自己的 AllBot 账户扣费。
  - `paid_group_guard_bot` 是独立 Telegram 审核 Bot，订阅付费群 `chat_join_request` 与普通 `message` update，按成功订单、后台赠送订单或筑基期及以上修为只读判断入群资格，并可对目标群执行非管理员链接/违禁词删除，不承载主业务 Bot 的菜单、生成、支付回调或文件处理。
  - `web-api` 承担认证、任务提交、任务运行态、历史、广场、用户中心、返佣兑换与站点通知读取等主能力。
  - `payment-api` 负责 RMB 回调；Stars 与 TON 各有对应履约入口。
  - TON 用户侧不再维护独立静态应用：主 Bot 通过 `MINI_APP_URL` 打开 Vue `/billing?method=ton&kind=membership`，低阶用户使用支付专用 Telegram 会话访问预建单与本人订单状态，链上到账仍由 Bot 轮询并进入共享履约内核。
  - `dashboard-frontend` 是管理后台云端 Nginx 网关，默认只通过 Tailscale/受控入口访问；`dashboard-backend` 除系统视图外，当前还承接站点通知管理和付费群审核 Bot 配置/日志管理入口。
- **核心领域与调度**
  - `task_core.py` 当前是稳定 facade，不再承担所有细节逻辑。
  - 真实默认装配已下沉到 provider/dependencies、submission、web-monitor、runtime 等子模块。
- **基础设施层**
  - 正式 PostgreSQL 与 Valkey/Redis 已迁到云侧托管/外部服务，保存主数据、业务账本、队列、并发锁、登录限流、任务运行态与 worker heartbeat。
  - 后端运行时数据库明确以 PostgreSQL 为唯一支持方言；schema、Alembic migration、seed SQL 和 shadow 同步脚本允许使用 PostgreSQL 专有能力，详见 `docs/adr/0001-postgresql-only-runtime.md`。
  - 新生成对象统一写入 R2 `user-data-prod`；本地对象存储只保存 R2 shadow/灾备副本，不参与正式 Web/Dashboard 运行时读取。

### 1.3 云正式生产口径


- 云端 Droplet `allbot-do-sgp1-control` 承载 `cloud-central-api-prod`、`cloud-web-api-prod`、`cloud-payment-api-prod`、`cloud-dashboard-backend-prod`、`cloud-dashboard-frontend-prod`、`cloud-qqcc-config-backend-prod`、`cloud-qqcc-config-frontend-prod`、`cloud-imgproxy-prod` 与 `cloud-tg-bot-prod`；`cloud-qqcc-bot-prod` 是独立 `qqcc-bot` profile 服务。2026-07-12 已执行 QQCC 私有 Bot migration 并显式启动 `cloud-qqcc-private-bot-worker-prod`（`qqcc-private-bots` profile），生产 webhook 复用 `api.aivison.it.com`，owner WebApp 使用公开 `private-bot.aivison.it.com`；后续默认 compose 操作仍须显式保留该 profile。
- `web.aivison.it.com` 由 Cloudflare Pages 承接静态前端；正式 Web API 独立走 `api.aivison.it.com` Cloudflare Tunnel 回源云 Web API，`rmb.aivison.it.com` 回源云 Payment API。
- 长期运维细节见 `docs/子模块_云正式控制面部署_cloud_prod_control_plane.md`。

### 1.4 云测试与本地灾备口径

- 云测试控制面运行在独立 DigitalOcean Droplet `allbot-do-sgp1-test-control`，Tailscale IP `100.82.124.91`。同机容器承载测试 PostgreSQL、Redis、Central API、Web API、Dashboard Backend、Dashboard Frontend、QQCC Config Backend/Frontend、imgproxy 与测试 Bot；`cloud-qqcc-bot-test` 仅在配置独立 `QQCC_BOT_TOKEN_TEST` 且显式/原运行状态需要时启动，私有 Bot worker 也必须通过 `qqcc-private-bots` profile 显式启动。本地主服务器的 `workers/docker-compose-cloud-worker-test.yml` 声明 `cloud-comfy-agent-test-1..8`，默认常驻只保留 test-1 与 test-8，其余测试 worker 只在 smoke/canary 窗口按需启用；`cloud_worker_test_08` 指向 gpu-002 SCAIL-2 LAN AIO runtime。
- 云测试 Web 公网入口是 Cloudflare Pages `web-cf-test.aivison.it.com`，API 经 `api-cf-test.aivison.it.com` Tunnel 回源云测试 Web API `100.82.124.91:8001`。
- 本地主服务器不再保留一套日常正式入口；只保留云正式整体故障时的临时本地正式灾备方案。操作手册见 `docs/子模块_本地正式灾备切换_local_prod_fallback.md`。

---

## 2. 关键数据流与核心闭环

### 2.1 生成任务主链路

```mermaid
sequenceDiagram
    autonumber
    actor U as 用户
    participant Entry as Bot / QQCC Bot / Web
    participant Auth as Auth / Permission
    participant Facade as task_core facade
    participant Deps as provider / dependencies
    participant Central as 云 Central API
    participant Worker as ComfyUI Worker
    participant Store as R2 / S3 presign
    participant PG as 托管 PostgreSQL

    U->>Entry: 提交生成请求
    Entry->>Auth: 校验身份/境界/登录态
    Entry->>Facade: 调用统一提交入口
    Facade->>Deps: 组装默认依赖或使用显式注入依赖
    Facade->>PG: 计费、历史、状态写入
    Facade->>Central: 派发 backend_task_id
    Worker->>Store: 新产物写 R2
    alt Web
        Facade->>Facade: 异步挂载 side-effect monitor
        Facade->>PG: 成功持久化/失败退款/释放锁
    else Bot
        Entry->>Entry: run_bot_task_application 前台监控
        Entry->>PG: 完成/取消/失败终态与消息回传
    end
    Entry-->>U: SSE / 结果查询 / Telegram 消息
```

当前关键事实：

- Web 主入口是 `/api/tasks/generate`，请求体以 `inputs` 为主。
- 任务链路显式区分 `registry_task_id` 与 `backend_task_id`。
- Web 运行态依赖 `src/services/task_web_side_effects.py`、`task_web_lifecycle_monitor.py` 与 `task_web_terminal_finalization.py`；Bot 则由 `run_bot_task_application(...)` 前台监控。
- 任务结果除了运行态 stream 外，还有 history fallback 与结果查询兜底。

延伸阅读：

- 生成任务全链路专题文档：`/docs/子模块_生成任务全链路_task_full_chain.md`
- 任务调度专题文档：`/docs/子模块_任务调度_task_scheduler.md`
- 执行面与节点通信专题文档：`/docs/子模块_中控API与节点通信_central_api.md`

### 2.2 认证与会话闭环

- Web 认证当前是双入口：Telegram 验签登录 + 用户名密码登录。
- JWT 以 `SECRET_KEY` 签发，并携带 `pwd_ver` / `channel` 等语义 claim。
- 改密会导致旧 token 失效；权限变化会触发动态复核。
- Telegram Bot 个人中心打开 Web/Mini App 时，当前通过 `build_versioned_mini_app_url()` 在 `MINI_APP_URL` 上追加 `v` 参数，借此主动击穿 Telegram 旧 WebView 快照。

### 2.3 支付、返佣与资产闭环

- 支付域已经从单一充值升级为“支付履约 + 返佣入账 + affiliate 兑换灵石/会员”的复合域。
- RMB 履约当前走 membership settlement 主路径，并保留 legacy fallback。
- affiliate 已不仅是返佣台账，还承担兑换与审计语义。

### 2.4 社区广场闭环

- 广场当前包含投稿、点赞、评论、收藏、我的投稿、我的收藏与 Web apply-context。
- `apply-context` 已成为 Web workbench 主路径。
- Telegram 端 `gallery_apply_fsm` 仅应视作兼容链路，不再是主产品路径。

### 2.5 站点通知闭环

- Dashboard 当前可维护全站站点通知，支持标题、正文、启用状态、置顶、目标修为与目标身份。
- Web 侧通过 `/api/app/site-notice` 与 `/api/app/site-notices` 读取通知。
- 通知可见性按用户当前 `group` / `identity` 做“任一命中即显示”过滤；两项都为空表示所有 Web 用户可见。

---

## 3. 业务板块划分

### 3.1 主营板块

- **01 AI 创作与生成**
  - 负责多模态生成、任务提交、排队、结果回传与模板应用。
- **02 商业化与会员资产**
  - 负责充值、身份月卡、订单履约、返佣账本与 affiliate 兑换。
- **03 社区广场与社交互动**
  - 负责投稿、互动、评论、收藏、apply-context 与公开资源分发。
- **04 用户修为与身份权限**
  - 负责境界、身份、Web 准入、动态权限复核与任务优先级。

### 3.2 支撑板块

- **任务调度与节点通信**
  - task core facade、provider/capability、Web monitor、runtime cleanup、QueueManager、Central API、Workers。
- **对象存储与媒体交付**
  - R2 正式写入、短签/公网 URL 与结果生命周期。
- **交互状态机与回调路由**
  - Telegram FSM、全局菜单黑盒退出、callback prefix 路由、临时文件服务。
- **本地经营与提示词分析**
  - `local_analytics_platform` 只读连接本地 shadow 数据库，提供用户、灵石、充值、生成、Prompt Mart、提示词瘦身、提示词向量化和媒体引用核验，不承担线上管理后台写操作。

---

## 4. 关键设计决策

### 4.1 Core 的目标边界与当前差距

- 已落地的硬边界是：`src/core/` 不接收或导入 Telegram `Update`、FastAPI `Request/APIRouter` 等平台入口对象，入口层先转换为内部 ID/request/context。
- 目标边界仍是 core 只消费内部协议、domain config、provider/capability 或显式 dependencies；facade 维持小 interface，复杂输入准备、billing、submission、side effect 与 runtime cleanup 下沉到实现层或 builder。
- 该目标尚未完全实现：当前 core 仍存在对 `config`、SQLAlchemy、HTTPX、PIL/subprocess 以及默认 provider 装配的直接依赖。它们是待迁移到 adapter/composition root 的架构债务，不能用“未发现平台对象 import”推导为“基础设施隔离已经完成”。

### 4.2 双 ID 运行态模型

- 本地注册与历史链路使用 `registry_task_id`。
- 后端执行与 best-effort cancel 使用 `backend_task_id`。
- 取消、恢复、僵尸清理、强制终止都必须显式区分两者。

### 4.3 Web 与 Bot 监控分流

- Web 提交成功后异步挂载 side-effect monitor。
- Bot 进入 `run_bot_task_application(...)` 前台监控与展示链路。
- 两条路径共享 task core，但不共享同一表示层职责。

### 4.4 测试 seam 前移

- 新测试优先通过 `dependencies` / `*_func` seam 注入能力。
- 不再鼓励依赖旧的模块级 patch 点。

---

## 5. 当前架构口径与维护约束

- 文档中的入口函数、异常类型、超时值、双 ID 语义必须与代码保持一致。
- `src/bot_main.py` 是 Telegram Bot shared entrypoint，测试/生产模式统一由 `BOT_TYPE` 选择。
- `paid_group_guard_bot/main.py` 是付费群审核 Bot 独立入口，必须使用独立 `PAID_GROUP_BOT_TOKEN`，不能复用主业务 `BOT_TOKEN` 或接入主 Bot FSM；群管理配置和 JSONL 删除日志由 Dashboard 通过共享文件目录管理。
- 若修改 task core facade、provider/dependencies、submission、web-monitor、runtime、Bot 五段式上下文或 stream fallback，必须同步更新知识库。
- 若修改云正式 compose、worker compose、边缘 upstream、R2/legacy 媒体策略、Central 状态观测缓存或 Dashboard 高频监控策略，必须同步更新云正式部署文档与相关 skills。
- 若技能文档与代码入口冲突，应先更新 skill / docs，再继续开发。

### 5.1 维护基线与知识库口径

- 2026-06-27 知识库维护口径：`AGENTS.md` 只保留全局路由，细节以 `.codex/skills/*/SKILL.md`、`/docs` 与 `docs/knowledge_base_audit_matrix.md` 为准；技能正文应记录稳定边界和入口，不沉淀一次性 Pod ID、任务 ID、失败尝试流水账或真实密钥值。一次性 canary、迁移证据和模型上传流水应进入 `docs/archive/` 或 `logs/`。
- `src/task_core_process_defaults.py` 是 task core process 默认装配的真实入口。
- `wan22_aio_video` 只保留为兼容/回滚 profile；新视频测试、扩容和正式备用 worker 都应使用 split profile。
- 当前主要风险集中在长期维护成本：`local_analytics_platform/app/prompt_vectors.py::_refresh_prompt_token_stats_unindexed`、`src/services/qqcc_draw_chain_service.py::execute_qqcc_draw_scene_chain`、本地分析 prompt 大路由、Dashboard RunPod 自动扩缩服务、双 worker bundle 漂移，以及 core 基础设施依赖尚未完全移出。
- workflow 资产已收口到 `workers/comfy_agent/workflows`；Central API 不再维护 backend 副本，也不再执行 workflow 启动校验。
- `TaskCoreServiceProviders` 与主要 capability 已补强 `Protocol` / 精确 `Callable` 契约；新增 provider/capability 时继续沿用显式类型与 dependencies seam。
- 详细质量基线见 `docs/子模块_代码静态分析与质量评估规范_code_quality.md` 与 `logs/code_analysis_report_20260711_2140.md`。
