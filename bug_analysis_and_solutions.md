# 系统运行日志 Bug 分析与解决方案

在近期的日志排查中，主要发现了以下四个核心问题及隐患。

## 1. 数据库连接池耗尽与死锁 (Deadlock & Pool Exhaustion)
**现象与日志特征**：
- `sqlalchemy.exc.DBAPIError: <class 'asyncpg.exceptions.DeadlockDetectedError'>: deadlock detected`
- `⚠️ Channel check failed: QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00`

**问题分析**：
- **死锁 (Deadlock)**：并发的数据库事务试图以不同的顺序获取相同的资源锁，导致互相等待并最终触发死锁报错。
- **连接池耗尽 (QueuePool limit reached)**：由于存在慢查询、死锁或未正确提交/回滚的长事务，导致 SQLAlchemy 配置的连接池（默认 pool_size=5, max_overflow=10）被占满。后续请求在等待 30 秒后全部超时，这会导致 Bot 整体响应变慢甚至局部卡死。

**解决方案**：
1. **排查长事务**：缩短数据库事务的作用域，仅在必要时持有 `session`。确保使用 `try...except...finally` 正确执行 `session.rollback()` 和资源释放。
2. **一致的加锁顺序**：排查并发更新逻辑（如扣除积分、更新任务状态的并发场景），确保总是以相同的顺序获取行锁。
3. **调整连接池参数**：若当前并发量确实较大且为合理请求，可在 SQLAlchemy 引擎初始化时适当调大 `pool_size` 和 `max_overflow`。

**代码审查结论**：文档描述无误，数据库连接池的配置（`DB_POOL_SIZE` 和 `DB_MAX_OVERFLOW`）已在 `src/database/core.py` 中正确落实，并支持通过环境变量动态调整。

---

## 2. ComfyUI 临时文件获取失败 (ComfyUI 404 Error)
**现象与日志特征**：
- `ERROR - Error in process_generation_task for user 6763305140: Result processing failed: Client error '404 Not Found' for url 'http://192.168.1.226:8188/view?filename=ComfyUI_temp_qytex_00001_.png...'`

**问题分析**：
- 任务完成时，Bot 尝试从内部局域网的 ComfyUI 节点（192.168.1.226）下载临时生成的图片结果，但服务端返回了 404。这可能是因为出图节点异常失败，或者临时文件由于超时已被 ComfyUI 的清理机制删除。

**解决方案**：
1. **增加重试与状态校验**：在拉取图片前，先检查工作流实际执行状态，或对下载操作增加适度的重试机制。
2. **优雅的错误与补偿处理**：捕获该 404 异常，避免直接抛出 `RuntimeError` 导致任务链断裂。通过兜底逻辑向用户发送友好的提示（例如：“图片获取超时或生成异常，已为您返还灵石”），并调用退款/补偿接口。

**代码审查结论与后续行动**：
- **已落实（补偿兜底）**：在核心生成逻辑中已正确捕获异常、发起退款并给用户发送友好提示。
- **未落实（重试失效）**：代码在拉取文件处加了 `@async_retry` 装饰器，但当前 404 抛出的是 `RuntimeError`，不在重试白名单内，因此重试机制实际并未生效。
- **当前状态**：**[暂时不解决 / Pending]** 记录在案，后续根据实际业务情况决定是否专项优化重试逻辑。

---

## 3. Telegram 消息超长导致发送失败 (Message Too Long)
**现象与日志特征**：
- `telegram.error.BadRequest: Message is too long`

**问题分析**：
- Bot 尝试向用户发送或编辑的单条文本消息超过了 Telegram API 的限制（4096 个字符）。这通常发生在回显超长 Prompt、返回过长的报错堆栈或未做分页的长列表中。如果不处理，对应的用户交互会直接失效断联。

**解决方案**：
1. **文本截断**：在发送消息前对文本长度进行检测，若超过 4000 字符则进行截断，例如尾部拼接 `...`。
2. **分页或转文件发送**：如果是必须完整展示的内容（如日志或长文），可以将其转换为 `.txt` 文件作为 Document 发送给用户，或者在 UI 交互上设计成分页展示。

**代码审查结论与后续行动**：
- **部分落实**：当前代码仅在 `src/utils.py` 的 `robust_edit_text` 方法中落实了 `text = text[:4000]` 的截断逻辑。
- **遗漏与优化方案**：更常用的 `robust_send_message` 和 `robust_reply_text` 并未实现截断。**后续优化需将文本截断逻辑补充到这两个方法中**，防止返回超长内容时依然引发异常。

---

## 4. 高频的数据库唯一约束冲突 (Unique Constraint Violations)
**现象与日志特征**：
- `WARNING - ... UniqueViolationError: duplicate key value violates unique constraint "uix_user_post_action" DETAIL: Key (user_id, post_id, action_type)=(..., apply) already exists.`

**问题分析**：
- 大量用户在短时间内多次点击“应用(apply) / 克隆 / 点赞”等交互按钮。由于数据库中有唯一约束 `uix_user_post_action`，重复插入被成功拦截，但每次拦截都会抛出异常，在日志中产生大量 Warning 并消耗数据库性能。

**解决方案**：
1. **使用 `ON CONFLICT DO NOTHING`**：在 SQLAlchemy 插入语句中引入 PostgreSQL 特有的 upsert 语法。当发生主键或唯一约束冲突时，静默忽略，不抛出异常。
2. **Redis 层防刷 (Debounce)**：结合 `allbot-task-engine` 技能中的并发锁防刷机制，在 API 或 Bot 路由入口处对同一用户的同一按钮操作进行频率限制拦截，避免无效请求打到数据库层。

**代码审查结论与后续行动**：
- **实现偏差**：当前业务代码（如 `gallery_core.py`）中，**并没有实际使用 upsert 语法**，而是通过 `session.flush()` 强行触发并捕获 `IntegrityError` 然后执行 `session.rollback()`。
- **隐患与优化方案**：这种“报错+回滚”的方式在高频并发时会产生较大的数据库事务开销。**后续优化需将代码重构为真正的 PostgreSQL upsert 语法**：
  ```python
  from sqlalchemy.dialects.postgresql import insert
  stmt = insert(UserInteraction).values(user_id=user_id, post_id=post_id, action_type="apply").on_conflict_do_nothing()
  await session.execute(stmt)
  ```
