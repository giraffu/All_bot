# Bot 后端代码审查与优化建议报告

## 1. 现有功能架构梳理 (Feature Summary)
当前 Bot 后端已具备多模块、强状态、容灾健全的分布式架构，主要包含：
- **Telegram 交互层**：支持多模态（图片、视频、文档、文本）处理，包含完善的指令与复杂的内联键盘回调状态机。
- **任务与调度体系**：基于 Redis 的并发防刷限制，基于 PostgreSQL 的数据持久化，以及与中控 API 和 ComfyUI Agents 的异步协同，支持断线重启后的任务自动恢复。
- **三大支付矩阵**：集成 TON 区块链支付（后台异步轮询）、Telegram Stars（原生回调机制）以及 RMB 易支付（独立 FastAPI 接收回调）。
- **网络容错**：启动时自动探测最佳代理通道（含本地端口回退）。

---

## 2. 🔴 严重问题 (Critical Issues - 必须修复)

### 2.1 `clean_zombies.py` 丢失导致自愈机制崩溃
- **位置**：`src/bot_test.py` -> `clean_zombies_loop` (第74-85行)
- **问题**：代码中动态向 `sys.path` 注入路径并尝试导入根目录的 `clean_zombies.py`，但该文件在当前代码库中已不存在。这将导致后台协程每 10 分钟抛出 `ModuleNotFoundError`，造成僵尸任务清理机制（防止死锁和算力浪费）完全失效。
- **修复建议**：重新实现僵尸清理逻辑，建议将其封装在 `src/services/zombie_cleaner_service.py` 中，并使用标准包导入替换 `sys.path.append` 的反模式。

### 2.2 异步后台任务缺少强引用导致可能被垃圾回收
- **位置**：`src/bot_test.py` -> `post_init` (第92-99行)
- **问题**：使用 `asyncio.create_task()` 创建了如 TON 支付轮询 (`poll_transactions`) 和任务恢复 (`recover_active_tasks`) 等关键后台任务，但未保存对其的强引用。在 Python 3.7+ 中，这极易导致任务在执行中途被垃圾回收器意外销毁，且没有任何报错。
- **修复建议**：在 `application.bot_data` 中创建一个集合（如 `set()`）来保存这些任务的强引用，并在任务完成时通过回调将其移除。

---

## 3. 🟡 代码级优化建议 (Code-level Suggestions)

### 3.1 修复 `post_shutdown` 中的局部导入异味
- **位置**：`src/bot_test.py` -> `post_shutdown` (第105-108行)
- **问题**：函数内部的局部导入隐藏了模块真实依赖关系，存在微小的性能损耗，属于代码异味。
- **修复建议**：将 `redis_client` 和 `image_service` 导入移至文件顶部，或在初始化时将其挂载到 `application.bot_data` 中，在 shutdown 时直接获取。

### 3.2 统一并精简环境变量加载
- **位置**：`src/bot_test.py` -> `main` (第118-124行)
- **问题**：为获取 Token 进行了繁琐的 fallback 处理（混用 `os.getenv`、`dotenv_values` 及大小写变体），项目缺乏唯一的配置来源 (Single Source of Truth)。
- **修复建议**：将所有环境变量的读取收口到统一的 `config.py` 中，主文件直接 `from config import BOT_TOKEN, BOT_TYPE`。

### 3.3 优化代理去重逻辑
- **位置**：`src/bot_test.py` -> `get_best_proxy` (第50-54行)
- **问题**：使用 `for` 循环和 `not in` 列表判断进行去重，时间复杂度为 O(n²)，不够 Pythonic。
- **修复建议**：替换为 `unique_proxies = list(dict.fromkeys(proxies))`，既能高效去重又能保留原始插入顺序。

### 3.4 修正具有误导性的入口文件命名
- **位置**：`src/bot_test.py` 
- **问题**：该文件通过读取 `BOT_TYPE` 环境变量同时支持正式服和测试服的启动，但命名为 `bot_test.py` 容易让后续开发者误以为该文件仅用于测试。
- **修复建议**：重命名为 `bot_main.py` 或 `main.py`，并同步更新部署脚本（如 `docker-compose.yml`）。

---

## 4. 🚀 宏观架构优化方向 (Architectural Optimizations)

### 4.1 增强后台协程的错误边界 (Error Boundaries)
除了目前的 `clean_zombies_loop`，其他如 `poll_transactions` 等长轮询任务在极端网络环境下抛出底层异常时可能导致协程静默崩溃。建议为所有常驻后台协程增加带有退避重试（Backoff Retry）机制的 `try-catch-sleep` 外层循环。

### 4.2 业务逻辑进一步解耦
主入口 `bot_test.py` 内部掺杂了诸如网络连通性测试（`get_best_proxy`）等底层实现细节。建议将这类逻辑抽取至 `src/utils/network_utils.py`，让主入口完全专注负责依赖装配与应用启动。

### 4.3 消除状态机硬编码，引入标准 FSM
在 `task_service.py` 和各 Handler 中，大量依赖硬编码的 `context.user_data['mode']` 进行状态判断。在多步交互（如视频换脸的传图、传视频过程）中，用户一旦进行跳跃性操作极易引发异常。建议引入标准的状态机模式 (FSM) 进行严格的状态流转管理和异常输入拦截。