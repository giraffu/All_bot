# Bug 3 修复方案：鉴权拦截异常与 i18n 规范适配

## 1. 问题分析

在正式环境（`tg-bot`）中出现了大量未被捕获的 `AccessDeniedError` 异常追踪（StackTrace）刷屏。核心原因及衍生风险如下：
1. **全局异常逃逸**：`PermissionService` 抛出 `AccessDeniedError` 时，部分未加装饰器的入口（如 `handle_prompt`）没有捕获该异常，导致其被 `python-telegram-bot` 框架视为未处理异常（Unhandled Exception）并打印日志，且用户端无任何响应。
2. **i18n 架构红线违规**：现有的拦截器装饰器（`@with_unified_error_handler`）内部硬编码了中文字符串，违反了项目的多语言（i18n）架构规范。
3. **FSM 状态机死锁风险**：如果仅仅添加一个全局错误处理器（Global Error Handler），在 FSM（状态机）流转中抛出异常时，全局拦截器无法像装饰器那样通过 `return ConversationHandler.END` 优雅退出状态机，会导致用户卡死在当前交互节点。

## 2. 实施方案：分层拦截策略

为彻底解决上述问题，必须采用**分层拦截策略**：
*   **第一层（装饰器层）**：重构现有的 `with_unified_error_handler` 装饰器，接入 `i18n` 动态翻译。它继续负责拦截 FSM 路由中的异常，并正确返回 `ConversationHandler.END`。
*   **第二层（全局兜底层）**：新增 `global_error_handler`，挂载到 `Application` 上。专门捕获游离于装饰器之外的业务异常，进行规范化的错误提示与状态字段的安全清理。

## 3. 代码修改指南

### 修改点一：重构异常处理模块
编辑 `src/handlers/error_handlers.py`，同步改造装饰器并新增全局兜底拦截器：

```python
import functools
import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from src.core.exceptions import AccessDeniedError, DomainException, InsufficientCreditsError
from src.utils import robust_send_message
from src.i18n.translator import get_text
from config import CHANNEL_INVITE_LINK

logger = logging.getLogger(__name__)

def with_unified_error_handler(func):
    """
    第一层：局部装饰器拦截
    捕获 DomainExceptions，适配 i18n 多语言，并安全终止 FSM 状态机。
    """
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            return await func(update, context, *args, **kwargs)
        except InsufficientCreditsError as e:
            if update.effective_chat:
                lang = context.user_data.get('language_code', 'zh') if context.user_data else 'zh'
                chat_id = update.effective_chat.id
                # TODO: 确保 i18n 字典已配置 system.error_insufficient_credits
                msg = get_text("system.error_insufficient_credits", lang, current=e.current, cost=e.cost)
                await robust_send_message(context.bot, chat_id, msg, parse_mode="Markdown")
            return ConversationHandler.END
            
        except AccessDeniedError as e:
            if update.effective_chat:
                lang = context.user_data.get('language_code', 'zh') if context.user_data else 'zh'
                chat_id = update.effective_chat.id
                invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"
                # TODO: 确保 i18n 字典已配置 system.error_access_denied
                msg = get_text("system.error_access_denied", lang, invite_link=invite_link)
                await robust_send_message(context.bot, chat_id, msg, parse_mode="Markdown")
            return ConversationHandler.END
            
        except DomainException as e:
            if update.effective_chat:
                chat_id = update.effective_chat.id
                await robust_send_message(context.bot, chat_id, str(e), parse_mode="Markdown")
            return ConversationHandler.END

    return wrapper

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    第二层：全局异常兜底拦截器
    用于捕获遗漏在装饰器之外的业务异常，适配 i18n 规范，并防止日志污染。
    """
    lang = context.user_data.get('language_code', 'zh') if context.user_data else 'zh'
    
    # 消除 CallbackQuery 的 Loading 状态
    if isinstance(update, Update) and update.callback_query:
        try:
            await update.callback_query.answer()
        except Exception as e:
            logger.debug(f"Failed to answer callback query in error handler: {e}")

    # 安全清理可能存在的全局交互状态字典，防止幽灵死锁（仅清理业务临时数据，保留语言等偏好）
    # 必须置于顶部，防止下方发生异常或 return 导致清理逻辑被跳过
    if context.user_data is not None:
        context.user_data.pop('in_conversation', None)
        keys_to_remove = [k for k in context.user_data.keys() if k.endswith('_data')]
        for k in keys_to_remove:
            context.user_data.pop(k, None)
            
    if isinstance(context.error, InsufficientCreditsError):
        if isinstance(update, Update) and update.effective_chat:
            msg = get_text("system.error_insufficient_credits", lang, current=context.error.current, cost=context.error.cost)
            await robust_send_message(context.bot, update.effective_chat.id, msg, parse_mode="Markdown")
            
    elif isinstance(context.error, AccessDeniedError):
        if isinstance(update, Update) and update.effective_chat:
            invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"
            msg = get_text("system.error_access_denied", lang, invite_link=invite_link)
            await robust_send_message(context.bot, update.effective_chat.id, msg, parse_mode="Markdown")
            
    elif isinstance(context.error, DomainException):
        if isinstance(update, Update) and update.effective_chat:
            await robust_send_message(context.bot, update.effective_chat.id, str(context.error), parse_mode="Markdown")
            
    else:
        logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
        return
```

### 修改点二：注册全局拦截器
在机器人的主启动入口（例如 `src/bot_test.py` 和主环境启动文件）中，确保注册了刚新增的 `global_error_handler`。

```python
from src.handlers.error_handlers import global_error_handler

# ... (在 app = ApplicationBuilder()...build() 之后) ...

app.add_error_handler(global_error_handler)
```

## 4. 后续行动事项 (Action Items)
- [x] **执行代码合并**：按上述规范更新 `src/handlers/error_handlers.py`。
- [x] **补齐装饰器**：前往 `src/handlers/message_handler.py`，为 `handle_prompt` 等核心入口函数添加 `@with_unified_error_handler` 装饰器。
- [x] **完善语言包**：前往 `shared/locales/zh.json` 和 `en.json` 中，补充对应的 `system.error_insufficient_credits` 和 `system.error_access_denied` 翻译键值。
- [ ] **重启生效**：执行安全部署脚本（`safe_deploy.sh`）以平滑重启容器更新内存热更生效代码，使新拦截规则生效。