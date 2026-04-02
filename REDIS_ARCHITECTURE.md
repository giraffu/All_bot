# Telegram AI 机器人系统 Redis 架构与交互逻辑详解

本文档详细记录了系统在经过“分库隔离”、“Pub/Sub 实时订阅”以及“自动化心跳哨兵”等重构后的最新 Redis 架构。

## 1. 全局架构：逻辑分库隔离 (Logical Database Isolation)

为了解决高并发下连接池争抢以及运维误操作（如 `FLUSHDB`）导致全局雪崩的风险，系统目前将同一个物理 Redis 实例划分为了两个独立的逻辑数据库：

- **DB 1 (业务层/网关层)**: 供 `Telegram Bot` 以及 `Dashboard` 的绝大部分业务使用。
- **DB 2 (调度层/计算层)**: 仅供 `Central API` (中控后端) 以及底层 Worker (Comfy Agent) 调度使用。

*注：虽然分库，但 Redis 的 Pub/Sub (发布/订阅) 机制是全局的，无视 DB 边界，因此可以用于跨库的实时通信。*

---

## 2. DB 1 (业务层) 数据结构与作用

此库由 `Telegram Bot` 进程维护，同时被 `Dashboard Backend` 进程只读或进行干预。

### 2.1 核心键值说明

| Key 模式 | 数据结构 | 作用域 | 核心职责 |
| :--- | :--- | :--- | :--- |
| `{REDIS_PREFIX}user_concurrency:{user_id}` | `String (Integer)` | Bot | **用户并发锁**。通过 `INCR` 和 `DECR` 控制单个用户同时最多只能有 `MAX_CONCURRENT_TASKS`（目前为 3 个）个任务在排队或生成。为了防死锁，设置了 1 小时的兜底过期时间。 |
| `{REDIS_PREFIX}active_tasks` | `Hash` | Bot / Dashboard | **任务追踪与容灾注册表**。<br>• **Field**: `task_id`<br>• **Value**: JSON 字符串，包含 `user_id`, `cost` (消耗灵石), `status`, `backend_task_id` 等。<br>• **用途**: Bot 重启异常恢复、Dashboard 实时队列监控、超时僵尸任务清理。 |

### 2.2 交互逻辑
- **新建任务**: Bot 接收请求 -> `INCR` 并发锁 -> 写入 `active_tasks` -> 发送 HTTP 请求给中控 API。
- **任务完成**: Bot 收到完成通知 -> 投递结果给用户 -> 删除 `active_tasks` 记录 -> `DECR` 并发锁。
- **后台巡检 (clean_zombies)**: 守护协程每 10 分钟扫描 `active_tasks`，对于驻留超过 2 小时的任务，判定为卡死，自动执行：Redis 清理 -> 释放并发锁 -> 调用中控 API 发送 `DELETE` 取消任务 -> 给用户退款。

---

## 3. DB 2 (调度层) 数据结构与作用

此库由 `Central API` (`backend_api`) 全权接管，负责底层高优先级的队列调度。

### 3.1 核心键值说明

| Key 模式 | 数据结构 | 作用域 | 核心职责 |
| :--- | :--- | :--- | :--- |
| `comfy:queue:pending` | `Sorted Set` | API | **全局优先级队列**。<br>• **Member**: `task_id`<br>• **Score**: 根据请求时间戳与用户优先级权重计算得出。Worker 使用 `ZPOPMIN` 抢占任务。 |
| `comfy:queue:running` | `Set` | API | **运行中任务集合**。追踪哪些任务已被 Worker 领走。 |
| `comfy:task:{task_id}` | `Hash` | API | **任务状态元数据**。<br>• 包含字段：`status`, `progress`, `params`, `worker_id` (接单的节点ID)。 |
| `comfy:agent:heartbeat:{agent_id}` | `Hash` | API / Worker | **节点健康注册表**。<br>• 包含字段：`types` (支持的业务), `status` (idle/running), `last_seen`, `current_task_id`。具有 30 秒过期时间 (TTL)。 |
| `comfy:task_heartbeat:{task_id}` | `String` | API | **任务心跳锁**。5分钟过期。用于防范 Worker 假死/掉线导致的僵尸任务。 |

### 3.2 调度与交互逻辑
- **入队**: 中控 API 收到请求 -> 存入 `comfy:task:{id}` -> 计入 `comfy:queue:pending`。
- **出队 (Worker 抢占)**: Worker 轮询 `GET /api/agent/task/pop` -> API 使用 `ZPOPMIN` 弹出最高优先级任务 -> 移入 `comfy:queue:running` -> 将 `worker_id` 绑定到任务。
- **僵尸回收**: 中控 API 后台运行 `check_zombie_tasks`，定期检查 `comfy:queue:running` 中的任务。若其对应的 `task_heartbeat` 已过期（>5分钟未更新），则判定 Worker 崩溃，自动将任务标为 `error` 并释放。

---

## 4. 全局跨库通信：Redis Pub/Sub

为了彻底消除之前架构中 Bot 侧每 2 秒向中控 API 发送 HTTP 轮询带来的巨大性能损耗，系统引入了全局 Pub/Sub 机制。

- **Channel 命名**: `comfy:task_events:{task_id}`
- **发布者 (Publisher)**: 中控 API (`queue_manager.py`)
  - 当任务状态变为 `running` (且有进度更新), `done`, `error`, `cancelled` 时，自动向该 Channel 发布包含状态 JSON 的消息。
- **订阅者 (Subscriber)**: Telegram Bot (`api_client.py`)
  - 使用 `pubsub.subscribe()` 异步阻塞监听。
  - 收到 `done` 或 `error` 后，立即断开订阅，处理后续的图片/视频下载与发放逻辑。
  - **兜底机制**: 为防止网络抖动导致 Pub/Sub 丢包，监听器内部结合了 `asyncio.wait_for` 超时机制，超时后会触发一次 HTTP 请求回查最新状态。

---

## 5. Dashboard (管理后台) 聚合逻辑

管理后台需要同时呈现“业务侧数据”与“底层硬件状态”，其交互路径如下：

1. **实时任务大表 (`/api/system/active_bot_tasks`)**:
   - Dashboard Backend 直连 **DB 1**。
   - 读取 `active_tasks`，并与 PostgreSQL 中的用户信息（境界、身份）进行 JOIN 聚合，展示排队中的用户画像。
2. **底层 Worker 看板 (`/api/system/workers`)**:
   - Dashboard Backend 通过 HTTP 请求中控 API（中控 API 连着 **DB 2**）。
   - 中控 API 遍历 `comfy:agent:heartbeat:*` 获取所有存活的节点，并利用 `current_task_id` 字段联查对应的进度和类型。
   - 返回给前端，形成“节点忙闲状态及实时进度条”的动态监控面板。
3. **双向终止任务**:
   - 管理员点击“强制退款” -> Dashboard Backend 删掉 DB 1 的 `active_tasks` 并退费 -> **强制发送 HTTP DELETE 请求给中控 API** -> 中控 API 将 DB 2 中的底层任务踢出队列并标记 `CANCELLED`。

---

## 6. 总结流转图

```text
[用户发图] 
   │
   v
[Bot] ──(1.锁与注册)──> Redis DB 1
   │
   └──(2.HTTP POST)──> [中控 API] ──(3.入队)──> Redis DB 2 (Pending)
                                       │
                                   (4.Pop)
                                       v
[Bot] <──(6.Pub/Sub 实时进度)────── [Worker] ──(5.执行并上报心跳)──> Redis DB 2 (Heartbeat)
   │
   v
[Bot 下载成品，投递给用户，解锁 DB 1]
```