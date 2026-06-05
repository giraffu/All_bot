---
name: "allbot-llm-ops"
description: "处理基于 LM Studio 的 CS Bot、LangGraph、技能工具绑定与群聊意图识别。当开发 AI 助理功能时调用本技能。"
---

# AllBot 智能客服与大模型操作 (LLM Ops)

本技能描述当前仓库中真正落地的 AI 助理能力：独立 `cs_bot` 服务、LangGraph 编排、LM Studio 兼容 OpenAI 接口调用，以及本地技能工具绑定。

## 1. 模块功能描述
- **客服意图识别**：先用 `check_intent()` 判断群消息是否需要机器人介入，避免无差别打扰。
- **LangGraph 对话编排**：使用 `StateGraph` + `ToolNode` + `tools_condition` 构建可带工具调用的客服对话流。
- **懒初始化运行时**：`build_langgraph_app()` / `get_langgraph_runtime()` 负责在首次使用时加载 `SkillManager`、绑定 tools 并编译图，避免 import `langgraph_client.py` 时立即初始化 LLM。
- **技能工具绑定**：`SkillManager` 在运行时初始化时加载 `cs_bot/skills`，把 prompt 与 tools 合并进 system prompt/LLM 工具集合。
- **线程隔离**：文本消息与图片消息使用不同 `thread_id`，避免视觉消息污染普通对话上下文。
- **内存型记忆**：当前 checkpointer 为 `MemorySaver()`，属于进程内存，不是 Redis 持久化。

## 2. 输入输出规范
- **接口**：`check_intent(user_text)`
  - 输入：用户文本
  - 输出：是否需要客服回复
- **接口**：`get_langgraph_reply(chat_id, username, user_text, base64_image=None)`
  - 输入：会话标识、用户名、文本、可选图片
  - 输出：客服回复文本

## 3. 核心红线
- 不要把当前实现描述成“Prompt Optimizer + Semaphore 主导”的体系；主链路是客服问答与工具化 LangGraph。
- 不要把 `MemorySaver` 写成 Redis/数据库持久化记忆。
- 不要在模块导入阶段构造 LangGraph / LLM；新增入口应复用 `get_langgraph_runtime()` 的懒初始化结果。
- 本地 LLM 异常时必须优雅降级，不能把错误透传到 Telegram 更新循环。
- 需要修改 Telegram 大文件 patch 或群消息入口时，应同时检查 `cs_bot/bot.py`，不要只盯 `langgraph_client.py`。

## 4. 边界条件处理
- 群聊静默策略优先，意图识别失败时默认不主动回复。
- 图片消息必须走独立 thread，避免把 base64 图像上下文长期混入普通文本历史。
- 如果没有可用 tools，LangGraph 图会退化为纯聊天节点，这属于正常设计，不要强行补假工具。

## 5. 测试要求
- 覆盖闲聊/求助的意图识别。
- 覆盖工具绑定与无工具两条图分支。
- 覆盖文本/图片 thread_id 隔离。
- 覆盖 LM Studio 不可用时的降级回复。
