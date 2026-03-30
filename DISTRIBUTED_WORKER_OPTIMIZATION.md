# 主控 API 与 Worker 分布式架构优化方案

本文档针对当前系统在**跨公网/外网部署**（不支持局域网挂载，暂不使用 WebSocket）条件下的主控 API (`main.py`) 与 Worker (`agent_main.py`) 交互架构进行梳理与优化。

## 1. 当前架构痛点分析

*   **活跃 Worker 统计不准**：主控 API `/system/status` 当前采用硬编码（`active_workers = 1 if queue_size > 0 else 0`）盲猜存活状态。
*   **短轮询效率低下**：Worker 每 2 秒发送一次 `GET /pop` 请求，大量空转消耗网络资源，且存在最高 2 秒的任务下发延迟。
*   **主控带宽瓶颈**：主控 API 作为中间件获取生成结果时，会先从 MinIO 下载临时文件再传给用户，导致主控服务器带宽加倍消耗。
*   **冗余废弃代码**：`t2i_pornmaster_turbo` 接口已被废弃，但其中包含的阻塞式轮询（`while sleep`）代码依然存在。
*   **GPU 算力泄漏风险**：外网 Worker 若发生超时（如 600 秒断连），未向 ComfyUI 发送中断信号，导致后台持续渲染浪费显存。

---

## 2. 详细优化实施步骤 (Step-by-Step)

### 第一步：建立 Worker 注册与心跳池 (Heartbeat)
**目标**：精准统计跨网 Worker 集群的真实在线数量。
1.  **QueueManager 修改 (`queue_manager.py`)**：
    *   新增 `register_worker_heartbeat(agent_id, supported_types)` 方法。
    *   利用 Redis 设置键值 `comfy:worker:active:{agent_id}`，TTL 设置为 30 秒。
    *   新增 `get_real_active_workers_count()` 方法扫描该前缀的 Key 数量。
2.  **主控接口新增 (`agent.py` & `main.py`)**：
    *   在 `agent.py` 增加 `@router.post("/heartbeat")` 接口接收存活信号。
    *   修改 `main.py` 的 `/system/status` 接口，替换硬编码，返回真实的在线 Worker 数。
3.  **Worker 侧改造 (`agent_main.py`)**：
    *   新增 `heartbeat_loop` 协程，每 15 秒向主控发送一次心跳。
    *   在 `start()` 方法中与其它 loop 共同启动。

### 第二步：废弃主控文件流转，启用 MinIO 预签名直链 (307 Redirect)
**目标**：解放主控带宽，让用户直连 NAS/MinIO 节点下载媒体。
1.  **修改主控 API (`main.py`)**：
    *   重构 `/image/{task_id}` 和 `/video/{task_id}` 接口。
    *   使用 `minio_client.presigned_get_object` 签发有效期为 1 小时的临时 URL。
    *   返回 `RedirectResponse(url=presigned_url, status_code=307)`，使用户端/前端直接跳转下载。

### 第三步：升级 HTTP 长轮询 (Long Polling)
**目标**：在纯 HTTP 协议下，实现任务秒级派发，并大幅减少无效握手。
1.  **主控接口挂起 (`agent.py`)**：
    *   在 `pop_task` 接口中引入内部循环：最多等待 15 秒（每次 `asyncio.sleep(1)` 检查队列）。
    *   如果有任务立刻返回；如果 15 秒后仍无任务，返回 `204 No Content` 状态码。
2.  **Worker 客户端配置 (`agent_main.py`)**：
    *   将 `httpx.AsyncClient` 的超时时间 `timeout` 延长至 30 秒以上。
    *   收到 204 或 404 响应后，**不再休眠等待**，立即发起下一轮请求，保持连接的连贯性。

### 第四步：代码精简与 GPU 容灾阻断
**目标**：清除冗余代码，并保护外网断连时的显卡算力。
1.  **清理废弃接口 (`main.py`)**：
    *   彻底删除 `@app.post("/api/v1/workflows/t2i-pornmaster-turbo")` 及其依赖的同步阻塞逻辑。
2.  **ComfyUI 中断机制 (`comfy_client.py` & `agent_main.py`)**：
    *   在 `comfy_client.py` 增加 `interrupt_task()` 方法，调用 ComfyUI 的 `/interrupt` 接口。
    *   在 Worker 的 `process_task` 异常捕获块（`try...except asyncio.TimeoutError:`）中，当任务执行超 600 秒时，强制触发中断信号以释放 GPU，随后抛出异常并向主控汇报失败。

---

## 3. 预期收益
*   **精准监控**：Dashboard 可真实展示分布式计算节点的健康状态。
*   **性能提升**：任务派发延迟从 2 秒降低至 1 秒以内。
*   **流量节约**：主控不再承担多媒体文件的下发工作，带宽压力下降 90% 以上。
*   **系统健壮性**：即使外网节点失联，GPU 资源也能被安全释放，不会产生死锁任务。