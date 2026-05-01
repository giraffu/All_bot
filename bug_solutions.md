# 核心异常修复与实施方案

根据监控日志分析报告，当前系统存在三个主要异常。以下是针对这三个 Bug 的具体实施方案：

## 1. Web API `ValidationError` (UserResponse 缺少 language_code) [已修复]

**问题分析**：
在 `/api/auth/telegram` 登录接口中抛出 `ValidationError: 1 validation error for UserResponse language_code`。原因是 i18n 重构期间部分存量用户的语言代码为空，而在 `src/web_api/schemas/auth_schema.py` 中，虽然 `language_code` 被声明为 `Optional[str]`，但没有赋予默认值 `= None`。Pydantic 仍会强制要求该字段必须出现在初始化参数中。

**实施方案**：
1. **修改 Pydantic 模型**：在 `src/web_api/schemas/auth_schema.py` 中为缺失默认值的可选字段赋默认值。
2. **显式透传字段**：在 `src/web_api/routers/auth.py` 构造响应时显式传入该字段。

**代码修改**：
```python
# src/web_api/schemas/auth_schema.py
class UserResponse(BaseModel):
    id: int
    telegram_id: Optional[int] = None      # 补充 = None
    username: Optional[str] = None         # 补充 = None
    full_name: Optional[str] = None        # 补充 = None
    language_code: Optional[str] = None    # 补充 = None
    # ...
```

```python
# src/web_api/routers/auth.py (login_telegram 和 login_with_password 接口中分别补充)
user_response_data = UserResponse(
    id=user.id,
    telegram_id=user.telegram_id,
    username=user.username,
    full_name=user.full_name,
    language_code=user.language_code,  # 显式透传语言字段，解决两个接口的报错
    # ...
)
```

---

## 2. 测试环境 `TypeError` (check_access 参数数量不匹配)

**问题分析**：
在 `tg-bot-test` 中出现 `TypeError: PermissionService.check_access() takes from 4 to 5 positional arguments but 6 were given`。
经全局代码排查，本地代码库已经完成了 `PermissionService.check_access` 签名的精简重构（去除了冗余参数，当前仅接受 4~5 个位置参数），且本地 `message_handler.py` 的调用也已对齐。
此报错系**容器内运行了陈旧的字节码或未同步最新代码**导致（Python 进程内存中的旧版本 `.pyc` 仍尝试传递 6 个参数）。

**实施方案**：
无需修改本地代码，直接重启或重建测试环境容器即可刷新运行态。

**执行命令**：
```bash
# 推荐：使用自带的安全部署脚本（能自动处理维护模式和清理僵尸任务）
bash ./safe_deploy.sh

# 或者：重启测试容器，强制重新加载最新代码
docker restart tg-bot-test

# 或彻底重建测试容器（以防卷挂载异常）
docker-compose -f deploy/docker-compose-test.yml down
docker-compose -f deploy/docker-compose-test.yml up -d --build
```

---

## 3. 鉴权拦截导致 `AccessDeniedError` 刷屏

**问题分析**：
正式环境 `tg-bot` 中出现大量未被捕获的 `AccessDeniedError` 异常追踪（StackTrace）。
`PermissionService` 在权限校验失败时主动抛出了该业务异常（继承自 `DomainException`），但 `python-telegram-bot` 的 `Application` 没有注册全局的 Error Handler，导致框架将其当作 Unhandled Exception 抛出，既污染了日志，也没有给用户发送友好的阻断提示。
此外，原本硬编码的中文字符串在当前多语言（i18n）架构规范下属于反模式。

**实施方案**：
1. **接入统一翻译器**：为符合 i18n 规范，通过 `src.i18n.translator` 的 `get_text` 动态获取提示文案。
2. **复用现有 Error Handler**：直接在现有的 `src/handlers/error_handlers.py` 中新增 `global_error_handler` 函数，使用 i18n 返回提示，并复用状态机清理逻辑。
3. **注册全局异常处理器**：在 Bot 启动文件（`src/bot_test.py` 等入口）中，将该拦截器绑定至 `Application`。

**代码修改**：
```python
# 修改现有文件: src/handlers/error_handlers.py
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from src.core.exceptions import AccessDeniedError, DomainException, InsufficientCreditsError
from src.utils import robust_send_message
from src.i18n.translator import get_text
from config import CHANNEL_INVITE_LINK

logger = logging.getLogger(__name__)

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """全局异常拦截器，用于替代装饰器捕获遗漏的业务异常，并适配 i18n 规范"""
    # 获取用户语言偏好，默认为 zh
    lang = context.user_data.get('language_code', 'zh') if context.user_data else 'zh'
    
    if isinstance(context.error, InsufficientCreditsError):
        if isinstance(update, Update) and update.effective_chat:
            # TODO: 确保在 i18n 的 json 文件中配置 error.insufficient_credits 对应的 key
            msg = get_text("error.insufficient_credits", lang, current=context.error.current, cost=context.error.cost)
            await robust_send_message(context.bot, update.effective_chat.id, msg, parse_mode="Markdown")
            
    elif isinstance(context.error, AccessDeniedError):
        if isinstance(update, Update) and update.effective_chat:
            invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"
            # TODO: 确保在 i18n 的 json 文件中配置 error.access_denied 对应的 key
            msg = get_text("error.access_denied", lang, invite_link=invite_link)
            await robust_send_message(context.bot, update.effective_chat.id, msg, parse_mode="Markdown")
            
    elif isinstance(context.error, DomainException):
        if isinstance(update, Update) and update.effective_chat:
            await robust_send_message(context.bot, update.effective_chat.id, str(context.error), parse_mode="Markdown")
            
    else:
        logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
        return

    # 安全清理可能存在的 FSM 状态上下文，防止死锁（保留用户偏好）
    if context.user_data is not None:
        context.user_data.pop('in_conversation', None)
        # 仅清理以 _data 结尾的状态机临时字典
        keys_to_remove = [k for k in context.user_data.keys() if k.endswith('_data')]
        for k in keys_to_remove:
            context.user_data.pop(k, None)
```

```python
# 修改入口文件: src/bot_test.py (在 main 函数的 app 构建之后)
from src.handlers.error_handlers import global_error_handler

# ...
app = (
    ApplicationBuilder()
    # ...
    .build()
)

# 注册全局异常处理器 (注意变量名是 app 而不是 application)
app.add_error_handler(global_error_handler)
```