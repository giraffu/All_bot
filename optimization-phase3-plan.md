# 🚀 阶段三：架构演进与深水区重构 (实施方案)

**目标**：拆解超高复杂度的神仙对象（God Object），打通从 Telegram Bot -> Web BFF -> 中控 API -> ComfyUI Worker 的全链路日志追踪。
**影响评估**：深远。涉及核心路由分发逻辑和底层日志拦截器的重构，代码变更范围广，必须严格遵循灰度测试原则。

---

## 任务 3.1: 重构 `handle_callback_query` (消除 CC=192 的神对象)

**背景**：当前 `src/handlers/callback_handler.py` 中的 `handle_callback_query` 函数承载了支付、图库、参数设置、任务操作等所有内联键盘（Inline Keyboard）的点击事件，充满了 `if-elif` 魔法字符串，圈复杂度高达 192，极易在修改时引发“牵一发而动全身”的 Bug。

### 1. 执行步骤 (Execution Steps)

*   **Step 1: 建立策略路由分发器 (Router Registry)**
    在 `src/handlers/` 下新建 `callback_router.py`，实现基于前缀匹配（Prefix-based Routing）的注册中心。
    ```python
    # 示例结构
    CALLBACK_ROUTES = {}
    SORTED_ROUTES = []  # 缓存排序后的路由列表
    
    def register_callback(prefix: str):
        def decorator(func):
            CALLBACK_ROUTES[prefix] = func
            # 🚨 修正：每次注册时动态更新排序缓存，避免模块加载顺序导致的空列表问题
            global SORTED_ROUTES
            SORTED_ROUTES = sorted(CALLBACK_ROUTES.keys(), key=len, reverse=True)
            return func
        return decorator
        
    # 🚨 必须在定义完注册器后显式导入子模块，触发装饰器执行
    # from src.handlers.callbacks import billing_callbacks, gallery_callbacks, misc_callbacks
    ```

*   **Step 2: 垂直业务拆分 (Module Splitting)**
    在 `src/handlers/` 下新建 `callbacks/` 目录，将原本堆在一起的逻辑按业务域抽离：
    *   `billing_callbacks.py` (处理 `buy_`, `pay_`, `vip_` 等前缀)
    *   `gallery_callbacks.py` (处理 `gallery_like_`, `gallery_apply_`, `public_share` 等前缀)
        *   🚨 **注意**：此处注册的前缀必须是 `public_share`（无下划线），因为原有的回调值包含 `public_share`、`public_share_request` 和 `public_share_cancel`，带下划线的前缀会导致精确匹配失败并落入兜底。在此文件最开头保留对全局开关 `ENABLE_PUBLIC_SHARE` 的拦截逻辑。
    *   `task_callbacks.py` (预留占位符，当前系统无主动取消排队内联按钮，无需强行适配)
    *   `misc_callbacks.py` (处理 `random_faceswap_again` 等独立操作。注：绝大多数 FSM 回调已被 `ConversationHandler` 在上层截获，无需单独的 fsm_callbacks 文件)

*   **Step 3: 重写主入口并设置兜底 (Rewrite & Fallback)**
    修改原 `handle_callback_query`，使其仅负责提取 `query.data`、匹配前缀并分发。同时**必须保留原有的数据库上下文装饰器和鉴权同步逻辑**。
    🚨 **红线注意**：**彻底废弃顶层的统一 `query.answer()` 拦截**。Telegram API 严格限制每个 CallbackQuery 只能被 `answer()` 一次，强行提前拦截会导致下游具体的业务弹窗（如使用 `show_alert=True` 的余额不足、操作失败等警告）全部静默失效。消除动画或弹窗的责任应下放给拆分后的各个子 Handler。
    🚨 **路由匹配防冲突**：为了防止短前缀劫持长前缀（如 `gallery_` 劫持 `gallery_like_`），遍历时必须使用上文动态维护的 `SORTED_ROUTES`（按前缀长度降序排列）。
    ```python
    # 重构后的 handle_callback_query 核心逻辑
    
    @with_db_logging_context
    async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        
        # 身份强同步保留
        await permission_service.ensure_user(update)
        
        # 按前缀长度降序匹配，防止短前缀劫持长前缀
        for prefix in SORTED_ROUTES:
            if query.data.startswith(prefix):
                return await CALLBACK_ROUTES[prefix](update, context)
        
        # 兜底机制 (Fallback)
        logger.warning(f"Unmatched callback data: {query.data}")
        await safe_answer_query(query)
        await query.message.reply_text("该按钮已过期或系统升级中，请重新发送指令。")
    ```

### 2. 验证标准 (Validation)
1.  **静态扫描**：执行 `radon cc src/handlers/`，断言 `handle_callback_query` 的圈复杂度降至 **< 15**。
2.  **功能回归**：在测试服点击历史消息中的旧按钮（如图库点赞、旧版套餐购买），预期能够正常路由或被友好的兜底机制拦截，且不抛出 HTTP 500/Telegram `BadRequest` 异常。

### 3. 回滚策略 (Rollback)
保留旧版的 `callback_handler.py`（重命名为 `callback_handler_legacy.py`）。如果新路由上线后出现大面积按钮失效，直接在 `src/bot_prod.py` 的 `Application` 构建阶段将 Handler 指针切回老函数，然后重启容器。

---

## 任务 3.2: 全链路 TraceID 注入 (打通跨容器可观测性)

**背景**：当前架构下，一个生图请求会穿透 `TG-Bot (或 Web BFF)` -> `Redis 队列` -> `Central API` -> `ComfyUI Worker`。一旦 Worker 报错，由于缺少唯一的追踪 ID，很难在海量日志中拼凑出该请求在各个容器中的上下文。

### 1. 执行步骤 (Execution Steps)

*   **Step 1: 引入上下文变量与依赖 (ContextVars)**
    修改项目的 `requirements.txt`，引入 `asgi-correlation-id`。
    🚨 **规范对齐**：全局统一使用 `asgi-correlation-id` 提供的 `correlation_id` 这个 ContextVar。为遵循现有项目记忆规范，配置中间件时统一指定 `header_name="X-Trace-ID"`，而不是默认的 `X-Request-ID`。

*   **Step 2: 改造日志格式器 (Logger Formatter)**
    修改 `src/logger.py`，自定义 Formatter 或引入 `CorrelationIdFilter` 使其在每行日志的头部自动读取并打印 TraceID：
    ```python
    # 目标日志格式: 
    # [2026-04-26 10:00:00] [INFO] [TraceID: 550e8400-e29b...] User 123 requested...
    ```

*   **Step 3: Web BFF 与 TG Bot 流量入口注入**
    *   **Web API 端**：在 FastAPI 挂载 `CorrelationIdMiddleware(app, header_name="X-Trace-ID")`，它会自动从请求头读取或生成一个 UUID 并塞入 `correlation_id`。
    *   **TG Bot 端**：在 `bot_prod.py`（及 `bot_test.py`）中注册一个最高优先级的 `TypeHandler(Update, inject_trace_id)`（例如分配 `group=-1`），确保其在任何其他业务 Handler 之前执行，为每一次 Telegram Update 生成 UUID 并塞入 `correlation_id`。
        *   *机制确认*：PTB 对同一个 Update 的所有 groups 处理是在**同一个 asyncio.Task 内**按顺序执行的，因此 `group=-1` 设置的变量能完美被后续 `group=0` 的 Handler 继承，请求结束后自动释放。

*   **Step 4: 跨进程透传 (Redis Pub/Sub & Task Payload)**
    *红线注意*：`contextvars` 只能在单进程的协程间传递。当任务被下发时，必须将 TraceID 透传给下游。
    修改 `src/api_client.py`，让它优先从 `correlation_id` 提取并塞入 HTTP Header `X-Trace-ID` 中。
    ⚠️ **边界防范**：目前使用的 `create_background_task` 底层是 `asyncio.create_task(coro)`，它会自动浅拷贝并继承 `contextvars`，因此**异步任务间 TraceID 传递是安全的**。
    🚨 **修正漏洞**：避免在 `.get()` 为空时仅生成 UUID 却不写回上下文（会导致后续同请求内日志 TraceID 断裂）。
    ```python
    # src/api_client.py
    from asgi_correlation_id import correlation_id
    import uuid

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        trace_id = correlation_id.get()
        if not trace_id:
            trace_id = str(uuid.uuid4())
            correlation_id.set(trace_id)  # 🚨 必须写回 contextvars，防止日志链路断裂
            
        headers = kwargs.get("headers", {})
        headers.update(self.headers)
        headers["X-Trace-ID"] = trace_id
        kwargs["headers"] = headers
        # ... 继续发起 HTTP 请求
    ```

*   **Step 5: 下游节点继承 (API & Worker)**
    *   修改 `backend/app/main.py`（中控 API），**直接在顶层挂载 `CorrelationIdMiddleware(app, header_name="X-Trace-ID")`**，取代手动从请求头提取。然后在 `backend/app/queue_manager.py` 中，直接调用 `correlation_id.get()` 获取 TraceID，并连同任务参数一起通过 `queue_manager.enqueue_task()` 注入到 Redis 的 Payload 中。
    *   🚨 **写入位置规范**：将其放置在 Payload 顶层字段中，不要塞入 `params` 内部以免污染工作流：
        ```python
        # backend/app/queue_manager.py
        from asgi_correlation_id import correlation_id
        
        async def enqueue_task(self, task_type: TaskType, params: Dict[str, Any], priority: int = 0) -> str:
            trace_id = correlation_id.get() or ""
            # ...
            task_data = {
                "task_id": task_id,
                "type": task_type,
                # ... 其他原有字段
                "trace_id": trace_id  # 写入 Redis 顶层 Payload
            }
        ```
    *   修改 ComfyUI Worker 的接收脚本。当从 Redis 弹出一个任务时，读取 payload 顶层中的 `trace_id` 并强行设置到当前的 `correlation_id` 中。

### 2. 验证标准 (Validation)
1.  发起一次复杂的 LTX Video 生成任务。
2.  在宿主机执行日志联合查询：
    ```bash
    docker logs tg-bot | grep "<生成的 TraceID>"
    docker logs web-api | grep "<生成的 TraceID>"
    # 预期能在不同容器的日志中看到相同 UUID 串联起的完整生命周期（鉴权 -> 扣费 -> 排队 -> 生成 -> 结算）。
    ```

### 3. 回滚策略 (Rollback)
TraceID 注入属于纯附加型（Additive）功能，不破坏现有业务状态。若发现由于 `contextvars` 泄漏导致不同用户的日志串包，可通过环境变量（如 `ENABLE_TRACE_ID=false`）在代码中一键关闭日志 Formatter 的动态读取逻辑，平稳退化为无 TraceID 模式。
