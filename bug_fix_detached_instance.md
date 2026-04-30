# `tg-bot` DetachedInstanceError Bug 分析与修复方案

## 1. 问题现象 (Symptoms)
在 `tg-bot` 运行日志中发现严重异常：
```text
sqlalchemy.orm.exc.DetachedInstanceError: Instance <User at ...> is not bound to a Session; attribute refresh operation cannot proceed
```
**报错位置**：发生于 `/app/src/services/task_service.py` (约 333 行)：`internal_user_id = internal_user.id`

## 2. 根本原因深度剖析 (Root Cause)
该 Bug 是由一系列连锁反应引起的数据库会话游离异常：

1. **唯一约束冲突 (`IntegrityError`)**：系统在同步或更新用户的 Telegram 资料时（如 `UPDATE users SET username='...'`），由于表结构存在 `username` 的唯一索引约束 (`idx_users_lower_username`)，且该名字与其他记录冲突，数据库抛出了 `asyncpg.exceptions.UniqueViolationError`。
2. **事务回滚 (Session Rollback)**：底层的异常处理捕获到了此冲突（日志打印了 `warning_db_conflict`），为了保证数据库安全，SQLAlchemy 的当前事务（Session）发生了回滚 (`session.rollback()`)。
3. **对象游离 (Detached Object)**：回滚操作会导致内存中现存的 SQLAlchemy ORM 对象（即 `internal_user`）被强制从会话中剥离（Detached）。
4. **延迟加载失败**：代码继续向下执行进入 `task_service.py`。当试图访问 `internal_user.id` 时，SQLAlchemy 默认会尝试去刷新或加载该属性，但因为对象已经没有绑定的 Session，直接触发 `DetachedInstanceError`。

## 3. 业务破坏性影响 (Impact)
1. **任务彻底失败**：用户发送生成指令后，后台在加锁和初始化阶段直接崩溃，Bot 无任何有效响应。
2. **⚠️ 致命：并发锁永久泄漏**：创建任务前，系统已在 Redis 中为用户增加了并发锁（`user_concurrency:{user_id}`）。由于代码直接抛出未预料的 Exception 中断了流程，如果外层缺少对应的 `finally` 释放锁逻辑，**该用户的并发锁将永远无法释放**。后续该用户发起任何请求都会被提示“有任务正在处理中”，导致账号陷入永久假死状态。
3. **状态机 (FSM) 异常**：用户可能被卡在多级菜单的中间状态无法退出。

---

## 4. 推荐修复方案 (Fix Plan)

为了彻底根除此问题，建议采用以下“组合拳”进行修复：

### 方案一：根治异常源头 —— 优化 Username 更新策略 (首选)
避免让 SQLAlchemy 触发 `IntegrityError`。
* 在更新 `username` 之前，先进行存在性校验或格式校验。
* **规则参考**：当 Telegram 传来的 `username` 为 `None` 时，绝不使用 `full_name` 兜底（因为 full_name 极易重复触发唯一约束）。
* **代码修改**：在 `user_service.py` 的用户信息同步逻辑中，如果是 `username` 冲突，应当捕获后跳过更新 `username` 字段，仅更新其他字段，然后正常 `commit()`，避免整个 Session 发生回滚。

### 方案二：回滚后的状态恢复 —— 重新绑定 Session
如果业务逻辑中确实无法避免 Rollback，必须在回滚后“复活”该对象。
* **代码修改**：在捕获 `IntegrityError` 并执行 `await session.rollback()` 之后，如果后续业务（如 `task_service`）仍需使用该用户对象，必须通过查询重新获取：
  ```python
  except IntegrityError:
      await session.rollback()
      logger.warning("warning_db_conflict: username conflict.")
      # 重新从数据库查出该用户，使其绑定到当前有效会话
      internal_user = await session.get(User, user_id) 
  ```

### 方案三：系统级容灾 —— 补全 Redis 并发锁清理机制
这是必须添加的防线，防止任何类似的未知异常导致用户“死机”。
* **代码修改**：在核心的请求入口（或 `task_service.py` 外层封装）加入严谨的 `try...finally` 块。
  ```python
  # 伪代码示例
  try:
      # 1. Redis 锁递增
      # 2. 执行核心业务逻辑 (如 task_service.create_task)
  except Exception as e:
      # 记录严重日志
      logger.error(f"Task creation failed: {e}")
      # 向用户发送友好报错提示
      await notify_user_error()
  finally:
      # 无论如何，一定要递减释放并发锁！
      await release_redis_concurrency_lock(user_id)
  ```

## 5. 待办建议
您可以检查 `src/services/user_service.py` 中关于 `upsert_user` 或 `ensure_user` 的逻辑，并对照上述方案进行修复。