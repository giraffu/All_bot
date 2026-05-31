# ComfyUI Agent 健康门禁与 Error 状态补齐方案（基于当前代码校正版）

> 本文档用于替换早期的旧版实施计划。旧文档中的部分描述已经与当前代码现状不一致，尤其是“Agent 仍会持续吞任务”这一前提已不再成立。本文以当前仓库真实代码为准，重新梳理现状、缺口与建议改造点。

## 1. 文档目标

当前 `ComfyAgent` 的主链路已经不是“盲拉任务 -> 处理时报错”，而是：

1. `poll_loop` 在每次拉取任务前，先通过 HTTP 探测本地 ComfyUI 是否健康。
2. 如果 ComfyUI 不可用，当前轮询会暂停，不会继续调用 `/api/agent/task/pop`。
3. 如果 ComfyUI 恢复，Agent 会自动恢复拉单。

因此，这份文档的目标不再是“从 0 修复队列击穿”，而是：

1. 说明当前已经落地的保护机制。
2. 指出当前仍缺失的 `error` 状态可观测性。
3. 给出与现有代码结构兼容的最小补齐方案。

---

## 2. 当前代码真实现状

### 2.1 已经落地的保护机制

当前代码中的以下行为已经实现：

1. **轮询前置健康检查**  
   `workers/comfy_agent/agent_main.py` 中的 `_probe_comfy_ready()` 会请求 ComfyUI 的 `/system_stats`。  
   `poll_loop()` 每轮开始前都会先做这次探测。

2. **不健康时暂停拉单**  
   当 `_probe_comfy_ready()` 返回失败时，`poll_loop()` 会：
   - 将 `self._comfy_poll_paused = True`
   - 记录 `ComfyUI unavailable, pausing task polling` 日志
   - `await asyncio.sleep(5)`
   - `continue`

   这意味着 Agent 在 ComfyUI 挂掉时，已经不会继续调用 `/api/agent/task/pop`，从而避免继续消耗排队任务。

3. **恢复后自动继续接单**  
   当探测重新成功时，如果之前处于暂停状态，代码会打印 `ComfyUI reachable again, resuming task polling`，然后恢复正常拉单。

4. **关键执行点额外重试**  
   在上传输入、提交工作流前，`_wait_for_comfy_ready()` 还会额外做最多 5 次、每次 2 秒的重试，减少刚恢复时的瞬时抖动误伤。

5. **WebSocket 断线自动重连**  
   `ws_listener_loop()` 已经包含超时检测、`ping()` 保活与异常后 5 秒重连逻辑，但它当前只负责执行事件监听，不参与 Agent 状态上报。

### 2.2 当前尚未实现的部分

虽然“停止吞队列”已经基本落地，但下面这些能力仍然没有实现：

1. **没有显式的熔断状态机**  
   当前只有 `self._comfy_poll_paused`，没有：
   - `consecutive_failures`
   - `max_failures`
   - `is_error_state`

2. **心跳不上报 `error`**  
   当前 `report_heartbeat()` 只会上报：
   - 有 `_active_execution` 时为 `running`
   - 否则为 `idle`

   也就是说，即使 ComfyUI 长时间不可用，Dashboard 仍无法从实时 Worker 状态中看到“故障”。

3. **Dashboard 仍是二元状态展示**  
   `dashboard/frontend/src/components/QueueStats.vue` 当前只区分：
   - `running` -> 绿色“忙碌”
   - 其他状态 -> 灰色“空闲”

   即使后端将来真的写入 `error`，前端也会把它显示成“空闲”。

4. **测试尚未覆盖 Error 状态闭环**  
   现有测试只验证了：
   - 心跳在有 `_active_execution` 时上报 `running`
   - 任务心跳会继续发送

   但没有覆盖：
   - 熔断阈值触发
   - `error` 状态上报
   - 自愈恢复
   - Dashboard `error` 渲染

### 2.3 对旧文档结论的纠偏

旧版文档的这条判断已经失真：

> “当 ComfyUI 不可用时，Agent 依然会不断从 Redis 中拉取任务并瞬间失败。”

这在当前代码中已不成立。  
当前真实情况是：

1. **队列保护问题已被部分解决**：因为 `poll_loop()` 已经在拉单前做健康门禁。
2. **可观测性问题仍未解决**：管理员无法从实时 Worker 卡片一眼看出该节点处于故障态。
3. **显式状态机仍未落地**：当前系统有“暂停拉单”行为，但没有“`error` 状态”语义。

---

## 3. 正确的改造目标

基于当前代码，建议把目标重新定义为以下 3 件事：

1. **保留现有的前置健康门禁**  
   不回退当前已经生效的 `_probe_comfy_ready()` + `_comfy_poll_paused` 保护逻辑。

2. **补齐 Agent 显式 `error` 状态**  
   在连续探测失败达到阈值后，把 Agent 状态从“静默暂停拉单”升级为“显式故障态”。

3. **让 Dashboard 正确展示 `error`**  
   一旦心跳写入 `status=error`，前端实时 Worker 卡片必须显示为红色故障，而不是灰色空闲。

---

## 4. 建议的最小实现方案

### 4.1 `agent_main.py`：在现有轮询门禁上补状态机

建议保留当前结构，不推翻重写，只做增量增强。

#### 需要新增的状态变量

在 `ComfyAgent.__init__` 中，基于现有字段追加：

```python
class ComfyAgent:
    def __init__(self):
        # ... 保留现有初始化 ...
        self.tasks = []
        self._idle_completed_event = asyncio.Event()
        self._active_execution: Optional[TaskExecutionContext] = None
        self.running = False
        self._comfy_poll_paused = False

        # 新增：显式故障态
        self.consecutive_failures = 0
        self.max_failures = 3
        self.is_error_state = False
```

这里要注意：

1. `self._comfy_poll_paused` 不能删除，它已经承载了当前“暂停拉单”的行为。
2. 新增字段的作用不是替代 `_comfy_poll_paused`，而是把“暂停”升级为“可观测的故障语义”。

#### 心跳状态优先级

建议把 `report_heartbeat()` 改成：

1. `is_error_state == True` 时，优先上报 `error`
2. 否则，有 `_active_execution` 时上报 `running`
3. 否则上报 `idle`

参考写法如下：

```python
async def report_heartbeat(self):
    try:
        active_execution = self._active_execution
        if self.is_error_state:
            status = "error"
        else:
            status = "running" if active_execution else "idle"

        await self.master_client.post(
            "/api/agent/task/heartbeat",
            json={
                "agent_id": AGENT_ID,
                "types": SUPPORTED_TASK_TYPES,
                "status": status,
            },
        )

        if active_execution:
            await self.master_client.post(
                "/api/agent/task/task_heartbeat",
                json={"task_id": active_execution.task_id},
            )
    except Exception as e:
        logger.debug(f"Failed to report heartbeat: {e}")
```

说明：

1. 中控路由 `backend/app/agent_router_helpers.py` 当前已经是透传 `status`。
2. `QueueManager.update_agent_heartbeat(...)` 也已经接受任意字符串 `status` 并写入 Redis。
3. 因此后端路由和存储层不需要为 `error` 再新增接口。

#### `poll_loop()` 的正确增量改法

旧文档里建议“完全重写 `poll_loop`”，现在不再合适。  
正确做法是基于当前实现做状态补齐，保留现有日志与过滤信息。

建议逻辑如下：

1. 每轮仍然先调用 `_probe_comfy_ready()`
2. 探测失败时：
   - `self._comfy_poll_paused = True`
   - `self.consecutive_failures += 1`
   - 未达到阈值时短休眠，例如 5 秒
   - 达到阈值后置 `self.is_error_state = True`
   - `error` 状态下可改为更慢探活，例如 15 秒
3. 探测恢复时：
   - 如果之前处于 `is_error_state`，打印恢复日志
   - `self.is_error_state = False`
   - `self.consecutive_failures = 0`
   - `self._comfy_poll_paused = False`
4. 后续拉单逻辑保持现状，不改 `types` 过滤与日志格式

参考骨架：

```python
async def poll_loop(self):
    logger.info(
        f"Agent {AGENT_ID} started polling {MASTER_API_URL} for tasks "
        f"(types: {SUPPORTED_TASK_TYPES or 'all'})..."
    )

    while getattr(self, "running", True):
        try:
            is_healthy = await self._probe_comfy_ready()
            if not is_healthy:
                self._comfy_poll_paused = True
                self.consecutive_failures += 1
                logger.warning(
                    "ComfyUI pre-flight check failed (%s/%s).",
                    self.consecutive_failures,
                    self.max_failures,
                )

                if self.consecutive_failures >= self.max_failures:
                    if not self.is_error_state:
                        self.is_error_state = True
                        logger.error(
                            "Agent %s reached max failures; marking worker as error.",
                            AGENT_ID,
                        )
                    await asyncio.sleep(15)
                else:
                    await asyncio.sleep(5)
                continue

            if self._comfy_poll_paused:
                logger.info("ComfyUI reachable again, resuming task polling")

            if self.is_error_state:
                logger.info("ComfyUI recovered, clearing error state")

            self._comfy_poll_paused = False
            self.is_error_state = False
            self.consecutive_failures = 0

            params = {}
            if SUPPORTED_TASK_TYPES:
                params["types"] = SUPPORTED_TASK_TYPES

            response = await self.master_client.get("/api/agent/task/pop", params=params)
            if response.status_code == 200:
                data = response.json()
                task = data.get("task")
                if task:
                    await self.process_task(task)
                    continue
            elif response.status_code != 404:
                logger.warning(f"Unexpected response from master: {response.status_code}")

        except Exception as e:
            logger.error(f"Polling error: {e}")

        await asyncio.sleep(2)
```

### 4.2 中控与数据模型：当前可直接复用

这一层不需要大改，当前链路已经足以承载 `error`：

1. `backend/app/agent_router_helpers.py` 的 `heartbeat_payload(...)` 会把 `status` 原样传给 `queue_manager.update_agent_heartbeat(...)`
2. `backend/app/queue_manager.py` 会把 `status` 和 `last_seen` 写入 Redis
3. `backend/app/models.py` 中的 `WorkerInfo.status` 本来就是 `str`

因此，最小闭环下：

1. **后端 API 无需新增字段**
2. **Redis 结构无需迁移**
3. **Dashboard 只要支持渲染 `error` 即可看到效果**

可选增强项：

1. 如果未来希望实时卡片显示“最后错误原因”，再补：
   - `last_error`
   - `last_error_at`
2. 这会涉及 Agent 心跳字段、`WorkerInfo` 模型、QueueManager 组装与前端卡片展示，不属于本次最小修正范围。

### 4.3 Dashboard：补齐 `error` 状态渲染

这里是本方案中必须同步修改的一环。

当前 `QueueStats.vue` 的判断仍是二元分支，因此至少要改以下两处：

1. Badge 状态
2. Card 顶部边框颜色

建议改成：

```html
<a-card
  size="small"
  hoverable
  class="worker-card h-full flex flex-col"
  :class="{
    'border-t-2 border-t-green-500': worker.status === 'running',
    'border-t-2 border-t-red-500': worker.status === 'error',
    'border-t-2 border-t-gray-300': worker.status === 'idle'
  }"
>
  <template #title>
    <div class="flex justify-between items-center w-full">
      <span class="font-mono text-sm font-bold truncate pr-2" :title="worker.agent_id">
        {{ worker.agent_id }}
      </span>
      <a-badge
        :status="
          worker.status === 'running'
            ? 'processing'
            : worker.status === 'error'
              ? 'error'
              : 'default'
        "
        :text="
          worker.status === 'running'
            ? '忙碌'
            : worker.status === 'error'
              ? '故障'
              : '空闲'
        "
      />
    </div>
  </template>
</a-card>
```

这样做的效果是：

1. 后端一旦开始上报 `status=error`
2. Dashboard 实时 Worker 卡片就会立即标红
3. 管理员不需要去查 Worker 历史表才能判断节点是否故障

### 4.4 测试补齐建议

建议至少新增以下测试：

1. **Worker 单测**
   - 连续探测失败 3 次后，`is_error_state == True`
   - `report_heartbeat()` 在错误态下发送 `status=error`
   - 探测恢复后，`is_error_state` 与 `consecutive_failures` 被重置

2. **前端展示测试或最小人工验收**
   - 构造 `worker.status = 'error'`
   - 验证 Badge 文案显示“故障”
   - 验证卡片边框变红

---

## 5. 可选增强项：WebSocket 断线时的 HTTP 降级探活

这一项仍然有价值，但应明确为**增强项**，而不是“当前最小修正闭环的必需项”。

### 5.1 当前现状

现在的 `ws_listener_loop()` 在异常时只会：

1. 打日志
2. `await asyncio.sleep(5)`
3. 自动重连

这对于“公网抖动”是友好的，但如果恰好是 ComfyUI 进程崩溃，也可能让任务等待较久。

### 5.2 建议做法

如果当前存在活跃任务，并且 WebSocket 断开，可增加一次 HTTP 探活：

1. HTTP 也失败  
   说明更可能是 ComfyUI 真挂了，可以更快设置 `execution.task_error` 并结束等待。

2. HTTP 仍成功  
   说明更可能只是 WS 抖动，应继续走自动重连。

参考骨架：

```python
except Exception as e:
    logger.error(f"WebSocket connection error: {e}")
    execution = self._active_execution
    if execution:
        try:
            is_healthy = await self._probe_comfy_ready()
            if not is_healthy:
                execution.task_error = f"ComfyUI service lost: {e}"
                execution.completed_event.set()
            else:
                logger.warning("HTTP probe succeeded after WS disconnect; keep reconnecting")
        except Exception as probe_error:
            logger.error(f"HTTP probe after WS disconnect failed: {probe_error}")
    await asyncio.sleep(5)
```

注意：

1. 这里建议继续复用 `_probe_comfy_ready()`，避免再发散出第三套探活实现。
2. 这一步要和跨公网部署场景一起评估，避免把短时网络闪断误判成任务失败。

---

## 6. 修正后的结论

基于当前代码，应该把结论修正为：

1. **“ComfyUI 挂掉时继续吞队列”这个核心风险，当前已经通过轮询前置健康门禁得到部分解决。**
2. **当前真正缺的是“显式 `error` 状态 + 心跳广播 + Dashboard 红色告警”这一套可观测性闭环。**
3. **因此后续改造应以“在现有门禁之上补状态机” 为主，而不是推翻当前 `poll_loop()` 重新设计。**
4. **Dashboard 的 `error` 渲染必须同步落地，否则后端即使开始上报 `error`，前端仍会显示成灰色空闲。**
