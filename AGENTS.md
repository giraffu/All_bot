# AI 编程助手参考指南 (AGENTS.md)

本文档是 AI 编程助手参与“修仙主题 Telegram 图像与视频机器人”项目时的全面开发指南。它基于系统最新的重构与功能迭代（包括三大支付体系的并入）进行了全面更新，涵盖了整个分布式架构、逻辑、数据流以及容灾机制。

## 1. 系统全景与模块架构 (System Panorama)

当前系统已经演进为一个多模块、多节点的分布式架构。主要由以下几个核心子系统构成：

### 1.1 核心 Bot 服务 (Telegram Bot)
这是系统的入口和核心业务逻辑层。
- **职责**：处理 Telegram 用户消息交互、状态机管理、修仙境界与权限判定、任务的下发排队，以及提供多种支付方式的 UI 菜单入口。
- **代码位置**：`/src` (主要入口 `src/bot_test.py` 与 `src/bot_prod.py`，回调入口在 `src/handlers/callback_handler.py`)
- **容器编排**：`deploy/docker-compose.yml` (正式服 `tg-bot`) 和 `deploy/docker-compose-test.yml` (测试服 `tg-bot-test`)。

### 1.2 支付回调服务 (Payment API)
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
- **Dashboard 后台服务**:
  ```bash
  cd dashboard && docker-compose up -d --build
  ```
- **中控 API 后端服务**:
  ```bash
  cd backend && docker-compose up -d --build
  ```

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

---
**👨‍💻 最终开发指引 (To AI Assistant)**：
在后续的系统功能研发与维护中，请将本架构全景铭记于心。当你被要求开发新功能、排查 Bug 或进行测试时，请清晰地界定该功能属于哪个子模块（Bot/Dashboard/API/Worker/Payment），并在对应的目录下进行代码修改与容器重建！