# 子模块：Prompt Optimizer Worker

本文是通用提示词优化平台的当前架构与扩展 SOP。当前消费者包括
`ltx_video_v2`、纯 `ltx_t2v` 与双角色 `ltx_t2v_ic`，但 Registry、任务类型、
结果存储和 Worker 主循环不得出现以 LTX 为条件的队列分支。

## 1. 组件与事实源

```text
Web capability/submit
  -> Task Core 扣费与幂等
  -> Central task type: prompt_optimize
  -> 四条独立 agent lane
  -> Profile/Template Registry
  -> MediaPreprocessor
  -> ModelProvider (LM Studio)
  -> OutputValidator
  -> Central text_delta + recoverable snapshot
  -> Central text completion
  -> owner-fenced Redis result (24h)
```

代码事实源：

- `src/prompt_optimizer/registry.py`
- `src/web_api/services/prompt_optimization_service.py`
- `src/web_api/services/prompt_result_store.py`
- `workers/prompt_optimizer/`
- `backend/app/routers/agent.py` 与 `backend/app/queue_manager_flow_helpers.py`

## 2. Registry 与版本规则

Profile 声明 target task、必选/可选媒体角色、严格 context、输出字段白名单、
primary field、model route、兼容模板和长度限制。Template 声明展示标签、system/user
正文、必需变量、兼容 Profile 和内容 hash。

发布过的 `id@version` 不可修改。载荷保存 `profile_ref`、`template_ref` 和
`template_hash`；Worker 缺少版本或 hash 不一致时失败。旧版本必须保留到所有排队
任务和审计重放窗口结束，通常不主动删除。

当前 `ltx_video_v2` 根据媒体角色解析：

- `start_image` -> `ltx_eros_v14_i2v@1`
- `start_image,end_image` -> `ltx_eros_v14_flf2v@1`

文生视频使用独立的参考语义：

- 无媒体 -> `ltx_eros_t2v@1`
- `reference_character_1,reference_character_2,scene_background` ->
  `ltx_eros_t2v_ic_msr@1`

当前新任务只开放 `ltx_scene_script_cinematic@3`。它使用中文规则理解图片、原始
要求与时长，默认增强成年 NSFW 场景的明确动作、镜头、多人归属、对白、声音与身体
连续性，并只输出英文 `positive_prompt`。Web 不展示模板选择器，由
`ltx_video_v2` capability 的唯一默认模板自动提交。`ltx_scene_script_cinematic@1`、
`ltx_timestamp_motion@1` 和 `ltx_scene_script_cinematic@2` 保留为 inactive，只用于
已排队任务和审计重放。FLF2V 的终帧硬约束仍在渲染时由 Profile 叠加，不复制一套
FLF 模板。

文生视频只开放 `ltx_scene_script_cinematic@4`。它沿用 @3 的中文成人场景规则和
英文 `positive_prompt` 输出，但人物图只定义两个稳定身份、背景图只定义场景，明确
禁止把任何 reference 写成视频首帧。IC 请求中的角色 ID 由 Web owner-fenced 解析
为实际面板；浏览器不能提交私有面板路径。@3 与 @4 互不兼容，防止帧语义串用。

## 3. API 与隐私

`GET /api/prompt-optimizations/capabilities?target_task_type=...` 只返回价格、媒体
契约和 active 模板的展示信息，不返回 system/user 模板正文。

`POST /api/prompt-optimizations/tasks` 使用用户范围的 `client_request_id` 幂等。
媒体只允许当前用户的 `web_uploads/{user_id}/` 对象，格式 PNG/JPEG/WebP，单文件
20 MB。context 拒绝未知字段。服务端解析后把不可变 refs/hash 放入 Central。

任务扣 1 灵石；Task Core 的扣费、派发补偿、pending 取消和失败退款负责 exactly
once。文本结果只保存在 `allbot:prompt_result:{task_id}` 类 owner-fenced Redis key，
TTL 24 小时；不写 History、R2 或 Gallery。

普通日志只记录 task ID、lane 和错误类型。禁止记录原始提示词、data URL、图片内容
或 LLM 原始响应。

任务载荷包含服务端生成的 `text_stream_contract`。Worker 使用
`POST /api/agent/task/text-delta` 上报 `attempt_id + sequence + field + delta`；
Central 原子检查 running、worker owner、Profile 字段和累计长度。重复序号幂等忽略，
跳号返回期望序号，Web SSE 通过 `text_snapshot` 恢复后继续接收 `text_delta`。
增量快照 TTL 24 小时，不包含原始 prompt、图片或完整 LLM JSON。

前端只把增量作为只读预览；最终 `/result` 成功才替换真实输入。部分输出后失败时，
原文恢复，片段以 `partial_unvalidated=true` 只读返回，退款状态只有账本确认后才显示
`refunded`。

## 4. Worker 与 LM Studio

一个容器启动 `prompt_optimizer_test_01..04` 四条 lane，每条只 pop
`prompt_optimize`，全局最多同时四任务；Web/Task Core 保持单用户并发 1。

readiness 通过 LM Studio `/api/v1/models` 验证别名 `ltx-prompt-optimizer` 已加载、
vision=true、context>=16384、parallel>=4。不满足时所有 lane heartbeat=error 并
停止 pop，不自动加载或卸载模型。

图片在内存转 JPEG 并缩至长边 1536px，以 data URL 调用 LM Studio
`/v1/responses`。当前 Qwen3.6 VLM 采用 Provider 内部两阶段：第一阶段在
`reasoning.effort=none` 下提取不落盘的视觉观察，第二阶段把视觉观察、原始输入和
版本化模板合并为纯文本请求，再使用 JSON Schema structured output。纯文本 Profile
跳过第一阶段。若 HauhauCS 视觉阶段只返回 reasoning item，可仅将其作为不落盘的
视觉观察继续；最终结构化阶段禁止 reasoning fallback，并把动态 schema 同时放入
API format 和 system 指令，仍由 OutputValidator fail closed。两个请求都必须
`store=false`，不得把原始响应写日志；超时 180 秒，
只对 429、5xx、网络错误或 timeout 重试一次。非法 JSON、未知字段、空文本或超过
2000 字符直接失败。不得通过剥离 Markdown fence 等宽松解析绕过 fail-closed。

结构化阶段支持 Responses SSE。Worker 只提取 `optimized_fields` 白名单字符串，处理
任意 chunk、JSON escape 和 Unicode；最终 `json.loads`/schema 结果必须与已发送文本
完全一致。首个 Central delta 确认前可按既有规则重试一次，确认后禁止重新生成并拼接
第二份输出。

健康入口：`127.0.0.1:8097/health` 和 `/ready`，只暴露 ready reason 与 active
lane 数，不暴露提示词或媒体。

## 5. 发布与回滚

Registry 内容仍遵循 Worker-first、Web-activation-last；涉及增量协议时固定为：

1. 部署兼容旧 Worker 的 Central 增量接口和 Redis snapshot。
2. 部署识别 `text_snapshot`/`text_delta` 的 Web API；旧前端仍只处理 progress。
3. 构建并部署 `prompt-optimizer-worker` exact digest，验证真实 structured stream。
4. 最后部署 Public Web，启用只读流式预览。
5. 验证 `/ready`、四 lane、断线、重复/跳号、部分失败退款与日志隐私。

Compose 禁止源码 bind mount，镜像必须 digest pinned。rollback 只回退到状态账本中的
上一 exact digest。prod mutation 仍需用户明确确认。

LTX v2 canary Agent 也使用单独的不可变入口
`deploy/docker-compose-ltx-v2-test-agent.yml`，由
`scripts/ltx_v2_test_agent_ops.py` 精确部署或回滚。该入口只声明
`ltx_video_v2,ltx_video_v2_flf2v`，不继承开发用 cloud-worker compose 的 build、
workflow 或 `src` 挂载；仅保留与本地 test relay 共享的日志和结果 spool 运行态目录。
它固定连接 gpu-177 GPU1 的 `ltx_unified` Comfy API，`restart=no`，只在 canary
窗口显式启动，不能替代或重启正式 LTX Agent。

## 6. 新任务接入 checklist

1. Registry 增加 Profile/模板版本。
2. 增加媒体角色、context、输出字段和旧版本重放 fixture。
3. 若需要，增加 MediaPreprocessor/ModelProvider/OutputValidator adapter。
4. 构建并部署新 Worker，验证它识别新 refs。
5. Central/API 保持 `prompt_optimize`，不要新增队列类型。
6. Web 最后激活 capability，并提供字段到 UI 控件的 typed mapping。
7. 运行 focused tests、`python scripts/doc_quality_checker.py` 和 Skill validator。
