# Redis 在系统中的架构与使用逻辑报告

本文档详细梳理了项目中 Redis 在 **Bot 交互系统** 与 **中控调度 API** 两个核心模块中的使用逻辑与定位。

---

## 一、 中控 API (Backend) 的 Redis 使用逻辑

在中控 API（主要涉及 `backend/app/main.py` 以及 `queue_manager.py`）中，Redis 被深度应用于**任务队列调度**、**状态同步**、**优先级控制**以及**分布式节点的健康监测**。

### 1. 任务队列与优先级调度 (ZSET)
这是系统中 Redis 最核心的应用之一，完美解决了“带优先级的排队防饿死”问题：
* **等待队列 (`comfy:queue:pending`)**：使用**有序集合 (Sorted Set)** 来管理排队中的任务。
* **防饿死算法**：在计算任务入队 Score 时，使用了公式 `time.time() - (priority * 60)`。这意味着优先级（`priority`）每提高 1 级，相当于该任务提前了 60 秒排队。既保证了高优先级任务能插队，又确保了低优先级任务在等待足够长的时间后，其 Score 能超越新来的高优先级任务，防止被无限期“饿死”。
* **执行中队列 (`comfy:queue:running`)**：使用**无序集合 (Set)** 记录已经被 Worker 领走、正在执行的任务 ID，防止任务丢失。

### 2. 任务元数据与状态流转 (HASH)
* **任务详情存储**：每个任务的详细参数（如提示词、图片路径等）使用 **哈希表 (Hash)** 结构存储在 `comfy:task:<task_id>` 中。
* **字段结构**：包含 `type` (任务类型)、`status` (状态：pending/running/done/error)、`params` (JSON格式的参数)、`progress` (进度) 以及 `result_path` (结果路径) 等。
* **生命周期管理**：任务创建后会被设置 `86400` 秒（24小时）的过期时间 (TTL)，避免 Redis 内存因历史数据无限膨胀。

### 3. Agent Worker 心跳与健康监测 (TTL & SCAN)
中控 API 需要实时感知当前是否有存活的下游生成节点（Agent Worker）：
* **心跳机制**：每个 Worker 会定时向 Redis 写入心跳信息到 `comfy:agent:heartbeat:<agent_id>`，TTL 设置为 30 秒。
* **自动剔除离线节点**：如果节点宕机或断网，超过 30 秒未上报，该键会自动消失。
* **存活统计**：通过非阻塞的 `SCAN` 命令扫描心跳键的前缀，动态计算出 `active_workers`，从而准确判断生成服务是否在线 (`comfy_online = active_workers > 0`)。

### 4. 任务映射与回调辅助 (STRING)
* **Prompt ID 映射**：任务提交给底层的 ComfyUI 时，ComfyUI 会返回内部的 `prompt_id`。Redis 使用普通的 String 类型在 `comfy:prompt:<prompt_id>` 键中存储对应的中控 `task_id`，过期时间为 1 小时。
* **回调寻址**：系统在接收到 ComfyUI 异步的进度或完成回调时，能迅速通过 `prompt_id` 反查出对应的 `task_id`，进而更新进度或完成状态。

---

## 二、 Bot 系统 (Telegram 端) 的 Redis 使用逻辑

在 Telegram Bot 系统的入口 `bot_test.py` 及其底层的交互逻辑中，Redis 的核心定位是**“单用户并发控制（防刷）”**以及**“状态持久化与宕机恢复（容灾）”**。

### 1. 单用户并发锁机制 (Concurrency Control)
为了防止单个用户疯狂点击发送任务，占用系统资源或导致并发计费错误，Bot 引入了基于 Redis 的并发锁。
* **实现机制**：位于 `src/services/redis_client.py`。
* **原子操作**：处理任何生成任务前，使用 Redis 的 `Pipeline(transaction=True)` 机制执行原子自增：
  ```python
  async with self.redis.pipeline(transaction=True) as pipe:
      pipe.incr(key)
      pipe.expire(key, 3600) # 兜底过期时间，防止死锁
  ```
* **并发拦截**：如果自增后的值超过系统设定的 `MAX_CONCURRENT_TASKS`（通常为3），Bot 会直接拦截请求并提示用户等待，同时立刻释放刚增加的计数。

### 2. Bot 端任务注册表 (Task Registry)
中控端的 Redis 只维护任务本身，不知道任务属于哪个 Telegram 用户或聊天窗口。Bot 端使用 `TaskRegistry` 维护了这层上下文映射。
* **数据结构 (Hash)**：在 Redis 中使用 `REDIS_PREFIX:active_tasks` 的哈希表。
* **存储内容**：包含 `user_id`, `chat_id`, `message_id`（用于更新 Telegram 中的排队进度消息）, `cost`（消耗的灵石）, 以及提交给中控后返回的 `backend_task_id`。

### 3. 容灾与意外宕机恢复 (Disaster Recovery)
位于 `src/services/recovery_service.py`。当 Bot 因为代码更新 (`docker restart`) 或意外崩溃重启时，内存中的任务上下文会全部丢失，此时：
1. **扫描僵尸任务**：Bot 重启进入 `post_init` 钩子时，从 Redis 的 `active_tasks` 哈希表中拉取所有未完成的任务。
2. **分类处理**：
   * **未提交的任务**：任务还没发给中控 API（`backend_task_id` 为空）Bot 就挂了，系统会调用退款逻辑，将灵石退还给用户。
   * **运行中的任务**：任务已发给中控，Bot 会重新构建上下文（模拟 `bot_context` 和 `message` 对象），并**重新挂载进度监听器**。确保生成完成后能准确地把媒体发回给用户。
3. **清理与释放**：恢复结束或退款后，从 Redis 中移除该任务记录，并释放用户的并发锁。

### 4. 标准任务流转生命周期
一个正常用户发起请求在 Bot 端 Redis 的流转：
1. **加锁**：Redis 增加用户并发数。
2. **注册**：在 Redis `active_tasks` 写入任务初始信息（记录成本和 Telegram 上下文）。
3. **更新**：调用中控 API 拿到 `task_id` 后，更新 Redis 中的记录，绑定 `backend_task_id`。
4. **监听**：不断拉取中控 API 进度，更新 Telegram 消息状态。
5. **解锁**：生成成功发图给用户后，从 Redis 中删除记录，并减少用户的并发数（解锁）。异常报错也会在此阶段执行清理退款。