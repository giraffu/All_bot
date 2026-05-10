# 针对 `dashboard/backend/routers/stats.py` 的重构与优化方案

## 1. 问题诊断 (Problem Diagnosis)

结合实际代码分析，`dashboard/backend/routers/stats.py` 存在严重的 **Critical (致命风险/架构瓶颈)**。以下是现存的“性能定时炸弹”：

1. **致命漏洞：在 HTTP 生命周期内串行阻塞轮询外部接口 (External API Polling)**
   - `get_stats` 接口虽然是异步的，但在单次请求内，会使用 `while` 循环实时调用 Telegram API (`bot.get_star_transactions`) 分页拉取历史记录。如果交易量极大，这会引发几十次网络 I/O，不仅极易触发 Telegram Rate Limit，还会耗尽 worker 线程池，导致服务雪崩。同样的问题也存在于 `httpx` 实时拉取 TON/USDT 余额，且每次请求都在重复实例化 Client 和 Bot。

2. **内存炸弹与逻辑盲点：无限制的日志加载与 Python 侧 JSON 解析**
   - 在 `get_stats_history` (第 1225 行) 查询 `UserLog` 时**完全没有加任何日期限制**！代码为了计算历史累计基数，将历史以来所有的充值日志全部拉到内存中并循环 `json.loads`。
   - **核心业务盲点**：系统实际上已经有结构化的 `Order` 表用于记录支付流水，舍近求远去扫描无结构的 `UserLog.extra_info` 文本进行财务统计，是导致 OOM 和耗时呈 $O(N)$ 线性增长的根本原因。

3. **标量与分组查询风暴 (N+1 查询变体)**
   - **`get_stats` 中**：为了获取各种维度的基础统计，代码连续独立执行了近 **30 次** `await db.execute(select(func.count...))`。
   - **`get_stats_history` 中**：代码对 `User` 和 `History` 表分别执行了近 **10 次** 独立的 `GROUP BY func.date(...)` 聚合查询，疯狂消耗数据库连接池资源。

4. **本可用 SQL 聚合，却在 Python 循环**
   - 计算邀请充值统计时，使用了 `.all()` 将所有成功的订单拉到内存，再通过 Python `for` 循环分类求和，完全浪费了数据库的聚合计算能力。

5. **代码极度膨胀与规范遗留**
   - 单文件长达 1435 行，缺乏 Repository/Service 层的隔离。
   - 存在 `== True` 的反模式（如 `User.is_channel_member == True`）。
   - 存在大量局部作用域内的 `import json` 和空泛捕获异常（`except Exception: pass`）。

---

## 2. 解决方案 (Solutions)

针对以上问题，建议采取分阶段重构，从**紧急止血**到**架构解耦**逐步实施：

### 阶段一：紧急止血与代码规范修复 (短期/快速见效)

**0. 引入接口级缓存 (Redis/内存 Cache) [首要任务]**
- 统计数据允许存在一定的延迟。立即为 `get_stats` 和 `get_stats_history` 引入 60~120 秒的接口级缓存（如使用 `fastapi-cache2`），瞬间将 DB 和外部 API 的压力降低 99%，为后续重构争取时间。

**1. 消除外部 API 阻塞与重复实例化**
- **强制后台增量同步**：针对 TON、USDT、Stars 的余额查询，**绝对禁止**在 Dashboard 接口中主动发起拉取。编写独立的后台定时任务，**增量（维护分页 cursor 或 offset）**拉取流水并写入 Redis/DB。Dashboard 接口**只读缓存**。
- 后台任务中应使用全局单例的 `httpx.AsyncClient`，避免连接池耗尽。

**2. 按表合并标量与分组查询 (Batch Queries)**
- 将 `get_stats` 中几十个零散查询，通过条件聚合合并。
- **⚠️ 避坑指南**：切勿将不同表（如 `User` 和 `History`）的聚合合并到同一个 SQL 中以免引发笛卡尔积爆炸。应按表归类合并。
- **合并 `User` 表**的大聚合示例：
  ```python
  await db.execute(select(
      func.date(User.created_at).label("date"),
      func.count(User.id).label("total_count"),
      func.sum(case((User.language_code.like("en%"), 1), else_=0)).label("en_count"),
      func.sum(case((User.hashed_password.is_not(None), 1), else_=0)).label("pwd_count")
  ).where(func.date(User.created_at) >= start_date).group_by(func.date(User.created_at)))
  ```

**3. SQL 聚合替换内存循环**
- 将 `Order` 的 Python 层循环求和，重写为原生 SQL 聚合查询：
  ```python
  rmb_sum = func.sum(case((Order.order_id.like("RMB_%"), Order.final_price), else_=0))
  # Stars 和 TON 同理转换
  ```

**4. 修复 Lint 警告**
- 将所有的 `== True` 替换为 `.is_(True)`。
- 将局部 `import json` 统一上移至文件顶部。
- 移除空泛的 `except Exception as e: pass`，记录具体日志。

### 阶段二：告别 JSON，转向结构化查询 (中期/解决性能瓶颈)

**1. 彻底废弃 `UserLog` 财务解析逻辑**
- 不再需要复杂的离线聚合表和夜间跑批（避免过度设计）。现代数据库对百万级数据的单表聚合毫无压力。
- 直接改造 `get_stats_history` 的财务统计逻辑，全部改为直接对结构化的 `Order` 表（`status == 'SUCCESS'`）执行 SQL 聚合 (`GROUP BY`)。

**2. 补齐 `Order` 表维度字段**
- 审查现有的 `Order` 表。如果为了前端统计图表还缺少某些维度（如具体带来的身份变动、使用的套餐分类），应优先对 `Order` 表进行字段扩充（例如增加 `plan_category`, `granted_identity`），并在核心支付回调逻辑中写入这些数据，从而彻底终结对日志 JSON 文本的依赖。

### 阶段三：架构演进与读写分离 (长期/终极方案)

**1. 路由与 Service 层拆分**
- 建立 `services/stats_service.py`，物理拆分当前 1400 行的路由文件为 `users.py`, `finance.py`, `generations.py`。
**2. CQRS 模式**
- 随着业务与流水增长，将后台复杂的 Dashboard 统计查询路由至只读从库 (Read Replica) 执行，避免影响前台机器人的主库写入性能。

---

## 3. 重构执行路线图 (Action Items)

### Phase 1: 紧急止血与 API 解耦 (本周)
- [ ] **Task 1**: 引入 `fastapi-cache2`，为 `get_stats` 和 `get_stats_history` 增加 60~120 秒的接口缓存。
- [ ] **Task 2**: 剥离外部网络请求。建立后台定时任务，**增量（维护分页 cursor）** 拉取 TG Stars 交易并缓存余额，TON/USDT 余额同理。
- [ ] **Task 3**: **按表合并查询风暴**。将 `User` 表的近 10 个独立聚合合并为 1 条 SQL；将 `History` 表的查询合并为 1 条 SQL。
- [ ] **Task 4**: 使用 `SQL func.sum + case` 重写 `Order` 的 Python 层循环求和逻辑。
- [ ] **Task 5**: 修复所有 `.is_(True)` 反模式，规范 Imports 并消除静默异常。

### Phase 2: 告别 JSON，转向结构化查询 (中期)
- [ ] **Task 6 (核心)**: **彻底废弃 `UserLog` 财务解析逻辑**。改造 `get_stats_history` 的财务统计逻辑，全部改为直接对结构化的 `Order` 表（`status == 'SUCCESS'`）执行 SQL 聚合 (`GROUP BY`)。
- [ ] **Task 7**: 审查 `Order` 表字段。如果缺失维度（如具体身份变动），对 `Order` 表进行字段扩充（如加 `plan_category`），并在核心支付逻辑中补齐数据，避免去解析 Log。

### Phase 3: 架构演进 (长期)
- [ ] **Task 8**: 将 `stats.py` 按业务域拆分为多个路由文件，并引入 Service 层剥离复杂的 DB 操作。
- [ ] **Task 9**: 评估引入数据库只读从库处理 Dashboard 的重度统计查询。
