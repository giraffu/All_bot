# 系统 Bug 修复实施方案 (Action Plan)

本文档基于前期的 Bug 分析报告，转化为可直接执行的代码修复与重构清单。开发人员可直接参考此文档进行逐一修复，并在完成后勾选对应项。

## 🔴 P0 级修复：核心流程与死锁隐患

### 1. 重构底层异步任务派发 (规避静默失败与超时)
- **目标文件**: `src/utils.py` 及各个 FSM/Callback Handlers
- **背景**: `create_background_task` 使用了原生的 `asyncio.create_task(coro)`，脱离了 PTB 框架的异常捕获。Callback 响应不及时导致 Telegram 客户端提示超时。
- **实施步骤**:
  - [ ] 修改 `src/utils.py` 中的 `create_background_task` 方法，废弃 `asyncio.create_task(coro)`，改为使用 `context.application.create_task(coro)`。
  - [ ] 全局核查 `create_background_task` 的调用方，确保正确传入了 `context` 参数。
  - [ ] 在各 Callback Handler 入口处（如 `button_click` 等），补充 `await update.callback_query.answer()` 立即响应客户端。

### 2. 补全并发锁自愈与优雅停机 (防死锁)
- **目标文件**: `src/services/zombie_cleaner_service.py` 及 Bot 主入口文件
- **背景**: 目前的清理脚本只处理了“驻留超时”的任务，没有处理“队列无活跃任务但并发锁未释放”的死锁情况。
- **实施步骤**:
  - [ ] 在 `clean_zombies` 方法中，增加逻辑：通过 `redis_client.get_user_concurrencies()` 获取 Redis 中所有的用户锁。
  - [ ] 交叉对比 `active_tasks` 列表，如果发现某用户的锁数量 > 0，但该用户没有任何活跃任务，强制调用 `redis_client.decrement_user_concurrency(user_id)` 将其重置。
  - [ ] 在 Bot 启动入口注册系统信号 (SIGINT/SIGTERM)，确保进程退出前能正常处理 Redis 挂起操作。

## 🟡 P1 级修复：数据一致性与执行回退

### 3. 统一全局视频任务常量 (规避执行回退异常)
- **目标文件**: `src/constants.py`, `src/core/task_core.py`, `src/core/task_dispatcher.py`
- **背景**: `video_types` 列表在多个文件中硬编码且内容不一致，导致新视频任务回退到图片逻辑引发崩溃。
- **实施步骤**:
  - [ ] 在 `src/constants.py` 中新增 `VIDEO_TASK_TYPES = ["doggy_style", "perfect_video_insert", "blowjob", "undress_tongue", "closeup_blowjob", "custom_video", "face_video", "face_video_step1", "face_video_step2", "video_lora", "ltx_video"]`。
  - [ ] 移除 `task_core.py` 和 `task_dispatcher.py` 中的局部硬编码，统一替换为 `from src.constants import VIDEO_TASK_TYPES`。

### 4. 修复 Worker WebSocket 断连异常
- **目标文件**: `workers/comfy_agent/agent_main.py`
- **背景**: 缺乏 JSON 容错，且新版 `websockets` 库移除了 `.closed` 属性。
- **实施步骤**:
  - [ ] 在解析接收到消息的逻辑处，增加容错：`if not isinstance(data, dict): continue`。
  - [ ] 搜索代码中的 `websocket.closed`，将其修改为 `websocket.state == websockets.protocol.State.CLOSED`。

### 5. 修正数据库一对一关联查询告警
- **目标文件**: `src/database/models.py`
- **背景**: `GalleryPost.history` 被定义为 `uselist=False`，但实际业务（任务重试等）会导致多条记录，触发 SQLAlchemy 告警。
- **实施步骤**:
  - [ ] 将 `GalleryPost` 模型中的 `history = relationship(..., uselist=False)` 改为 `uselist=True`。
  - [ ] (可选) 将属性重命名为 `histories`，并同步修改相关引用逻辑，以符合“一对多”语意。

### 6. 规范 Username 同步的 Flush 机制
- **目标文件**: `src/core/user_core.py` (或其他相关的数据库更新事务)
- **背景**: 捕获 `IntegrityError` 之前未 Flush，导致 SQLAlchemy 的 `autoflush` 机制在后续操作中提前引爆异常，绕过容错块。
- **实施步骤**:
  - [ ] 检查代码中处理 Username 唯一键冲突的 `try...except IntegrityError` 块。
  - [ ] 在 `try` 块内执行核心插入操作后，显式添加 `await session.flush()`。

### 7. 完善消息编辑的 API 容错
- **目标文件**: `src/utils.py`
- **背景**: 尝试调用 `edit_message_text` 去修改一条仅包含媒体内容的消息会引发异常。
- **实施步骤**:
  - [ ] 优化 `robust_edit_*` 系列方法，在 `except` 块中静默忽略 `Message to edit not found` 和 `There is no text in the message to edit` 异常。
  - [ ] 业务侧调用时，确保对于媒体消息使用 `robust_edit_caption`。

## ✅ 状态说明：已完成或无需修改的代码

### 8. SQLAlchemy DetachedInstanceError
- **状态**: ✅ 代码已修复
- **说明**: `src/services/task_service.py` 中已全面规范传递 `internal_user_id` 代替 `internal_user` 对象，跨会话传递的隐患已消除。

### 9. Worker 容器缺少工作流文件
- **状态**: ℹ️ 运维操作规范
- **说明**: 宿主机挂载的工作流 `.json` 文件是动态读取的。**新增或修改工作流文件后，无需执行 `--build` 重建容器**，Worker 下一次任务会自动加载新文件。只有在修改 `mappings.json` 时才需要 `docker-compose restart`。