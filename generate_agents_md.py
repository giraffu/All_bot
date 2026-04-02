content = """# AI 编程助手参考指南 (AGENTS.md)

本文档是 AI 编程助手参与“修仙主题 Telegram 图像与视频机器人”项目时的全面开发指南。它基于系统最新的重构与功能迭代进行了全面更新，涵盖了整个分布式架构、逻辑、数据流以及容灾机制。

## 1. 系统全景与模块架构 (System Panorama)

当前系统已经演进为一个多模块、多节点的分布式架构。主要由以下几个核心子系统构成：

### 1.1 核心 Bot 服务 (Telegram Bot)
这是系统的入口和核心业务逻辑层。
- **职责**：处理 Telegram 用户消息交互、状态机管理、修仙境界与权限判定、订单支付生成以及任务的下发排队。
- **代码位置**：`/src` (主要入口 `src/bot_test.py`)
- **容器编排**：`deploy/docker-compose.yml` (正式服 `tg-bot`) 和 `deploy/docker-compose-test.yml` (测试服 `tg-bot-test`)。

### 1.2 后台管理系统 (Dashboard)
用于管理员监控系统状态、管理用户和处理异常任务。
- **Dashboard 后端**：FastAPI 架构，代理前端对后端的请求，监控 Redis 中的活动任务，提供人工干预接口（如强制退款终止）。
  - **代码位置**：`/dashboard/backend`
- **Dashboard 前端**：Vue 3 架构，可视化监控面板。
  - **代码位置**：`/dashboard/frontend`
- **容器编排**：`/dashboard/docker-compose.yml` (服务：`dashboard-frontend`, `dashboard-backend`)，默认使用 `host` 网络模式。

### 1.3 支付前端 (TON Frontend)
用于处理 TON 区块链支付的 Web App 前端界面（Bot 内嵌）。
- **职责**：生成并拉起 TON 钱包支付请求（通过 `tonconnect-ui`）。
- **代码位置**：`/frontend` (通常编译后提供静态资源或由 nginx 托管)。

### 1.4 中控 API 后端 (Central API Backend)
作为 Bot 与底层生图节点 (Workers) 之间的中间调度层。
- **职责**：接收 Bot 发来的任务，解析工作流 (Workflows)，与对象存储交互，并调度后端的 ComfyUI Agents。
- **代码位置**：`/backend` (主要入口 `/backend/app/main.py`)
- **容器编排**：`/backend/docker-compose.yml` (服务：`api`，端口 8003)。

### 1.5 图像/视频生成节点 (Workers / Comfy Agents)
实际执行生图和视频任务的计算节点。
- **职责**：运行具体的 ComfyUI 实例，执行 JSON 工作流并返回结果。
- **代码位置**：`/workers/comfy_agent1`, `/workers/comfy_agent2` 等（通过多开隔离）。
- **协同**：API 后端通过配置或 Redis 队列向这些 Agent 派发具体任务。

---

## 2. 核心基础设施服务 (Infrastructure Services)

系统高度依赖以下三大基础设施，在开发和本地联调时需确保它们可用：

1. **Redis 服务**：
   - **用途**：高速缓存、任务排队调度 (`ActiveTasksTable`)、分布式锁（单用户并发控制 `MAX_CONCURRENT_TASKS`）以及 Bot 和 Dashboard 之间的状态同步。
2. **PostgreSQL 服务**：
   - **用途**：系统的唯一持久化信源。存储用户数据 (`users`)、订单 (`orders`) 和严格的资产流水 (`user_logs`)。
   - **访问**：使用 SQLAlchemy Async 进行异步交互。
3. **MinIO 服务**：
   - **用途**：对象存储，兼容 S3 协议。用于存储用户上传的图片/视频、系统生成的中间产物以及模板。
   - **结构**：主要包含 `bot-data` (系统主数据), `comfyui-input` (传给 Worker 的输入), `comfyui-temp` (Worker 的输出), `bot-template` (模板) 等 Bucket。

---

## 3. 运维指南与容器管理 (Operations & Maintenance)

### 3.1 容器的启动与重建 (Build & Start)
当修改了代码后，必须通过 Docker Compose 重新构建并启动容器。
- **主 Bot 服务 (正式服)**:
  ```bash
  docker-compose -f deploy/docker-compose.yml up -d --build bot
  ```
- **主 Bot 服务 (测试服)**:
  ```bash
  docker-compose -f deploy/docker-compose-test.yml up -d --build bot-test
  ```
- **Dashboard 后台服务**:
  ```bash
  cd dashboard && docker-compose up -d --build
  ```
- **中控 API 后端服务**:
  ```bash
  cd backend && docker-compose up -d --build
  ```

*⚠️ 重建报错处理 (ContainerConfig KeyError)：当使用旧版 docker-compose 时，如果遇到此报错，请先手动停止并删除旧容器（`docker stop <容器名> && docker rm <容器名>`），再执行重建命令。*

### 3.2 Bot 暂停与维护模式 (Maintenance Mode)
当系统需要紧急维护、修复 Bug 或排查问题时，可以开启维护模式。这会无缝拦截新生成任务的创建，但不影响用户的查询与签到功能。
- **后台强制开启维护模式**：
  ```bash
  # 正式服
  docker exec tg-bot touch /app/MAINTENANCE
  # 测试服
  docker exec tg-bot-test touch /app/MAINTENANCE
  ```
- **关闭维护模式，恢复服务**：
  ```bash
  docker exec tg-bot rm -f /app/MAINTENANCE
  ```

### 3.3 日常排障脚本 (Troubleshooting Scripts)
宿主机根目录提供了一系列排障脚本：
- **清理僵尸任务**：`docker exec tg-bot python clean_zombies.py` (自动清理驻留过长占用并发锁的任务)。
- **查看 Redis 排队**：`docker exec tg-bot python check_redis.py`。
- **核查官方 Stars 漏单**：`python check_stars.py`。

---

## 4. 核心业务逻辑红线 (Business Logic Redlines)

1. **单轨制代币 (`credits`)**：
   曾经的 `temp_credits` 已被完全废弃，系统目前只有 `credits`（灵石）。所有代码中严禁再使用或恢复 `temp_credits`。
2. **强制数据流审计**：
   任何涉及灵石增减的代码修改，**必须**同步在 `user_logs` 表中插入流水记录。底层通过 `contextvars` 自动追踪 SQL 触发者的 User ID。如果遗漏，会导致严重的对账错误。
3. **并发锁与状态一致性**：
   在修改 `src/services/task_service.py` 任务调度逻辑时，请务必保证 `ActiveTasksTable` 的状态更新与 PostgreSQL 的扣费/退费逻辑在业务上保持最终一致。
4. **计算与存储分离**：
   不要在 Bot 或 API 容器内部保存任何状态文件。所有状态必须写入 PostgreSQL、Redis 或 MinIO，以便于未来随时横向扩容 Worker 或网关节点。

---
**👨‍💻 最终开发指引 (To AI Assistant)**：
在后续的系统功能研发与维护中，请将本架构全景铭记于心。当你被要求开发新功能、排查 Bug 或进行测试时，请清晰地界定该功能属于哪个子模块（Bot/Dashboard/API/Worker），并在对应的目录下进行代码修改与容器重建！
"""

with open('AGENTS.md', 'w', encoding='utf-8') as f:
    f.write(content)

print("AGENTS.md updated successfully.")
