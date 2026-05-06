# ComfyUI Agent 熔断与状态上报（Error 标记）实施方案

## 1. 问题背景与根因分析

在当前的架构中，`ComfyAgent` 采用 HTTP Pull 模型，通过 `poll_loop` 不断从中控 API (`/api/agent/task/pop`) 拉取任务并派发给本地的 ComfyUI。
**当前存在的问题**：
当后端的 ComfyUI 服务因显存溢出 (OOM)、网络断开或进程崩溃而不可用时，Agent 依然会不断从 Redis 中拉取任务。由于本地连接 ComfyUI 失败，这些任务会瞬间被标记为 `failed`，导致严重的队列击穿（吞噬排队任务）。

---

## 2. 核心解决思路：Agent 异常状态标记 (Error State)

根据新的思路，当 Worker Agent 发现下游 ComfyUI 连续不可用时，不只是单纯地休眠，而是**将 Agent 自身的状态标记为 `error`，彻底停止接取任务，并将该异常状态通过心跳同步给中控 API**。

其核心工作流如下：
1. **本地失败计数器**：Agent 本地维护一个 `consecutive_failures` 计数器。
2. **状态流转**：在每次拉取任务前探测 ComfyUI（或在处理任务时捕获连接异常）。当连续失败达到 3 次时，将 Agent 的内部状态 `is_error_state` 置为 `True`。
3. **心跳广播**：`report_heartbeat` 优先读取 `is_error_state`。如果为 `True`，则向中控 API 广播 `"status": "error"`。这样管理员或监控面板就能直接看到该节点已瘫痪。
4. **拒绝接单与自愈**：处于 `error` 状态的 Agent 会跳过 `/api/agent/task/pop` 接口的调用，保护任务队列不被消耗。同时在后台缓慢探活，一旦 ComfyUI 恢复，自动重置回 `idle` 状态。

---

## 3. 具体代码修改实施

请对 `/home/hfy/APP/All_bot/workers/comfy_agent/agent_main.py` 进行以下三个部分的修改：

### 3.1 初始化状态变量
在 `ComfyAgent.__init__` 方法中，增加失败计数器和错误状态标志：

```python
class ComfyAgent:
    def __init__(self):
        # ... (保留原有的初始化代码) ...
        self.running = False
        
        # 新增：断路器与状态标记
        self.consecutive_failures = 0
        self.max_failures = 3
        self.is_error_state = False
```

### 3.2 修改心跳逻辑以支持 Error 状态上报
修改 `report_heartbeat` 函数，使其在 `is_error_state` 为 `True` 时优先上报 `error`：

```python
    async def report_heartbeat(self):
        try:
            # 优先判断是否处于 error 状态
            if getattr(self, 'is_error_state', False):
                status = "error"
            else:
                status = "running" if self.current_task_id else "idle"
                
            await self.master_client.post("/api/agent/task/heartbeat", json={
                "agent_id": AGENT_ID,
                "types": SUPPORTED_TASK_TYPES,
                "status": status
            })
            if self.current_task_id:
                # Add task heartbeat specifically
                await self.master_client.post("/api/agent/task/task_heartbeat", json={
                    "task_id": self.current_task_id
                })
        except Exception as e:
            logger.debug(f"Failed to report heartbeat: {e}")
```

### 3.3 修改 `poll_loop` 停止接单并实现探活恢复 (合并优化版)
修改任务轮询主循环，采用统一的健康检查与状态流转逻辑，避免冗余网络请求：

```python
    async def poll_loop(self):
        logger.info(f"Agent {AGENT_ID} started polling {MASTER_API_URL} for tasks (types: {SUPPORTED_TASK_TYPES or 'all'})...")
        
        while getattr(self, 'running', True):
            try:
                # ==========================================
                # 1. 统一的前置探活与状态流转
                # ==========================================
                is_healthy = await self.comfy_client.check_connection()
                
                if not is_healthy:
                    self.consecutive_failures += 1
                    logger.warning(f"ComfyUI pre-flight check failed ({self.consecutive_failures}/{self.max_failures}).")
                    
                    if self.consecutive_failures >= self.max_failures:
                        if not getattr(self, 'is_error_state', False):
                            self.is_error_state = True
                            logger.error(f"Agent {AGENT_ID} reached max failures! Marking status as ERROR.")
                    
                    # 错误状态下长休眠(15s)，正常状态下短休眠(5s)
                    await asyncio.sleep(15 if getattr(self, 'is_error_state', False) else 5)
                    continue
                    
                # 检查通过，重置状态
                if getattr(self, 'is_error_state', False):
                    logger.info("ComfyUI connection restored! Resetting agent status to normal.")
                    self.is_error_state = False
                
                self.consecutive_failures = 0

                # ==========================================
                # 2. 正常拉取与处理任务
                # ==========================================
                params = {}
                if SUPPORTED_TASK_TYPES:
                    params["types"] = SUPPORTED_TASK_TYPES
                
                response = await self.master_client.get("/api/agent/task/pop", params=params)
                if response.status_code == 200:
                    data = response.json()
                    task = data.get("task")
                    if task:
                        await self.process_task(task)
                        continue  # Immediately poll again after finishing
                elif response.status_code != 404: 
                    logger.warning(f"Unexpected response from master: {response.status_code}")
                    
            except httpx.RequestError as e:
                logger.error(f"Connection to master failed: {e}")
            except Exception as e:
                logger.error(f"Polling error: {e}")
                
            # Wait before next poll
            await asyncio.sleep(2)
```

## 4. 预期收益与架构优势
1. **防止雪崩**：连续 3 次失败后，Agent 会主动放弃接取任务，完美保护了 Redis 中的未分配任务不被吞噬。
2. **状态可视化**：中控 API (`/api/agent/task/heartbeat`) 会收到明确的 `"status": "error"`，结合你的监控 Dashboard，管理员可以直接看到该 Worker 节点标红离线，便于及时排障。
3. **自动化运维闭环**：当管理员修复了 ComfyUI 服务后，处于 Error 状态的 Agent 会通过后台探活（`check_connection`）发现服务恢复，自动清除 Error 标记并继续接单，全程无需重启 Agent 容器。

## 5. 实施时的关键修正点 (Review 建议)

在实际实施上述方案时，需要注意并修复以下隐患，以保证系统表现符合预期：

### 5.1 前端 Dashboard 的状态展示修正
**隐患**：中控 API 收到了 `"status": "error"`，但前端 `dashboard/frontend/src/components/QueueStats.vue` 中的状态展示是二元判断（`worker.status === 'running'`），这会导致处于 error 状态的 Worker 在面板上显示为灰色的“空闲”而非标红。
**修正**：同步修改 `QueueStats.vue` 中的 Badge 和 Card 边框渲染逻辑，增加对 `error` 状态的支持：
```html
<a-badge 
  :status="worker.status === 'running' ? 'processing' : (worker.status === 'error' ? 'error' : 'default')" 
  :text="worker.status === 'running' ? '忙碌' : (worker.status === 'error' ? '故障' : '空闲')" 
/>
```
同时将 Card 的 class 绑定修改为包含 `'border-t-2 border-t-red-500': worker.status === 'error'`。

### 5.2 跨公网部署下的 WebSocket 容错与防死锁策略 (优化版)
**隐患**：如果在任务执行中，ComfyUI 突然崩溃（如 OOM），`ws_listener_loop` 会断开，`process_task` 仍在死等导致 10 分钟死锁。但考虑到**跨公网部署**，WebSocket 断开可能是单纯的网络抖动，如果一断开就立即判定任务失败，会误杀大量正常任务。
**修正**：在 `ws_listener_loop` 捕获到异常时，增加一层 **HTTP 降级探活机制**，区分是“网络抖动”还是“服务崩溃”：
```python
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            # 新增：跨公网容错机制。WS 断开时，通过 HTTP 确认是否真的崩溃
            if getattr(self, 'current_task_id', None):
                try:
                    is_healthy = await self.comfy_client.check_connection()
                    if not is_healthy:
                        logger.error("HTTP pre-flight also failed, ComfyUI crashed. Failing task fast.")
                        self.task_error = f"ComfyUI service lost: {e}"
                        self.task_completed_event.set()
                    else:
                        logger.warning("HTTP is alive, likely just WS network jitter. Retrying WS connection...")
                except Exception as probe_e:
                    logger.error(f"Error during HTTP probe: {probe_e}")
            await asyncio.sleep(5)
```
通过这种机制，既能容忍公网的 WebSocket 闪断自动重连，又能在 ComfyUI 真正崩溃时实现快速失败，避免死锁。

### 5.3 保留原有的关键日志上下文
**隐患**：方案提供的代码片段中，可能会遗漏原代码中关键的过滤信息（如 `(types: {SUPPORTED_TASK_TYPES or 'all'})`），不利于运维排查。
**修正**：在实际修改代码时，务必保留原有的日志语句和业务逻辑，仅在指定位置注入断路器相关的状态判断。