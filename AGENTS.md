# AI 编程助手参考指南 (AGENTS.md)

本文档是 AI 编程助手参与“修仙主题 Telegram 图像与视频机器人”项目时的全面开发指南。它基于系统最新的重构与功能迭代（包括三大支付体系的并入）进行了全面更新，涵盖了整个分布式架构、逻辑、数据流以及容灾机制。

## 1. 系统全景与模块架构 (System Panorama)

当前系统已经演进为一个多模块、多节点的分布式架构。主要由以下几个核心子系统构成：

### 1.1 核心 Bot 服务 (Telegram Bot)
这是系统的传统入口和即时交互层。
- **职责**：处理 Telegram 用户消息交互、状态机管理、修仙境界与权限判定、任务的下发排队，以及提供多种支付方式的 UI 菜单入口。Bot 层已全面瘦身，核心业务逻辑已下沉至 `src/core/`。
- **代码位置**：`/src` (主要入口 `src/bot_test.py` 与 `src/bot_prod.py`，回调入口在 `src/handlers/callback_handler.py`)
- **容器编排**：`deploy/docker-compose.yml` (正式服 `tg-bot`) 和 `deploy/docker-compose-test.yml` (测试服 `tg-bot-test`)。

### 1.2 Web BFF 后端 API (Backend For Frontend)
这是系统的新一代 Web 端统一接口层，采用 FastAPI 架构。
- **职责**：为 Vue3 前端提供 RESTful API，处理 JWT 鉴权（如 Telegram Widget 登录）、生成 MinIO 预签名直传 URL（绕过后端直接上传大文件），并通过 SSE (Server-Sent Events) 实时向前端推送生图/视频任务进度。
- **代码位置**：`/src/web_api/` (路由在 `src/web_api/routers/`)
- **容器编排**：集成在 `deploy/docker-compose.yml` 中（服务名：`web-api`，默认监听 `8000` 端口）。

### 1.3 Web 前端应用 (Vue3 SPA)
现代化、响应式的修仙主题 AI 创作工作台。
- **职责**：提供沉浸式的图片/视频上传、生成预览、参数调节与资产管理界面。与 BFF 后端交互，实现所见即所得的 AI 创作体验。
- **代码位置**：`/frontend` (基于 Vue 3 + Vite + Tailwind CSS + Ant Design Vue)
- **容器编排**：集成在 `deploy/docker-compose.yml` 中（服务名：`web-frontend`，开发服 `5173`，正式服通过 Nginx 托管静态资源）。

### 1.4 核心业务逻辑层 (Core Layer)
这是系统最重要的底座，实现了**平台无关 (Platform-Agnostic)** 的业务流转。
- **职责**：无论是 Telegram Bot 还是 Web BFF，都必须调用 `src/core/` 下的函数来执行扣费、鉴权、并发锁检查和任务分发。
- **代码位置**：`/src/core/` (包含 `task_core.py`, `user_core.py`, `billing_core.py`)
- **红线**：此目录下的代码**绝对禁止**引入任何与 Telegram `Update` 或 FastAPI `Request` 相关的特定平台对象。必须使用内部统一的 `internal_user_id` 进行数据流转。

### 1.5 支付回调服务 (Payment API)
用于处理第三方支付网关（如易支付/人民币支付）的异步回调请求。
- **职责**：监听外网（通过 Cloudflare Tunnel）发来的 HTTP 回调请求，验证签名，进行订单的幂等处理，并调用统一发货服务发放灵石与身份特权。
- **代码位置**：`src/payment_api_server.py` 与 `src/services/payment_fulfillment_service.py`
- **容器编排**：集成在 `deploy/docker-compose.yml` 中（服务名：`payment-api`，监听本地 `8021` 端口）。

### 1.3 后台管理系统 (Dashboard)
用于管理员监控系统状态、管理用户和处理异常任务。
- **Dashboard 后端**：FastAPI 架构，代理前端对后端的请求，监控 Redis 中的活动任务，提供人工干预接口（如强制退款终止）。
  - **代码位置**：`/dashboard/backend`
- **Dashboard 前端**：Vue 3 架构，可视化监控面板。
  - **代码位置**：`/dashboard/frontend`
- **容器编排**：`/dashboard/docker-compose.yml` (服务：`dashboard-frontend`, `dashboard-backend`)，默认使用 `host` 网络模式。

### 1.4 支付前端 (TON Frontend)
用于处理 TON 区块链支付的 Web App 前端界面（Bot 内嵌）。
- **职责**：生成并拉起 TON 钱包支付请求（通过 `tonconnect-ui`）。
- **代码位置**：`/frontend` (通常编译后提供静态资源或由 nginx 托管)。

### 1.5 中控 API 后端 (Central API Backend)
作为 Bot 与底层生图节点 (Workers) 之间的中间调度层。
- **职责**：接收 Bot 发来的任务，解析工作流 (Workflows)，与对象存储交互，并调度后端的 ComfyUI Agents。
- **代码位置**：`/backend` (主要入口 `/backend/app/main.py`)
- **容器编排**：`/backend/docker-compose.yml` (服务：`api`，端口 8003)。

### 1.6 图像/视频生成节点 (Workers / Comfy Agents)
实际执行生图和视频任务的计算节点。
- **职责**：运行具体的 ComfyUI 实例，执行 JSON 工作流并返回结果。
- **代码位置**：`/workers/comfy_agent1`, `/workers/comfy_agent2` 等（通过多开隔离）。
- **协同**：API 后端通过配置或 Redis 队列向这些 Agent 派发具体任务。

### 1.7 AI 客服大师姐 (LLM Customer Service Bot)
基于大语言模型和 LangGraph 构建的专属社群服务智能体，扮演“合欢宗大师姐”的人设。
- **职责**：在指定的官方群组内，解答新老弟子关于系统操作、充值、排队报错等疑问。
- **核心能力**：
  - **意图嗅探 (Intent Sniffing)**：即使群友没有 `@` 机器人，也能通过轻量级 LLM 调用实时分析超过3个字符的对话意图，一旦判定为“求助/疑问”则主动搭话。
  - **长效记忆**：使用 LangGraph 的 `MemorySaver` 按 `chat_id` 自动隔离并持久化各个群组的上下文。
  - **防打扰隔离**：严格受限于 `.env` 中的 `ALLOWED_GROUP_IDS` 白名单，拒绝私聊和其他陌生群组。
- **代码位置**：`/cs_bot` (核心逻辑在 `langgraph_client.py` 和 `bot.py`)。
- **容器编排**：独立部署，通过 `host.docker.internal` 连接宿主机上的本地 LM Studio 推理服务 (端口 1234)。与主 Bot 一样直连 `69.63.220.115:8081` 的 Telegram Local API。

---

## 2. 核心基础设施服务 (Infrastructure Services)

系统高度依赖以下三大基础设施，在开发和本地联调时需确保它们可用：

1. **Redis 服务**：
   - **分库隔离架构**：系统目前采用逻辑分库隔离以防止数据误删（Bot 使用 `DB 1`，API 使用 `DB 2`）。
   - **用途**：
     - **DB 1 (Bot 侧)**：高速缓存、任务追踪 (`ActiveTasksTable`)、分布式锁（单用户并发控制 `MAX_CONCURRENT_TASKS`）以及 Bot 和 Dashboard 之间的状态同步。
     - **DB 2 (API 侧)**：任务排队调度 (`comfy:queue:pending` / `running`)、Worker 心跳检测 (`comfy:agent:heartbeat:`)、僵尸任务巡检等。
   - **Pub/Sub 实时订阅**：Bot 端通过 Redis 的全局 Pub/Sub 机制 (`comfy:task_events:{task_id}`) 实时获取生图进度，摒弃了传统的 HTTP 高频轮询。
2. **PostgreSQL 服务**：
   - **用途**：系统的唯一持久化信源。存储用户数据 (`users`)、订单 (`orders`) 和严格的资产流水 (`user_logs`)。
   - **访问**：使用 SQLAlchemy Async 进行异步交互。
3. **MinIO 服务**：
   - **用途**：对象存储，兼容 S3 协议。用于存储用户上传的图片/视频、系统生成的中间产物以及模板。
   - **结构**：主要包含 `bot-data` (系统主数据), `comfyui-input` (传给 Worker 的输入), `comfyui-temp` (Worker 的输出), `bot-template` (模板) 等 Bucket。
   - **引用传递机制**：为了节省内网带宽和 API 内存，Bot 和 Central API 之间不再直接传输媒体文件流，而是仅传递 MinIO 中的 `Object Key`（JSON 格式）。由底层的 Worker 直接从 MinIO 对应 Bucket 下载。
   - **大文件直传 (Web 端)**：针对 100MB+ 的视频，Vue3 前端调用 BFF 获取**预签名直传 URL (Presigned PUT URL)** 后，直接与 MinIO 交互上传文件，彻底绕过后端流量瓶颈。注意，BFF 层使用了 `_region_map` 离线签名防御机制，防止在 MinIO 负载过高时因 SDK 发起同步的 `?location=` 网络请求而卡死主事件循环。
4. **Cloudflare R2 (边缘存储/加速)**：
   - **用途**：作为国内 MinIO 的公网加速层，专为“社区广场 (Gallery)”的高并发读取场景设计。
   - **同步机制**：当作品被推送到排行榜时，后端的 `StorageService` 会开启异步守护线程，将作品从本地 MinIO 节点转存到国外的 R2 节点，然后下发 R2 的公共访问域名，极大缓解国内主节点的上行带宽压力。

---

## 3. 支付与发货体系红线 (Payment & Fulfillment Redlines)

系统目前共存三种支付通道（TON、Telegram Stars、RMB/易支付），在修改支付或发货代码时，**必须严格遵守以下业务规则**：

1. **建单与幂等性**：
   - RMB（支付宝/微信）体系采用了“先预建单 (PENDING)，后异步验签发货 (SUCCESS)”的标准流程，这具有极高的幂等性安全性。在设计新的支付通道时应以此为标杆。
   - Stars 支付依赖 `successful_payment` 回调才建单，存在极小概率的竞态重复发货风险，修改时需小心数据库锁。
2. **直充与月卡折算的隔离 (`is_pure_credit`)**：
   - 当 `membership_plans.duration_days == 0` 时，此为“灵石直充”套餐。发货时绝对不可改变用户的 `current_identity` (当前身份) 和 `identity_expire_at` (到期时间)。
3. **月卡跨级折算逻辑**：
   - **升级**：剩余老套餐价值按权数（外门1 : 内门2 : 核心5 : 真传10）折算成新套餐的额外天数，并加上新买天数。
   - **降级/同级保护**：拒绝降低身份等级（保持高级身份），将新买的低级套餐按权数折现，延长高级身份的到期时间。
   - **收口代码**：上述核心逻辑目前已收口在 `src/services/payment_fulfillment_service.py`，所有通道应尽量复用该逻辑以防计算 Bug 分化。

---

## 4. 运维指南与容器管理 (Operations & Maintenance)

### 4.1 容器的启动与重建 (Build & Start)
当修改了代码后，必须通过 Docker Compose 重新构建并启动容器。
为避免旧版本 docker-compose 常见的 `ContainerConfig` 报错，建议在构建前先移除旧容器。

- **主 Bot 服务与 Payment API (正式服)**:
  ```bash
  docker rm -f tg-bot payment-api
  docker-compose -f deploy/docker-compose.yml up -d --build
  ```
- **主 Bot 服务与 Payment API (测试服)**:
  ```bash
  docker rm -f tg-bot-test payment-api-test
  docker-compose -f deploy/docker-compose-test.yml up -d --build
  ```
- **Web 体系 (BFF API 与 Vue Frontend)**:
  ```bash
  # 若在生产环境，可能只需启动 web-api，前端静态资源由 Nginx 托管
  docker-compose -f deploy/docker-compose.yml up -d --build web-api web-frontend
  ```
- **Dashboard 后台服务**:
  ```bash
  cd dashboard && docker-compose up -d --build
  ```
- **中控 API 后端服务**:
  ```bash
  cd backend && docker-compose up -d --build
  ```
- **AI 客服大师姐 (CS Bot)**:
  ```bash
  cd cs_bot && docker rm -f cs-bot && docker-compose up -d --build
  ```
  *(注意：对于 CS Bot，单纯的 `docker restart` 或 `docker-compose restart` 通常不会使环境变量或代码修改生效，必须通过 `--build` 重新构建容器！)*

### 4.2 Bot 暂停与维护模式 (Maintenance Mode)
当系统需要紧急维护、修复 Bug 或排查问题时，可以开启维护模式。这会无缝拦截新生成任务的创建，但不影响用户的查询与签到功能。
- **后台强制开启维护模式**：
  ```bash
  # 正式服
  docker exec tg-bot touch /app/MAINTENANCE
  ```
- **关闭维护模式，恢复服务**：
  ```bash
  docker exec tg-bot rm -f /app/MAINTENANCE
  ```

### 4.3 日常排障脚本 (Troubleshooting Scripts)
宿主机根目录提供了一系列排障脚本：
- **清理僵尸任务**：已内置到 `bot_test.py` 的后台自愈协程中 (`clean_zombies_loop`)。如果需要手动执行，可运行 `docker exec tg-bot python clean_zombies.py` (自动清理驻留过长占用并发锁的任务，并向 API 端发送取消请求实现双向剔除)。
- **查看 Redis 排队**：`docker exec tg-bot python check_redis.py`。
- **独立 API 支付联调测试**：如果易支付网关报错，可通过独立脚本如 `test_huanyuy.py` 单独发起 POST/GET HTTP 请求进行调试，以避免受限于 Docker 容器环境的调试盲区。

### 4.5 MinIO 存储高并发与 503 宕机排障 (MinIO RequestTimeout)
- **现象**：Web 端大文件上传报错 503，同时所有访问 Web 后端的请求（如获取历史记录、获取用户信息）全部陷入几十秒的死锁超时。
- **根本原因**：当底层生图节点执行重负载任务导致磁盘 IO 拥堵时，MinIO 会因检测不到磁盘响应而强制将其下线 (`taking drive /data offline`)，进而拒绝发放资源锁。若后端（如 FastAPI）的 MinIO SDK 未做防御处理，它发起预签名时的一个**同步网络请求**（`?location=`）将会把整个异步事件循环完全卡死。
- **恢复方案**：此情况为瞬时软故障，直接通过 `docker restart minio-server` 重启容器重新挂载磁盘即可。为了彻底避免事件循环被阻塞，代码中已通过 `self.client._region_map[MINIO_BUCKET] = "us-east-1"` 注入了静态离线映射。
### 4.4 Web 端与海外 VPS 边缘节点运维 (Web & VPS Edge Node Maintenance)
为了提升海外用户访问网页和加载媒体的速度，系统引入了海外 VPS 作为边缘节点（通过 Tailscale 等与武汉底座组建虚拟局域网）。相关核心运维经验如下：

1. **前端自动化部署 (Frontend Deployment)**：
   - 前端代码发布已自动化。在 `/frontend` 目录下执行 `npm run deploy` 即可一键完成打包并同步至 VPS。
   - 底层使用 `scp` 与内置私钥 (`ssh_key/id_rsa.pem`) 推送文件至 VPS 的 `/root/dist/` 目录。
   - **注意**：部署环境私钥必须严格保持 `600` 权限 (`chmod 600 id_rsa.pem`)，否则 SSH 协议将拒绝连接。
2. **Nginx 反向代理排障 (Nginx Proxy Troubleshooting)**：
   - **502 Bad Gateway**：表示 VPS 接收到请求但无法连通武汉后端。需检查武汉服务器的 `web-api` 容器是否启动，以及两端虚拟局域网 IP 是否互通。
   - **404 Not Found (API 路由丢失)**：极高概率是 Nginx 代理配置错误。**正确配置**：`location /api/ { proxy_pass http://<武汉IP>:8000; }`。`proxy_pass` 末尾**严禁**携带斜杠 `/`，否则会导致 `/api/auth` 等路由被截断为 `/auth` 传给后端。
3. **Telegram 网页登录授权排障 (Telegram Web Auth)**：
   - **前端显示 "Username invalid"**：缺少前端环境变量 `VITE_TELEGRAM_BOT_USERNAME`，或未前往 Telegram 官方 `@BotFather` 使用 `/setdomain` 绑定当前网页的访问域名。
   - **后端报错 401 Unauthorized**：前端登录成功但后端拒绝发牌。原因是武汉服务器后端 `.env` 中配置的 `BOT_TOKEN` 与前端使用的 Bot 身份不一致，导致后台的 HMAC-SHA256 签名比对失败。

---

## 5. 核心业务逻辑红线 (Business Logic Redlines)

1. **单轨制代币 (`credits`)**：
   曾经的 `temp_credits` 已被完全废弃，系统目前只有 `credits`（灵石）。所有代码中严禁再使用或恢复 `temp_credits`。
2. **强制数据流审计**：
   任何涉及灵石增减的代码修改，**必须**同步在 `user_logs` 表中插入流水记录。底层通过 `contextvars` 自动追踪 SQL 触发者的 User ID。如果遗漏，会导致严重的对账错误。
3. **并发锁与状态一致性**：
   在修改 `src/services/task_service.py` 任务调度逻辑时，请务必保证 `ActiveTasksTable` 的状态更新与 PostgreSQL 的扣费/退费逻辑在业务上保持最终一致。
   - **双向取消机制**：一旦在 Bot 侧主动抛弃或终止了某个任务（如 `clean_zombies`），必须调用中控 API 的 `DELETE /api/tasks/{task_id}` 进行双向踢除，防止 Worker 算力浪费（俗称“幽灵任务”）。
4. **ComfyUI 工作流参数注入原则**：
   - 所有的生图或视频任务类型，其 JSON 工作流模板必须由 `workflow_patcher.py` 负责动态修改参数。
   - **红线**：禁止在带有多个图像输入的工作流（如 `face_swap`）中使用启发式 (Heuristic) 匹配来盲目覆盖图片节点，这会导致参数错乱并触发 ComfyUI 的 HTTP 400 错误。
   - 所有的节点映射必须通过 `mappings.json` 精确绑定。例如：视频类工作流中的尺寸调整应当映射给 `FindPerfectResolution` 节点，时长控制应映射给 `PainterI2V` 节点。并且要小心 Python 的 `None` 与 `JSON null` 类型转换对 `seed` 等整数型参数引发的问题。
5. **数据库表结构迁移规范 (Alembic)**：
   - **严禁使用原生 SQL**：绝对禁止在 `src/database/core.py` 的 `init_db()` 或任何地方使用原生 `ALTER TABLE` 语句来修改表结构，以免引发分布式启动时的锁表冲突和状态混乱。
   - **正确流程**：
     1. 直接在 `src/database/models.py` 中修改、添加或删除字段。
     2. 在宿主机（项目根目录）终端执行：`alembic revision --autogenerate -m "变更备注"` 以生成迁移脚本。
     3. 容器启动时（或代码中 `run_alembic_upgrade()`）会自动应用这些迁移脚本。

---

## 6. Telegram Local API 与大文件架构 (Telegram Local API & Large File Architecture)

为了突破官方 Bot API 的文件大小限制（下载 20MB / 上传 50MB）并大幅提升视频等大文件的传输速度，系统采用了一套基于独立 VPS 的 Local API 与 HTTP 文件服务双轨架构。

### 6.1 VPS 容器部署架构
在独立 VPS 上运行了两个核心容器：
1. **API Server (`telegram-bot-api`)**：
   - **监听端口**：`8081`
   - **关键环境变量**：`TELEGRAM_LOCAL=1`。开启 Local 模式后，API 获取文件时不再返回 HTTP 下载链接，而是返回宿主机的绝对文件路径。
   - **权限红线**：容器内部通常以 UID 101 运行，需确保挂载的宿主机目录（如 `/var/lib/telegram-bot-api`）具备读写权限（`chown -R 101:101` 或 `chmod -R 777`），否则 Bot 获取媒体时会报 `Permission Denied` 进而引发 404 错误。
2. **File Server (`telegram-file-server`)**：
   - **监听端口**：`8082`
   - **职责**：由于 API 返回的是绝对路径，必须通过额外的 HTTP 服务器将其暴露。通常运行一个极简的 Python HTTP 服务（如 `python -m http.server 8000 --directory /`），并将 API 的文件目录通过**只读模式 (ro)** 挂载到容器中，用于提供文件的直接 HTTP 下载。

### 6.2 Bot 代码层适配与 Monkey Patch
在 Bot 的主入口文件（`src/bot_test.py` 和 `src/bot_prod.py`）中，必须进行如下适配才能配合上述 VPS 架构：
- **请求路由指向**：
  ```python
  .base_url("http://<VPS_IP>:8081/bot")
  .base_file_url("http://<VPS_IP>:8082")
  ```
- **Monkey Patch 修复 PTB 路径拼接 Bug**：
  `python-telegram-bot` (PTB) 默认在处理自定义的 `base_file_url` 时，会强行拼接 `bot<token>`（例如生成 `http://ip:8082bot<token>/var/lib/...`），这会导致文件服务器报 404。
  为此，代码中对 `telegram.File.download_to_drive` 进行了全局 **Monkey Patch**：
  1. 拦截底层下载请求，解析出真实的绝对路径。
  2. 手动拼接至 `8082` 端口 URL：`f"http://<VPS_IP>:8082{raw_path}"`。
  3. 使用 `httpx.AsyncClient(proxy=None)`（强制直连，禁用代理以防干扰）发起下载，并配置足够长的 `timeout` (如 120s) 以应对大文件传输。

## 7. Web 端架构与鉴权红线 (Web Architecture & Auth)

随着 Web 端的引入，系统形成了一套有别于 Telegram Bot 的长连接与鉴权机制，开发时必须遵循：

### 7.1 JWT 鉴权与身份白名单机制 (Identity Access Control)
- **无状态设计**：Web BFF 必须保持无状态 (Stateless)，用户的登录凭证完全依赖 `Authorization: Bearer <JWT>` 传递。
- **动态白名单拦截**：在签发 JWT 时，BFF 会调用 `permission_service` 计算用户实时身份。当前 Web 端仅对**“内门弟子、核心弟子、真传弟子”**开放，不满足条件者将直接返回 HTTP 403。
- **Token 解析**：在 `src/web_api/core/security.py` 中，JWT Payload 里的 `sub` 字段存储的是系统内部的 `internal_user_id`（对应 `users.id`），**严禁将其混淆为 Telegram ID**。

### 7.2 SSE (Server-Sent Events) 状态同步机制
- **单向数据流**：前端不采用短轮询，而是通过向 BFF 发起 `/{task_id}/stream` 请求建立 SSE 连接。
- **竞态条件防御**：任务提交与完成之间的耗时极短。为了防止前端建立 SSE 连接前任务已完成（导致死锁等待），BFF 的 Stream 路由中必须**先查询一次 Redis 当前状态**（`get_task_status_full`），再进入 Pub/Sub 订阅监听循环。
- **并发锁释放策略 (Ghost Locks Defense)**：由于 Web 请求可能因网络异常中断（Client Disconnect），BFF 层采用了 FastAPI 的 `BackgroundTasks` 来监控任务执行。无论前端 SSE 是否断开，后台协程都将确保在任务结束时释放该用户的并发锁。

---

## 8. 社区广场与一键应用功能架构 (Community Gallery Architecture)

本章节梳理了社区广场（Gallery）、排行榜、点赞/点踩以及一键应用模版等核心功能的架构、数据流和业务逻辑，以及相关开发规范。

### 8.1 核心实体与缓存架构
- **数据关联**：社区功能建立在现有的用户和任务历史体系之上，新增了 `GalleryPost` (投稿) 和 `UserInteraction` (互动) 两个核心表。`GalleryPost` 通过 `task_id` 与 `History` 1对1关联。
- **0流量转发机制 (Zero-Bandwidth Forwarding)**：为了优化服务器带宽，排行榜采用了基于 `telegram_file_id` 的缓存转发机制。优先使用 TG 内置 file_id 转发，若无缓存才从 MinIO 下载流并重新上传，随后更新 DB 缓存。

### 8.2 业务逻辑红线与设计亮点
- **原创保护与“禁止套娃”机制**：
  - 如果用户一键应用别人的模板生成了作品，底层发起生成请求时会**强制传入 `allow_contribute=False`**。
  - 生成完毕后的消息键盘将不再展示“一键投稿”按钮，从而彻底切断复制者的二次投稿链路。
- **时长计费容错与动态降级**：
  - **阈值容错**：视频生成存在误差（如 5.78s），在计费时加入容错（`≤6秒` 均视为 5s 基础档），防止越档扣费。
  - **动态降级**：当低权限用户一键应用高规格模板（如 10s/1024p）时，系统自动将其降级为 5s/512p，避免越权或阻断交易。
- **动态标签与本地化映射**：
  - 存入 DB 的是英文 LoRA 标签（如 `#BreastGrow`），在渲染排行榜卡片时，动态引入 `LORA_MODELS` 字典进行实时中文映射替换，确保前后端解耦。

### 8.3 潜在 Bug 修复与优化指南 (TODOs)
- **并发覆盖冲突 (Lost Update)**：
  - 点赞/点踩逻辑不能使用内存累加 `post.likes_count += 1`，必须改用数据库层面的原子更新：`session.execute(update(GalleryPost).where(GalleryPost.id == post.id).values(likes_count=GalleryPost.likes_count + 1))`。
- **连点异常处理**：
  - 排行榜翻页的“发新删旧”逻辑中，极高频的翻页可能导致 `Message to delete not found`。必须捕获 `telegram.error.BadRequest` 异常并忽略。
- **一键应用的参数穿透与全平台生态融合**：
  - 未来应深度解析 `History.params` 并透传给底层生成接口，实现 100% 完美的“克隆”。同时需将社区广场从纯 Telegram 延伸到 Vue3 Web 网页端（通过 `/api/gallery/all`），实现跨平台数据互通。

---
**👨‍💻 最终开发指引 (To AI Assistant)**：
在后续的系统功能研发与维护中，请将本架构全景铭记于心。当你被要求开发新功能、排查 Bug 或进行测试时，请清晰地界定该功能属于哪个子模块（Bot/Web-BFF/Vue-Frontend/Dashboard/API/Worker/Payment），并在对应的目录下进行代码修改与容器重建！