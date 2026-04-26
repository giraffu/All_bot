# 架构重构方案：落实单一职责原则 (SRP) 及 Core 层演进

在对项目的全局代码静态分析中，我们发现以下具体的路由文件存在大量的“上帝函数”（God Functions）：

- **`backend/app/main.py`**: `create_t2i_pornmaster_turbo_task` (圈复杂度: 12)
- **`src/web_api/routers/tasks.py`**: `create_generation_task` (圈复杂度高达 28，包含计费、并发锁、重试和后台任务等逻辑)、`monitor_task_and_release_lock`
- **`src/web_api/routers/gallery.py`**: `get_gallery_posts` (圈复杂度: 24)、`submit_to_gallery` (圈复杂度: 21)
- **`src/web_api/routers/auth.py`**: `login_telegram` (圈复杂度: 17)

这些路由函数往往同时包含了：HTTP请求验证、并发锁管理、扣费逻辑、数据库直接操作、Redis队列交互以及长轮询同步等待等多种逻辑。

这种“大杂烩”式的设计严重违反了**单一职责原则 (Single Responsibility Principle, SRP)**，会导致代码复用率低、测试困难、耦合度过高等问题。

结合当前代码库实际现状（已经存在 `src/core/` 架构演进，且 `src/services/task_service.py` 实际上是重度耦合 Telegram Bot 的表示层），我们提出以下“贴合现状”的重构方案。

---

## 1. 目标分层架构 (Core-Driven Architecture)

为了彻底解耦并顺应现有的架构演进，我们建议废弃传统的 Service/Repository 三层架构思路，全面拥抱 **核心领域层 (Core Layer)** 架构：

- **Layer 1: Presentation / Router 层** (`routers/` 或 `handlers/`)
  - **职责**：仅负责外部请求/响应映射。
  - **行为**：
    - `web_api/routers/`: 接收 Web HTTP 请求（解析 JSON/Query），处理 SSE (Server-Sent Events) 推送，返回 FastAPI 响应。
    - `handlers/` (原 `services/task_service.py`): 负责 Telegram Bot 的 Update 解析、消息发送、InlineKeyboard 构建。
- **Layer 2: Core Facade 层** (`src/core/`)
  - **职责**：作为核心业务的门面（Facade），负责所有纯粹的业务逻辑编排。
  - **行为**：包含核心的领域规则（如：调用 `billing_core` 检查余额和并发锁，计算动态成本，调用底层入队接口）。完全不知道 HTTP 或 Telegram Bot 的存在。
- **Layer 3: Data Access / Integration 层** (`database/` 和底层抽象)
  - **职责**：负责与底层存储的数据交互。
  - **行为**：直接在 `core` 层中使用 SQLAlchemy (如 `AsyncSessionLocal`) 进行短生命周期 CRUD。**🚨 警告：对于包含外部副作用（如 Redis 入队）的核心业务，严禁使用 Router 层注入的全局 Session（UoW 模式），必须由 Core 层内部自主掌控独立的短事务提交，防止 FastAPI 自动回滚引发数据不一致。**

---

## 2. 实施方案与代码示例

### 2.1 现状反模式示例 (Before)
在目前的 `src/web_api/routers/tasks.py` 中，`create_generation_task` 包含了动态成本计算、并发锁和扣费逻辑：

```python
# 🚨 反模式：Controller 里堆积了成本计算、并发控制等所有逻辑
@router.post("/generate")
async def create_generation_task(req: TaskGenerateRequest, ...):
    # 1. 业务计算 (不该在路由层)
    cost = calculate_task_cost(req.task_type, req.inputs)
    
    # 2. 并发与计费
    can_run, lock_err = await check_concurrency_lock(current_user.id)
    if not can_run: raise HTTPException(status_code=429)
    success, billing_err = await check_and_deduct_credits(current_user.id, cost, ...)
    
    # 3. 提交任务
    success, msg, task_id, ... = await core_submit_generation_task(...)
```

### 2.2 目标重构示例 (After)

重构后，我们将职责完全下沉到 `core` 层，同时**严守事务防线、优先级计算与底层路由分发逻辑**。

**Step 1: Core 层（`src/core/task_core.py`）**
将编排封装进门面函数，通过依赖注入传入 Session，并完善异常回滚与特殊任务的分发分支。

```python
async def process_and_submit_task(
    # 🚨 移除外层注入的 session，防止 Router 层自动 rollback 导致双重退款漏洞
    user_id: int, 
    username: str,
    task_type: str, 
    inputs: dict,
    base_priority: int = 0
) -> dict:
    # 1. 成本计算下沉至 core
    cost = calculate_task_cost(task_type, inputs)
    is_video = task_type in ["face_video", "txt2video", "video_lora", "custom_video", "perfect_video_insert", "doggy_style", "blowjob", "undress_tongue", "closeup_blowjob", "ltx_video"]
    
    # 2. 并发与计费编排
    can_run, err = await check_concurrency_lock(user_id)
    if not can_run: raise ConcurrencyLimitError(err)
    
    task_submitted = False
    credits_deducted = False
    
    try:
        # 扣费本身自带独立短事务并立即 commit
        success, err = await check_and_deduct_credits(user_id, cost, task_type, username)
        if not success:
            raise InsufficientCreditsError(err)
            
        credits_deducted = True
            
        # 🚨 必须从这里（扣费成功的下一行）立刻开启内层 try 块！
        # 防止优先级计算或参数组装报错，导致跳过退款逻辑（永久吞费 Bug）
        try:
            # 3. 身份优先级计算 (保留修仙身份特权)
            priority, _, _ = await get_user_priority_and_identity(user_id)
            final_priority = min(base_priority + priority, 100)
            
            # 4. 核心提交与路由分发 (保留特定任务的分支处理)
            task_id = None
            registry_task_id = None
            saved_inputs = [] # 🚨 必须保留 saved_inputs，用于后台任务写入 History
            
            if task_type == "face_swap":
                success, msg, task_id, saved_inputs, registry_task_id = await core_submit_generation_task(..., priority=final_priority)
            elif task_type == "face_video":
                success, msg, task_id, saved_face_img, saved_vid, registry_task_id = await core_submit_face_video(..., priority=final_priority)
                if success: saved_inputs = [saved_face_img, saved_vid]
            else:
                success, msg, task_id, saved_inputs, registry_task_id = await core_submit_generation_task(..., priority=final_priority)
                
            if not success or not task_id:
                raise CoreDomainError(msg)
                
            # 🚨 5. 放弃脆弱的 BackgroundTasks，直接在 Core 层作为独立协程发起，防御 CancelledError 与 Router 层验证崩溃
            import asyncio
            asyncio.create_task(
                monitor_task_and_release_lock(
                    task_id, user_id, username, registry_task_id,
                    is_video, task_type, inputs.get("prompt", ""), saved_inputs
                )
            )
            task_submitted = True
                
            return {
                "task_id": task_id, 
                "registry_task_id": registry_task_id, 
                "cost": cost,
                "saved_inputs": saved_inputs
            }
            
        except Exception as e:
            # Saga 模式（补偿事务）：异常被捕获后进入 finally 退款
            raise CoreDomainError(f"任务下发失败: {str(e)}")
            
    finally:
        # 🚨 致命缺陷防范：必须使用 finally，防止 FastAPI 断连抛出 asyncio.CancelledError 导致锁永久泄漏
        if credits_deducted and not task_submitted:
            import asyncio
            # 必须用 create_task 屏蔽当前协程的 Cancelled 状态，确保退款和解锁成功执行
            asyncio.create_task(refund_credits(user_id, cost, f"refund_{task_type}", username))
            asyncio.create_task(release_concurrency_lock(user_id))
        elif not credits_deducted:
            # 扣费没成功，只需释放并发锁
            import asyncio
            asyncio.create_task(release_concurrency_lock(user_id))
```

**Step 2: Router/Controller 层（`src/web_api/routers/tasks.py`）**
此时路由将变得极其干净，只做 HTTP 边界的事情和透传。

```python
@router.post("/generate")
async def create_generation_task(
    req: TaskGenerateRequest, 
    current_user: User = Depends(get_current_user)
):
    try:
        # 路由层只负责调用 Core Facade
        result = await process_and_submit_task(
            current_user.id, current_user.username, req.task_type, req.inputs, req.priority
        )
        
        return TaskGenerateResponse(task_id=result["task_id"], cost=result["cost"], status="pending")
    except CoreDomainError as e:
        # 全局异常拦截或在此处翻译
        raise HTTPException(status_code=400, detail=str(e))
```

---

## 3. 隐藏的重灾区与防坑指南 (Hidden Issues & Pitfalls)

结合实际代码细节，在正式实施重构前，必须注意以下容易遗漏的深层耦合点：

### 3.1 `tasks.py` 中的跨层污染与业务补丁
- **Telegram Bot 依赖污染**：Web API 路由中直接引用了 `src.handlers.fsm.edit_image_fsm` 中的 Lora 默认强度配置。这打破了表现层的物理隔离。必须将模型配置抽取到 `src/constants.py` 或新建的 `src/core/model_core.py` 中，供双端复用。
- **硬编码的 Prompt 业务逻辑**：对特定模型（如 `qwen/adjust_pussy_anus.safetensors`）自动追加 Prompt 的逻辑属于核心领域规则，不应留在路由层，必须随计算逻辑下沉至 `task_core.py`。
- **后台任务直连数据库**：`monitor_task_and_release_lock` 后台任务包含了直接操作 `History` 表及调用 `UserLogger` 的逻辑，应将其封装为 `task_core.py` 中的核心回调门面方法。

### 3.2 `auth.py` 的安全与权限规则硬编码
- **双重 HMAC 签名解析**：路由中混杂了 Widget (`hash`) 和 WebApp (`initData`) 两种不同 Telegram 签名解包校验算法，应提取到 `src/core/auth_core.py` 或统一的鉴权模块中。
- **修仙等级白名单硬编码**：路由直接写死了身份（`["内门弟子", ...]`）和境界（`["金丹期", ...]`）数组。这属于核心业务鉴权规则，应下沉至 `permission_service.py` 或 `user_core.py`。

### 3.3 `gallery.py` 的复杂业务规则提取
- **逻辑过度堆叠**：`submit_to_gallery` 不仅处理 HTTP 响应，还包含了 Redis 发帖防刷频率校验、防盗发校验（`allow_contribute` 判断），以及手写正则解析 Prompt 提取 `[模型: xxx]` 自动生成 Tags 的逻辑。这些必须全部下沉至新建的 `src/core/gallery_core.py`。
- **R2 异步上传的响应优化**：`submit_to_gallery` 在最后执行了 `await storage.async_copy_to_r2`。虽然目前代码已被妥善包裹在 `try...except` 中且在 `session.commit()` 之后执行（**不存在数据库事务回滚风险**），但直接在 Router 层 `await` 依然会阻塞 HTTP 响应，增加前端等待时间。
  - **优化方案**：在重构到 `gallery_core.py` 时，必须将 R2 复制操作挂载到 FastAPI 的 `BackgroundTasks` 或放入独立队列中，实现 API 的毫秒级返回，前端配合 404 轮询机制平滑体验。

### 3.4 `backend/app/main.py` 的长轮询与链路追踪（架构升级）
- **同步阻塞的死循环问题**：`create_t2i_pornmaster_turbo_task` 中包含长达 60 秒的 `while asyncio.sleep(1)` 轮询等待逻辑，严重消耗 FastAPI 的协程资源。
  - **优化方案与死锁竞态防范**：重构为基于 Redis Pub/Sub 的监听时（监听 `comfy:task_events:{task_id}`），**必须严格遵循安全时序**，并且**必须由外部预先生成 task_id 并传入 `enqueue_task`**。
    - **当前代码漏洞**：目前 `QueueManager.enqueue_task` 内部自己生成了 UUID 并直接入队。如果 Central API 调用它入队，等拿到 `task_id` 再去订阅频道，此时 Worker 可能已经处理完并发布了完成消息，Central API 将永远错过该消息导致死锁超时。
    - **修复要求**：修改 `QueueManager.enqueue_task` 签名支持传入 `task_id: str = None`。在 Central API 中必须先生成 `task_id`，然后：`1. 订阅频道 -> 2. 入队 -> 3. 主动查询一次当前状态 (防遗漏) -> 4. 若未完成则 await wait_for 监听`。
- **防丢追踪 (TraceID)**：Central API 依赖 `X-Trace-ID` 标头进行端到端追踪。目前的 `QueueManager.enqueue_task` 签名并未直接传递 TraceID，务必确保在入队前将 TraceID 显式注入到 `params` 字典（Task payload）中持久化到 Redis，并在后台任务取出时将其手动注入到 Logger 上下文中，防止分布式日志断链。

### 3.5 Bot 端 FSM 状态机同步接入
- **架构闭环**：重构不能仅停留在 Web API 层面。目前 Telegram Bot 的交互逻辑（位于 `src/handlers/fsm/`）和 Web API 都在各自直接调用底层。在建立 `task_core.py` 门面后，**必须强制要求 Bot 端的 FSM 回调（如 `edit_image_fsm.py`）也改用这个 Core 接口**，否则扣费、并发锁校验等规则仍会多处维护。

---

## 4. 重构路径规划 (Action Plan)

为了不影响现有业务，建议采取“绞杀者无花果模式 (Strangler Fig Pattern)”进行渐进式重构：

1. **正本清源 (明确现有边界)**：
   - 将现有的 `src/services/task_service.py` 明确为 **Bot 专属表示层**。可以考虑重命名为 `bot_task_handler.py` 或增加强注释，严禁 Web API 调用其中的逻辑以防交叉污染。
2. **核心逻辑下沉 (Core Facade 强化)**：
   - 针对 `src/web_api/routers/tasks.py`，将其中的 `calculate_task_cost`（动态成本计算）、特定 Prompt 业务补丁、以及杂糅的编排逻辑，下沉至 `src/core/task_core.py` 中，对外暴露统一的 Facade 接口。
   - 新建 `src/core/gallery_core.py` 和 `src/core/auth_core.py`，承接标签解析、防刷校验和签名验证等逻辑。
3. **统一异常处理与事务 (Exception Handling & Transactions)**：
   - 确立统一的事务边界（如通过 Depends 注入 Session），理清 `rollback` 和手动 `refund` 的互斥关系。
   - 在 Core 层定义自定义异常类（如 `InsufficientBalanceError`, `ConcurrencyLimitError`）。
   - 在 FastAPI 应用层配置全局的 `exception_handler`，自动将领域异常转化为 400/401/402/429 状态码。
4. **Central API 的 Pub/Sub 改造**：
   - 针对 `backend/app/main.py`（连接 ComfyUI 的中控层），将 `while` 死循环重构为基于 Redis Pub/Sub 的被动事件监听，提升并发承载力。
5. **Bot 端 FSM 接入**：
   - 逐步将 Telegram Bot 的各个 FSM 迁移到调用新的 Core 门面，实现双端逻辑大一统。

## 5. 预期收益
- **代码复杂度降低**：单个路由函数的圈复杂度预期将从 >20 降低到 5 以下。
- **消除交叉污染**：明确 Telegram Bot (Handler) 和 Web API (Router) 的边界，它们共同调用纯净的 `src/core/` 层。
- **心智负担减轻**：开发者在修改计费规则、成本计算或发帖规则时，只需关注 `core` 层，不再需要分别修改 Bot Handler 和 Web API Router。
- **中控性能飙升**：消除 `while` 轮询后，Central API 处理同步任务的并发能力将呈指数级提升。
- **消除锁泄漏与死锁风险**：通过在 Core 层原子化挂载 `BackgroundTasks`，以及由外部预先生成 `task_id` 的重构，彻底堵住隐患。

## 6. 落地细节与防坑建议 (Execution Details & Pitfalls)

在正式实施重构前，必须严格遵守以下执行细节，否则会引发严重的线上故障：

1. **🚨 致命缺陷防范：分布式事务的不一致性、异常作用域与锁泄漏**：
   - **客户端断连导致的 `CancelledError` 穿透漏洞 (永久锁死+吞费)**：这是 FastAPI 中最容易被忽视的黑洞！如果用户在请求未完成时断开连接（关闭页面/网络波动），FastAPI 会抛出 `asyncio.CancelledError`。该异常在 Python 3.8+ 继承自 `BaseException`，会**直接穿透**常规的 `except Exception:` 块。若没用 `finally` 兜底，并发锁将永久泄漏，灵石也无法退还；且在 `finally` 中执行异步退款时，必须使用 `asyncio.create_task` 将其放入独立的事件循环上下文中，否则会被当前的 Cancelled 状态瞬间中断！
     - **红线**：扣费后的任何兜底释放锁或退款逻辑，必须放在 `finally` 块中，并用 `asyncio.create_task` 屏蔽取消异常。
   - **双重退款漏洞（白嫖）**：如果在使用 Saga 模式手动 `refund_credits()` 的同时，还在路由层注入了 `Depends(get_db)` 统管全局事务（UoW）。当外部调用抛出异常时，Router 会自动 `rollback()` 撤销之前的扣费，而 `except`/`finally` 块又执行了 `refund_credits()`，结果就是**用户余额不减反增**。
     - **红线**：严禁在带有外部副作用的 Facade 中透传 Router 层的 Session。扣费操作必须在其内部自带的独立短事务中立即 Commit。
   - **异常作用域漏洞（永久吞费）**：如果在 `check_and_deduct_credits` 执行成功后，没有**立刻**开启内层 `try...except/finally` 状态机进行保护，那么两者之间的任何代码（如参数解析、优先级查询等）一旦抛出异常，就会跳过退款逻辑。用户的灵石被扣了，任务没下发，且永远得不到补偿。
     - **红线**：用于 Saga 退款补偿的状态标志位（如 `credits_deducted = True`）必须紧贴在扣费成功的下一行设置，确保 `finally` 能精准感知！

2. **⚠️ 易踩坑点：后台任务 (BackgroundTasks) 的原子性盲区与传参失误**：
   - **`BackgroundTasks` 的脆弱性**：在 FastAPI 中，若 Router 结尾发生异常或 Pydantic 校验响应体失败导致 500 错误，`BackgroundTasks` 将**直接被丢弃不执行**！这会导致已经下发给 ComfyUI 的任务无法被监控，用户的并发锁永久泄漏。
     - **方案**：对于 `monitor_task_and_release_lock` 这种极其关键的清理任务，最稳妥的做法是不依赖生命周期脆弱的 `BackgroundTasks`，而是直接在 Core 层通过 `asyncio.create_task(monitor_task_and_release_lock(...))` 将其作为一个独立的守护协程运行。
   - **传参顺序错位Bug**：调用 `monitor_task_and_release_lock` 时，原代码第 5 个参数是 `is_video: bool = False`。重构时切忌盲目传参，若将 `task_type`（字符串）传给它，会导致监控任务内部在区分视频和图片扩展名时发生类型崩溃。
   - **退款流水命名规范**：`refund_credits` 里的 `task_type` 字段必须加上 `refund_` 前缀（如 `f"refund_{task_type}"`）。如果直接传 `task_type`，会导致退款和扣费流水的类型字段一模一样，破坏后台对账系统。
   - **Session 生命周期**：作为守护协程运行的 `monitor_task_and_release_lock`，**绝对不能使用 Router 层或 Core 层传递过来的 `session`**。协程执行时 HTTP 响应已结束，原 session 已被关闭，会抛出 `DetachedInstanceError`。必须在方法内部重新 `async with AsyncSessionLocal() as session:`。

3. **TraceID 跨进程的真正透传**：
   - 代码中目前已在 `api_client.py` 和 `backend/app/main.py` 通过 `CorrelationIdMiddleware` 实现了 HTTP 标头层面的传递。必须确保在入队前将 TraceID 作为 `Task payload` 显式注入到 `params` 字典中持久化到 Redis，并在后台任务取出时将其手动注入到 Logger 上下文中，否则日志链路依然会断裂。