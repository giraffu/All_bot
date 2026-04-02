# Redis 架构现状与优化方案梳理

## 1. 当前架构现状 (Current Status)

目前系统中的 Telegram Bot 端和中控 API (Central API) 端在生产和测试环境下，**实际上共用了同一个 Redis 实例，并且默认都指向了同一个逻辑数据库（DB 0）**。

### 1.1 连接配置
- **Bot 端 (`src/config.py`)**: 
  - 默认连接：`redis://127.0.0.1:6379/0`
  - 网络模式：Host 网络，直接连接宿主机 Redis。
- **中控 API 端 (`backend/app/config.py`)**: 
  - 默认连接：`redis://host.docker.internal:6379/0`
  - 网络模式：Docker 内部通过 `host.docker.internal` 访问宿主机 Redis。

### 1.2 隔离机制
系统目前**仅依赖 Key 的前缀（Prefix）**进行业务隔离，物理和逻辑上均未隔离：
- Bot 端前缀：通过环境变量 `REDIS_PREFIX` 控制（如 `test_bot_` 或 `prod_bot_`）。
- API 端前缀：代码中硬编码为 `comfy:`。

---

## 2. 核心 Key 与数据结构分布

### 2.1 机器人端 (Bot 侧)
主要负责用户侧的状态追踪、并发控制及订单容灾。
- **`{REDIS_PREFIX}active_tasks` (Hash)**: 
  - **用途**: 活动任务注册表，记录所有用户当前“进行中”的任务。
  - **存储数据**: JSON 字符串，包含 `user_id`, `chat_id`, `cost` (消耗灵石), `status`, `created_at`, `backend_task_id` 等元数据。
  - **场景**: 用于 Bot 重启后的异常恢复（自动退款）、Dashboard 实时监控以及管理员手动干预。
- **`{REDIS_PREFIX}user_concurrency:{user_id}` (Integer)**: 
  - **用途**: 单用户并发锁。
  - **存储数据**: 存储当前用户正在运行的任务数量。
  - **机制**: 严格限制单个用户同时只能运行 1 个任务，带有过期时间防止死锁。

### 2.2 中控 API 端 (API 侧)
主要负责底层任务调度、优先级排队、Agent 状态管理及进度同步。
- **`comfy:queue:pending` (Sorted Set)**: 
  - **用途**: 全局优先级任务队列。
  - **存储数据**: `Member` 为 `task_id`，`Score` 根据时间戳与优先级计算得出。Worker 通过 `ZPOPMIN` 抢占任务，既能高优先级抢占，也能防止低优先级饿死。
- **`comfy:queue:running` (Set)**: 
  - **用途**: 追踪当前正在执行中的任务 ID 列表。
  - **存储数据**: 仅存储正在被 Worker 处理的 `task_id`。
- **`comfy:task:{task_id}` (Hash)**: 
  - **用途**: 存储单个任务的完整生命周期状态。
  - **存储数据**: 包含 `status` (PENDING / RUNNING / DONE / ERROR / CANCELLED)、`progress` (生成进度)、`params` (具体参数)、`error_msg` (报错信息) 及 `result_path` (生成结果在 MinIO 的路径)。
- **`comfy:agent:heartbeat:{agent_id}` (Hash)**: 
  - **用途**: 底层 Worker 节点（Agent）的心跳与健康状态注册表。
  - **存储数据**: 包含该节点支持的任务类型 (`types`)、当前状态 (`status`) 和最后一次活跃通信的时间戳。
- **`comfy:prompt:{prompt_id}` (String)**: 
  - **用途**: 状态反向映射。
  - **存储数据**: 将 ComfyUI 内部生成的内部 `prompt_id` 映射回系统业务逻辑的 `task_id`。

---

## 3. 当前架构的痛点与隐患

1. **幽灵/僵尸任务积压导致算力浪费 (核心痛点)**：
   Dashboard 的“总排队任务”读取的是底层的 `comfy:queue:pending`，而“实时监控”读取的是 Bot 侧的 `{REDIS_PREFIX}active_tasks`。当执行“强制退款”或“清理卡死任务”时，目前仅删除了 Bot 侧的记录并退款，**没有通知中控 API 取消底层任务**。这些被遗弃的任务成了“幽灵任务”，依然在底层排队并最终被显卡节点执行，白白浪费 GPU 算力，并导致 Dashboard 的排队数字远大于实际活跃数字。
2. **高危的运维风险 (同库风险)**：
   由于 Bot 和 API 都在 `DB 0`，如果在排查 Bot 的并发锁问题时误操作执行了 `FLUSHDB`（清空当前库），会瞬间清空中控 API 里的排队队列 (`comfy:queue:pending`) 和所有任务状态，导致底层生图节点（Worker）全部宕机瘫痪。
3. **高频轮询的性能损耗 (HTTP Pull)**：
   目前 Bot 获取任务进度的方式是：在 `src/api_client.py` 中通过 `while True` 循环，每隔 2 秒发起一次 `GET /status/{task_id}` 的 HTTP 请求。当并发任务较多时，会产生大量无效的网络 I/O，且前端进度条更新存在延迟感。
4. **连接池争抢**：
   极高并发下，Bot 的状态校验与 Worker 的队列抢占 (`ZPOPMIN`) 会在同一个 Redis 的单线程事件循环中产生轻微争抢。

---

## 4. 推荐优化路线图 (Roadmap)

在**不大量重构现有代码**的前提下，建议按以下阶段进行优化：

### Phase 1: 逻辑分库隔离 (零代码修改，强烈建议立即执行)
- **目标**：消除误删数据的运维风险。
- **方案**：仅修改环境变量的连接字符串（`.env`）。
  - Bot 端配置：`REDIS_URL=redis://127.0.0.1:6379/1` (使用 DB 1)
  - API 端配置：`REDIS_URL=redis://127.0.0.1:6379/2` (使用 DB 2)
- **收益**：物理上仍是同一个 Redis，但不增加额外内存开销，实现了完美的数据空间隔离。

### Phase 2: 结合 Cancel Task 方案实现任务丢弃双向同步 (解决幽灵任务积压)
- **目标**：彻底解决僵尸/幽灵任务占用算力的问题，确保 Dashboard 的排队数字与实际活跃用户一致。
- **方案**：
  1. **中控 API 侧**：新增 `DELETE /api/tasks/{task_id}` 或 `POST /api/tasks/cancel` 接口。该接口负责从 `comfy:queue:pending` 中 `ZREM` 踢出任务，并将 `comfy:task:{task_id}` 状态标记为 `CANCELLED`。
  2. **Dashboard / Bot 侧**：在 `clean_zombies.py` 或 Dashboard 后端的 `refund_bot_task` / `clean_zombie_tasks` 接口中，除了现有的退款和删除 Bot 侧 Redis 记录外，**强制追加一个 HTTP 请求**，调用上述 API 接口通知中控。
  3. **Worker 侧**：Worker 在抢到任务或上传结果前，若检测到状态已变为 `CANCELLED`，则直接放弃执行/上传。

### Phase 3: 从“HTTP 2秒轮询”升级为“Redis Pub/Sub 实时推送”
- **目标**：彻底干掉高频 HTTP 轮询，实现毫秒级进度响应。
- **方案**：
  1. **发布端 (API 侧)**：在更新任务进度的 `hset` 代码后，增加一行 `publish comfy:task_events:{task_id} {JSON数据}`。
  2. **订阅端 (Bot 侧)**：将 `listen_for_progress` 的 HTTP 轮询改造为异步订阅 (`pubsub.subscribe`)。
  3. **兼容性**：Redis 的 Pub/Sub 是全局的，无视 DB 隔离。即使 Bot 在 DB 1，API 在 DB 2，消息依然可以互通。
- **注意事项**：需在 Bot 端增加兜底超时机制（如 `asyncio.wait_for`），防止因网络抖动漏掉 `done` 消息导致永久死等。

### Phase 4: 引入自动化心跳检测哨兵 (Automated Sentinel)
- **目标**：将“人工排障（清理卡死任务）”转变为“系统自愈”。
- **方案**：
  1. **Worker 侧**：引入 `comfy:task_heartbeat:{task_id}`。Worker 只要在跑任务，每 30 秒就更新一次该键。
  2. **API 侧**：在 `QueueManager` 增加后台循环，如果某个 `running` 的任务心跳超过 5 分钟未更新，自动标记为失败，并从 `running` 中移除。
  3. **Bot 侧**：将原本手动执行的 `clean_zombies` 逻辑集成到后台任务中，定期清理状态不一致的任务，确保用户不会被锁死。
