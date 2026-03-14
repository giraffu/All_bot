# Telegram Bot 系统技术分析报告

## 1. 项目概述 (Project Overview)

本项目是一个基于 `python-telegram-bot` 框架构建的高级 Telegram 机器人系统，专注于提供 AI 图像和视频生成服务。系统深度集成了 ComfyUI 作为后端生成引擎，并创新性地引入了“修仙”主题的用户等级体系（凡人、练气、筑基等）与积分（灵石）经济系统，以增强用户粘性与活跃度。

该机器人采用现代化的异步架构（Asyncio），实现了高并发的消息处理与任务调度，确保在处理耗时生成任务时仍能保持界面的即时响应。系统设计遵循模块化原则，将业务逻辑、数据持久化与接口交互层分离，具备良好的可扩展性与维护性。

---

## 2. 系统架构 (System Architecture)

系统整体采用分层架构设计，主要包含以下核心组件：

### 架构图 (Architecture Diagram)

```mermaid
graph TD
    User[用户 (Telegram Client)] -->|消息/指令/回调| TG_Server[Telegram Server]
    TG_Server -->|Long Polling| Bot_Entry[入口: src/bot_test.py]
    
    subgraph "Bot Core Layer"
        Bot_Entry -->|分发| Handlers[处理器层 (src/handlers)]
        Handlers -->|业务逻辑| Services[服务层 (src/services)]
        Handlers -->|鉴权/状态| Permission[权限服务]
        
        Services -->|任务调度| Task_Service[任务服务]
        Services -->|生成请求| Image_Service[图像服务]
    end
    
    subgraph "Infrastructure Layer"
        Services -->|读写| DB[(SQLite/PostgreSQL)]
        Task_Service -->|API调用| ComfyUI[ComfyUI 后端]
        Bot_Entry -->|日志记录| Logger[日志系统]
    end
```

### 核心流程
1.  **消息接收**：`Application` 通过长轮询（Polling）机制从 Telegram 服务器获取更新。
2.  **路由分发**：根据更新类型（Command, Message, CallbackQuery）分发至对应的 Handler。
3.  **鉴权与流控**：`PermissionService` 检查用户订阅状态与积分余额。
4.  **任务执行**：`TaskService` 将生成请求封装并提交至 ComfyUI 队列，实时监控进度。
5.  **结果反馈**：生成完成后，通过 `ImageService` 回传结果图片/视频，并扣除相应积分.

---

## 3. 功能模块说明 (Functional Modules)

### 3.1 入口与初始化 (`src/bot_test.py`)
- **职责**：系统的启动入口，负责组装各个组件。
- **关键逻辑**：
  - **代理自动检测**：`get_best_proxy()` 函数实现了智能代理检测机制，自动测试配置的代理及本地常见端口（如 7890, 10808），确保网络连通性。
  - **应用构建**：使用 `ApplicationBuilder` 构建 Bot 实例，开启 `concurrent_updates=True` 以支持并发处理。
  - **生命周期钩子**：通过 `post_init` 在启动时自动初始化数据库连接。

### 3.2 处理器层 (`src/handlers/`)
- **Command Handler** (`command_handler.py`): 处理 `/start`, `/help` 等基础指令，负责新用户引导与菜单展示。
60→- **Message Handler** (`message_handler.py`):
61→  - 处理文本消息：解析 Prompt 或处理菜单指令。
62→  - 处理图片/视频消息：触发“图生图”或“图生视频”任务，支持自动防抖与防刷屏。
- **Callback Handler** (`callback_handler.py`): 响应内联键盘（Inline Keyboard）点击事件，实现模式切换（如换脸、脱衣、修仙签到）与分页导航。

###65→### 3.3 服务层 (`src/services/`)
66→- **Task Service**: 核心任务调度器，负责与 ComfyUI 通信，管理任务队列，实时推送“排队中... 第 N 位”的进度通知。
67→- **Permission Service**: 实现复杂的权限逻辑，包括频道订阅强制验证、积分（灵石）扣除与回滚、等级晋升判断。

### 3.4 数据持久化 (`src/database/`)
- **ORM 框架**: 采用 SQLAlchemy (AsyncIO) 进行数据库操作。
- **核心模型**:
  - `User`: 存储用户基本信息、积分余额、修仙等级、邀请统计。
  - `History`: 记录每一次生成任务的详细参数与结果，用于审计与回溯。
  - `Referral`: 追踪邀请关系，实现裂变奖励机制。

### 3.5 日志与监控 (`src/logger.py`)
- **双向输出**: 同时输出到控制台（带颜色高亮）与按日轮转的日志文件。
- **调试增强**: 异常堆栈记录包含文件的**绝对路径**，便于开发者在 IDE 中直接点击定位错误代码。
- **用户行为追踪**: 独立的 `UserLogger` 记录关键交互路径，辅助运营分析。

---

## 4. 依赖清单 (Dependencies)

基于 `requirements.txt` 与代码分析，主要依赖如下：

| 库名称 | 用途 | 备注 |
| :--- | :--- | :--- |
| `python-telegram-bot[socks]` | Telegram Bot API 核心库 | 支持异步与 Socks 代理 |
91→| `httpx[socks]` | 异步 HTTP 客户端 | 用于 ComfyUI API 调用 |
| `sqlalchemy` | 数据库 ORM | 异步版本 (AsyncIO) |
| `aiosqlite` | SQLite 异步驱动 | 轻量级数据库后端 |
| `python-dotenv` | 环境变量管理 | 加载 `.env` 配置 |

---

## 5. 配置说明 (Configuration)

配置系统采用 **环境变量 + 代码常量** 的混合模式，主要集中在根目录的 `config.py` 与 `.env` 文件。

### 关键配置项
- **Bot Token**: `BOT_TOKEN` / `BOT_TOKEN_TEST` (区分生产与测试环境)。
- **路径配置**: 自动计算项目根目录，动态定位 `prompts`, `output`, `logs` 等目录。
- **业务常量**:
  - `COST_IMAGE`: 2 灵石/张
  - `COST_VIDEO`: 6 灵石/次
  - `REWARD_SIGNIN`: 20 灵石/天
- **代理设置**: 支持 HTTP/SOCKS5 代理，并在 `bot_test.py` 中实现了故障转移逻辑。

---

## 6. 运行与部署 (Run & Deployment)

### 环境要求
- Python 3.10+
- Redis (可选，用于缓存或队列增强)
- ComfyUI (需本地或远程部署并开放 API)

### 启动流程
1.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **配置环境**:
    复制 `.env.example` 为 `.env` 并填入 Token 与 API 地址。
3.  **运行测试 Bot**:
    ```bash
    python src/bot_test.py
    ```
    *注：脚本会自动检测最佳代理并初始化数据库。*

---

## 7. 已知问题与风险 (Known Issues & Risks)

1.  **长轮询稳定性**: 当前使用 `run_polling` 方式，在网络波动极大时可能会丢失部分更新，且对服务器带宽占用较高。
2.  **ComfyUI 强依赖**: 机器人完全依赖 ComfyUI 后端的可用性。若 ComfyUI 宕机或队列阻塞，机器人将无法响应生成请求，需增加熔断机制。
3.  **同步阻塞风险**: 尽管启用了异步，若 Handler 中存在未被 `await` 的 CPU 密集型操作（如大型图像预处理），仍可能阻塞事件循环。
4.  **代理单点故障**: 虽然有自动检测，但若所有预设代理均不可用，机器人将无法连接 Telegram 服务器。

---

## 8. 后续升级建议 (Future Recommendations)

1.  **Webhook 迁移**: 在生产环境建议从 Polling 切换为 Webhook 模式，配合 Nginx 反向代理，提高响应速度与稳定性。
2.  **任务队列解耦**: 引入 Celery 或 Redis Queue 将生成任务与 Bot 进程完全解耦，支持横向扩展 ComfyUI 节点。
3.  **监控告警完善**: 集成 Prometheus + Grafana 或 Sentry，对错误率、API 延迟、队列长度进行实时监控与告警。
4.  **单元测试覆盖**: 补充针对 `TaskService` 与 `PermissionService` 的单元测试，确保核心业务逻辑的稳定性。
