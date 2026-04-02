# 中控 API 任务取消功能 (Cancel Task) 实现方案

## 1. 背景与目标
目前系统中 Bot 侧与中控 API 侧的任务状态存在脱节：当 Bot 侧因为超时清理（如 `clean_zombies.py`）、异常重启或用户主动操作而放弃某个任务时，中控 API 和底层 ComfyUI Agent 并不知情。这导致了算力浪费（GPU 继续跑无效任务）、存储浪费（无效产物上传 MinIO）以及队列拥堵。

**目标**：通过在 API 侧增加“取消任务”接口，让 Bot 侧能够主动通知 API 丢弃特定任务，从而释放资源，保持两侧状态一致。

## 2. 核心架构设计

采用**主动通知**的模式。Bot 侧在清理任务时，调用 API 侧提供的 HTTP `DELETE` 接口。API 侧根据任务当前所处的生命周期状态（`PENDING` 或 `RUNNING`），采取不同的取消策略。

### 2.1 任务状态流转补充
在原有的任务状态（`PENDING`, `RUNNING`, `DONE`, `ERROR`）基础上，逻辑上增加 `CANCELLED` 状态处理。

## 3. 具体实现步骤

### 第一步：API 层路由与控制 (backend/app/routers/agent.py 或类似路由文件)
新增一个用于取消任务的 RESTful 接口。

**接口定义**：
- **Method**: `DELETE`
- **Path**: `/api/tasks/{task_id}`
- **Response**: 返回取消操作的结果（成功、任务不存在、或任务已完成无法取消）。

**处理逻辑**：
1. 接收到 `task_id`。
2. 调用 `QueueManager` 的取消方法（需新增）。

### 第二步：Redis 队列管理层 (backend/app/queue_manager.py)
在 `QueueManager` 中新增 `cancel_task(task_id: str)` 方法。此方法需要处理两种核心情况：

**场景 A：任务在 `PENDING` 状态（排队中）**
- **特征**：任务 ID 存在于 `comfy:queue:pending` (Sorted Set) 中。
- **动作**：
  1. 使用 `ZREM` 从 `comfy:queue:pending` 中移除该任务。
  2. 将 `comfy:task:{task_id}` 哈希表中的 `status` 字段更新为 `CANCELLED`（或直接复用 `ERROR` 状态，附加 `error_msg: "Task cancelled by bot"`，视现有前端和枚举定义而定）。
- **效果**：该任务永远不会被 Worker 取走，完美避免资源浪费。

**场景 B：任务在 `RUNNING` 状态（执行中）**
- **特征**：任务 ID 存在于 `comfy:queue:running` (Set) 中，说明已经被 Worker 领走并可能在 ComfyUI 中执行。
- **动作**：
  1. 将 `comfy:task:{task_id}` 哈希表中的 `status` 字段标记为 `CANCELLED`。
  2. **进阶中断（可选/推荐）**：如果系统中维护了 `task_id` 与执行该任务的 `agent_id` 的映射，可以通过 Redis Pub/Sub 或专用的中断队列向该 Agent 发送中断指令。Agent 收到后调用 ComfyUI 的 `/interrupt` API 停止推理。
  3. **基础防御（兜底）**：即便不发中断指令，由于状态已标记为 `CANCELLED`，Worker 在执行完毕准备上传 MinIO 前，需要检查此状态。

### 第三步：Worker 执行层 (workers/comfy_agentX/)
增强 Worker 对被取消任务的感知能力，避免无意义的后处理。

**拦截点**：
在 Worker 完成 ComfyUI 推理，拿到本地生成的图片/视频后，**准备上传到 MinIO 之前**。

**逻辑补充**：
1. Worker 向 Redis 查询当前 `task_id` 的最新状态（调用类似 `get_task_status`）。
2. 如果发现状态是 `CANCELLED`（或包含取消标志的 `ERROR`），则：
   - 放弃上传动作（跳过 MinIO S3 PutObject）。
   - 删除本地的临时产物文件。
   - 不再向中控 API 汇报 `DONE` 状态（或上报一种特殊的忽略状态）。

### 第四步：Bot 侧调用层 (src/services/task_service.py & clean_zombies.py)
让 Bot 在决定丢弃任务时，触发上述 API。

**修改点 1：清理脚本 (`clean_zombies.py`)**
- 遍历并决定删除某个超时任务时，提取该任务记录中的 `backend_task_id`。
- 如果存在 `backend_task_id`，发起 `HTTP DELETE` 请求到中控 API。
- 随后再清理本地 Redis 中的 `active_tasks` 和并发锁。

**修改点 2：异常恢复与主动退款逻辑 (`TaskRegistry` / `TaskService`)**
- 封装一个工具函数 `cancel_backend_task(backend_task_id: str)`。
- 在任何需要彻底终结任务并退还灵石的地方（如用户触发某种中止命令，或者 Bot 重启时判断某些任务已失效），调用该函数。

## 4. 实施建议与阶段划分

为了降低风险并快速见效，建议分阶段实施：

**Phase 1：实现排队拦截（性价比最高）**
- 完成 API 路由 `DELETE /api/tasks/{task_id}`。
- 在 `QueueManager` 中实现针对 `PENDING` 任务的移除逻辑。
- 在 `clean_zombies.py` 中接入调用。
- **预期收益**：解决大部分由于长时间排队导致的僵尸任务积压问题，不再空转 GPU。

**Phase 2：实现运行中拦截（节约存储）**
- 在 Worker 上传 MinIO 前增加状态校验（检查是否被标记为 Cancelled）。
- 如果 Cancelled 则跳过上传并清理本地临时文件。
- **预期收益**：节省对象存储空间和网络带宽。

**Phase 3：实现硬件级打断（终极优化，视需求而定）**
- 建立中控与 Agent 的双向通信或中断信道。
- Agent 监听中断信号并调用 ComfyUI `/interrupt`。
- **预期收益**：立刻释放 GPU 显存，供下一个任务使用。

## 5. 边界情况与注意事项
- **并发竞争（Race Condition）**：在 API 执行 `ZREM` 移除排队任务的瞬间，Worker 可能恰好 `ZPOPMIN` 取走了该任务。因此，将状态强行标记为 `CANCELLED` 是必须的，这样即便 Worker 抢到了，在开始干活前（或干活后上传前）校验状态时也能拦截。
- **状态枚举兼容**：检查现有的 `TaskStatus` 模型（如 `app.models`），决定是新增 `CANCELLED` 枚举，还是复用 `ERROR` 并辅以特定的 `error_msg`，以最小化对现有前端面板 (Dashboard) 解析的冲击。
