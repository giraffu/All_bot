# 全局静态分析与代码质量评估报告 (Code Analysis Report)

## 📊 可量化指标 (Metrics)

- **Total Lines of Code**: 19089
- **Average Complexity (Cyclomatic)**: 4.69
- **Dead Code Ratio**: 0.39% (est.)
- **Code Duplication Rate**: 0.31% (est.)
- **Total Issues**: 287

## 🏗️ 架构问题与重构建议 (Architecture & Refactoring)

✅ 未发现明显的架构层隔离违规问题。

## 📋 问题清单 (Issue Details by File)

### 📁 `backend/app/main.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 56 | 🟠 High | Scope Issue | Using the global statement |
| 190 | 🟡 Medium | Code Smell | Too many local variables (22/15) |
| 190 | 🟡 Medium | Code Smell | Too many statements (64/50) |

### 📁 `backend/app/models.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 2 | 🟢 Low | Import Optimization | standard import "typing.Optional" should be placed before third party import "pydantic.BaseModel" |
| 3 | 🟢 Low | Import Optimization | standard import "enum.Enum" should be placed before third party import "pydantic.BaseModel" |

### 📁 `backend/app/queue_manager.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 3 | 🟢 Low | Unused Import | Unused import uuid |

### 📁 `backend/app/routers/agent.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 46 | 🟠 High | Scope Issue | Redefining name 'settings' from outer scope (line 9) |
| 59 | 🟡 Medium | Dead Code | unused variable 'authorized' (100% confidence) |
| 81 | 🟡 Medium | Dead Code | unused variable 'authorized' (100% confidence) |
| 92 | 🟡 Medium | Dead Code | unused variable 'authorized' (100% confidence) |
| 110 | 🟡 Medium | Dead Code | unused variable 'authorized' (100% confidence) |
| 124 | 🟡 Medium | Dead Code | unused variable 'authorized' (100% confidence) |
| 136 | 🟡 Medium | Dead Code | unused variable 'authorized' (100% confidence) |
| 3 | 🟢 Low | Import Optimization | standard import "typing.Optional" should be placed before third party imports "fastapi.APIRouter", "pydantic.BaseModel" |
| 4 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party imports "fastapi.APIRouter", "pydantic.BaseModel" |
| 46 | 🟢 Low | Import Optimization | Reimport 'settings' (imported line 9) |

### 📁 `backend/tests/conftest.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 25 | 🟠 High | Scope Issue | Redefining name 'mock_queue_manager' from outer scope (line 10) |
| 2 | 🟢 Low | Import Optimization | standard import "unittest.mock.AsyncMock" should be placed before third party import "pytest" |

### 📁 `backend/tests/test_t2i_pornmaster.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 2 | 🟢 Low | Import Optimization | standard import "unittest.mock.patch" should be placed before third party import "pytest" |

### 📁 `cs_bot/bot.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 42 | 🟡 Medium | Dead Code | unused variable 'out' (100% confidence) |
| 98 | 🟡 Medium | Code Smell | Too many local variables (22/15) |
| 98 | 🟡 Medium | Code Smell | Too many branches (18/12) |
| 98 | 🟡 Medium | Code Smell | Too many statements (57/50) |
| 215 | 🟡 Medium | Code Smell | Too many branches (13/12) |
| 5 | 🟢 Low | Import Optimization | standard import "time" should be placed before third party import "httpx" |
| 6 | 🟢 Low | Import Optimization | standard import "collections.defaultdict" should be placed before third party import "httpx" |
| 14 | 🟢 Low | Import Optimization | standard import "re" should be placed before third party imports "httpx", "dotenv.load_dotenv", "telegram.Update" (...) "telegram.request.HTTPXRequest", "langgraph_client.get_langgraph_reply", "db.init_db" |

### 📁 `cs_bot/db.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 37 | 🟡 Medium | Code Smell | Too many arguments (8/5) |
| 2 | 🟢 Low | Import Optimization | standard import "os" should be placed before third party import "aiosqlite" |
| 3 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party import "aiosqlite" |
| 4 | 🟢 Low | Import Optimization | standard import "json" should be placed before third party import "aiosqlite" |

### 📁 `cs_bot/skill_manager.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 37 | 🟠 High | Scope Issue | Redefining name 'importlib' from outer scope (line 3) |
| 38 | 🟠 High | Scope Issue | Redefining name 'inspect' from outer scope (line 4) |
| 4 | 🟡 Medium | Dead Code | unused import 'inspect' (90% confidence) |
| 38 | 🟡 Medium | Dead Code | unused import 'inspect' (90% confidence) |
| 3 | 🟢 Low | Unused Import | Unused import importlib.util |
| 4 | 🟢 Low | Unused Import | Unused import inspect |
| 6 | 🟢 Low | Unused Import | Unused tool imported from langchain_core.tools |
| 38 | 🟢 Low | Import Optimization | Reimport 'inspect' (imported line 4) |

### 📁 `dashboard/backend/routers/gallery.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 24 | 🟡 Medium | Code Smell | Too many arguments (6/5) |
| 3 | 🟢 Low | Unused Import | Unused func imported from sqlalchemy |
| 3 | 🟢 Low | Unused Import | Unused desc imported from sqlalchemy |
| 3 | 🟢 Low | Unused Import | Unused update imported from sqlalchemy |
| 3 | 🟢 Low | Unused Import | Unused delete imported from sqlalchemy |
| 4 | 🟢 Low | Unused Import | Unused selectinload imported from sqlalchemy.orm |
| 5 | 🟢 Low | Import Optimization | standard import "typing.Optional" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select", "sqlalchemy.orm.selectinload" |
| 5 | 🟢 Low | Unused Import | Unused List imported from typing |
| 5 | 🟢 Low | Unused Import | Unused Dict imported from typing |
| 5 | 🟢 Low | Unused Import | Unused Any imported from typing |
| 6 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select", "sqlalchemy.orm.selectinload" |
| 8 | 🟢 Low | Unused Import | Unused User imported from src.database.models |
| 8 | 🟢 Low | Unused Import | Unused History imported from src.database.models |
| 10 | 🟢 Low | Import Optimization | third party import "pydantic.BaseModel" should be placed before first party imports "src.database.core.get_db", "src.database.models.GalleryPost", "src.services.storage.storage"  |
| 11 | 🟢 Low | Import Optimization | standard import "datetime.datetime" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select", "sqlalchemy.orm.selectinload", "pydantic.BaseModel" and first party imports "src.database.core.get_db", "src.database.models.GalleryPost", "src.services.storage.storage"  |
| 11 | 🟢 Low | Unused Import | Unused datetime imported from datetime |

### 📁 `dashboard/backend/routers/history.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 17 | 🟡 Medium | Code Smell | Too many arguments (7/5) |
| 17 | 🟡 Medium | Code Smell | Too many local variables (23/15) |
| 17 | 🟡 Medium | Code Smell | Too many branches (13/12) |
| 4 | 🟢 Low | Import Optimization | standard import "typing.Optional" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select" |
| 5 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select" |
| 6 | 🟢 Low | Import Optimization | standard import "os" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select" |
| 6 | 🟢 Low | Unused Import | Unused import os |
| 10 | 🟢 Low | Import Optimization | Imports from package src are not grouped |

### 📁 `dashboard/backend/routers/logs.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 12 | 🟡 Medium | Code Smell | Too many arguments (6/5) |
| 2 | 🟢 Low | Import Optimization | standard import "typing.Optional" should be placed before third party import "fastapi.APIRouter" |
| 3 | 🟢 Low | Import Optimization | standard import "datetime.datetime" should be placed before third party import "fastapi.APIRouter" |
| 4 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party import "fastapi.APIRouter" |

### 📁 `dashboard/backend/routers/plans.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 81 | 🟡 Medium | Code Smell | Too many arguments (6/5) |
| 81 | 🟡 Medium | Code Smell | Too many local variables (17/15) |
| 4 | 🟢 Low | Import Optimization | standard import "typing.Optional" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select" |
| 5 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select" |

### 📁 `dashboard/backend/routers/referrals.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 15 | 🟡 Medium | Code Smell | Too many local variables (27/15) |
| 15 | 🟡 Medium | Code Smell | Too many statements (57/50) |
| 3 | 🟢 Low | Unused Import | Unused and_ imported from sqlalchemy |
| 7 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select", "sqlalchemy.orm.aliased" and first party imports "src.database.core.get_db", "src.database.models.User"  |

### 📁 `dashboard/backend/routers/stats.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 29 | 🟠 High | Scope Issue | Using global for '_exchange_rates_cache' but no assignment is done |
| 65 | 🟡 Medium | Code Smell | Too many local variables (127/15) |
| 65 | 🟡 Medium | Code Smell | Too many branches (46/12) |
| 65 | 🟡 Medium | Code Smell | Too many statements (209/50) |
| 463 | 🟡 Medium | Code Smell | Too many local variables (25/15) |
| 463 | 🟡 Medium | Code Smell | Too many branches (20/12) |
| 463 | 🟡 Medium | Code Smell | Too many statements (63/50) |
| 559 | 🟡 Medium | Code Smell | Too many local variables (25/15) |
| 559 | 🟡 Medium | Code Smell | Too many branches (18/12) |
| 559 | 🟡 Medium | Code Smell | Too many statements (60/50) |
| 723 | 🟡 Medium | Code Smell | Too many local variables (93/15) |
| 723 | 🟡 Medium | Code Smell | Too many branches (47/12) |
| 723 | 🟡 Medium | Code Smell | Too many statements (195/50) |
| 4 | 🟢 Low | Import Optimization | standard import "datetime.datetime" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select" |
| 5 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select" |
| 6 | 🟢 Low | Import Optimization | standard import "os" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select" |
| 7 | 🟢 Low | Import Optimization | standard import "time" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select" |

### 📁 `dashboard/backend/routers/system.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 150 | 🟡 Medium | Code Smell | Too many local variables (19/15) |
| 150 | 🟡 Medium | Code Smell | Too many branches (19/12) |
| 150 | 🟡 Medium | Code Smell | Too many statements (56/50) |
| 5 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select", "httpx" |
| 11 | 🟢 Low | Import Optimization | third party import "fastapi.responses.StreamingResponse" should be placed before first party imports "src.database.core.get_db", "src.database.models.User", "src.core.task_core.get_system_task_stats", "src.services.image_service.image_service", "config.API_BASE"  |
| 11 | 🟢 Low | Import Optimization | Imports from package fastapi are not grouped |
| 13 | 🟢 Low | Import Optimization | third party import "pydantic.BaseModel" should be placed before first party imports "src.database.core.get_db", "src.database.models.User", "src.core.task_core.get_system_task_stats", "src.services.image_service.image_service", "config.API_BASE"  |

### 📁 `dashboard/backend/routers/templates.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 4 | 🟢 Low | Import Optimization | standard import "typing.List" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select" |
| 5 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select" |
| 6 | 🟢 Low | Import Optimization | standard import "os" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select" |
| 10 | 🟢 Low | Import Optimization | Imports from package src are not grouped |

### 📁 `dashboard/backend/routers/users.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 215 | 🟡 Medium | Code Smell | Too many local variables (18/15) |
| 5 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select", "sqlalchemy.orm.selectinload" |
| 6 | 🟢 Low | Import Optimization | standard import "json" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select", "sqlalchemy.orm.selectinload" |
| 7 | 🟢 Low | Import Optimization | standard import "uuid" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select", "sqlalchemy.orm.selectinload" |
| 8 | 🟢 Low | Import Optimization | standard import "os" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select", "sqlalchemy.orm.selectinload" |
| 8 | 🟢 Low | Unused Import | Unused import os |
| 9 | 🟢 Low | Import Optimization | standard import "datetime.datetime" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select", "sqlalchemy.orm.selectinload" |
| 9 | 🟢 Low | Unused Import | Unused timedelta imported from datetime |
| 13 | 🟢 Low | Import Optimization | Imports from package src are not grouped |

### 📁 `dashboard/backend/routers/workers.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 4 | 🟢 Low | Import Optimization | standard import "typing.Optional" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.ext.asyncio.AsyncSession", "sqlalchemy.select" |

### 📁 `dashboard/backend/schemas.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 2 | 🟢 Low | Import Optimization | standard import "datetime.datetime" should be placed before third party import "pydantic.BaseModel" |
| 3 | 🟢 Low | Import Optimization | standard import "typing.Optional" should be placed before third party import "pydantic.BaseModel" |

### 📁 `dashboard/backend/services/worker_listener.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 47 | 🟡 Medium | Code Smell | Too many local variables (29/15) |
| 47 | 🟡 Medium | Code Smell | Too many branches (17/12) |
| 47 | 🟡 Medium | Code Smell | Too many statements (65/50) |

### 📁 `src/api_client.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 315 | 🟠 High | Scope Issue | Redefining name 'httpx' from outer scope (line 3) |
| 68 | 🟡 Medium | Code Smell | Too many arguments (8/5) |
| 88 | 🟡 Medium | Code Smell | Too many arguments (8/5) |
| 107 | 🟡 Medium | Code Smell | Too many arguments (9/5) |
| 128 | 🟡 Medium | Code Smell | Too many arguments (6/5) |
| 156 | 🟡 Medium | Code Smell | Too many arguments (8/5) |
| 206 | 🟡 Medium | Code Smell | Too many arguments (7/5) |
| 228 | 🟡 Medium | Code Smell | Too many arguments (6/5) |
| 245 | 🟡 Medium | Code Smell | Too many arguments (8/5) |
| 296 | 🟡 Medium | Code Smell | Too many local variables (18/15) |
| 296 | 🟡 Medium | Code Smell | Too many branches (23/12) |
| 296 | 🟡 Medium | Code Smell | Too many statements (79/50) |
| 4 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party import "httpx" |
| 5 | 🟢 Low | Import Optimization | standard import "uuid" should be placed before third party import "httpx" |
| 6 | 🟢 Low | Import Optimization | standard import "typing.Optional" should be placed before third party import "httpx" |
| 16 | 🟢 Low | Import Optimization | Imports from package src are not grouped |
| 23 | 🟢 Low | Import Optimization | third party import "asgi_correlation_id.correlation_id" should be placed before first party imports "src.utils.async_retry", "config.IMG2IMG_ENDPOINT", "src.circuit_breaker.CircuitBreaker"  |
| 315 | 🟢 Low | Import Optimization | Reimport 'httpx' (imported line 3) |

### 📁 `src/bot_test.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 40 | 🟠 High | Scope Issue | Redefining name 'urlparse' from outer scope (line 23) |
| 68 | 🟠 High | Scope Issue | Redefining name 'logger' from outer scope (line 30) |
| 79 | 🟠 High | Scope Issue | Redefining name 'logger' from outer scope (line 30) |
| 114 | 🟠 High | Scope Issue | Redefining name 'logger' from outer scope (line 30) |
| 122 | 🟠 High | Scope Issue | Redefining name 'logger' from outer scope (line 30) |
| 22 | 🟡 Medium | Dead Code | unused import 'socket' (90% confidence) |
| 34 | 🟡 Medium | Code Smell | Too many arguments (6/5) |
| 120 | 🟡 Medium | Code Smell | Too many local variables (20/15) |
| 120 | 🟡 Medium | Code Smell | Too many statements (52/50) |
| 12 | 🟢 Low | Import Optimization | standard import "uuid" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id" |
| 13 | 🟢 Low | Import Optimization | Imports from package telegram are not grouped |
| 14 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id", "telegram.request.HTTPXRequest" |
| 15 | 🟢 Low | Import Optimization | standard import "os" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id", "telegram.request.HTTPXRequest" |
| 22 | 🟢 Low | Import Optimization | standard import "socket" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id", "telegram.request.HTTPXRequest" and first party imports "src.logger.setup_logging", "src.handlers.command_handler.start", "src.handlers.message_handler.handle_photo", "src.handlers.callback_handler.handle_callback_query", "src.database.core.init_db"  |
| 22 | 🟢 Low | Unused Import | Unused import socket |
| 23 | 🟢 Low | Import Optimization | standard import "urllib.parse.urlparse" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id", "telegram.request.HTTPXRequest" and first party imports "src.logger.setup_logging", "src.handlers.command_handler.start", "src.handlers.message_handler.handle_photo", "src.handlers.callback_handler.handle_callback_query", "src.database.core.init_db"  |
| 23 | 🟢 Low | Unused Import | Unused urlparse imported from urllib.parse |
| 26 | 🟢 Low | Import Optimization | third party import "telegram.File" should be placed before first party imports "src.logger.setup_logging", "src.handlers.command_handler.start", "src.handlers.message_handler.handle_photo", "src.handlers.callback_handler.handle_callback_query", "src.database.core.init_db"  |
| 26 | 🟢 Low | Import Optimization | Imports from package telegram are not grouped |
| 27 | 🟢 Low | Import Optimization | third party import "httpx" should be placed before first party imports "src.logger.setup_logging", "src.handlers.command_handler.start", "src.handlers.message_handler.handle_photo", "src.handlers.callback_handler.handle_callback_query", "src.database.core.init_db"  |
| 28 | 🟢 Low | Import Optimization | Reimport 'os' (imported line 15) |
| 28 | 🟢 Low | Import Optimization | standard import "os" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id", "telegram.request.HTTPXRequest", "telegram.File", "httpx" and first party imports "src.logger.setup_logging", "src.handlers.command_handler.start", "src.handlers.message_handler.handle_photo", "src.handlers.callback_handler.handle_callback_query", "src.database.core.init_db"  |
| 28 | 🟢 Low | Import Optimization | Imports from package os are not grouped |
| 29 | 🟢 Low | Import Optimization | Reimport 'logging' (imported line 14) |
| 29 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id", "telegram.request.HTTPXRequest", "telegram.File", "httpx" and first party imports "src.logger.setup_logging", "src.handlers.command_handler.start", "src.handlers.message_handler.handle_photo", "src.handlers.callback_handler.handle_callback_query", "src.database.core.init_db"  |
| 29 | 🟢 Low | Import Optimization | Imports from package logging are not grouped |
| 40 | 🟢 Low | Import Optimization | Reimport 'urlparse' (imported line 23) |
| 59 | 🟢 Low | Import Optimization | standard import "asyncio" should be placed before third party imports "telegram.ext.ApplicationBuilder", "telegram.Update", "asgi_correlation_id.correlation_id", "telegram.request.HTTPXRequest", "telegram.File", "httpx" and first party imports "src.logger.setup_logging", "src.handlers.command_handler.start", "src.handlers.message_handler.handle_photo", "src.handlers.callback_handler.handle_callback_query", "src.database.core.init_db"  |
| 60 | 🟢 Low | Import Optimization | Imports from package src are not grouped |

### 📁 `src/constants.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 170 | 🟡 Medium | Code Smell | Too many local variables (23/15) |

### 📁 `src/core/billing_core.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 80 | 🟡 Medium | Code Smell | Too many local variables (16/15) |
| 4 | 🟢 Low | Unused Import | Unused AsyncSessionLocal imported from src.database.core |
| 5 | 🟢 Low | Unused Import | Unused User imported from src.database.models |
| 77 | 🟢 Low | Import Optimization | standard import "datetime.datetime" should be placed before first party imports "src.database.core.AsyncSessionLocal", "src.database.models.User", "src.services.redis_client.redis_client", "src.constants.MAX_CONCURRENT_TASKS", "src.quota.QuotaManager"  |
| 78 | 🟢 Low | Import Optimization | standard import "math" should be placed before first party imports "src.database.core.AsyncSessionLocal", "src.database.models.User", "src.services.redis_client.redis_client", "src.constants.MAX_CONCURRENT_TASKS", "src.quota.QuotaManager"  |

### 📁 `src/core/gallery_core.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 48 | 🟡 Medium | Code Smell | Too many arguments (6/5) |
| 48 | 🟡 Medium | Code Smell | Too many local variables (28/15) |
| 48 | 🟡 Medium | Code Smell | Too many branches (13/12) |
| 48 | 🟡 Medium | Code Smell | Too many statements (53/50) |
| 213 | 🟡 Medium | Code Smell | Too many arguments (10/5) |
| 213 | 🟡 Medium | Code Smell | Too many local variables (22/15) |
| 213 | 🟡 Medium | Code Smell | Too many branches (20/12) |
| 213 | 🟡 Medium | Code Smell | Too many statements (57/50) |
| 4 | 🟢 Low | Unused Import | Unused import asyncio |

### 📁 `src/core/task_core.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 185 | 🟠 High | Scope Issue | Redefining name 'UserLogger' from outer scope (line 6) |
| 43 | 🟡 Medium | Code Smell | Too many arguments (9/5) |
| 43 | 🟡 Medium | Code Smell | Too many local variables (21/15) |
| 103 | 🟡 Medium | Code Smell | Too many arguments (10/5) |
| 103 | 🟡 Medium | Code Smell | Too many local variables (49/15) |
| 103 | 🟡 Medium | Code Smell | Too many branches (30/12) |
| 103 | 🟡 Medium | Code Smell | Too many statements (109/50) |
| 1 | 🟢 Low | Unused Import | Unused List imported from typing |
| 29 | 🟢 Low | Import Optimization | Imports from package src are not grouped |
| 30 | 🟢 Low | Unused Import | Unused TASK_COSTS imported from src.constants |
| 30 | 🟢 Low | Unused Import | Unused RESOLUTION_COST imported from src.constants |
| 30 | 🟢 Low | Unused Import | Unused DURATION_MULTIPLIER imported from src.constants |
| 30 | 🟢 Low | Unused Import | Unused MODE_I2I_PRO imported from src.constants |
| 30 | 🟢 Low | Unused Import | Unused MODE_FACESWAP_STEP1 imported from src.constants |
| 30 | 🟢 Low | Unused Import | Unused LTX_RESOLUTION_COST imported from src.constants |
| 30 | 🟢 Low | Unused Import | Unused LTX_DURATION_MULTIPLIER imported from src.constants |
| 185 | 🟢 Low | Import Optimization | Reimport 'UserLogger' (imported line 6) |

### 📁 `src/core/task_dispatcher.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 139 | 🟡 Medium | Code Smell | Too many local variables (18/15) |
| 139 | 🟡 Medium | Code Smell | Too many branches (14/12) |

### 📁 `src/core/user_core.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 3 | 🟢 Low | Import Optimization | standard import "datetime.datetime" should be placed before third party imports "sqlalchemy.select", "sqlalchemy.exc.IntegrityError" |
| 8 | 🟢 Low | Import Optimization | standard import "typing.Tuple" should be placed before third party imports "sqlalchemy.select", "sqlalchemy.exc.IntegrityError" and first party imports "src.database.core.AsyncSessionLocal", "src.database.models.User"  |

### 📁 `src/core/user_facade.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 19 | 🟡 Medium | Code Smell | Too many local variables (22/15) |
| 2 | 🟢 Low | Import Optimization | standard import "typing.Dict" should be placed before third party import "pydantic.BaseModel" |
| 2 | 🟢 Low | Unused Import | Unused Optional imported from typing |

### 📁 `src/handlers/callback_handler.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 12 | 🟡 Medium | Dead Code | unused import 'billing_callbacks' (90% confidence) |
| 12 | 🟡 Medium | Dead Code | unused import 'gallery_callbacks' (90% confidence) |
| 12 | 🟡 Medium | Dead Code | unused import 'misc_callbacks' (90% confidence) |

### 📁 `src/handlers/prompt_router.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 🟡 Medium | Dead Code | unused import 'Awaitable' (90% confidence) |

### 📁 `src/logger.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 107 | 🟡 Medium | Code Smell | Too many arguments (8/5) |

### 📁 `src/payment_api_server.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 5 | 🟢 Low | Import Optimization | standard import "os" should be placed before third party imports "fastapi.FastAPI", "fastapi.responses.HTMLResponse", "uvicorn" |

### 📁 `src/quota.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 159 | 🟠 High | Scope Issue | Redefining name 'func' from outer scope (line 2) |
| 164 | 🟡 Medium | Dead Code | unused variable 'new_full_name' (100% confidence) |
| 8 | 🟢 Low | Import Optimization | third party import "sqlalchemy.exc.IntegrityError" should be placed before local imports "database.core.AsyncSessionLocal", "database.models.User", "services.log_service.LogService", "constants.GENERATION_TASK_TYPES" |
| 159 | 🟢 Low | Import Optimization | Reimport 'func' (imported line 2) |

### 📁 `src/utils.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 160 | 🟠 High | Scope Issue | Redefining name 'asyncio' from outer scope (line 1) |
| 160 | 🟢 Low | Import Optimization | Reimport 'asyncio' (imported line 1) |

### 📁 `src/web_api/dependencies.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 30 | 🟡 Medium | Code Smell | Too many local variables (17/15) |

### 📁 `src/web_api/main.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 15 | 🟠 High | Scope Issue | Redefining name 'app' from outer scope (line 23) |
| 5 | 🟢 Low | Import Optimization | standard import "contextlib.asynccontextmanager" should be placed before third party imports "fastapi.FastAPI", "fastapi.middleware.cors.CORSMiddleware", "asgi_correlation_id.CorrelationIdMiddleware" |

### 📁 `src/web_api/routers/auth.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 2 | 🟢 Low | Unused Import | Unused Optional imported from typing |
| 4 | 🟢 Low | Unused Import | Unused JSONResponse imported from fastapi.responses |
| 7 | 🟢 Low | Unused Import | Unused Token imported from src.web_api.schemas.auth_schema |

### 📁 `src/web_api/routers/gallery.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 68 | 🟡 Medium | Code Smell | Too many arguments (8/5) |
| 68 | 🟡 Medium | Code Smell | Too many local variables (28/15) |
| 157 | 🟡 Medium | Code Smell | Too many local variables (28/15) |
| 244 | 🟡 Medium | Code Smell | Too many local variables (30/15) |
| 4 | 🟢 Low | Import Optimization | standard import "typing.List" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.select", "sqlalchemy.exc.IntegrityError" |
| 4 | 🟢 Low | Unused Import | Unused List imported from typing |
| 12 | 🟢 Low | Unused Import | Unused redis_client imported from src.services.redis_client |
| 13 | 🟢 Low | Import Optimization | standard import "json" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.select", "sqlalchemy.exc.IntegrityError" and first party imports "src.database.core.AsyncSessionLocal", "src.database.models.GalleryPost", "src.web_api.dependencies.get_current_user" (...) "src.config_mapping.ALL_LORA_MODELS", "src.constants.MODE_NAME_MAP", "src.services.redis_client.redis_client"  |
| 14 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.select", "sqlalchemy.exc.IntegrityError" and first party imports "src.database.core.AsyncSessionLocal", "src.database.models.GalleryPost", "src.web_api.dependencies.get_current_user" (...) "src.config_mapping.ALL_LORA_MODELS", "src.constants.MODE_NAME_MAP", "src.services.redis_client.redis_client"  |
| 15 | 🟢 Low | Import Optimization | standard import "os" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.select", "sqlalchemy.exc.IntegrityError" and first party imports "src.database.core.AsyncSessionLocal", "src.database.models.GalleryPost", "src.web_api.dependencies.get_current_user" (...) "src.config_mapping.ALL_LORA_MODELS", "src.constants.MODE_NAME_MAP", "src.services.redis_client.redis_client"  |
| 15 | 🟢 Low | Unused Import | Unused import os |
| 16 | 🟢 Low | Import Optimization | standard import "re" should be placed before third party imports "fastapi.APIRouter", "sqlalchemy.select", "sqlalchemy.exc.IntegrityError" and first party imports "src.database.core.AsyncSessionLocal", "src.database.models.GalleryPost", "src.web_api.dependencies.get_current_user" (...) "src.config_mapping.ALL_LORA_MODELS", "src.constants.MODE_NAME_MAP", "src.services.redis_client.redis_client"  |
| 17 | 🟢 Low | Unused Import | Unused storage imported from src.services.storage |
| 495 | 🟢 Low | Import Optimization | Imports from package src are not grouped |
| 495 | 🟢 Low | Unused Import | Unused toggle_like imported from src.core.gallery_core |
| 495 | 🟢 Low | Unused Import | Unused DuplicateInteractionError imported from src.core.gallery_core |

### 📁 `src/web_api/routers/storage.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 3 | 🟢 Low | Unused Import | Unused status imported from fastapi |
| 4 | 🟢 Low | Import Optimization | standard import "typing.Optional" should be placed before third party import "fastapi.APIRouter" |
| 4 | 🟢 Low | Unused Import | Unused Optional imported from typing |
| 5 | 🟢 Low | Import Optimization | standard import "datetime.datetime" should be placed before third party import "fastapi.APIRouter" |

### 📁 `src/web_api/routers/tasks.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 77 | 🟠 High | Scope Issue | Redefining name 'httpx' from outer scope (line 4) |
| 155 | 🟠 High | Scope Issue | Redefining name 'status' from outer scope (line 6) |
| 71 | 🟡 Medium | Code Smell | Too many statements (119/50) |
| 90 | 🟡 Medium | Code Smell | Too many local variables (23/15) |
| 90 | 🟡 Medium | Code Smell | Too many branches (29/12) |
| 90 | 🟡 Medium | Code Smell | Too many statements (111/50) |
| 4 | 🟢 Low | Unused Import | Unused import httpx |
| 5 | 🟢 Low | Import Optimization | standard import "typing.AsyncGenerator" should be placed before third party import "httpx" |
| 5 | 🟢 Low | Unused Import | Unused AsyncGenerator imported from typing |
| 6 | 🟢 Low | Unused Import | Unused status imported from fastapi |
| 6 | 🟢 Low | Unused Import | Unused Request imported from fastapi |
| 77 | 🟢 Low | Import Optimization | Reimport 'httpx' (imported line 4) |

### 📁 `src/web_api/routers/users.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 2 | 🟢 Low | Unused Import | Unused Query imported from fastapi |
| 2 | 🟢 Low | Unused Import | Unused HTTPException imported from fastapi |
| 3 | 🟢 Low | Unused Import | Unused func imported from sqlalchemy |

### 📁 `src/web_api/schemas/auth_schema.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 🟢 Low | Unused Import | Unused Field imported from pydantic |
| 2 | 🟢 Low | Import Optimization | standard import "typing.Optional" should be placed before third party import "pydantic.BaseModel" |
| 3 | 🟢 Low | Import Optimization | standard import "datetime.datetime" should be placed before third party import "pydantic.BaseModel" |

### 📁 `src/web_api/schemas/gallery_schema.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 2 | 🟢 Low | Import Optimization | standard import "typing.List" should be placed before third party import "pydantic.BaseModel" |
| 3 | 🟢 Low | Import Optimization | standard import "datetime.datetime" should be placed before third party import "pydantic.BaseModel" |

### 📁 `src/web_api/schemas/task_schema.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 2 | 🟢 Low | Import Optimization | standard import "typing.Optional" should be placed before third party import "pydantic.BaseModel" |
| 2 | 🟢 Low | Unused Import | Unused List imported from typing |

### 📁 `src/web_api/schemas/user_schema.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 2 | 🟢 Low | Import Optimization | standard import "typing.Optional" should be placed before third party import "pydantic.BaseModel" |
| 3 | 🟢 Low | Import Optimization | standard import "datetime.datetime" should be placed before third party import "pydantic.BaseModel" |

### 📁 `workers/comfy_agent/agent_main.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 1 | 🟡 Medium | Code Duplication | Similar lines in 2 files
==src.core.user_core:[16:30]
==src.quota:[43:55]
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user:
                updated = False
                if username and user.username != username:
                    user.username = username
                    updated = True
                if full_name and user.full_name != full_name:
                    user.full_name = full_name
                    updated = True
                if updated:
                    await session.commit() |
| 1 | 🟡 Medium | Code Duplication | Similar lines in 2 files
==backend.main:[52:62]
==src.web_api.main:[31:39]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 |
| 1 | 🟡 Medium | Code Duplication | Similar lines in 2 files
==app.main:[251:259]
==src.web_api.routers.tasks:[147:158]
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    # Parse to see if finished or running
                    try:
                        parsed = json.loads(data)
                        status = parsed.get("status")

                        # Map backend status to frontend expected status
                        if status == "done": |
| 1 | 🟡 Medium | Code Duplication | Similar lines in 2 files
==app.main:[30:41]
==app.routers.agent:[17:27]
    redis = Redis.from_url(settings.redis_url)
    try:
        yield redis
    finally:
        await redis.close()

# Dependency for QueueManager
async def get_queue_manager(redis: Redis = Depends(get_redis)):
    return QueueManager(redis)

async def check_zombie_tasks_loop(): |
| 1 | 🟡 Medium | Code Duplication | Similar lines in 2 files
==backend.routers.history:[50:58]
==backend.routers.plans:[108:116]
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.offset(offset).limit(page_size)
        result = await db.execute(stmt)

        items = []
        for row in result: |
| 1 | 🟡 Medium | Code Duplication | Similar lines in 2 files
==src.core.task_core:[140:146]
==src.core.task_dispatcher:[224:230]
        dur_str = str(duration).replace("s", "")
        try:
            dur_val = int(dur_str)
        except ValueError:
            dur_val = 5
 |
| 143 | 🟡 Medium | Code Smell | Too many local variables (23/15) |
| 143 | 🟡 Medium | Code Smell | Too many branches (21/12) |
| 143 | 🟡 Medium | Code Smell | Too many statements (70/50) |
| 272 | 🟡 Medium | Code Smell | Too many local variables (38/15) |
| 272 | 🟡 Medium | Code Smell | Too many branches (42/12) |
| 272 | 🟡 Medium | Code Smell | Too many statements (153/50) |
| 11 | 🟢 Low | Import Optimization | standard import "typing.Dict" should be placed before third party imports "asgi_correlation_id.correlation_id", "httpx", "websockets", "minio.Minio", "dotenv.load_dotenv" |
| 564 | 🟢 Low | Import Optimization | Reimport 'sys' (imported line 5) |
| 564 | 🟢 Low | Import Optimization | Imports from package sys are not grouped |

### 📁 `workers/comfy_agent/comfy_client.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 2 | 🟢 Low | Import Optimization | standard import "logging" should be placed before third party import "httpx" |
| 3 | 🟢 Low | Import Optimization | standard import "typing.Dict" should be placed before third party import "httpx" |

### 📁 `workers/comfy_agent/workflow_patcher.py`

| 行号 | 严重程度 | 问题类型 | 具体描述 |
| --- | --- | --- | --- |
| 65 | 🟡 Medium | Code Smell | Too many local variables (16/15) |
| 65 | 🟡 Medium | Code Smell | Too many branches (30/12) |
| 65 | 🟡 Medium | Code Smell | Too many statements (60/50) |
| 159 | 🟡 Medium | Code Smell | Too many branches (23/12) |

