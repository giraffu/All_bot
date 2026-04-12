# 代码审查总结 (Code Review Summary)
**审查日期**: 2026-04-12

通过对项目的架构、数据流、核心服务及操作逻辑进行排查，发现了 3 个需要修复的关键问题，以及多个优化建议。由于您要求不直接修改代码，以下仅提供排查结果与优化方案：

## 🔴 关键问题 (Critical - Must Fix)

### 1. 支付回调并发导致的重复发货漏洞 (Race Condition)
FilePath: `src/services/payment_fulfillment_service.py` line 21
```python
order_res = await session.execute(select(Order).where(Order.order_id == out_trade_no))
order = order_res.scalar_one_or_none()
```
#### Explanation
**架构与数据流问题**：在统一发货逻辑 `fulfill_order` 中，读取订单状态和更新用户灵石之间没有加互斥锁。如果第三方支付网关（如易支付、Stars 回调等）由于网络波动并发发送了两个相同的 Webhook 回调，两个请求可能同时读取到 `order.status != "SUCCESS"`，从而导致给用户重复增加灵石（Double-Spending）。
#### Suggested Fix
1. 引入数据库行级悲观锁。在查询订单时使用 `with_for_update()`，例如 `select(Order).where(...).with_for_update()`，确保同一订单的并发回调必须排队执行。
2. 或使用原子更新语句：`update(Order).where(Order.order_id == id, Order.status == 'PENDING').values(status='SUCCESS')`，通过受影响的行数来判断是否需要继续发货逻辑。

### 2. 审计日志与资产更新脱离同一数据库事务
FilePath: `src/services/payment_fulfillment_service.py` line 112-115
```python
await session.commit()
# 使用统一的 LogService 记录流水...
await LogService.log_action(...)
```
#### Explanation
**数据流问题**：根据 AGENTS.md 的红线要求，灵石增减必须同步记录 `user_logs` 流水以防对账错误。当前代码在 `session.commit()` 提交了灵石与身份更新后，才去调用 `LogService.log_action`。如果程序在两者之间崩溃（如容器重启），用户的灵石增加了，但流水却没有记录，破坏了严格的数据流审计。
#### Suggested Fix
1. 优化 `LogService.log_action`，使其支持接收外部传入的 `session` 实例。
2. 将流水插入逻辑包含在 `order.status` 和 `user.credits` 更新的同一个事务中，最后统一 `await session.commit()`。

### 3. MinIO 文件下载同步阻塞 FastAPI 异步事件循环
FilePath: `backend/app/main.py` line 299
```python
minio_client.fget_object(
    settings.minio_result_bucket,
    result_path,
    temp_path
)
```
#### Explanation
**架构与性能问题**：`/image/{task_id}` 和 `/video/{task_id}` 路由是 `async def` 定义的异步接口，但内部调用的 `minio_client.fget_object` 是一个同步的阻塞 I/O 操作。在高并发或大文件（如长视频）下载时，会完全阻塞 FastAPI 的 asyncio 事件循环，导致中控 API 在此时无法响应任何其他网络请求（包括心跳和新建任务）。
#### Suggested Fix
1. 使用 `asyncio.to_thread(minio_client.fget_object, ...)` 将同步阻塞调用放入后台线程池执行。
2. **（更优架构方案）** API 不直接代理文件流，而是通过 `minio_client.presigned_get_object` 生成一个具有时效性的 Presigned URL，并向客户端返回 `HTTP 302 重定向`，将大文件的下载流量完全从 API 节点剥离。

---

## 🟡 优化建议 (Suggestions - Should Consider)

### 1. Telegram 消息通知可能导致 Webhook 响应超时
FilePath: `src/services/payment_fulfillment_service.py` line 161
```python
await http_session.post(telegram_api_url, json=payload)
```
#### Explanation
**操作逻辑问题**：在处理支付网关的回调请求结束时，程序同步等待 Telegram API 的消息发送响应。如果 Telegram 官方 API 响应缓慢或超时，会导致您的 Webhook 接口无法及时给支付网关返回 `200 OK`，进而触发支付网关的自动重试机制。
#### Suggested Fix
1. 使用 `asyncio.create_task()` 将 Telegram 消息通知放入后台异步执行，即发即弃 (Fire-and-forget)，让 Webhook 接口能立刻结束并响应支付网关。

### 2. Bot 内存泄漏风险 (bot_data 无限增长)
FilePath: `src/services/task_service.py` line 904
```python
context.bot_data[f"msg_meta_{sent_msg.message_id}"] = { ... }
```
#### Explanation
**架构问题**：为了支持用户在出图后点击内联键盘进行评分（👍/👎），代码将任务的元数据永久存储在了 `context.bot_data`（内存字典）中。随着任务的不断生成，这个字典会越来越大且没有任何清理机制，长期运行最终会导致 Bot 容器 OOM 崩溃。
#### Suggested Fix
1. 将 `msg_meta_*` 数据存储到 Redis 中，并为其设置一个合理的 TTL（例如 7 天过期），彻底消除内存泄漏风险。

### 3. 并发锁校验逻辑重复且存在泄漏风险
FilePath: `src/services/task_service.py` line 64
```python
active_tasks = await redis_client.increment_user_concurrency(user_id)
if active_tasks > MAX_CONCURRENT_TASKS:
    await redis_client.decrement_user_concurrency(user_id)
    return None, None
```
#### Explanation
**代码质量问题**：这段限制单用户并发任务数量的代码在 `task_service.py` 中被硬编码复制粘贴了 5 次以上。如果在 `increment` 之后但在任务执行的 `try...finally` 块之前发生意外异常，该用户的并发锁将无法释放，导致被永久“卡死”。
#### Suggested Fix
1. 将该逻辑抽象为一个 Python 异步上下文管理器 (Async Context Manager) 或装饰器，例如 `async with user_concurrency_lock(user_id):`，将自增、上限校验和必定释放的逻辑集中管理。

### 4. 异常情况下的临时文件泄漏
FilePath: `backend/app/main.py` line 306
```python
except Exception as e:
    logger.error(f"MinIO download failed: {e}")
    raise HTTPException(status_code=404, detail="File not found in storage")
```
#### Explanation
**操作逻辑问题**：在下载 MinIO 文件的接口中，代码提前通过 `tempfile.mkstemp()` 创建了临时文件。如果随后的 `fget_object` 发生异常抛出，由于未走到 `BackgroundTasks().add_task(os.remove)` 这一步，临时文件将永远不会被删除，随着时间推移会塞满宿主机的 `/tmp` 目录。
#### Suggested Fix
1. 将文件删除操作包裹在 `try...finally` 块中，或者在 `except` 分支中主动调用 `os.remove(temp_path)` 进行防御性清理。

---

## 🟢 细节建议 (Nits - Optional)

### 1. Redis 连接池的频繁创建与销毁
FilePath: `backend/app/main.py` line 43
#### Explanation
`check_zombie_tasks_loop` 作为一个后台常驻的死循环协程，每 60 秒就会执行一次 `Redis.from_url` 并随后 `await redis.close()`。这种频繁建立和销毁 TCP 连接池的做法增加了不必要的网络开销。
#### Suggested Fix
- 复用系统全局生命周期的 Redis 连接池实例，而不是在 while 循环内部反复创建。

### 2. 订单表缺乏货币单位标识
FilePath: `src/database/models.py` line 123
#### Explanation
根据记忆库中的规则说明，系统目前混用了 TON、Stars、RMB 等多种支付方式，但 `Order` 表中的 `final_price` 字段仅为一个 `DECIMAL` 数值。1.99 RMB 和 1.99 TON 在数据库中缺乏区分维度，会导致 Dashboard 后台在统计财务报表时将不同法币/加密货币混合累加，造成数据污染。
#### Suggested Fix
- 在 `Order` 表中新增 `currency` 字段（如 `RMB`, `TON`, `STARS`），以便后续做汇率折算与分类对账。

---

## ✅ 值得肯定的设计 (What's Good)

- **分布式解耦架构**：将 Telegram Bot、中控 API 与底层的 ComfyUI Workers 通过 Redis 队列完全解耦，系统具备了极佳的横向扩展能力和故障隔离性。
- **引用传递机制**：通过 MinIO 的 `Object Key` 代替直接在微服务内部网络传输媒体流（特别是视频），极大地节省了 API 节点的内存和带宽开销。
- **容错与幂等意识**：在 `payment_fulfillment_service.py` 中虽然缺乏数据库锁，但预先设计了 `if order.status == "SUCCESS": return True` 的幂等校验机制；`task_service.py` 中也广泛使用了 `finally` 块来保证状态复位，整体展现了良好的防御性编程习惯。