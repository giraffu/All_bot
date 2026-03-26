# AI 编程助手参考指南 (AGENTS.md)

本文档是 AI 编程助手参与“修仙主题 Telegram 图像与视频机器人”项目时的全面开发指南。它基于系统最新的重构与功能迭代进行了全面更新，涵盖了架构、逻辑、数据流以及容灾机制。

## 1. 项目概述
这是一个提供 AI 图像和视频生成服务（如：换脸、文生图、视频模板等）的 Telegram 机器人。它具有独特的“修仙”主题进度系统、双轨制代币经济模型，并集成了去中心化的 TON 区块链支付、Redis 高速缓存、强大的任务排队调度以及完善的后台监控与违禁词过滤机制。

## 2. 系统混合架构 (7 大核心模块)
* **入口与网络网关 (`src/bot_test.py`)**：处理 PROD/TEST 双环境切换、动态代理探活、超大并发连接池 (`connection_pool_size=250`)，以及后台定时任务调度（例如 48 小时定时清理临时灵石）。
* **交互与处理器 (`src/handlers/`)**：管理用户状态机，渲染 UI，拦截违禁词，并支持接收多格式媒体（Photo, Video, Document）用于高级场景（如模板共建）。
* **权限与经济 (`src/services/permission_service.py`, `src/quota.py`)**：管理永久与临时双代币系统，并基于用户的修为和身份执行阶梯式的视频画质/时长权限控制。
* **任务编排与 Redis (`src/services/task_service.py`, `task_registry.py`)**：工作流编排，**全面使用 Redis** 进行活动任务元数据的追踪以及单用户并发锁控制。
* **底层通信 (`src/api_client.py`)**：封装与 AI 后端的 HTTP 异步请求，采用持久连接池，内置弹性**熔断器 (Circuit Breaker)**和异步重试机制。
* **TON 支付守护 (`src/services/payment_validator.py`)**：独立守护协程，每 15 秒轮询 TON RPC 节点，校验链上 BOC 备注防双花，并**自动处理跨套餐升级的残值折算**。
* **持久化存储 (`src/database/`, `src/services/storage.py`)**：**严格唯一使用 PostgreSQL** 管理资产流水，放弃 SQLite。使用 MinIO 存储多媒体，并生成预签名 URL 供外部访问。

## 3. 修仙与 VIP 身份系统
双轨制特权系统控制高画质（最高 1024p）和长时长（最高 10s）的访问，并决定排队优先级。
* **修为系统（免费驱动）**：凡人 -> 练气期 -> 筑基期 -> 金丹期。通过签到、邀请加群和生成次数自动升级。
* **VIP 身份（付费驱动）**：外门 -> 内门 -> 核心 -> 真传弟子。
* **动态优先级衰减机制**：`最终优先级 = 修为优先级 + 身份优先级`。
  * **新手指引**：历史总生成 < 2 次时，无条件获得 +30 极速优先级。
  * **防霸占衰减**：无论境界多高，优先级都会随当日生成次数阶梯式衰减（例如真传弟子 <40次为 +45，>=100次后降为 0）。

## 4. 经济与审计模型
* **双轨制代币**：
  * `credits`（永久灵石）：充值或邀请获得（基础5 + 进群10 = 15灵石）。永不过期。
  * `temp_credits`（临时灵石）：每日签到获得（根据身份 15~60 不等）。消费时**优先扣除**。后台每 48 小时自动清零。
* **强制数据流审计**：
  * **开发者红线**：任何涉及灵石增减的代码修改，**必须**同步在 `user_logs` 表中插入流水记录，否则会引发严重对账错误！底层通过 `contextvars` 自动追踪 SQL 触发者的 User ID。

## 5. Dashboard 监控后台
* **前后端分离**：FastAPI 后端 + Vue 3 前端，与 Bot 共享 DB 与 MinIO。
* **核心新特性**：
  * **双队列监控**：不仅展示底层 ComfyUI 的实时队列，还新增了基于 Redis 轮询的 `ActiveTasksTable`，展示 Bot 层面的活动任务。
  * **人工干预**：提供了强制拦截接口 (`/api/system/refund_bot_task`)，管理员可一键终止卡死或违规的任务，释放锁并全额退款。

## 6. 服务重启与容灾机制 (Deployment & Disaster Recovery)
本项目依赖 Docker Compose 进行编排（正式服 `tg-bot`，测试服 `tg-bot-test`，后台 `dashboard`）。
* **代码修改后必须重建容器**：如果修改了 `src/` 下的核心逻辑，仅仅重启容器是不够的，必须加上 `--build` 参数强制重建镜像，否则代码修改不会生效。
  * **正式服**: `docker-compose -f deploy/docker-compose.yml up -d --build bot`
  * **测试服**: `docker-compose -f deploy/docker-compose-test.yml up -d --build bot-test`
  * **⚠️ 重建报错处理 (ContainerConfig KeyError)**：当使用旧版 `docker-compose` (如 v1.29.2) 且遇到 `KeyError: 'ContainerConfig'` 报错时，请先手动停止并删除冲突的旧容器（可通过 `docker ps -a` 查找容器 ID/名称，然后执行 `docker stop <容器名> && docker rm <容器名>`），之后再执行上述重建命令。
* **平滑停机与退款**：Bot 接收到正常的停机信号时（`post_shutdown`），会自动从 Redis 中读取排队任务并全额退款。
* **意外断电补偿**：即使遭遇 `docker kill` 或强制断电，Bot 在下次启动初始化（`post_init`）时，会调用 `recovery_service.py` 扫描并恢复/清理滞留任务。
* **维护模式**：管理员可通过发送 `/maintenance` 指令无缝拦截新生成任务的创建，不影响用户的查询与签到。
  * **后台强制模式**：当 Bot 卡死或无法响应指令时，可直接在宿主机通过命令在容器后台控制：
    * **开启**：`docker exec tg-bot touch /app/MAINTENANCE`
    * **关闭**：`docker exec tg-bot rm -f /app/MAINTENANCE`
    * *(注：测试服请将 `tg-bot` 替换为 `tg-bot-test`)*

## 7. 日常运维与排障 (Daily Ops & Troubleshooting)
* **Redis 僵尸任务清理**：
  在系统长期运行中，偶尔可能出现任务因后端异常或网络问题挂起，导致驻留时间过长（僵尸任务）。这会占用用户的并发锁（最多3个）。
  * **监控与识别**：可通过 Dashboard 实时查看排队情况，或在宿主机执行 `docker exec tg-bot python check_redis.py` 查看活动任务的执行时间 (`Age`) 及并发锁状态。
  * **单点干预 (Dashboard)**：在 Dashboard 发现卡死任务时，可通过人工干预按钮（调用 `/api/system/refund_bot_task`）一键强制终止、释放并发锁并全额退款。
  * **脚本批量清理 (CLI)**：当出现大面积卡死或需要快速清理时，可执行 `docker exec tg-bot python clean_zombies.py`。该脚本会自动清理驻留时间过长（默认 > 7200秒/2小时）的任务。如需调整判定阈值，可直接修改根目录下的 `clean_zombies.py`。

---
**👨‍💻 最终开发指引 (To AI Assistant)**：
当你被要求开发新功能、排查 Bug 或进行测试时，请遵循本文件及 `docs/` 目录下的具体文档（如 `TESTING_GUIDE.md` 建议使用 conda 环境进行测试）。在修改状态逻辑时，请时刻注意 PostgreSQL 事务的完整性与 Redis 缓存的同步！