# 项目概览与开发指南 (AGENTS.md)

这份文档旨在为AI Agent提供关于该Telegram Bot项目的全面上下文，包括核心功能、架构设计、业务逻辑以及开发规范。可以直接用于Trae或其他AI辅助开发环境。

## 1. 项目概览

这是一个基于 `python-telegram-bot` 构建的高级Telegram机器人，专注于AI图像和视频生成服务（如AI换脸、特定场景视频生成等）。项目采用了前后端分离的架构：
- **后端 (Bot)**: 基于异步架构处理Telegram交互、任务调度和ComfyUI接口通信。
- **管理后台 (Dashboard)**: FastAPI 后端 + Vue 3 (Vite + Tailwind) 前端，提供实时统计、用户管理、历史记录查询及模板审核功能。

## 2. 核心功能与历史任务总结

以下是项目开发至今已完成的主要任务和功能模块总结：

### 2.1 用户、权限与等级体系 (修仙主题)
项目引入了修仙主题的等级体系和积分系统：

- **积分系统 (Credits/灵石)**：
  - **定价**：图像生成消耗 **2 灵石**，视频生成消耗 **6 灵石**。
  - **获取方式**：
    - **每日签到**：每日一次，奖励 **20 灵石**。
    - **邀请奖励**：被邀请者加入频道后，邀请人获得 **20 灵石**。
    - **模板贡献**：用户提交图片/视频作为模板，审核通过后奖励 **10-20 灵石**。

- **用户等级 (User Groups / Cultivation Levels)**：
  - **凡人 (Mortal)**：初始状态。无法签到或邀请。
  - **练气期 (Qi Refining)**：加入指定频道后晋升。解锁签到和邀请功能。
  - **筑基期 (Foundation)**：邀请 > 1, 签到 > 3, 生成次数 > 10。
  - **金丹期 (Golden Core)**：邀请 > 10, 签到 > 30, 生成次数 > 100。

- **权限控制**：
  - **频道订阅验证**：用户必须订阅指定频道才能使用Bot（主要鉴权方式）。
  - **白名单/群组回退**：若未配置频道或验证失败，回退检查白名单或允许的群组。
  - **数据一致性**：确保前端展示的用户状态与后端数据库保持一致，特别是布尔值字段的默认处理。

### 2.2 核心业务功能 (生成模式)
支持多种生成模式（定义在 `src/constants.py`），包括但不限于：

- **基础图像处理**：
  - 自由P图 (`edit`)
  - 快速脱衣 (`undress`)
  - 快速自慰 (`masturbation`)
  - 快速换脸 (`face_swap`)

- **视频生成**：
  - **特定场景视频**：
    - 动图传教士 (`perfect_video_insert`)
    - 动图后入 (`doggy_style`)
    - 口交黑人 (`blowjob`)
    - 脱衣吐舌 (`undress_tongue`)
    - 特写口交 (`closeup_blowjob`)
  - **自定义视频**：图生视频功能，支持用户输入Prompt (`custom_video`)。

- **模板贡献 (Template Contribution)**：
  - 用户可提交图片/视频作为Bot模板。
  - 管理员在Dashboard审核通过后，素材存入系统库并自动发放奖励。

### 2.3 任务处理与并发
- **并发机制**：启用了 `ApplicationBuilder(concurrent_updates=True)`，允许Bot同时处理多个更新，防止耗时生成任务阻塞其他用户交互（如查询状态）。
- **队列管理**：
  - **进度监控**：实时获取 ComfyUI 队列位置并反馈给用户 ("排队中... 第 X 位")。
  - **批量处理**：任务队列有序处理，并带有进度提示。
- **会话管理**：
  - `SessionManager` 负责管理用户对话上下文。
  - 支持自动清理过期消息。

### 2.4 系统稳定性与运维
- **网络鲁棒性**：实现了 `async_retry` 装饰器和 `robust_send_*` 封装，增强网络请求的重试机制。
- **日志系统**：
  - `UserLogger` 记录所有用户交互（菜单点击、命令）。
  - 错误日志包含完整堆栈信息，并记录绝对路径以便IDE直接点击跳转。
- **闲置状态管理**：引入 `MODE_NONE`（闲置状态），当用户未选择模式时忽略图片并提示，包含防刷屏冷却。

### 2.5 Web Dashboard
- **架构**：FastAPI (Backend) + Vue 3 (Frontend, Vite + Tailwind).
- **功能**：
  - **实时统计**：展示总用户、今日活跃、灵石消耗、任务类型分布、24小时活跃趋势等。
  - **用户管理**：查看用户等级、积分、邀请关系，支持手动修改积分或封禁。
  - **模板审核**：可视化审核用户提交的模板，一键完成文件转移及积分发放。
  - **队列监控**：实时显示 ComfyUI 后端的任务堆积情况。

## 3. 技术架构

### 目录结构
- `src/`: 核心代码
  - `handlers/`: 消息、命令、回调处理器 (Controller层)。
    - `message_handler.py`: 处理文本和图片消息。
    - `callback_handler.py`: 处理按钮点击。
    - `command_handler.py`: 处理 /start, /help 等命令。
  - `services/`: 业务逻辑 (Service层)。
    - `task_service.py`: 封装了通用的生成任务模版，处理排队、监控及结果分发。
    - `permission_service.py`: 处理等级晋升、积分检查及订阅验证。
    - `image_service.py`: 与 ComfyUI API 通信。
  - `database/`: 数据库模型 (`models.py`) 和核心操作 (`core.py`)。
    - 包含 `User`, `History`, `Referral`, `TemplateContribution` 等模型。
  - `bot.py`: 程序入口，负责初始化Application。
- `dashboard/`: Web管理后台代码。
  - `backend/`: FastAPI 接口。
  - `frontend/`: Vue 3 + Vite 现代化前端。
- `user_data/`: 用户历史数据 (JSONL格式，作为备份或日志)。
- `scripts/`: 数据迁移和运维脚本。

### 关键依赖
- **Python**: `python-telegram-bot` (Bot API), `sqlalchemy` (ORM, Async), `fastapi` (Dashboard Backend).
- **Frontend**: `Vue.js 3`, `Vite`, `Tailwind CSS`.

## 4. 开发规范 (Development Guidelines)

1.  **异步优先**：
    - 所有 IO 操作（DB, 网络请求, 文件处理）必须使用 `async/await`。
2.  **错误处理**：
    - 所有关键路径必须包含 try-except 块，并使用 `logger.error(..., exc_info=True)` 记录堆栈。
3.  **等级/积分同步**：
    - 修改用户数据后，需调用 `permission_service.refresh_user_group` 确保等级即时更新。
4.  **文件路径**：
    - 始终使用绝对路径 (`Path.resolve()`)，方便日志点击跳转。
5.  **前端数据同步**：
    - 后端修改 `User` 或 `History` 模型时，务必检查 Dashboard 后端接口是否需要同步更新字段映射，防止UI状态异常。
6.  **并发安全**：
    - 积分扣除应在任务开始前通过 `check_quota` 验证，并配合事务确保数据一致性。
