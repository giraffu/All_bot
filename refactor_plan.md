# 全局代码重构与修改实施方案

> 基于 `code_analysis.md` 的静态分析结果以及实际代码的交叉验证，为解决系统架构耦合、作用域风险和高复杂度问题，特制定本渐进式重构方案。重构目标是严格遵循 `AGENTS.md` 中的核心隔离（Core Isolation）原则，提升代码的可维护性与扩展性。

## 🎯 核心目标
1. 解除核心业务层与外部框架（Telegram/FastAPI）的耦合。
2. 拆分“上帝文件”（如 `backend/app/main.py`），消除全局变量风险。
3. 抽象通用逻辑，降低 `src/api_client.py` 等模块的圈复杂度和代码冗余。
4. 增强分布式系统的一致性，修复潜在的事务回滚漏洞、并发锁泄漏和 Pub/Sub 竞态条件。

---

## 📅 实施路线图 (渐进式重构)

建议按照以下顺序逐步实施，每次完成一个阶段后，需运行测试确保核心业务功能未受影响。

### 阶段一：核心层解耦与准入策略重构 (中风险)
**目标**：解决 `src/core/auth_core.py` 违反架构隔离原则的问题 (Critical)。
**行动项**：
- [ ] **拆分验签层 (Signature Verifier)**：
  - 提取 Telegram WebApp/Widget 的 Hash 验签逻辑，创建一个纯粹的工具类（如 `TelegramAuthVerifier`），仅负责计算和比对 Hash。
- [ ] **提取准入策略层 (Access Policy)**：
  - 将硬编码的“内门弟子”、“金丹期”等境界限制逻辑移出 `auth_core.py`，转交由 `permission_service.py` 或独立的策略类/中间件处理，使 Core 层纯粹负责鉴权契约。
- [ ] **依赖倒置与异常纯粹化 (Dependency Inversion)**：
  - 核心认证函数不再直接抛出强耦合 HTTP 状态码（如 401/403）的异常，而是抛出自定义的纯领域异常（如 `InvalidSignatureError`、`InsufficientPermissionError`）。
  - 由最外层的 FastAPI Exception Handler 或 Telegram 路由层统一捕获这些领域异常，再将其转换为对应的 HTTP 响应或 Telegram 文本提示。

---

### 阶段二：解构“上帝文件”与明确状态管理物理边界 (高风险)
**目标**：拆分中间件网关 `backend/app/main.py` 消除全局变量风险，并规范 Bot 端 `src/core/task_core.py` 的事务与并发锁生命周期。
**行动项**：
#### 2A. Central API 现代化 (`backend/app/main.py`)
- [ ] **生命周期现代化与路由模块化**：
  - 移除已废弃的 `@app.on_event("startup/shutdown")`，改用 `Lifespan` 统一管理 Redis 连接池、MinIO 客户端。移除 `global minio_client` 声明。
  - 将现有的十几个几乎一模一样的 `@app.post("/comfy_xxx")` 路由，利用泛型或统一的 `/api/v1/tasks` 路由替代，大幅削减冗余代码。

#### 2B. Bot 端任务门面与 Saga 规范 (`src/core/task_core.py`)
- [ ] **提取 Task Facade (TaskService) 与防白嫖漏洞 (Saga Pattern)**：
  - 封装一个纯粹的 `TaskFacade`。核心红线：严禁在一个数据库 `AsyncSession` (UoW) 中包裹扣费和 Redis 入队。
- [ ] **并发锁防泄漏与异常链闭环 (Lock Leak Prevention)**：
  - 在 `process_and_submit_task` 中，执行 `check_and_deduct_credits` 扣费成功后，**紧接着的第一行代码**必须是开启 `try...except...finally` 块。
  - 将后续的“组装 Prompt”、“调用 api_client”、“挂载 monitor_task” 全部放入 `try` 块中。
  - 必须在 `except` 中显式触发 `refund_credits` 进行补偿，并在 `finally` 中显式触发 `release_concurrency_lock`，实现 100% 防并发锁泄漏。

---

### 阶段三：降低客户端调度复杂度 (中风险)
**目标**：解决 `src/api_client.py` 和 `src/core/task_core.py` 中圈复杂度过高（级别 D）及硬编码方法过多的问题 (Medium)。
**行动项**：
- [ ] **通用化提交接口**：
  - 将 `api_client.py` 中十几个硬编码的 `submit_xxx` 方法收敛重构为一个通用的 `submit_task(endpoint: str, payload: dict)` 方法。
- [ ] **引入策略模式 (Strategy Pattern)**：
  - 针对 `task_core.py` 中 `core_submit_generation_task` 的臃肿 `if/elif` 判断链（如 ltx_video 换算分辨率、face_swap 调整双图顺序），建立一个 `TaskHandler` 字典注册表进行分发，消除高圈复杂度。
- [ ] **Pub/Sub 竞态条件完美闭环**：
  - 将 `listen_for_progress` 的逻辑抽取到独立的 `TaskMonitor`。
  - **避坑红线 (严格时序契约)**：客户端（Bot）**预生成 UUID 作为 task_id** -> 客户端**先 `subscribe`** 该任务频道 -> 客户端**再**将 task_id 作为 Payload 发送给 Central API 入队。从根本上抹除 Worker 处理过快导致订阅事件丢失的时间差漏洞。

---

## ✅ 验收标准
1. **静态分析指标改善**：`radon` 报告的平均圈复杂度降低，消除 D 级别的超大函数；`pylint` 报告的架构违规和作用域风险清零。
2. **测试覆盖率**：核心重构模块（Auth, TaskService, API Client）的单元测试通过，且覆盖率提升。
3. **系统稳定性**：现有所有生图、视频生成、回调通知功能在本地及测试环境中运行正常，无回归 Bug。事务回滚与并发锁机制在压测下无异常。
