# 代码重复率 (26.48%) 深度分析与处理建议

## 1. 为什么重复率这么高？(怎么回事)

经过编写专门的脚本对项目进行逐行哈希查重分析，发现 `26.48%` 这个数字主要是由**基础脚手架代码、高频 API 调用和固定 UI 样式**造成的“伪重复”，而非大段的核心业务逻辑被复制粘贴。

具体的重复来源主要分为以下几类：

### 1.1 数据库会话管理 (高频)
大量出现了 `async with AsyncSessionLocal() as session:` 这样的代码（全项目出现了 48 次）。由于代码库中广泛使用原生的 SQLAlchemy 异步会话，导致每个需要查库的核心函数或 Handler 都包含了这行脚手架代码。

### 1.2 异常处理与依赖导入 (高频)
- `raise HTTPException(status_code=500, detail=str(e))` (在 Dashboard 路由中出现了 36 次)
- `from src.core.user_core import get_or_create_user_by_telegram` (出现了 34 次)
- `from src.services.permission_service import permission_service` (出现了 26 次)
- `from src.database.core import AsyncSessionLocal` (出现了 19 次)

### 1.3 Telegram Bot API 交互模板 (中频)
由于这是一个交互式的 Bot，各个 FSM（状态机）节点都需要发送相同的过渡提示和获取上下文：
- `await query.answer(text="⏳ 任务初始化中...", cache_time=2)` (出现了 18 次)
- `await robust_reply_text(update.message, msg, parse_mode="Markdown")` (出现了 17 次)
- `user_id = update.effective_user.id if update.effective_user else "Unknown"` (出现了 16 次)
- `reply_markup = InlineKeyboardMarkup(keyboard)` (出现了 19 次)

### 1.4 前端样式与布局 (中频)
在 Vue Dashboard 中，存在大量相同的栅格布局和基础阴影样式被分散写在各个组件里：
- `<a-col :xs="24" :sm="12" :md="8" :lg="4">` (出现了 25 次)
- `box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.03);` (出现了 14 次)

---

## 2. 处理建议 (无痛优化指南)

基于以上分析，项目目前的健康度其实很不错，没有严重的“复制粘贴坏味道”。这 `26.48%` 更多是框架特性带来的必然冗余。

为了进一步提高代码的整洁度和可维护性，建议在后续开发或技术债清理时，采用以下策略（**目前不需要立刻全面修改**）：

### 建议一：重构数据库会话获取方式 (后端)
**问题**：到处都是 `async with AsyncSessionLocal() as session:` 导致代码缩进变深且重复。
**方案**：
- **在 FastAPI 路由层**：充分利用 `Depends(get_db)` 依赖注入，将 session 作为参数传递给逻辑函数，而不是在函数内部创建。
- **在 Telegram Bot 核心层**：可以实现一个 `@with_db_session` 的装饰器，自动将 `session` 注入到被装饰的异步函数中，彻底消灭这行样板代码。

### 建议二：统一异常处理 (Dashboard)
**问题**：各个接口手动 `try...except... raise HTTPException(status_code=500...)`。
**方案**：
- FastAPI 提供了全局异常捕获机制（Global Exception Handler）。可以注册一个全局捕获 `Exception` 的处理器，统一格式化返回 500 错误，路由函数内部只管写正确的逻辑，去掉大量的 `try-catch` 块。

### 建议三：抽取常量与上下文工具 (Bot 端)
**问题**：硬编码的文案和重复解析 `update`。
**方案**：
- 将 `"⏳ 任务初始化中..."` 等高频交互文案提取到 `src/constants.py`（例如定义为 `MSG_TASK_INIT`），方便后期维护或支持多语言。
- 编写一个辅助函数 `def get_user_id(update: Update) -> int:` 来替代到处写的 `user_id = update.effective_user.id if update.effective_user else "Unknown"`。

### 建议四：前端 CSS 抽象 (Frontend)
**问题**：每个图表组件里都写了一遍相同的 `box-shadow`。
**方案**：
- 在 `assets/main.css` 或基础样式文件中定义 `.card-shadow` 等全局原子类，组件直接使用 `class="card-shadow"` 即可，减少 `<style scoped>` 里的重复代码。

## 结论
`26.48%` 是一个偏向严格的统计结果。实际的**核心业务逻辑重复率非常低**。您可以放心继续当前的开发推进。当需要重构时，优先考虑使用**装饰器**和**依赖注入**来干掉那些基础的模板代码即可。