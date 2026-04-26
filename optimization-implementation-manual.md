# 🚀 All_Bot 系统优化与修复实施手册 (V1.0)

> **基于报告**：`/home/hfy/APP/All_bot/optimization-report.md` (2026-04-25)
> **目标**：在低风险、可验证、可监控的前提下，分阶段安全修复系统 P0/P1/P2 级别隐患。

---

## 零、 总体前置条件与准备工作 (Prerequisites)

在执行任何阶段的修改前，必须确保以下前置条件已满足：
1. **代码基线控制**：基于主分支拉取全新的优化分支（例如 `feature/optimization-202604`）。
2. **环境隔离**：所有步骤必须先在测试环境（`tg-bot-test`, `web-api-test`, `payment-api-test`）验证，再推至正式服。
3. **数据备份**：执行数据库全量备份（`pg_dump`），特别是 `users`, `orders`, `user_logs`, `history` 表。
4. **监控就绪**：确认 Dashboard 与 Redis 监控面板处于可用状态，以便实时观察并发锁与连接数。
5. **维护窗口**：P0 级别的数据库迁移建议在凌晨低峰期（如 03:00 - 05:00）执行，期间可通过 `touch /app/MAINTENANCE` 开启维护模式。

---

## 一、 第一阶段：核心资产与可用性保卫战 (P0 级别)
**目标**：解决支付双花漏洞，消除数据库慢查询引发的全站宕机风险。
**影响评估**：极高。直接关系到公司资产安全与系统核心可用性。

### 步骤 1.1: 修复支付发货并发双花漏洞 (Double Spend)
* **执行步骤**：
  1. 定位 `src/services/payment_fulfillment_service.py`。
  2. 将查询订单的语句从 `select(Order)...` 修改为 `select(Order)...with_for_update()`，引入悲观行级锁。
* **输入/输出**：输入为代码变更；输出为具备事务排他锁的验证发货逻辑。
* **所需资源**：后端开发 1 人，测试 1 人。
* **验证标准**：使用 `ab` 或 `JMeter` 针对同一 `out_trade_no` 的 Webhook 接口并发发送 10 个请求，数据库中 `orders` 状态仅变更一次，`user_logs` 仅产生一条充值流水。
* **潜在风险与应对**：
  * *风险*：死锁或长事务阻塞。
  * *应对*：确保 `with_for_update` 所在的 Session 作用域极小，且处理完状态后立即 `commit()` 释放锁。
* **回滚策略**：直接 Git Revert 撤销 `with_for_update()` 代码，重启 `payment-api` 容器。

### 步骤 1.2: 添加 History 表查询索引
* **执行步骤**：
  1. 定位 `src/database/models.py`，在 `History` 类的 `user_id` 和 `task_id` 列增加 `index=True`。
  2. 在宿主机执行：`alembic revision --autogenerate -m "add_history_indexes"`。
  3. 审查生成的 Alembic 迁移脚本，确认无误后执行 `alembic upgrade head`。
* **输入/输出**：输入为 ORM 模型变更；输出为 Alembic 迁移脚本与 PostgreSQL 索引。
* **所需资源**：DBA/后端开发 1 人。
* **验证标准**：在 PostgreSQL 终端对 BFF 的查询语句执行 `EXPLAIN ANALYZE`，执行计划必须从 `Seq Scan` 变为 `Index Scan`，耗时从秒级降至毫秒级。
* **潜在风险与应对**：
  * *风险*：表数据量过大时，建索引会触发表锁（Table Lock），导致正在写入的 `tg-bot` 任务报错。
  * *应对*：开启系统维护模式（挂起新任务生成）后再执行迁移；或手动修改 Alembic 脚本使用 `CREATE INDEX CONCURRENTLY`。
* **回滚策略**：执行 `alembic downgrade -1` 撤销索引，并删除对应的迁移脚本。

---

## 二、 第二阶段：并发控制与可观测性基建 (P1 级别)
**目标**：彻底解决 Redis 并发锁漂移问题，恢复全网异常监控能力。
**影响评估**：中等。主要改善系统边界条件下的稳定性和运维排障效率。

### 步骤 2.1: 修复 Redis 并发锁的竞态条件
* **执行步骤**：
  1. 定位 `src/services/redis_client.py` 中的 `decrement_user_concurrency` 方法。
  2. 移除原有的 Read-Modify-Write 逻辑，替换为原子化的 Lua 脚本执行（`eval`）。
* **输入/输出**：输入为 Lua 脚本代码；输出为强一致性的 Redis 递减锁方法。
* **所需资源**：后端开发 1 人。
* **验证标准**：编写单元测试，使用 `asyncio.gather` 并发 100 个递减请求，断言 Redis 中的值绝不会出现负数，且并发累加的总和绝对精确。
* **潜在风险与应对**：
  * *风险*：Lua 脚本语法错误导致 Redis Client 抛出异常，引发大面积任务状态死锁。
  * *应对*：部署前在本地单测环境中严格跑通，确保脚本语法正确且返回值类型匹配（Lua 的 number 与 Python 的 int）。
* **回滚策略**：Git Revert 恢复原有的 Python 层递减逻辑，重启对应容器。若发生锁混乱，运行 `docker exec tg-bot python clean_zombies.py` 自愈脚本重置状态。

### 步骤 2.2: 治理异常吞没与调试日志
* **执行步骤**：
  1. 全局检索 FSM 文件（`quick_video_fsm.py`, `ltx_video_fsm.py`, `callback_handler.py`）中的 `except Exception: pass`。
  2. 替换为 `logger.error("操作失败描述", exc_info=True)`，并确保向用户返回友好提示（如 "系统繁忙，请重试"）并正确释放锁。
  3. 将 `src/quota.py` 等业务代码中的 `print()` 替换为标准 `logger.info()`。
* **输入/输出**：输入为代码搜索替换；输出为标准化的标准输出流（stdout）日志。
* **所需资源**：后端开发 1 人。
* **验证标准**：主动在测试服触发异常（如断开网络或传递非法参数），观察 `docker logs tg-bot` 是否能输出完整的 Traceback 堆栈，且用户端不会卡死在等待状态。
* **潜在风险与应对**：
  * *风险*：高频报错引发日志刷屏（Log Spamming），撑爆容器磁盘。
  * *应对*：在 Docker Compose 中配置 `logging.options.max-size="100m"` 防止日志文件无限膨胀。
* **回滚策略**：非阻断性修改，通常无需回滚，若有报错直接热修复即可。

---

## 三、 第三阶段：架构演进与深水区重构 (P2 级别)
**目标**：拆解神仙对象，打通全链路追踪。
**影响评估**：深远。涉及大量历史逻辑重构，回归测试成本极高。

### 步骤 3.1: 重构 `handle_callback_query` 路由 (CC=192)
* **前置条件**：必须拥有一套核心业务流程的自动化端到端（E2E）测试用例。
* **执行步骤**：
  1. 引入工厂/策略模式，创建 `routers/` 目录。
  2. 按照前缀（如 `billing_`, `gallery_`, `fsm_`）将 `callback_handler.py` 中的巨大 `if-elif` 块拆分到独立的处理类中。
* **验证标准**：所有 Telegram 历史菜单按钮（支付、参数调节、翻页等）点击无异常，且圈复杂度扫描 `radon cc src/handlers/` 均 < 15。
* **潜在风险与应对**：
  * *风险*：遗漏个别老旧按钮的路由，导致点击无响应。
  * *应对*：设计一个兜底（Fallback）路由记录未匹配的 callback_data，并在上线前进行全员灰度内测。
* **回滚策略**：保留旧版 `callback_handler_v1.py`，一旦发现大面积失效，一键修改入口引用指回老代码。

### 步骤 3.2: 全链路 TraceID 注入
* **执行步骤**：
  1. 引入 `asgi-correlation-id` 库。
  2. 在 Web API 添加中间件，提取或生成 `X-Request-ID`。
  3. 将 TraceID 注入 Python `contextvars`，并修改 `logger` 的 formatter 使其在每行日志打印。
  4. 修改 Redis Pub/Sub Payload，将 TraceID 传导至后端的 ComfyUI Worker。
* **验证标准**：通过 ELK/Loki 搜索同一个 TraceID，能查出从 API 接收请求 -> 写入 DB -> Redis 派发 -> Worker 执行的完整生命周期日志。

---

## 四、 应急响应预案 (Emergency Playbook)
如果任何实施步骤在正式服引发不可控的级联故障（Cascading Failure）：
1. **立即熔断**：执行 `docker exec tg-bot touch /app/MAINTENANCE` 阻止增量任务。
2. **切断流量**：在 Nginx 层面将 Web 端请求临时指向静态的维护页面（503）。
3. **全面回滚**：
   - 数据库：若 Alembic downgrade 失败，从 `pg_dump` 备份中全量恢复（不到万不得已不触发）。
   - 代码：`git reset --hard HEAD~1`，然后重新 `docker-compose up -d --build`。
4. **状态清洗**：运行 `python clean_zombies.py` 和 `python check_redis.py` 重置因宕机受损的内存锁状态。
