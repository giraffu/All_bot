# 数据库连接池耗尽分析与解决方案报告

## 1. 问题根因分析 (Root Cause Analysis)

经过全盘代码分析，我们在代码库中发现了多个会导致数据库会话（DB Session）在长时间外部网络 I/O 期间被持续持有的位置。这正是偶发性触发 `idle_in_transaction_session_timeout`（事务空闲超时 60s）并导致连接被数据库主动掐断的根本原因。

**数据库当前健康状态验证**：经实时查询 `pg_stat_activity`，当前系统绝大多数连接处于健康的 `idle` 状态（约 60+ 个），仅有极个别处于 `idle in transaction`。这表明连接池并未出现永久性泄露，而是由于特定长耗时接口被并发调用时产生的**偶发性耗尽**。

### 1.1 Web API 层：生命周期绑定导致的长事务 (准确)
在 `src/web_api/dependencies.py` 中，数据库会话是通过 `yield session` 的方式注入的。这意味着**只要这个 HTTP 请求没结束，数据库连接就不会被归还到连接池**。
- **重灾区：发送大文件至 Bot 私聊**
  在 `src/web_api/routers/users.py` 的 `send_history_to_bot` 接口中，持有 DB 会话期间执行了：
  1. 生成 MinIO/R2 的预签名 URL。
  2. 使用 `httpx` 调用 Telegram Local API 发送大文件（甚至设置了长达 30 秒的 timeout）。
  **缺陷**：在这长达数秒甚至数十秒的网络传输期间，哪怕并没有执行任何 SQL 语句，该事务依旧处于 `idle in transaction` 状态，死死霸占着连接。

### 1.2 Web API 层：致命隐患 - SSE 长连接霸占事务 (新增/核心元凶)
原排查遗漏了代码中隐藏最深、破坏力最大的一个“重灾区”：**流式响应（SSE, Server-Sent Events）**。
在 `src/web_api/routers/tasks.py` 的 `task_status_stream` 路由中：
1. 该路由依赖了 `Depends(get_current_user)`，而后者又依赖了 `Depends(get_db)`（包含 `yield session`）。
2. FastAPI/Starlette 的生命周期机制规定：**只有在整个 HTTP Response 传输彻底结束后，才会执行 `yield` 之后的释放逻辑**。
3. 由于这是 SSE 长连接，前端等待图片/视频生成的过程可能长达 **1~3 分钟**。
**致命后果**：每一个在 Web 前端等待出图的用户，都会在后台死死锁住一个 `idle in transaction` 的数据库连接长达数分钟。如果同时有几十个用户在线等图，数据库连接池瞬间就会被榨干。

### 1.3 Bot 任务分发与处理层 (验证为误报，当前设计安全)
最初怀疑 `src/services/task_service.py` 中的 `_monitor_task_progress` 或大文件上传下载时会卡住数据库连接。
**实际代码验证**：`task_service.py` 是 Telegram Bot 的 Handler，它**并没有**在函数级注入或持有任何全局的 `AsyncSession`。代码中调用的 `user_logger.save_output_image` (上传 MinIO) 是纯粹的文件 I/O；而落库操作 `user_logger.log_task` 和计费操作 `check_and_deduct_credits` 都是在其内部通过 `async with AsyncSessionLocal() as session:` 开启的极其短暂的局部连接，执行完 SQL 瞬间就 `commit` 并释放了。**因此，Bot 层不存在文件流转阻塞数据库连接池的问题，此部分无需重构。**

### 1.4 Dashboard 系统监控接口 (准确)
- **批量外部网络轮询**：
  在 `dashboard/backend/routers/system.py` 的 `get_active_bot_tasks` 路由中，持有着 `db: AsyncSession`，接着发起 `httpx` 遍历查询所有的 ComfyUI worker 节点来同步任务进度。
  **缺陷**：如果存在 10 个活跃任务，就需要发起 10 次外部网络请求。这段时间内的网络延迟叠加起来，极易让数据库连接超时。

---

## 2. 解决方案与重构建议 (Solutions & Refactoring Plan)

解决此类问题的核心原则是：**“快进快出”——把慢速的网络 I/O (MinIO / LLM / ComfyUI / Telegram API) 踢出数据库事务的生命周期之外。**

### 2.1 针对 SSE 长连接 (task_status_stream) 的紧急改造 (高优)
**坚决不能**在长轮询或流式响应的路由签名中使用 `Depends(get_db)` 相关的依赖。
**重构示例**：
```python
@router.get("/{task_id}/stream")
async def task_status_stream(task_id: str, request: Request):
    # 1. 手动从 request 提取 Token
    token = request.query_params.get("token")
    
    # 2. 在内部使用临时短会话进行鉴权，鉴权完毕立马释放 DB 连接
    async with AsyncSessionLocal() as session:
        current_user = await verify_and_get_user(session, token)
        
    # 3. 此时 DB 已经安全归还连接池，接下来再安全地建立长达数分钟的 SSE 长连接
    async def event_generator():
        # ... 原有的业务逻辑 (内部如果还需要查库，再次使用 async with AsyncSessionLocal() 开启短连接)
        pass
        
    return EventSourceResponse(event_generator())
```

### 2.2 针对 FastAPI 路由层 (Web API)
不要让长耗时的路由直接依赖 `Depends(get_db)` 贯穿全场。
**重构示例 (以 `send_history_to_bot` 为例):**
```python
# 错误的做法：
@router.post("/send-to-bot")
async def send_history_to_bot(request: Request, db: AsyncSession = Depends(get_db)):
    history = await db.execute(...) # 查询数据
    # 漫长的外部调用，此时 db 一直被持有
    await httpx.post("https://telegram.api/...", timeout=30)
    return {"status": "ok"}

# 推荐的做法（拆分 DB 事务）：
@router.post("/send-to-bot")
async def send_history_to_bot(request: Request):
    # 1. 开启短暂的局部会话，仅用于查询
    async with AsyncSessionLocal() as session:
        history = await get_history(session, ...)
    # 离开 with 块，session 自动归还！
    
    # 2. 执行漫长的外部网络 I/O，此时不再占用数据库连接
    await httpx.post("https://telegram.api/...", timeout=30)
    
    # 3. 如果需要更新状态，再次开启一个短连接
    async with AsyncSessionLocal() as session:
        await update_history_status(session, ...)
        await session.commit()
```

### 2.3 针对 Dashboard 与后台系统
如果存在批量查外部状态的需求（如 Dashboard `get_active_bot_tasks`），先一次性从数据库查出所需列表，**释放会话或离开 `with` 块**，然后异步并发查外部 API，最后如果需要写回缓存或数据库，再新开一个极短的连接写入。

### 2.4 全局最佳实践
- 继续保持 `ALTER SYSTEM SET idle_in_transaction_session_timeout = '60000';` 配置开启。这属于“熔断保护”，宁可单个请求抛出 500 错误，也决不能让连接池耗尽导致全站瘫痪。
- 维持当前 Bot 层 (`task_service.py`) 局部申请 `AsyncSession` 并快进快出的良好设计。
