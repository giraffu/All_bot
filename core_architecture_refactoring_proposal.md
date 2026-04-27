# 核心架构重构与“双轨制”消除方案

## 1. 背景与现状

在对整个代码库（特别是 Web API、Telegram Bot Handler 以及 Dashboard 后端之间）的深入对比分析后，发现系统存在**严重的“多轨制”业务逻辑重复**，且部分核心服务（如 `permission_service.py`）仍严重违规耦合了平台对象。

为了支持多端复用（Web API、Bot、Dashboard 等），必须对现有架构进行深度重构。

---

## 2. 核心问题诊断

### 2.1 表现层与核心层耦合违规
- **问题定位**：`src/services/permission_service.py`
- **现象**：大量导入 `Update` 和 `ContextTypes`，在核心业务方法（如签到 `perform_checkin`、鉴权 `check_access`）中直接读取 `update.effective_user`，甚至直接调用 `robust_send_message` 发送 Markdown 格式的 Telegram 消息文案。
- **影响**：完全无法被 Web API 端复用，且违反了 Clean Architecture（洋葱架构）的依赖倒置原则。

### 2.2 任务派发与并发计费编排重复
- **问题定位**：`src/web_api/routers/tasks.py` vs `src/services/task_service.py`
- **现象**：Web 端规范地调用了 `task_core.process_and_submit_task`，但 Bot 端的 `task_service.py` 在处理复杂任务（如 LTX 视频、FaceVideo）时，**完全手动复制了核心层的编排逻辑**（包括手动检查并发锁、扣费、注册任务）。
- **影响**：若计费规则或并发限制（Saga 补偿模式）改变，极易导致一端退款成功而另一端吞费的严重 Bug。

### 2.3 画廊 (Gallery) 核心逻辑“双轨制”
- **问题定位**：`src/web_api/routers/gallery.py` vs `src/handlers/callbacks/gallery_callbacks.py`
- **现象**：
  - **发帖/投稿**：Web 端调核心层，而 Bot 端直接手写 SQL 创建 `GalleryPost`，并重复编写了每日上限与原创属性等校验规则。
  - **互动 (点赞/点踩)**：两端各自实现了一遍操作 `UserInteraction` 表和更新帖子计数的 SQL。
  - **查询**：两端分别实现了复杂的 SQL 列表分页查询。

### 2.4 纯业务数据映射硬编码
- **问题定位**：模型标签与名称映射 (`translate_tags` 等)
- **现象**：将模型 ID（如 `qwen/realistic.safetensors`）转为展示标签（如 `#真实质感`）的函数在 API 和 Bot 两端各复制了一份，缺乏统一的配置中心。

### 2.5 管理后台 (Dashboard) 越权与逻辑重复 (隐蔽的第三轨)
- **问题定位**：`dashboard/backend/routers/` (如 `system.py`, `users.py`, `gallery.py`)
- **现象**：Dashboard 后端直接操作 Redis 强行解除并发锁、手写会员开通的残值计算与天数折算逻辑，并独立拼接了画廊的分页 SQL 查询。
- **影响**：脱离 Core 层统一管控，若计费规则或并发调度策略发生变更，Dashboard 的后台操作将与用户端操作产生严重的数据状态不一致。

---

## 3. 解决方案与实施细则

### 3.1 第一步：强行剥离 Bot 编排逻辑 (Task Core)
- **目标**：将 `task_service.py` 中重复的 LTX、FaceVideo 等组装与计费扣除逻辑**全面下沉**到 `src/core/task_core.py` 中。
- **标准**：`task_service.py` 必须退化为只负责“解析 Update、发 TG 消息、更新 TG 键盘”的薄层（展示层），所有与 Redis、并发锁、数据库的直接交互全部交由 Core 层。
- **⚠️ 优化与避坑 (Saga 模式防漏洞)**：**绝对不能**将整个任务派发流程包裹在一个大的数据库 `AsyncSession` 事务（UoW）中。如果包含外部调用（API请求/Redis队列）失败导致事务回滚，同时又在 `except` 中手动执行 `refund_credits`，会引发**双重退款漏洞**。必须严格遵循 Saga 补偿模式：先执行扣费并提交，设置 `credits_deducted = True` 标志，外部调用失败时再通过 `asyncio.shield` 手动触发退款。

### 3.2 第二步：彻底改造 `permission_service.py` 与异常处理机制
- **目标**：解耦 Telegram 特定对象，并规范化异常拦截。
- **策略**：
  - 将接收 `Update` 的参数全部改为接收基础类型（如 `internal_user_id`, `tg_id`, `username`）。
  - **异常/返回值驱动**：将业务文案（如余额不足提示）的发送移交回 Handler 层，Service 仅返回结果状态（如 `bool`, `Enum`）或抛出自定义领域异常（如 `InsufficientCreditsError`）。
- **实施优化 (统一异常捕获)**：为避免在几十个 Bot Handler 里散弹枪式地写冗长的 `try...except` 块，导致代码极度臃肿，**应实现一个统一的错误捕获装饰器**（如 `@with_core_error_handling`）。该装饰器负责自动拦截核心层抛出的 `CoreDomainError`，并转换为友好的 `robust_send_message` 或 `safe_answer_query` TG 弹窗。
- **⚠️ 优化与避坑 (Bot 瘫痪风险)**：
  - 修改 `ensure_user` 等方法签名时，**必须同步修改所有 Handler 的调用方**，漏改将导致路由瘫痪。
  - **频道验证解耦**：采用依赖倒置，将“调用 Bot API 查频道状态”的动作留在 Handler 层，把结果（布尔值 `is_channel_member`）传给 Service；或向 Service 注入 `ITelegramClient` 接口。

### 3.3 第三步：完善 Gallery Core 收口与动态分页优化
- **目标**：消除画廊模块的 SQL 冗余，根治分页错位 Bug。
- **策略**：在 `src/core/gallery_core.py` 中补充完整的 `toggle_like`, `create_post`, `get_gallery_feed` 等业务门面，让 Web 路由和 Bot 回调仅作为调用方。
- **实施优化 (动态 Pagination)**：在下沉 SQL 时，**避免人为维护独立的 `count_stmt`**。应通过 SQLAlchemy 的 `select(func.count()).select_from(query.subquery())` 模式动态生成统计语句，确保 `.where()` 和 `.outerjoin()` 条件天然对齐，彻底解决前端页码计算错位的问题。
- **⚠️ 优化与避坑 (异常翻译原则)**：Core 层必须只抛出领域异常（如 `DuplicateInteractionError`），**严禁**直接抛出 FastAPI 的 `HTTPException` 或调用 Telegram 的弹窗方法。由外层 Web Router 捕获并翻译为 HTTP 400 状态码，由 Bot Handler 捕获并翻译为相应的 TG 提示。

### 3.4 第四步：建立统一配置字典
- **目标**：消除魔法字符串和硬编码映射。
- **策略**：在 `src/constants.py` 或新建 `src/config_mapping.py` 中统一定义 `ALL_LORA_MODELS` 和 `translate_tags` 等映射关系，Web 路由和 Bot Handler 统一 `import` 该字典进行解析。

### 3.5 第五步：Dashboard 逻辑全面接入 Core 门面与物理隔离
- **目标**：消除 Dashboard 中手写的底层越权操作，从架构层面封堵直连行为。
- **策略**：将 Dashboard 中的会员充值折算、任务强杀与并发锁释放、画廊管理等，全部替换为调用 `src/core/` 暴露的统一方法，确保任何状态变更都经过核心业务校验。
- **实施优化 (严格物理隔离)**：在重构 `system.py` 将 Dashboard 接入 Core 层后，通过 Linter 规则或代码结构调整，**直接禁止** `dashboard/backend/routers` 导入 `redis_client.py` 等底层资源操作类，从根源上杜绝越权。

---

## 4. 潜在问题与风险核对（⚠️ 重点关注）

在具体实施时，有几个隐藏的架构约束必须严格遵守，否则会导致严重的系统级 Bug：

### 4.1 Task ID 生成位置打破 Pub/Sub 订阅顺序与 TraceID 贯穿
- **现象与后果**：如果在 `task_core.py` 内部封装编排逻辑时，顺便在 Core 层内部使用 `uuid.uuid4()` 生成了 `task_id`，将引发致命的 Race Condition（并发竞争）。因为系统的 Central API 采用了 Redis Pub/Sub 架构来监听任务完成事件，调用方（Web BFF 或 Bot Handler）**必须先订阅通道，再派发任务**。若内部生成 ID，调用方在派发完成前拿不到 ID，无法提前订阅，导致 Worker 处理太快而漏接消息。
- **修正建议**：在 `task_core.py` 的重构中，**必须将 UUID 的生成权强制上移给调用方**（预先生成并传入 `task_id`）。例如，Web 端的 `POST /generate` 在调用 Core 层前必须先生成 ID。
- **实施优化 (全链路 TraceID)**：在生成权上移的同时，顺便将生成的 `task_id` 放入 `contextvars`，作为全链路的 `TraceID` 贯穿所有的 Logger。这不仅解决了并发竞态，还能在排障时一键串联 API、Core 以及底层 Worker 的日志。

### 4.2 `ensure_user` 签名修改导致全局路由瘫痪
- **现象与后果**：方案提到“必须同步修改所有 Handler 的调用方”，但在剥离 `Update` 对象时，如果 Handler 层没有做判空安全提取，直接访问 `.id` 会引发异常。在某些特殊的 Telegram 更新（如 `poll` 投票更新或某些 `my_chat_member` 状态变更）中，`update.effective_user` 可能为 `None`。此时直接访问会导致 `AttributeError`，从而使 Bot 核心中间件崩溃。
- **修正建议**：在所有调用 `ensure_user` 的入口（如 `message_handler.py`, `callback_handler.py`），必须增加 `if not update.effective_user: return` 的前置防御逻辑，再将基础类型参数传给 Service。

### 4.3 FastAPI 自动回滚与手动退款的冲突
- **现象与后果**：在 Web API 端，如果使用了依赖注入的 `AsyncSession`（UoW 模式），当抛出异常时 FastAPI 路由会自动回滚数据库。如果在回滚之后（或者回滚的同时）手动触发了 `refund_credits`，会导致数据库状态不一致或产生重复退款漏洞。
- **修正建议**：确保 Core 层抛出 `InsufficientCreditsError` 等领域异常时，事务的边界是清晰的。Saga 模式下的扣费应该是一个独立的、已 commit 的短事务，而不是包裹在整个请求的大事务中。

---

## 5. 执行计划（分阶段实施）

建议采用**分阶段 PR** 的方式进行，优先处理高收益低风险的模块，最后处理高风险硬骨头：

1. **第一阶段（提炼配置与画廊收口）**：
   - 全局搜索并抽取 `translate_tags` 等方法至常量文件。
   - 重构 `gallery_callbacks.py`，将重复的 SQL 查询下沉至 `gallery_core.py`，并**实施 SQLAlchemy 的动态分页优化** (`subquery().count()`)。
2. **第二阶段（核心逻辑下沉与 TraceID 贯穿）**：
   - 重构 `task_service.py`，将重复编排逻辑转移至 `task_core.py`，**强制 UUID 上移生成，并注入 Contextvars** 作为 TraceID。
   - 严格审查事务边界，确保 Saga 补偿模式的正确性，防止双重退款。
3. **第三阶段（解除鉴权耦合与异常装饰器 - 硬骨头）**：
   - 重构 `permission_service.py` 函数签名，解耦 Telegram 对象，并在所有调用方加入 `effective_user` 前置防御。
   - 全局替换并修复所有 Handler 的调用方报错，处理频道验证的依赖倒置。
   - 为 Handler 补充 `@with_core_error_handling` **统一异常捕获与文案发送逻辑**。
4. **第四阶段（Dashboard 接入、隔离与回归测试）**：
   - 重构 Dashboard 后端相关路由，剥离手写 SQL 和 Redis 操作，全面接入 Core 层方法。
   - **在代码规范或 Linter 层面禁止 Dashboard 直连 Redis 资源**。
   - 确保 Web API、Telegram Bot 以及 Dashboard 管理后台在鉴权、发帖、扣费、退款流程上的表现完全一致。