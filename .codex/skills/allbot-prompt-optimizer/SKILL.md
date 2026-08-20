---
name: allbot-prompt-optimizer
description: 开发和运维 AllBot 多模态 Prompt Optimizer。修改优化任务、模板、模型 provider、媒体适配器或 Worker 部署时必须使用。
---

# AllBot Prompt Optimizer

## 目标与边界

提示词优化是独立 Central 任务 `prompt_optimize`，不绑定 Comfy workflow。目标差异
属于 Profile，风格属于 Template；队列、扣费、结果存储和 Worker 主循环保持通用。

先读：

- `docs/子模块_Prompt_Optimizer_Worker.md`
- 涉及本地模型选择时再读
  `docs/子模块_本地多模态LLM提示词优化_prompt_optimizer.md`
- 涉及任务扣费/终态时叠加 `allbot-task-engine` 和 `allbot-billing-auth`
- 涉及部署时叠加 `allbot-ops-deployment`

## 稳定入口

- Registry：`src/prompt_optimizer/registry.py`
- Web API：`src/web_api/routers/prompt_optimizations.py`
- 提交服务：`src/web_api/services/prompt_optimization_service.py`
- 管理端场景配置：`src/web_api/services/prompt_optimizer_config_service.py`、
  `dashboard/backend/routers/prompt_optimizer.py`
- owner-fenced 结果：`src/web_api/services/prompt_result_store.py`
- Worker：`workers/prompt_optimizer/`
- Relay：`workers/local_relay/relay_main.py`
- Central 请求契约：`backend/app/models.py` 的 `PromptOptimizeRequest`
- 文本增量存储：`src/services/task_text_stream_store.py`
- Bot draft/投递：`src/services/advanced_video_prompt_task_*`
- Worker 镜像/Compose：`deploy/docker/Dockerfile.test-execution`、
  `deploy/docker-compose-prompt-optimizer-test.yml`
- 精确运维入口：`scripts/prompt_optimizer_worker_ops.py`

## 不可越过的契约

- 客户端只能选择 active 的 `template id + version`；禁止提交自由 meta-prompt，
  capability 不返回模板正文。
- Registry 中已发布 Profile/Template 不原地改内容；新内容增加版本。管理后台维护的
  四个 scene config（H3 三模式共享 `minimax_h3`）是可变“当前配置”，保存递增 revision/hash，
  新任务保存渲染后的不可变 snapshot。Dashboard/提交端复用同一配置服务；后台显示
  数据库/内置来源与不兼容回退，禁止镜像版本差异静默改变默认模板。
- Worker 必须核对 Profile、Template 和 hash；未知版本、未知字段、空文本、超长
  文本或不兼容媒体角色一律失败。
- H3 固定 10Eros/LightX2V；LoRA 由生成端注入，优化器拒绝 LoRA/触发词，
  输出官方三字段，
  I2V/FLF2V 对齐由 Profile 注入、Worker 复验。
- 图片必须 owner-fenced，PNG/JPEG/WebP，单文件不超过 20 MB；发送 LM Studio 前
  在内存中缩至长边 1536px，不落额外持久副本。
- 文本结果只进 Redis，TTL 24 小时，不写 History/R2/Gallery。普通日志不得含完整
  原始提示词、图片内容或 LLM 原始响应。
- Web 用全局任务和 24 小时草稿恢复，且不覆盖已变化的上下文。Bot 先持久化
  owner-fenced draft 再退出 FSM；callback 不依赖 FSM，收费生成二次确认并幂等。
- `text_delta` 幂等上报；H3@5 发布前校验结构、时序与服务端台词
  `<d>[Language] 原文</d>`。JSON 匹配增量才能 `/complete`，失败幂等退款。
- Worker 领取任务后必须在媒体预处理和 LM Studio 推理全程每 15 秒续
  `task_heartbeat`，终态上报前停止；普通 lane heartbeat 不能替代任务续租。
- 优化任务扣 1 灵石并使用 Task Core Saga；入队/Worker 失败和 pending 取消只退款
  一次。运行任务 pop 时锁定取消。
- readiness 不满足已加载、vision、16K context、parallel 4 时 heartbeat=error 且
  停止 pop；Worker 不自动装卸 LM Studio 模型。
- LTX @3/@4 新任务读取管理端 scene config 并写入 snapshot；IC 的两个 typed
  character refs 与一个 environment ref 由服务端解析，绝不能渲染为首帧。
- snapshot 必须包含 scene_key/revision/config hash/profile/rendered messages，Worker
  核对 snapshot hash 与 Profile 后执行；无 snapshot 的旧任务继续走 template ref/hash。

## 扩展流程

### 新增目标任务 Profile

1. 在 Registry 增加不可变 Profile，声明目标 task types、媒体角色、严格 context、
   输出字段白名单、primary field、model route、允许模板与输入/输出上限。
2. 增加 I2V/多媒体角色和未知字段的 fixtures/tests。
3. 仅在需要新媒体类型时增加 MediaPreprocessor；不要修改 Central task type 或
   Worker lane 主循环。
4. 构建并部署含新 Registry bundle 的 exact-digest Worker，验证旧版本重放。
5. 最后激活 Web capability。禁止 Web-first。

### 新增模板版本

1. 保留旧 ref，增加 `id@next_version` 和新 content hash。
2. 声明 compatible Profile refs 和 required variables。
3. 测试 capability 展示、不同渲染请求、hash 不匹配 fail closed。
4. Worker-first 部署，再让 Web 返回新版本。

### 新增 ModelProvider

实现等价的 readiness 和结构化输出 seam；网络只重试一次 429/5xx/timeout，4xx
不重试。H3 非法 JSON/Profile 候选由执行器丢弃并受控再生成；Provider 不负责队列、
退款或 Profile 解析。

### 新增媒体预处理器

按 Profile 媒体角色选择适配器。视频可新增抽帧实现，但对象归属/大小验证留在 Web，
队列载荷仍保存 object key，Worker 不持久化派生媒体。

## 最小验证

```bash
ALLBOT_ENV=test .venv/bin/python -m pytest -q \
  tests/prompt_optimizer \
  tests/web_api/test_prompt_optimizations.py \
  tests/web_api/test_prompt_result_store.py \
  tests/workers/test_prompt_optimizer_worker.py

cd frontend && npm test -- --run \
  src/composables/lab-workbench/usePromptOptimizer.test.ts
```

部署前验证 `/ready.ready_lanes=4`、四 lane heartbeat、4+1 排队、退款和日志隐私。
流式变更按 Central → Web API → Worker → Public Web 发布；回滚反向执行，且不得在
流式 Worker 仍运行时先回滚 Central。
