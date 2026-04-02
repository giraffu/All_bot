# 修仙主题 Telegram 图像与视频机器人 - 项目说明书

## 1. 项目概述与目标 (Project Overview)
本项目是一个提供 AI 图像和视频生成服务（如：换脸、文生图、视频模板等）的高级 Telegram 机器人。项目结合了独特的“修仙”主题进度系统与单轨制代币经济模型，集成了去中心化的 TON 区块链支付与 Telegram Stars 原生支付双通道。系统底层通过 Redis 高速缓存进行强大的任务排队与并发调度，并配备完善的 Dashboard 监控后台与容灾机制，旨在提供高并发、高可用、高趣味性的 AI 创作体验。

## 2. 系统架构设计说明 (Architecture Design)
系统采用混合微服务架构，主要包含以下核心子系统：
- **网关与入口层**：通过 `bot_test.py` 提供统一的双环境入口，维护超大并发的底层连接池。
- **业务交互层 (Handlers)**：处理各类 Telegram 消息、多媒体接收、命令路由以及 UI 渲染，内置违禁词拦截机制。
- **权限与经济模型层**：基于用户“修为”与“VIP身份”动态计算排队优先级和访问权限（画质/时长）。
- **任务编排层**：全面采用 Redis 追踪 Active Tasks 元数据，实现分布式单用户并发锁控制。
- **后端通信层**：`api_client.py` 封装 HTTP 异步请求，内置熔断器 (Circuit Breaker)、重试和 Trace ID 追踪。
- **支付网关**：双通道守护协程，TON 链上数据轮询校验与 Telegram Stars 官方回调拦截，具备防双花与残值折算能力。
- **持久化层**：唯一信源 PostgreSQL 管理资产流水与用户状态，MinIO 处理多媒体文件存储。

## 3. 主要功能模块详细介绍 (Core Modules)
- **`src/bot_test.py`**: 系统核心启动点与网络网关，管理 PROD/TEST 环境切换和连接池。
- **`src/handlers/`**: 包含各类交互逻辑，如 `payment_handler.py`（处理支付界面）、生成任务参数收集等。
- **`src/services/permission_service.py` & `src/quota.py`**: 核心权限校验逻辑，控制高画质（最高 1024p）和长时长（最高 10s）视频的生成权限。计算动态优先级（修为优先级 + 身份优先级）。
- **`src/services/task_service.py`**: 任务编排引擎，控制 `MAX_CONCURRENT_TASKS` 并发限制。
- **`src/services/payment_validator.py`**: 独立守护协程，每 15 秒轮询 TON RPC 节点，确认链上交易。
- **`src/database/`**: 包含 SQLAlchemy 异步模型，管理数据库表映射与会话。
- **`backend/`**: FastAPI 后端与 Vue 3 前端分离的 Dashboard，提供实时任务监控、API 代理及管理干预功能。

## 4. 技术栈与依赖环境说明 (Tech Stack)
- **编程语言**: Python 3.10+
- **Bot 框架**: python-telegram-bot / pyTelegramBotAPI
- **Web 框架**: FastAPI (用于 Dashboard 后端)
- **前端框架**: Vue 3 (用于 Dashboard 前端)
- **数据库**: PostgreSQL (数据持久化), Redis (缓存与任务队列、分布式锁)
- **ORM / 数据库交互**: SQLAlchemy Async
- **存储**: MinIO (对象存储，S3 兼容)
- **容器化部署**: Docker, Docker Compose

## 5. 安装部署步骤指南 (Installation & Deployment)
本项目依赖 Docker Compose 进行服务编排：
1. **克隆代码库**:
   ```bash
   git clone <repository_url>
   cd All_bot
   ```
2. **环境配置**:
   复制 `.env.example` 为 `.env` 并填写相关数据库、Redis、Bot Token 密钥。
3. **构建与启动 (正式服)**:
   ```bash
   docker-compose -f deploy/docker-compose.yml up -d --build bot
   ```
4. **构建与启动 (测试服)**:
   ```bash
   docker-compose -f deploy/docker-compose-test.yml up -d --build bot-test
   ```
*注意：每次修改 `src/` 下的核心逻辑后，必须使用 `--build` 参数强制重建镜像。*

## 6. 配置参数说明 (Configuration)
核心环境变量配置（位于 `.env`）：
- `BOT_TOKEN`: Telegram Bot 访问令牌。
- `DATABASE_URL`: PostgreSQL 异步连接字符串 (如 `postgresql+asyncpg://user:pass@host/db`)。
- `REDIS_URL`: Redis 连接 URL。
- `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`: 多媒体存储凭证。
- `TON_WALLET_ADDRESS`: 收款的 TON 钱包地址。

## 7. 数据库设计文档 (Database Design)
- **`users` 表**: 存储用户基本信息、永久灵石 (`credits`)、当前修为境界、VIP 身份等级及邀请关系。*(注：`temp_credits` 已废弃)*
- **`user_logs` 表**: **强审计核心**，记录所有灵石增减流水。底层通过 `contextvars` 自动追踪 User ID。
- **`orders` 表**: 记录支付订单（TON 或 Stars），包含订单状态、防双花校验哈希。
- **Redis `ActiveTasksTable`**: 存储当前排队中及执行中的活动任务元数据（生命周期状态、并发锁）。

## 8. 运行与测试方法 (Running & Testing)
- **单元与集成测试**: 建议在 conda 虚拟环境中运行。具体参考 `docs/TESTING_GUIDE.md`。
- **后台控制模式**: 可在宿主机通过命令管理 Bot 的维护模式：
  - 开启维护：`docker exec tg-bot touch /app/MAINTENANCE`
  - 关闭维护：`docker exec tg-bot rm -f /app/MAINTENANCE`

## 9. 常见问题解决方案 (FAQ & Troubleshooting)
1. **Redis 僵尸任务占用并发锁**:
   - **症状**: 用户提示任务达到上限，但实际未在执行。
   - **方案**: 在 Dashboard 一键终止，或在宿主机执行 `docker exec tg-bot python clean_zombies.py` 自动清理驻留时间 > 7200秒的任务。
2. **容器重建报错 (KeyError: 'ContainerConfig')**:
   - **方案**: 这是旧版 docker-compose 的 Bug，请手动 `docker stop <容器名> && docker rm <容器名>`，然后再执行启动命令。
3. **Telegram Stars 漏单核查**:
   - **方案**: 在宿主机根目录执行 `python check_stars.py` 拉取最近的官方流水进行对账。

## 10. 版本更新记录 (Changelog)
- **2026-03-28 (架构演进与代码审查)**:
  - 后端项目 `backend` 取消独立 Git 仓库状态，整合为普通目录直接受主仓库版本控制。
  - 全面废除 `temp_credits`（临时灵石）系统，统一使用单轨制 `credits`。
  - 规划计算存储分离，Bot/API/Redis/DB 集中计算节点，MinIO 挂载 NAS。
- **早期迭代**:
  - 引入了熔断器与 API 连接池。
  - 新增 Telegram 原生 Stars 支付支持。

## 11. 项目目录结构说明 (Directory Structure)
```text
├── AGENTS.md
├── Dockerfile
├── backend
│   ├── ARCHITECTURE_UPDATE_SUMMARY.md
│   ├── BACKEND_TECHNICAL_REPORT.md
│   ├── Dockerfile
│   ├── HOW_TO_ADD_WORKFLOW.md
│   ├── REFACTORING_PLAN.md
│   ├── app
│   ├── backend.log
│   ├── cleanup.log
│   ├── docker-compose.yml
│   ├── perform_api_test.py
│   ├── requirements.txt
│   └── workflows
├── calculate_total_stars.py
├── check_redis.py
├── check_redis2.py
├── check_stars.py
├── clean_zombies.py
├── clean_zombies2.py
├── code_analyzer.py
├── code_analyzer_radon.py
├── config.py
├── dashboard
│   ├── backend
│   ├── check_plans_debug.py
│   ├── docker-compose.yml
│   ├── frontend
│   └── test_db.py
├── deploy
│   ├── charts
│   ├── docker-compose-test.yml
│   └── docker-compose.yml
├── docs
│   ├── BOT_ARCHITECTURE.md
│   ├── DEPLOYMENT_AND_OPERATIONS.md
│   ├── TESTING_GUIDE.md
│   ├── bot_services_and_logic.md
│   ├── cultivation_identity_system.md
│   ├── dashboard_frontend_backend.md
│   ├── database_and_data_flow.md
│   └── ton_payment_system.md
├── find_commented_code.py
├── find_dead_locks.py
├── force_cleanup.py
├── frontend
│   ├── README.md
│   ├── README_ZH.md
│   ├── dist
│   ├── eslint.config.js
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── public
│   ├── src
│   ├── test_parse_boc_2.py
│   ├── tsconfig.app.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── vite.config.ts
├── generate_tree.py
├── logs
│   ├── bot.log
│   ├── bot.log.1
│   ├── bot.log.2
│   ├── bot.log.3
│   ├── bot.log.4
│   └── bot.log.5
├── migrate_history.py
├── print_exception.patch
├── project_analysis.json
├── project_tree.txt
├── prompts.ini
├── requirements.txt
├── smart_cleanup.py
├── smart_cleanup2.py
├── src
│   ├── __init__.py
│   ├── api_client.py
│   ├── bot_test.py
│   ├── circuit_breaker.py
│   ├── constants.py
│   ├── context.py
│   ├── database
│   ├── handlers
│   ├── logger.py
│   ├── quota.py
│   ├── services
│   └── utils.py
├── templates
│   ├── quick_face
│   ├── temps
│   └── video_nice
├── test_db.py
├── test_db2.py
├── test_users_query.py
└── workers
    ├── comfy_agent1
    ├── comfy_agent2
    └── comfy_agent3

```
