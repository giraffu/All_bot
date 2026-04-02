# Telegram Bot 系统数据流通、接口请求与优化指南

本文档基于系统经过“分库隔离”、“Pub/Sub 改造”及“MinIO 引用传递”重构后的最新架构，详细梳理了各个微服务之间的数据流向、核心 API 请求，并分析了系统中仍然存在的潜在性能瓶颈与优化方向。

---

## 1. 全链路数据流通与交互逻辑梳理

整个系统是一个高内聚低耦合的**异步事件驱动 + 微服务架构**，分为四个主要角色：**Telegram Bot（用户网关）**、**Dashboard（管理后台）**、**Central API（中控调度）** 和 **Worker（执行节点）**。

任务的生命周期流转可以分为以下四个阶段：

### 阶段 A：任务接收入库 (Bot -> MinIO -> API)
1. **用户发单**：用户在 Telegram 发送图片/视频或点击功能按钮触发 Handler。
2. **并发校验与扣费**：Bot 连接 `Redis DB 1`，通过 `INCR {REDIS_PREFIX}user_concurrency:{user_id}` 检查并发数（限制单用户最多 3 个）。校验通过后扣除灵石，在 DB 1 的 `active_tasks` 哈希表中登记任务元数据。
3. **素材云化**：Bot 将用户上传的媒体文件直接流式写入 **MinIO** 的 `bot-data` 桶，获取其 `Object Key`（如 `12345/input/abc.jpg`）。
4. **派发任务**：Bot (`src/api_client.py`) 组装纯 JSON 格式的请求体（包含 Prompt、图片 Key、优先级等），通过 `HTTP POST` 发送给中控 API（如 `/comfy_img2img`）。
5. **API 入队**：中控 API (`backend/app/main.py`) 接收 JSON，在 **Redis DB 2** 创建任务详情 (`comfy:task:{id}`)，并将其推入 `comfy:queue:pending` 有序集合（Score 为按优先级加权的时间戳）。

### 阶段 B：调度与执行 (Worker <-> API <-> MinIO)
1. **Worker 轮询抢单**：底层 3 个 Worker (`agent_main.py`) 每隔 2 秒向中控 API 发送 `GET /api/agent/task/pop?types=xxx` 请求。
2. **API 派单**：中控 API (`backend/app/queue_manager.py`) 从 DB 2 的 `pending` 队列中弹出一个匹配该 Worker 支持类型的最高优任务，移入 `running` 集合，并在任务元数据中绑定该 Worker 的 `agent_id`。
3. **下载与注入**：Worker 拿到任务 JSON，直接凭 `image_key` 访问 **MinIO** 下载原始图片。随后调用 `workflow_patcher.py`，严格根据 `mappings.json` 将图片路径、Prompt 及自动补齐的 Seed 注入到 ComfyUI 工作流模板中。
4. **提交引擎**：Worker 将图片通过 HTTP API 传入 ComfyUI，并提交组装好的工作流 JSON 开始推理。

### 阶段 C：进度同步与交付 (Worker -> API -> Bot)
1. **心跳与进度上报**：
   - Worker 内部协程监听 ComfyUI WebSocket 获取执行进度，通过 `POST /api/agent/task/status` 实时发给中控 API。
   - Worker 每 15 秒向 API 发送节点存活心跳 (`heartbeat`) 和任务防卡死租约 (`task_heartbeat`)。
2. **Pub/Sub 广播**：中控 API 收到进度，更新 DB 2，并通过 Redis 的 Pub/Sub 频道 `comfy:task_events:{task_id}` 将进度广播。
3. **Bot 实时响应**：Bot 端异步阻塞监听该频道，收到消息后立即调用 Telegram API 更新用户的进度条文本（平滑滚动）。
4. **成品回传**：ComfyUI 生成完毕，Worker 将成品上传到 MinIO 的 `comfyui-temp` 桶，调用 API 的 `/complete`。Bot 收到 `done` 信号，调用 API 的 `/image/{id}` 接口把成品拉回来发给用户，并清理 DB 1 的并发锁。

### 阶段 D：大屏监控与自愈 (Dashboard & Background Jobs)
1. **双线聚合监控**：
   - Dashboard 前端请求 `/api/system/active_bot_tasks`，后端直连 `Redis DB 1` 读取队列，并 JOIN PostgreSQL 补充用户画像（境界/身份）。
   - Dashboard 前端请求 `/api/system/workers`，后端代理请求中控 API，API 遍历 `Redis DB 2` 的心跳记录，返回各个 Worker 的忙闲状态及进度条。
2. **僵尸清理 (自愈)**：
   - **API 侧**：后台协程扫描 `running` 队列，若任务心跳超过 5 分钟未更新，自动标为 `error` 释放。
   - **Bot 侧**：`clean_zombies_loop` 每 10 分钟扫描 `active_tasks`，排队超 2 小时的任务自动退还灵石，并调用 API `DELETE /api/tasks/{id}` 实现双向取消，杜绝幽灵任务。

---

## 2. 潜在瓶颈与深度优化空间 (Optimization Roadmap)

虽然系统已解决内网带宽爆炸和 API OOM 问题，但在调度性能和高并发架构设计上，仍有以下优化方向可供未来演进：

### 💡 优化点一：Worker 的“无脑轮询” (Polling) 损耗
- **现状**：Worker 只要空闲，就会写死一个 `while True: sleep(2)`，每 2 秒请求一次 `/pop` 接口。在夜间低谷期，10 个 Worker 每天会产生数十万次无效的 404 请求，浪费 CPU 并刷屏日志；而突发任务时，最多会有 2 秒的接单延迟。
- **优化方案**：把 `/pop` 接口改为 **长轮询 (Long Polling)** 或者引入 Redis 的 **阻塞弹出 (`BZPOPMIN`)**。
  - Worker 发起请求时，若队列为空，API 将请求挂起（例如设置 30 秒超时）。
  - 一旦有新任务入队，API 立刻放行一个挂起的请求。既能做到**毫秒级零延迟**接单，又能让空闲时的网络请求数量骤降 95%。

### 💡 优化点二：多类型任务匹配的 O(N) 扫描效率低下
- **现状**：在中控 API `queue_manager.py` 中，当 Worker 请求特定类型的任务（如只要 `face_swap`）时，API 是从 `pending` 队列按优先级抓取前 50 个任务，在 Python 中通过 `for` 循环查 Hash 表对比类型。不匹配再抓下 50 个。
- **痛点**：若队列积压了 1000 个长视频任务，而某空闲 Worker 只想接换脸任务，API 必须扫描并跳过大量无关记录，严重阻塞 Redis 事件循环。
- **优化方案**：**队列分型 (Multi-Queues)**。
  - 弃用单一的 `comfy:queue:pending`。改为按类型建队列，如 `comfy:queue:pending:video` 和 `comfy:queue:pending:image`。
  - Worker 需要什么类型，就直接去对应的 Sorted Set 里 `ZPOPMIN`，时间复杂度瞬间从 O(N) 降为 O(logN)。

### 💡 优化点三：Dashboard 的“N+1”查询风暴
- **现状**：Dashboard 后端的 `get_active_bot_tasks` 为了判断每个任务在底层的状态（排队中 vs 生成中），使用了 `asyncio.gather` 并发请求中控 API 的 `/status/{backend_id}`。如果 50 个任务排队，它会瞬间向中控 API 发出 50 个独立的 HTTP 请求。
- **优化方案**：在中控 API 侧新增一个 `/status/batch` 接口。Dashboard 只需要传一个 `[id1, id2, id3]` 的 JSON 数组，API 利用 Redis Pipeline 一次性查完所有 Hash 状态并返回大字典。极大降低 Dashboard 刷新时的网络开销和卡顿感。

### 💡 优化点四：Worker 负载不均衡与 OOM 风险
- **现状**：Worker 只要空闲就抢最高优先级的任务。
- **痛点**：长视频生成极其消耗显存。如果一个显卡较小的 Worker 连续抢到了两个重度视频任务，极易引发显存溢出 (OOM)。
- **优化方案**：在 Worker 的心跳 (`heartbeat`) 里，不仅上报 `idle/running`，还可以通过 Python 获取并上报**当前的显存余量 (VRAM) 和系统负载**。中控 API 分发任务时，引入资源感知的调度算法，优先把“重活”派发给负载最低的强力节点。

### 💡 优化点五：Worker 下载 MinIO 的本地中转冗余
- **现状**：Worker 是通过 `minio_client.fget_object` 将输入图片完整下载到本地硬盘 (`COMFY_INPUT_DIR`)，然后再通过 HTTP `Upload` API 把这套文件流发给 ComfyUI 实例。
- **优化方案**：如果 ComfyUI 容器和 Worker 运行在同一台宿主机上（或挂载了相同的 Docker Volume），Worker 完全可以直接把文件从 MinIO 下载到 ComfyUI 的 `input` 目录里，然后仅需将文件名填入 JSON 工作流，省去了“下载到本地 -> 再次 HTTP 上传给 ComfyUI”的冗余步骤，进一步提升 I/O 效率。