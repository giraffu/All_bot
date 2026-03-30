# ComfyUI 代理系统可靠性改造计划

针对 **Agent 卡死**（WebSocket 断连导致搬运进程挂起）及 **僵尸任务**（任务状态长期停留在 `running` 但无实际执行）的问题，制定以下改造方案。

## 1. 核心改进方案

### 1.1 引入 Agent 心跳与任务“租约”机制
- **心跳 (Heartbeat)**：Agent 增加独立协程，每 30s 向 Master 发送心跳包。
- **活跃时间戳 (updated_at)**：Master 在 Redis 中为每个任务记录 `updated_at` 时间戳。
- **僵尸回收 (Watchdog)**：Master 启动后台守护任务，自动扫描 `running` 队列。若任务超过 15 分钟（可配置）未更新，则自动判定为失败并释放资源。

### 1.2 增强 Agent 的容错与状态回查
- **HTTP 兜底回查**：在 Agent 处理任务超时或 WebSocket 异常时，主动调用 ComfyUI 的 `/history` 接口查询任务状态，防止因 WS 丢失消息而导致任务被判定为挂起。
- **协程健康监控**：在 Agent 内部实现主循环自愈逻辑，确保 WS 监听或 Poll 循环崩溃后能自动重启。

---

## 2. 实施路线图

### 第一阶段：Master 节点强化 (backend/app)
- **QueueManager 升级**：
    - 增加 `update_task_heartbeat(task_id)`：更新任务活跃时间。
    - 增加 `cleanup_stale_tasks(timeout_seconds)`：扫描并清理超时任务。
- **API 扩展**：
    - 增加 `/api/agent/heartbeat` 接口，接收 Agent 心跳。
- **后台守护进程**：
    - 在 `main.py` 启动时通过 `asyncio.create_task` 挂载 `cleanup_loop`。

### 第二阶段：Agent 节点强化 (backend/comfy_agent)
- **独立心跳协程**：在 `agent_main.py` 中增加 `heartbeat_loop`。
- **执行逻辑增强**：
    - 在 `process_task` 的 `asyncio.wait_for` 超时捕获中，加入 `comfy_client.get_history()` 调用。
    - 增强 WebSocket 报错后的指数级退避重连机制。

### 第三阶段：测试与验证
- **故障模拟**：停止 Agent 容器，验证 Master 是否在超时后自动标记任务失败。
- **WS 注入错误**：模拟 WS 消息丢失，验证 Agent 是否能通过 HTTP 成功回查任务结果。

---

## 3. 任务列表 (Todo List)
- [ ] Master: 增加任务更新时间戳及清理逻辑 (`QueueManager`)
- [ ] Master: 增加心跳接口及后台清理任务 (`main.py`)
- [ ] Agent: 增加独立心跳协程 (`agent_main.py`)
- [ ] Agent: 增强超时处理，增加 HTTP 状态回查 (`process_task`)

---
**日期**: 2026-03-25
**状态**: 计划中 (Pending Implementation)
