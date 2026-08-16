# 子模块：Prompt Optimizer Worker

本文是通用提示词优化平台的当前架构与扩展 SOP。当前消费者包括
`ltx_video_v2`、纯 `ltx_t2v`、双角色 `ltx_t2v_ic` 与 MiniMax H3 三种模式，但 Registry、任务类型、
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

管理后台另外提供四个可变 scene config：`ltx_video_v2`、`ltx_t2v`、
`ltx_t2v_ic`、`minimax_h3`。H3 的 T2V/I2V/FLF2V 共用最后一个“高级图生视频pro”配置。
它们允许管理员修改 system/user prompt、展示名称和说明，但不能修改
Profile、媒体契约、模型、价格、workflow 或输出 schema。保存时校验占位符并递增
revision/content hash；Web 在提交时读取当前配置、渲染正文并保存
`prompt_config_snapshot`。Worker 校验 snapshot hash/Profile 后使用，旧静态
template ref 任务仍可重放。配置保存只影响之后的新任务。

Dashboard Backend 与 Web API 复用
`src/web_api/services/prompt_optimizer_config_service.py`，因此管理页展示的模板、保存
校验和提交时实际渲染必须来自同一事实源。管理 API 返回 `template_ref`、
`config_source`、`compatibility_status`、`fallback_reason` 与 `stored_revision`：数据库
没有配置时显示当前 built-in 默认值，管理员首次保存后创建 revision 1；已有配置不兼容
当前 Profile 契约时保留原行但明确显示 built-in fallback，保存当前有效内容才发布新
revision。管理页不得把 fallback 冒充为数据库配置，preview 与 save 必须执行同一个
场景占位符和 H3 官方结构校验。Dashboard 与 Web API 发布时必须使用包含相同共享配置
代码的完整 Git SHA，避免两个容器各自从不同 Registry 版本生成 revision 0。

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

H3 新任务注册 `minimax_h3_t2v_prompt@5`、`minimax_h3_i2v_prompt@5` 与
`minimax_h3_flf2v_prompt@5`，分别接受 0 张图、一张 `start_image`、按顺序的
`start_image,end_image`，时长只允许 5/10/15 秒。三者使用
`minimax_h3_10eros_naughtytimes@4`，按 MiniMax 官方 `h3-prompt-writing/base-en.txt`
输出三个固定字段：`integrated_multimodal_description`、`overall_soundscape`、
`non_diegetic_music`。T2V 直接从第一个字段开始；I2V 先输出精确的 0.00 秒
`<Picture 1>` 对齐句；FLF2V 先输出 Picture 1/2、动态结束时间和实际最终 Shot 编号的
对齐句。Profile 最大输出为 7000 字符，Worker 复验字段顺序、空行、Shot 连续编号、
动态时间戳、图片锚点和对齐句后才发布流式结果。英文运行模板与完整中文审阅翻译的
事实源均为 `src/prompt_optimizer/minimax_h3_prompt.py`；运行时只使用英文常量。
模型输出中的 CRLF、多余空行、字段冒号两侧空白、缺失但可由模式确定的 I2V 对齐行、
带合法 `[Shot 1]` 正文且后两个字段完整时遗漏的首字段标签，以及遗漏的 I2V/FLF2V
图片所有权短句，先由 Worker 确定性规范化并重新组装为官方格式；正文本身缺失、后两个
字段缺失或乱序、非法前缀、Shot 乱序、越界时间戳和错误 FLF2V 终帧对齐
仍然 fail closed。这样不会把排版随机性误判成语义错误，也不会放宽媒体所有权。
LM Studio structured output 偶尔只返回合法的 `optimized_fields` 而省略空
`warnings`；Worker 仅对这个精确键集合补 `warnings=[]`，再继续执行完整字段、正文和
H3 官方结构校验。任何额外未知键、错误类型或非空非法 warning 仍 fail closed，且该
规范化不得消耗本可用于语义重试的 H3 generation attempt。
服务端从带“说、喊、问、回答、耳语、唱”或对应英文标记的引号台词中提取原文，按
台词自身字符而非外围叙述语言生成 `[Chinese]`、`[English]` 等语言契约并写入不可变
snapshot。Worker 发布前逐条核对 `<d>[Language] 原文</d>`；翻译、改写、漏写或错误
语言标签都会在同一次扣费内受控重试，不能把错误台词交给 H3。没有明确台词时不凭空
增加对白；画面招牌等无说话标记的引号文字不按对白处理。

## 3. API 与隐私

`GET /api/prompt-optimizations/capabilities?target_task_type=...` 只返回价格、媒体
契约和 active 模板的展示信息，不返回 system/user 模板正文。

`POST /api/prompt-optimizations/tasks` 使用用户范围的 `client_request_id` 幂等。
用户临时媒体只允许当前用户的 `web_uploads/{user_id}/` 对象，格式 PNG/JPEG/WebP，
单文件 20 MB；published 官方素材由服务端直接解析。IC 接受恰好两个 typed 角色引用
（private/official 可混合）和一个环境引用（official/upload 互斥），并固定按角色 1、
角色 2、环境三图顺序发送。服务端可信人物/环境描述一并进入渲染快照。
数据库中的可信角色或环境媒体键可以保留兼容的 `bucket/object_key` 形式，但 Web 在
写入优化任务载荷前必须移除当前桶名前缀；Worker 的 `media.object_key` 始终是桶内纯
对象键，不能再次包含桶名。

H3 生成基础链固定 10Eros Beta2 与 LightX2V 8-step，六个 LoRA 由生成任务的
服务端目录可选注入。Prompt Optimizer 自身仍不接受非空 `lora_items`、单模型字段
或自由规则文本；它只编译内容，不决定或输出 LoRA。`minimax_h3_hmnsfw@1` 与
`minimax_h3_10eros_naughtytimes@1/@2/@3` 及三个 `@1/@2/@3/@4` profile 仅用于历史
snapshot 解析；新请求使用三个 `@5` profile。旧的可变 H3 scene config 若不含
官方三字段、服务端对白语言占位符或新“可选服务端附件”契约，
读取时自动前移到新的 built-in 默认值，并通过管理 API 标记不兼容历史 revision；已提交
任务仍使用其不可变 snapshot。Web/Bot 只
提交时长、媒体角色和原始提示词；优化器也不得输出模型名、LoRA 名或触发词。
Bot 调用 H3 优化前必须在入口边界把 Telegram 平台 ID 映射为
`internal_user_id`；共享服务仅接收内部 ID，并用它完成扣费、结果 owner fence 与素材
staging。Telegram ID 只可参与 Bot 回调的确定性请求 ID，不能作为账本用户主键。
同一次 Bot 点击使用 `optimizer_request_token` 固定该次 `client_request_id`；终态失败后
用户再次点击必须生成新的 token 和请求 ID，避免重新 staging 后的媒体对象键与旧任务
指纹冲突。Central 对“同 ID、不同载荷”的 409 防护保持不变。Bot 只展示可操作的领域
错误，不得把 Central 内网 URL、HTTP 客户端异常或堆栈返回给用户。
快照不包含生成 Worker 使用的魔法触发词。最终输出校验同时拒绝 `hmmotion`、
`HMBreasts`、`HMPenis`、`hmpussy`；旧 profile 继续使用原有词数/词汇校验，新
profile 改用官方结构与模式对齐校验。

任务扣 1 灵石；Task Core 的扣费、派发补偿、pending 取消和失败退款负责 exactly
once。文本结果只保存在 `allbot:prompt_result:{task_id}` 类 owner-fenced Redis key，
TTL 24 小时；不写 History、R2 或 Gallery。

普通日志只记录 task ID、lane，以及白名单格式的错误类型/校验码。Worker 向 Central
上报 `PromptOptimizationExecutionError:<code>` 或 `ModelResponseError:<code>`；未知
异常只上报类型，不包含异常文本。禁止记录原始提示词、data URL、图片内容或 LLM
原始响应。

任务载荷包含服务端生成的 `text_stream_contract`。Worker 使用
`POST /api/agent/task/text-delta` 上报 `attempt_id + sequence + field + delta`；
Central 原子检查 running、worker owner、Profile 字段和累计长度。重复序号幂等忽略，
跳号返回期望序号，Web SSE 通过 `text_snapshot` 恢复后继续接收 `text_delta`。
增量快照 TTL 24 小时，不包含原始 prompt、图片或完整 LLM JSON。
Central 的 `PromptOptimizeRequest` 必须显式保留 `trusted_context`、
`prompt_config_snapshot` 和 `text_stream_contract`；禁止依赖 Pydantic 的 extra 字段，
否则这些协议字段会在入队前被静默丢弃。
本地 Worker Relay 必须同步转发 `/api/agent/task/text-delta` 的请求体、上游状态码与
响应体；不能只覆盖传统媒体 Worker 的 pop/status/complete/heartbeat 路由。

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
版本化模板合并为纯文本请求，再通过当前 LM Studio 构建已验证的
`/v1/completions` + `response_format.json_schema` 使用 structured output。纯文本 Profile
跳过第一阶段。若 HauhauCS 视觉阶段只返回 reasoning item，可仅将其作为不落盘的
视觉观察继续；最终结构化阶段把动态 schema 同时放入 API format 和 system 指令，
仍由 OutputValidator fail closed。HauhauCS/Qwen 的 Chat Completions 模板会把长 H3
候选错误路由到 reasoning channel，因此最终阶段保留已通过真实 H3 canary 的 text
completion 模板；不得改成只依赖提示词约束，也不得从两个输出通道拼接候选。
两个请求都必须
`store=false`，不得把原始响应写日志；超时 180 秒，
只对 429、5xx、网络错误或 timeout 重试一次。非法 JSON、未知字段、空文本或超过
2000 字符直接失败。不得通过剥离 Markdown fence 等宽松解析绕过 fail-closed。

结构化阶段支持 Responses SSE。Worker 只提取 `optimized_fields` 白名单字符串，处理
任意 chunk、JSON escape 和 Unicode；最终 `json.loads`/schema 结果必须与已发送文本
完全一致。首个 Central delta 确认前可按既有规则重试一次，确认后禁止重新生成并拼接
第二份输出。

健康入口：`127.0.0.1:8097/health` 和 `/ready`，只暴露 ready reason、
`ready_lanes` 与 `active_lanes`，不暴露提示词或媒体。本机受控恢复使用仅绑定
loopback 的 `POST /drain` 停止新 pop，等待 `active_lanes=0` 后再释放模型显存。

## 5. 发布与回滚

Registry 内容仍遵循 Worker-first、Web-activation-last；涉及增量协议时固定为：

1. 部署兼容旧 Worker 的 Central 增量接口和 Redis snapshot。
2. 部署识别 `text_snapshot`/`text_delta` 的 Web API；旧前端仍只处理 progress。
3. 构建并部署 `prompt-optimizer-worker` exact digest，验证真实 structured stream。
4. 最后部署 Public Web，启用只读流式预览。
5. 验证 `/ready`、四 lane、断线、重复/跳号、部分失败退款与日志隐私。

Compose 禁止源码 bind mount，镜像必须 digest pinned。rollback 只回退到状态账本中的
上一 exact digest。prod mutation 仍需用户明确确认。

115 GPU0 与正式图生图共享显存时，只允许运行
`scripts/prompt_optimizer_worker_ops.py preflight|takeover|recover|status`。`takeover`
通过 LAN fleet 事务排空、持久禁用并停止精确图生图 slot，再以 16K/parallel 4/full
offload 加载 LM Studio，并验证 `/ready` 与四条 test Central idle heartbeat。任一步骤
失败会停止优化器、卸载本次模型并调用 fleet `recover`；主动恢复也必须先 drain 四条
lane。若 preflight 的 fleet live observation 已明确表明精确旧 slot 不在运行，
`takeover` 将该停机视为幂等完成，不再对已停止容器调用 Comfy queue 检查。
Central 状态核验必须使用测试环境 `AGENT_SECRET_TOKEN`，不得匿名读取
`/system/workers`。Prompt Optimizer Compose 使用独立 project name；清理只允许移除
该项目及固定的 `allbot-prompt-optimizer-test` 容器，禁止 `--remove-orphans` 波及同机
测试基础设施。fleet 恢复的物理槽必须使用 `<node>:gpuN` 格式。禁止临时
Docker/Compose 命令绕过 XDG ledger。

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
