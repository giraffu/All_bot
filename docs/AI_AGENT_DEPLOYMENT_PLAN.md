# AI Agent 框架上线灰度方案与回滚预案

## 1. 灰度方案 (Grayscale Plan)

### 阶段一：内部测试 (Internal Test)
- **目标**：验证核心流程在真实环境下的稳定性。
- **操作**：
  - 将开发者的 Telegram ID 加入白名单。
  - 仅白名单用户可以触发 `bot.py` (AI Bot) 的消息处理。
  - 监控日志中的 `bot.ai_handler` 和 `bot.session_manager` 关键字。

### 阶段二：小规模灰度 (Small Scale Grayscale)
- **目标**：观察数据库压力和多轮对话上下文的增长情况。
- **操作**：
  - 随机选择 5% 的活跃用户，通过配置中心将其流量导向 AI Handler。
  - 设置 `session_limit=10` 和 `compress_threshold=8` 以减小初期压力。
  - 实时监控数据库连接数和响应耗时。

### 阶段三：全量上线 (Full Rollout)
- **目标**：全面替代旧版 AI 逻辑。
- **操作**：
  - 移除白名单限制，全量开放。
  - 观察 24 小时内的内存占用趋势。

## 2. 回滚预案 (Rollback Plan)

### 触发条件
- 接口响应耗时持续超过 500ms。
- 数据库连接池溢出或 CPU 占用率持续高于 80%。
- 用户报告严重的对话串扰（Isolation 失败）。

### 操作步骤
1. **代码回滚**：
   - 使用 Git 回滚至 `refactor-ai-agent` 分支之前的 commit。
   - `git checkout <last_stable_commit> src/handlers/message_handler_ai.py`
2. **状态重置**：
   - 如果回滚后旧逻辑无法处理新表数据，紧急调用 `session_manager.clear_session(user_id)` 清空受影响用户的状态。
3. **降级开关**：
   - 在 `config.py` 中增加 `ENABLE_AI_AGENT = False` 开关，紧急情况下直接跳过 AI Handler 回退到原始 Prompt 处理。

## 3. 性能基准总结
- **单会话 1000 轮平均延迟**：177.27 ms (达标)
- **内存增长**：约 97 KB/轮 (线性可控)
- **并发表现**：通过 `asyncio.gather` 验证用户隔离正常。
