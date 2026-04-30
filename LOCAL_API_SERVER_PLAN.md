# AllBot Local Telegram API Server 实施方案

## 1. 背景与问题描述

在 AllBot 项目中，`payment-api` 容器在处理支付网关回调（如易支付）并进行订单履约后，需要调用 Telegram Bot API 发送“履约成功”的消息给用户。
当前在 `src/services/payment_fulfillment_service.py` 中，发送消息的逻辑直接使用了 `aiohttp.ClientSession()` 并请求 Telegram 官方服务器（`https://api.telegram.org/bot{bot_token}/sendMessage`）。
由于服务器部署环境（如国内网络限制），直接请求官方服务器会遇到 `Connection timeout` 错误，导致用户无法收到充值成功的通知。

同时，为了解决 Telegram 官方 API 对大文件下载（>20MB）和上传（>50MB）的限制，本项目已经在海外边缘节点（VPS IP: `69.63.220.115`）部署了 Local Telegram API Server。

本方案旨在复用已搭建的 Local Telegram API Server，解决 `payment-api` 的发信超时问题，并统一项目内的 API 调用入口。

## 2. 架构概览

已部署的 Local Telegram API Server 提供以下两个端口服务：
- **8081 端口 (Bot API)**：处理标准的 Bot API 请求（如 `sendMessage`）。基础 URL 格式为：`http://69.63.220.115:8081/bot{bot_token}/`
- **8082 端口 (File API)**：提供大文件直连下载服务。

主机器人 (`tg-bot`) 和客服机器人 (`cs_bot`) 已经通过硬编码 `base_url` 的方式接入了该本地服务，我们需要将 `payment-api` 等独立服务也接入此架构。

## 3. 实施步骤

### 3.1 统一配置 API URL
为了避免在代码中到处硬编码 IP 地址，建议在项目的全局配置文件（如 `config.py`）中统一管理 Telegram API 的基础 URL。

**修改 `config.py`：**
在 `config.py` 中增加或更新 `TELEGRAM_API_BASE_URL` 配置，优先从环境变量读取，默认回退到 Local API Server 的地址。

```python
# config.py
import os

# ... 现有代码 ...

# --- Telegram API Configuration ---
# 默认使用部署好的 Local API Server
TELEGRAM_API_BASE_URL = os.getenv("TELEGRAM_API_BASE_URL", "http://69.63.220.115:8081")
```

### 3.2 修改 `payment_fulfillment_service.py`
将 `payment_fulfillment_service.py` 中硬编码的官方 API URL 替换为使用 `config.py` 中配置的本地 API URL。由于是在本地局域网或受信任的网络间通信，无需再配置代理。

**修改目标文件：`src/services/payment_fulfillment_service.py`**

```python
# 导入 config
from config import TELEGRAM_API_BASE_URL, BOT_TOKEN

# ... 现有代码 ...

async def fulfill_order(out_trade_no: str, external_trade_no: str, paid_amount: float) -> bool:
    # ... 现有履约逻辑 ...
    
    # 替换原有的 telegram_api_url
    # 原代码: telegram_api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # 新代码: 使用 Local API Server 的地址
    telegram_api_url = f"{TELEGRAM_API_BASE_URL}/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": user.telegram_id or user.id,
        "text": success_msg,
        "parse_mode": "HTML"
    }

    try:
        # 直接发起请求，无需 proxy
        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(telegram_api_url, json=payload, timeout=10) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to send TG message, status: {resp.status}, response: {await resp.text()}")
    except Exception as e:
        logger.error(f"Exception while sending TG message: {e}")
        
    # ... 返回履约结果 ...
```

### 3.3 （可选）改造其他独立 API 调用
项目中可能还存在其他独立调用 Telegram API 的地方（如 `auth_core.py` 中的 `send_tg_security_notification`），也应一并检查并统一使用 `TELEGRAM_API_BASE_URL`。

例如 `src/core/auth_core.py`：
```python
# src/core/auth_core.py
from config import TELEGRAM_API_BASE_URL

# ...

async def send_tg_security_notification(...):
    # url = f"http://69.63.220.115:8081/bot{bot_token}/sendMessage"
    url = f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/sendMessage"
    # ...
```

## 4. 验证与测试方案

实施完成后，需要验证 `payment-api` 是否能够成功发送通知：

1. **重启服务**：
   ```bash
   docker-compose restart payment-api
   ```
2. **触发回调测试**：
   在开发环境或测试环境中，手动触发一个支付网关的回调请求到 `payment-api` 的 webhook 接口。
3. **检查日志**：
   使用命令 `docker logs --tail 100 payment-api` 查看日志，确认不再出现 `Connection timeout` 错误。
4. **端到端验证**：
   检查关联的测试 Telegram 账号是否成功收到了“充值/履约成功”的消息推送。

## 5. 安全与运维注意事项

- **网络安全**：暴露在公网（或局域网）的 Local API Server (8081 端口) 应该配置防火墙规则（如 `iptables` 或云厂商安全组），仅允许白名单内的服务器 IP（如本项目所在的服务器）访问，防止被恶意扫描或滥用。
- **超时设置**：在 `aiohttp.ClientSession().post()` 中务必设置 `timeout` 参数（例如 10 秒），防止因 Local API Server 异常卡死导致 `payment-api` 的请求积压。

## 6. 附加修复方案：tg-bot 数据库唯一约束冲突 (UniqueViolationError)

### 6.1 问题回顾
在 `tg-bot` 容器日志中，出现了大量 `asyncpg.exceptions.UniqueViolationError: duplicate key value violates unique constraint "uix_user_post_action"` 的报错。
这发生在用户进行“点赞”或“一键应用”操作时，业务层 `src/core/gallery_core.py` 实际上已经通过捕获 `IntegrityError` 做了防刷处理（预期内异常）。但由于 `src/database/logger.py` 中注册了全局的 SQLAlchemy 事件监听器（`handle_error`），它在底层直接拦截了该错误并以 `ERROR` 级别输出了日志，导致日志被严重污染。

### 6.2 修复步骤
无需修改业务逻辑，只需优化数据库日志监听器，将这类预期的完整性错误降级处理。

**修改目标文件：`src/database/logger.py`**

```python
# src/database/logger.py
from sqlalchemy.exc import IntegrityError
import asyncpg

# ...

@event.listens_for(target_engine, "handle_error")
def handle_error(exception_context):
    # ... 现有获取耗时和 SQL 的逻辑 ...
    
    error_msg = str(exception_context.original_exception)
    
    # 判断是否为预期内的唯一约束冲突
    is_expected_constraint = False
    if isinstance(exception_context.original_exception, IntegrityError) or \
       "UniqueViolationError" in error_msg or \
       "duplicate key value violates unique constraint" in error_msg:
        is_expected_constraint = True

    log_entry = {
        "event": "db_operation",
        "operation_type": op_type,
        "execution_time": datetime.now().isoformat(),
        "duration_ms": round(total * 1000, 2),
        "sql": statement,
        "parameters": str(parameters) if parameters else None,
        "user_id": user_id,
        # 预期内的冲突标记为 warning_db_conflict，而不是 failure
        "status": "warning_db_conflict" if is_expected_constraint else "failure",
        "error": error_msg
    }
    
    # 预期内的唯一约束冲突降级为 WARNING 或 INFO 级别，避免污染 ERROR 日志
    if is_expected_constraint:
        db_logger.warning(json.dumps(log_entry))
    else:
        db_logger.error(json.dumps(log_entry))
```

通过上述修改，日志系统依然会记录这些冲突操作，但只会作为 `WARNING` 输出，不再触发严重的错误告警，保持了业务日志的清晰与健康。