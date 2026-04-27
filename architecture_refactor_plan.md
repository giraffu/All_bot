# 架构解耦与 Saga 模式重构方案

## 1. 现状与痛点分析

根据静态分析报告和业务规范（特别是 `allbot-billing-auth` 和核心层隔离红线），当前 `src/handlers/message_handler.py` 和 `src/core/task_core.py` 存在以下严重问题：

1. **`handle_prompt` 复杂度过高 (F级)**：
   - 使用了超过 10 个 `if/elif` 语句直接对文本（如 `"🖼️ 懒人P图"`）进行硬编码匹配。
   - 耦合了 Telegram 相关的键盘组件 (`ReplyKeyboardMarkup`, `InlineKeyboardMarkup`) 创建与文本返回逻辑。
   - 个人中心 (`💰 个人中心`) 甚至在 Handler 层直接包含了极度复杂的业务规则（如升级条件判断、等级字符串拼接）。

2. **`core_submit_generation_task` / `process_and_submit_task` 承担过多职责且极易产生状态不一致**：
   - 同时处理并发锁检查 (`check_concurrency_lock`)。
   - 同时处理计费 (`check_and_deduct_credits`)。
   - 根据复杂的 `if is_video` 和 `task_type` 分发请求到后端的 ComfyUI Client (`image_service.submit_*`)。
   - 在发起外部网络请求（调用 ComfyUI 节点）后，如果失败或系统崩溃，缺乏完善的 **Saga 补偿机制**。目前通过巨大的 `try...except` 包裹，若中途出现未知异常抛出，极易导致**用户扣费成功但没派发任务（双花/吞钱漏洞）**。

---

## 2. 实施方案：门面隔离与策略模式

### 2.1 Handler 层路由解耦 (策略模式 + 字典映射)
针对 `handle_prompt` 函数中的巨型分支树，使用**策略模式（Strategy Pattern）**或**字典映射路由**进行重构。

**✨ 优化建议**：
1. 建议采用更优雅的**装饰器注册机制（Decorator-based Routing）**，如 `@prompt_route("🖼️ 懒人P图")`，并**支持正则表达式匹配**（以兼容 FSM 取消机制中的动态参数）。这样新增菜单时无需集中修改统一的字典，更符合开闭原则（OCP）。
   * **进阶：静态菜单工厂 (Static Menu Route)**：对于仅返回固定文本和二级键盘的菜单，建议在 `@prompt_route` 基础上再封装 `@static_menu_route(pattern="...", text="...", keyboard=[...])`，进一步消除样板代码。
   * **进阶：正则预编译**：对于 `is_regex=True` 的路由，建议在装饰器注册阶段直接调用 `re.compile()` 缓存正则对象，提升匹配性能。
2. **🚨 致命隐患修复（全局动态菜单拦截器）**：当前各个 FSM 内部（如 `edit_image_fsm.py`）使用了极长的硬编码正则拦截主菜单。在 `prompt_router.py` 中，除了收集路由，还必须对外暴露一个**黑盒化的全局动态正则过滤器**（如 `is_global_menu_command()`）。FSM 必须使用该过滤器作为前置拦截，以防止新增 `@prompt_route` 后 FSM 无法识别导致“菜单文本被当成提示词发送”的严重 Bug。**💡 避坑提示**：在拼接生成全局正则时，务必对特殊字符使用 `re.escape` 进行转义（例如菜单名 `🎬 图生视频(附加模型)` 包含括号），否则会导致正则编译崩溃，进而导致整个 Bot 启动失败。
3. **🛡️ FSM 路由优先级说明**：得益于 PTB (python-telegram-bot) 的天然路由机制，只要 `ConversationHandler` (FSM) 优先注册（例如在 `bot_test.py` 的 `app.add_handler` 中），处于 FSM 状态的用户输入会被 FSM 自动消费。因此，作为 Fallback 的全局路由层**完全无需**手动检查 `context.user_data.get('current_state')`，只需专注于解析主菜单即可。
4. **💡 CallbackQuery 防转圈机制（按需调用）**：如果触发源是 Inline Keyboard (`CallbackQuery`)，**绝不能**在全局路由分发处无条件调用 `await query.answer()`，因为 Telegram 限制 `CallbackQuery` 只能 `answer` 一次，全局调用会导致后续业务逻辑中所有需要弹窗（`show_alert=True`）的提示全部失效。应将“尽早 answer”的逻辑**下推到具体的 FSM 入口函数**或明确不需要弹窗的末端 Handler 中。

**改造示例**：
在 `src/handlers/` 下新建 `prompt_router.py`。
```python
# src/handlers/prompt_router.py

from typing import Callable, Awaitable
from telegram import Update
import re

# 定义装饰器与路由表
prompt_routes = {}
GLOBAL_MENU_FILTER = None

def prompt_route(pattern: str, is_regex: bool = False):
    def decorator(func):
        prompt_routes[(pattern, is_regex)] = func
        return func
    return decorator

def build_global_menu_filter():
    """在路由注册完成后的系统启动阶段，统一预编译一次正则对象"""
    global GLOBAL_MENU_FILTER
    # 提取所有精准匹配的菜单文本并转义
    menu_texts = [re.escape(k[0]) for k, v in prompt_routes.items() if not k[1]]
    pattern = f"^({'|'.join(menu_texts)})$"
    from telegram.ext import filters
    GLOBAL_MENU_FILTER = filters.Regex(re.compile(pattern))

def is_global_menu_command(text: str) -> bool:
    """黑盒化拦截器：供各个 FSM 内部调用，无需暴露底层的正则细节"""
    if not GLOBAL_MENU_FILTER:
        return False
    return bool(GLOBAL_MENU_FILTER.match(text))

# 定义每个菜单的独立处理器
@prompt_route("🖼️ 懒人P图")
async def handle_photo_edit_menu(update: Update, text: str):
    keyboard = [["💃 快速脱衣", "🎭 快速换脸"], ["🔙 返回主菜单"]]
    # ... return reply logic

@prompt_route("💰 个人中心")
async def handle_personal_center(update: Update, text: str):
    # 内部将调用 core 层的纯净数据接口获取 user_stats，然后只负责拼装 Markdown
    pass
```
**`message_handler.py` 的精简**：
```python
@with_db_logging_context
async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    # 遍历 prompt_routes 进行匹配（包含正则与精确匹配）
    for (pattern, is_regex), handler_func in prompt_routes.items():
        if (is_regex and re.match(pattern, text)) or (not is_regex and text == pattern):
            return await handler_func(update, text)
            
    # 处理普通对话/Prompt 输入
    pass
```

### 2.2 核心层隔离 (Facade 模式)
为了严格遵循 AGENTS.md 的规定：“`/src/core/` 下的代码**绝对禁止**引入任何与 Telegram `Update` 相关的对象”，必须将现有的业务逻辑抽取到 Facade 层。

**✨ 优化建议**：
1. **引入 Pydantic DTO (防腐层约束)**：建议 `user_facade.py` 返回强类型的 Pydantic Model（如 `UserDashboardDTO`），而非裸字典（`dict`），提供更好的类型推导与自动验证。
   * **进阶：双向约束**：Pydantic 不仅用作返回值，也应作为 Core 层的入参。建议废弃向 Core 传入松散的 `inputs: dict`，改为强制传入验证过的 `GenerationRequestDTO`，防止脏数据污染核心业务逻辑。
2. **引入统一规则引擎 (Rule Engine)**：当前计费动态价格（如 `LTX_DURATION_MULTIPLIER`）和特权等级散落在 `task_core.py` 与 `constants.py` 中。Facade 层应挂载一个独立的“规则引擎”（甚至可从 Redis 动态加载配置），统一接管并核算 Web 端和 Bot 端的价格与境界突破条件，消除硬编码，彻底解决 **Web 端和 Bot 端**计费逻辑不统一的痛点，确保多端行为绝对一致且支持热更新修改价格免重启。

例如，“个人中心”的等级判定逻辑，应抽象为：
```python
# src/core/user_facade.py
from pydantic import BaseModel

class UserDashboardDTO(BaseModel):
    current_group: str
    credits: int
    breakthrough_requirements: dict

async def get_user_dashboard_info(internal_user_id: int) -> UserDashboardDTO:
    """
    返回纯数据结构，绝不包含任何 TG 专属的 Markdown 或 Keyboard
    """
    stats = await get_user_detailed_stats(internal_user_id)
    # 通过规则引擎计算距离下一级的缺口、过期时间折算等核心业务逻辑...
    
    return UserDashboardDTO(
        current_group=stats['group'],
        credits=stats['credits'],
        breakthrough_requirements={...}
    )
```

---

## 3. 实施方案：Saga 事务模式分片重构

针对 `process_and_submit_task` 与 `core_submit_generation_task`，引入基于 `allbot-billing-auth` 规范的 Saga 补偿机制。核心原则：**外部副作用（如 Redis 入队、调用 ComfyUI）绝不能包裹在数据库的同一个同步事务中。**

**✨ 优化建议（可靠性升级）**：
目前的 `process_and_submit_task` 初步实现了基于 `try...finally` 的 Saga 模式，但若进程在扣费成功后瞬间崩溃（Crash / OOM），`finally` 块的异步退款任务将丢失。而且由于 Telegram 断连可能引发 `asyncio.CancelledError`，原有的补偿逻辑极易被打断。
**🚨 避免重复造轮子与吞钱漏洞**：系统已有 `TaskRegistry` 和 `zombie_cleaner_service.py` 的兜底机制。无需新增 `Redis Pending` 状态。但**务必注意边界**：必须在强扣费**成功后**，将其后的**所有操作（包括写入 TaskRegistry）**严格包裹在补偿块中。若在扣费后写入 Redis 失败，必须立即触发退款，彻底杜绝“扣费成功但没派发任务”的吞钱漏洞。

### 3.1 Saga 编排器重构设计
将大函数拆分为 3 个独立的阶段（Step）。

**🚨 致命问题优化（Task ID 悖论与并发锁泄露）**：
1. **并发锁包裹与 Shield 防御**：必须用全局大 `try...finally` 包裹并发锁释放，并且使用 `asyncio.shield()` 防御 `CancelledError`，避免提前 `raise` 或客户端断连导致锁永久泄露。
   * **进阶：Outbox 终极容灾**：`refund_credits` 内部涉及数据库事务（`session.commit()`），如果此时数据库宕机，`refund_credits` 抛出异常会导致后续的 `release_concurrency_lock` 被跳过。因此，每个 `shield` 操作必须独立包裹 `try...except`。如果退款失败，必须记录到本地 Outbox 或本地文件日志，通过定时任务兜底，但**无论如何都要执行并发锁释放**。
2. **联动修改 Central API（Task ID 强制前置与消除脑裂）**：为确保 Step 1 的 `TaskRegistry` 记录具有可追溯的 `task_id`，必须在 Bot 端**前置生成 UUID**。**注意**：为了确保后续向 Redis Pub/Sub 架构演进时，调用方能“先订阅、后入队”以消除竞态条件，Central API 必须**强制**接收由客户端传入的 `task_id`，**绝不能**在后端提供 `uuid.uuid4()` 兜底生成。
   * **进阶：消除 TaskRegistry 的双 ID 脑裂**：`TaskRegistry.add_task` 必须改为接收外部传入的 `task_id`，废弃其内部自建 UUID 的逻辑，彻底统一 `registry_task_id` 和 `backend_task_id`，实现端到端唯一 TraceID 透传。

**Step 1: 本地事务准备 (Prepare & Deduct)**
```python
import uuid
import asyncio

# 获取并发锁
can_run, err = await check_concurrency_lock(user_id)
if not can_run: raise ConcurrencyLimitError()

# 🚨 核心优化：获取锁之后，后续所有流程必须包裹在 try...finally 中防止锁泄露
task_submitted_successfully = False
try:
    # 🚨 核心优化：前置生成 Task ID，Central API 必须强制接收此 ID
    task_id = str(uuid.uuid4())
    
    # 强同步插入流水，扣除灵石
    success, err = await check_and_deduct_credits(user_id, cost, task_type)
    if not success: 
        raise InsufficientCreditsError()
```

**Step 2: 外部副作用执行与 Saga 补偿 (Execute External Action)**
```python
    # 核心红线：一旦扣费成功，后续的 ANY 操作（包括写 Redis）必须进入 try...except 触发 Saga 补偿
    try:
        # 🚨 致命漏洞修复：必须在扣费成功后的补偿块内写 Redis，防止 Redis 连接失败导致吞钱
        await TaskRegistry.add_task(task_id, user_id, cost, status="pending")
        
        # 调用 Central API（强制透传已生成的 task_id）
        success = await dispatch_to_worker(task_id, task_type, inputs)
        if not success:
            raise ExternalServiceError("API refused connection")
            
        # 派发成功，更新 Registry 状态为处理中
        try:
            await TaskRegistry.update_task_status(task_id, "processing")
        except Exception as redis_err:
            # 🚨 避坑提示：如果 API 调用已成功但状态更新失败，绝对不能触发退款补偿！
            logger.warning(f"Task dispatched successfully but failed to update Redis status: {redis_err}")
            pass

        task_submitted_successfully = True
    except Exception as e:
        # --- Saga 补偿机制触发 ---
        # 仅在明确的外部派发失败（如 Connection Refused/Timeout）时执行退款
        logger.error(f"Saga Execute Failed: {e}")
        # 🚨 使用 shield 免疫外部取消信号，并使用 try 隔离 DB 崩溃异常，确保最终执行并发锁释放
        try:
            await asyncio.shield(refund_credits(user_id, cost, reason=f"Task Failed: {str(e)}"))
        except Exception as refund_err:
            logger.critical(f"REFUND FAILED! Log to Outbox. User: {user_id}, Amount: {cost}, Error: {refund_err}")
            # 写入本地 Outbox/文件...
            
        try:
            await asyncio.shield(TaskRegistry.remove_task(task_id))
        except Exception: pass
        
        raise CoreDomainError("系统派发失败，灵石已全额退还。")
        
finally:
    # 🚨 兜底保障：无论抛出何种异常（含 CancelledError），必须确保并发锁释放
    if not task_submitted_successfully:
        await asyncio.shield(release_concurrency_lock(user_id))
```

**Step 3: 异步状态监控 (Async Monitoring)**
```python
# 任务提交成功后，将监控任务挂载到后台 (不阻塞主线程)
import asyncio
try:
    asyncio.create_task(
        monitor_task_and_release_lock(task_id, user_id, ...)
    )
except Exception as e:
    # 🚨 原子性防范：如果挂载后台任务失败，必须立即释放锁，防止永久死锁
    await release_concurrency_lock(user_id)
    raise CoreDomainError("后台监控挂载失败")
return task_id
```

### 3.2 路由分发器 (Dispatcher) 的简化 (面向跨域业务的 Strategy 基类)
将原来 `core_submit_generation_task` 里长达百行的 `if task_type == 'face_swap': ... elif is_video: ...` 改造为强类型的策略模式（Strategy Pattern）。

**✨ 优化建议**：
为了支撑未来跨域业务（如短剧生成、音频生成等），不要仅仅使用一个巨型的 `get_task_payload` 工厂函数，而是抽象出 `BaseTaskStrategy` 基类，实现**零核心代码修改**接入新业务线。

```python
# src/core/task_dispatcher.py
from abc import ABC, abstractmethod

class BaseTaskStrategy(ABC):
    @abstractmethod
    def get_cost(self, inputs: dict) -> int:
        """根据特定任务的逻辑核算灵石"""
        pass
        
    @abstractmethod
    def build_payload(self, inputs: dict) -> dict:
        """负责将前端参数组装为特定 Worker 需要的 JSON Payload"""
        pass
        
    @abstractmethod
    def get_metadata(self, inputs: dict) -> dict:
        """返回落库所需的标准化 metadata (如 saved_inputs, duration)"""
        pass

class LTXVideoStrategy(BaseTaskStrategy):
    def get_cost(self, inputs: dict) -> int:
        return 12  # 结合规则引擎动态计算
        
    def build_payload(self, inputs: dict) -> dict:
        return {"image": inputs["image"], "prompt": inputs["prompt"]}
        
    def get_metadata(self, inputs: dict) -> dict:
        return {"saved_inputs": [inputs.get("image")]}

class FaceSwapStrategy(BaseTaskStrategy):
    def get_cost(self, inputs: dict) -> int:
        return 2
        
    def build_payload(self, inputs: dict) -> dict:
        return {"face_image": inputs["face_image"], "body_image": inputs["target_image"]}
        
    def get_metadata(self, inputs: dict) -> dict:
        return {"saved_inputs": [inputs.get("target_image"), inputs.get("face_image")]}

# 策略注册表
STRATEGIES = {
    "ltx_video": LTXVideoStrategy(),
    "face_swap": FaceSwapStrategy(),
}

async def dispatch_to_worker(task_id: str, task_type: str, inputs: dict) -> bool:
    """统一的请求发送口"""
    strategy = STRATEGIES.get(task_type)
    if not strategy:
        raise ValueError(f"Unknown task type: {task_type}")
        
    payload = strategy.build_payload(inputs)
    metadata = strategy.get_metadata(inputs)
    
    # 统一落库 TaskRegistry (使用 metadata)
    await register_task_to_db(task_id, task_type, metadata)
    
    # 派发给后端 Central API
    return await image_service.submit_generic_task(task_id, payload)
```

## 4. 验收标准
1. **代码结构验证**：`src/handlers/message_handler.py` 中 `handle_prompt` 行数应缩减至 20 行以内。
2. **隔离性验证**：检索 `src/core/` 目录，不应存在任何 `from telegram import Update` 语句。
3. **容灾验证 (Saga)**：模拟进程瞬间崩溃或客户端主动断开连接（抛出 `CancelledError`），断言并发锁能被释放且 `refund_credits` 成功执行。
4. **全链路 Task ID 验证**：断言 Central API 和底层队列的 Task ID 与 Bot 前置生成的 Task ID 完全一致，且 Central API 去除了后备的 UUID 生成逻辑。

## 5. 关键细节优化补充

在具体实施上述方案时，必须严格落实以下 6 个关键细节，以确保重构的安全性和完整性：

### 5.1 Central API 契约修改的具体落地 (强制 Task ID 透传)
*   **现状**：排查发现 `backend/app/queue_manager.py` 的 `enqueue_task` 方法**已经支持接收** `task_id` 参数 (`def enqueue_task(..., task_id: str = None)`)。
*   **优化方案**：为了杜绝 Pub/Sub 订阅时的竞态条件，修改 `backend/app/models.py` 中的各类 Request 实体，将其 `task_id` 字段变为**必传项**。在 `backend/app/main.py` 的各个路由中，强制要求客户端透传此参数给 `queue_manager.enqueue_task`。**坚决不要做向下兼容（如提供 `uuid.uuid4()` 兜底）**，必须将 `enqueue_task` 签名中的 `task_id: str = None` 默认值删除，从协议层面倒逼链路规范化。

### 5.2 Saga 补偿操作必须使用 `asyncio.shield`
*   **痛点**：现有的 `try...finally` 模式若使用后台任务执行退款，存在进程崩溃导致补偿丢失的风险；如果单纯使用 `await`，在客户端断连时会被 `CancelledError` 打断。
*   **优化方案**：在重构后的 Step 2 (Saga 补偿) 和 `finally` 块中，**必须使用 `await asyncio.shield(refund_credits(...))`** 强同步等待执行完成，确保退款和并发锁释放具有强一致的原子性。

### 5.3 全局动态正则过滤器的预编译与黑盒化收敛
*   **痛点**：FSM `unexpected_input` 需要使用动态生成的正则来拦截主菜单，但菜单名可能包含正则特殊字符。如果每次动态拼接，性能和维护性也会有折损。并且各个 FSM 直接依赖正则对象，耦合度过高。
*   **优化建议**：在 `prompt_router.py` 中，建议**在路由注册完成后的系统启动阶段，统一预编译一次正则对象**。同时对外只暴露 `is_global_menu_command(text)` 工具函数。所有 FSM 文件只需 `if is_global_menu_command(text): return await unexpected_input(...)`，将正则逻辑彻底黑盒化。

### 5.4 计费逻辑与 Strategy 基类的深度结合 (跨域扩展)
*   **痛点**：当前 `task_core.py` 中的 `calculate_task_cost` 函数极其臃肿，充满了各类判断逻辑，且无法轻易复用给新的跨域业务。
*   **优化方案**：务必将动态计费规则下沉至继承自 `BaseTaskStrategy` 的各个子类中，**完全废弃并在 `task_core.py` 中删除原有的 `calculate_task_cost`**。每个具体的 Strategy 类强制实现 `get_cost(inputs)`、`build_payload(inputs)` 和 `get_metadata(inputs)`。这样新增业务（如跨域的短剧生成、音频生成）时，只需新建一个策略类，外层调度器 `dispatch_to_worker` 完全不需要修改。

### 5.5 CallbackQuery 防转圈的微操优化
*   **痛点**：Inline Keyboard 按钮容易因为路由提前 return 或抛错而无限转圈。但在全局统一 `answer` 会破坏特定逻辑的弹窗效果。
*   **优化方案**：不要在全局无条件调用 `answer`。应当将 `await query.answer()` 下推至具体的 FSM 入口函数中。对于正常放行的按钮，建议带上短暂的占位提示和缓存：**`await query.answer(text="⏳ 任务初始化中...", cache_time=2)`**。这样既能消除按钮转圈，提供触觉反馈，又能利用 `cache_time` 实现基础的前端防连点（防抖）。

### 5.6 BackgroundTasks 与并发锁的原子性防范
*   **痛点**：在异步监控任务挂载阶段，如果发生异常（如由于路由层的 Pydantic 校验异常或其他上下文环境错误），导致监控任务未能成功启动，由于前面已经通过了并发检查，这会导致用户的并发锁永久泄露。
*   **优化方案**：必须将 `asyncio.create_task`（或 FastAPI 的 `BackgroundTasks.add_task`）紧贴着任务提交成功后的逻辑，并**包裹在 `try...except` 块中**。如果任务挂载失败，必须在 `except` 块内同步调用 `release_concurrency_lock` 释放并发锁，确保万无一失的原子性。

### 5.7 终极容灾：Outbox 模式与 DB 崩溃兜底
*   **痛点**：在 Saga 补偿的最后一步 `refund_credits` 中，其底层依赖 `session.commit()`。如果在退款时恰好遇到数据库宕机，会抛出异常中断补偿流程，导致紧随其后的 `release_concurrency_lock` 也被跳过。
*   **优化方案**：对每个关键的 Saga 补偿动作进行独立的 `try...except` 隔离。如果 `refund_credits` 抛错，将其记录到本地 Outbox（如 Redis 的 `pending_refunds` 队列或本地文件），由定时任务在数据库恢复后执行兜底重试。**但无论如何，并发锁释放和任务清理逻辑必须执行**。

## 6. 重构优先级建议 (执行路径)

为确保系统稳定性并平滑过渡，建议按以下优先级顺序分批实施重构：

1. **🔥 优先级一：修复高危链路 (Saga 补偿与 Task ID 透传)**
   - 优先落实 `asyncio.shield()` 的 Saga 补偿机制，彻底封堵“吞钱”和“并发锁泄露”漏洞。
   - 实施 `Task ID` 在 Bot 端的前置生成，并强制完成与 Central API 的透传对接，为向 Pub/Sub 架构演进打好地基。

2. **🚀 优先级二：实施架构解耦 (路由与 FSM 改造)**
   - 落地 `@prompt_route` 装饰器机制，拆解 `message_handler.py` 中的巨型分支。
   - 在 `prompt_router.py` 初始化时预编译并暴露全局黑盒化的拦截器，替换各个 FSM 内部的硬编码拦截，消除正则编译崩溃隐患。

3. **🏗️ 优先级三：推进业务隔离 (Facade 与 Strategy 下沉)**
   - 引入 `UserFacade` 和 Pydantic DTO 剥离 `💰 个人中心` 等复杂业务规则。
   - 引入 `BaseTaskStrategy` 策略基类，将 Payload 构建、Metadata 落库和 `calculate_task_cost` 计费规则深度下沉至各业务实现类，实现真正的开闭原则。
