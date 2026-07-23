---
name: "allbot-task-engine"
description: "处理任务提交流程、provider/capability 装配、双 ID 运行态清理、Web side-effect monitor 与队列/僵尸任务收口。开发或修改任务生命周期逻辑时必须调用本技能。"
---

# AllBot 任务引擎与调度

本技能是任务提交、排队、执行、回流和清理的轻量入口。正文保留稳定入口、红线和排障路由；长链路细节以 `/docs` 为事实源，避免技能调用时被截断。

## 1. 先读什么

| 场景 | 必读材料 |
| :--- | :--- |
| 修改任务提交、provider/dependencies、扣费补偿或 public facade | `docs/子模块_任务调度_task_scheduler.md`、`src/core/task_core.py`、`src/core/task_core_process_flow.py`、`src/core/task_core_dependencies.py` |
| 修改 Web 任务提交、side-effect monitor、取消或结果轮询 | `docs/子模块_生成任务全链路_task_full_chain.md`、`src/web_api/services/*task*`、`src/services/task_web_lifecycle_monitor.py` |
| 修改 Central 队列、worker 协议、complete/status 或 drain | `docs/子模块_中控API与节点通信_central_api.md`、`backend/app/queue_manager.py`、`backend/app/main_simple_task_routes.py` |
| 新增或调整任务类型、workflow、RunPod profile | 本技能 + `allbot-comfy-models` + `src/domain_config/task_type_registry.py` + `src/workflow_mapping_validation.py` |
| 线上 pending/running stuck、僵尸任务、支付/鉴权异常 | 叠加 `allbot-diagnosing-bugs`、`ops-log-monitor`、`allbot-billing-auth` |
| 需要锁定行为或回归 | 叠加 `allbot-tdd`，通过 public facade / API / FSM / provider dependencies seam 测试 |

## 2. 稳定入口与术语

- `process_and_submit_task(...)` 是任务提交 facade。它负责鉴权/额度入口、输入归一、provider/capability 选择、扣费、持久化、提交队列和失败补偿的编排。
- `process_and_submit_task(...)` 会把原始 `task_type` 传入 billing concurrency seam。低阶外门用户按 `worker_pool_registry` 解析目标共享执行池，并在扣费前用 Central `queue_pressure_by_worker_profile` 判断 projected pending；不得退回全局总队列阈值。
- `process_and_submit_task(base_priority=..., user_cancel_allowed=...)` 可承接入口层任务控制语义：`base_priority` 只影响 Central 队列优先级，`user_cancel_allowed=false` 写入 active task registry 并让用户取消入口直接返回 `not_cancellable`，不调用 backend cancel、不退款；默认值保持普通任务行为。
- `task_core` 只能依赖内部类型、协议和显式 provider/dependencies。不要在 `src/core/` 引入 Telegram `Update`、FastAPI `Request/APIRouter`、SQLAlchemy session 全局对象或 Worker HTTP 细节。
- “双 ID”必须区分：`task_id` 是 AllBot 业务 ID，`backend_task_id` 是 Central/Worker 执行 ID。运行时锁、状态轮询、历史落库和退款日志必须写清使用哪一个。
- Web 自由P图 v3 是单一逻辑任务、两段 backend 执行：根业务 `task_id` 固定，BF16 成功后 active registry 切到确定性的换脸 backend ID，并以 `stage2_task_type=face_swap_v2` 提交第二阶段。pending Web finalizer 必须先持久化带版本 continuation intent，再切 registry 与提交第二阶段；升级前缺少该字段或残留旧 `face_swap` 标签的 v3 intent 均强制按 `face_swap_v2` 恢复。第二阶段不得重复扣费、不得允许取消、不得持久化中间结果，失败/取消统一使用根任务退款幂等键。
- 自由P图 v2.5 的公开/History 类型是 `free_edit_v2_5`：1 张图扣 3 灵石并派发 `pornmaster_flux2_edit_bf16`，2 张图扣 7 灵石并派发仅内部使用的 `pornmaster_flux2_multi_edit_bf16`；其它图片数必须在扣费前拒绝。两者都走标准单阶段生命周期，不写 v3 continuation、不调用 `face_swap`；失败/取消按根业务任务实际扣费幂等退款。
- `cleanup_task_runtime_state(...)` 是运行态收口入口。取消、失败、成功、恢复脚本和 finalizer 都应走同一类清理语义，不要复制散落删除 Redis/DB 状态。
- Web side-effect monitor 默认入口是 `monitor_task_and_release_lock_default(...)`。Web 提交成功后的锁释放、终态观测和异常收口应通过 monitor，而不是让 request handler 长时间持有业务逻辑。
- 成功结果持久化使用 `TaskSuccessPersistenceCommand` 语义收口。新增结果字段时，同时检查 History、Gallery/apply、LTX/SCAIL-2 extra context 和 Bot completion。
- Bot 多阶段任务用 presentation `record_history` 区分公开结果与内部阶段，默认 `true`；内部阶段设为 `false` 时仍物化输出并完成运行态收口，但不写 History、生成次数或 warmup。该字段必须持久化进恢复契约；`send_result=false` 只表示不向 Telegram 投递，不能替代历史语义。

## 3. 高压红线

- Core Isolation：`src/core/` 禁止平台对象和入口层对象。入口层把 Telegram/Web 请求转换为内部 request/context 后再调用 core。
- 扣费与入队是 Saga：扣费成功但提交失败必须补偿；提交成功但后续执行失败必须走终态与退款规则，不得静默丢状态。
- Web 锁必须有释放路径。提交、取消、monitor 超时、finalizer 异常、用户断连都不能让同一用户永久卡住。
- finalizer 处理终态前必须重新读取权威状态并考虑幂等。重复 complete/status、重复 Bot completion、重复 History 插入不得生成多份业务结果。
- 用户取消退款必须使用 `registry_task_id` 派生的账本幂等键；用户取消接口、Web monitor 或恢复流程重复观察到 `cancelled` 时，只允许第一次 `refund_user_cancel` 真正增加灵石。
- 用户取消入口必须先尊重 active task registry 的 `user_cancel_allowed`。入口层可隐藏取消按钮，但权威拒绝必须在 core runtime，避免旧 Telegram/Web 按钮绕过。
- finalizer 内部异常不能阻断 runtime cleanup。清理失败要记录并暴露可恢复信息，但不要让任务永远停在 running。
- provider/dependencies 不要在 import 时绑定运行态资源；测试优先显式注入 fake provider、fake queue、fake persistence。
- Worker 池容量准入只限制 `外门弟子 + 凡人/练气期`：拒绝条件为 `(pending + 1) > 50 × max(健康 enabled Worker 数, 1)`；筑基期或内门以上豁免。Central 快照缺失、请求失败或任务未映射时 fail-open，继续执行个人并发上限，且拒绝必须发生在扣费/入队前。
- Central/Redis transient error 应按可重试基础设施故障处理：入队等幂等安全写可有限 retry，真实出队 `zpopmin` 不做盲 retry；Central Redis retry 耗尽返回 503，Bot/Web 应映射为“当前服务器繁忙”并走补偿/收口路径。
- 不要只改 `SIMPLE_TASK_TYPE_MAP` 就宣称新增任务类型完成。必须核对 request model、dispatcher、registry、Central route、worker mapping、SUPPORTED_TASK_TYPES、workflow 和结果持久化。
- 不要在任务类型里继续扩大 legacy alias。用户可见类型、执行类型、Central 类型和 workflow/profile 的映射要明确记录。
- 正式 LAN AIO Worker 以及由统一 create request 新建的 RunPod Worker 默认只允许深度 1 的原子预接：当前任务进入 ComfyUI 后用既有 `/api/agent/task/pop?cancel_lock=true` 接走同类型下一单，本地预备输入并在下一轮优先消费。`PREFETCH_TASK_TYPES` 必须跟随 `SUPPORTED_TASK_TYPES`，预接任务等待期间用 `set_current=false` 续 heartbeat，不能覆盖当前任务或扩成无界本地队列。RunPod 只对后续新建 Pod 注入该环境契约，不原地修改存量 Pod。需要把 GPU 与结果交付重叠时，必须分别设置全局占单上限、Comfy inflight 上限和交付并发；占单计数要覆盖 execution、delivery 与 reserved task，结果仍只能在上传成功且 Central `/complete` 确认后终态。当前首个例外只允许 LAN `pornmaster_flux2_edit_bf16` 使用 `3/2/1`，其它 profile 保持默认单计算槽。

## 4. 当前任务链

1. Bot/Web/QQCC 入口收集用户输入，转换为内部 payload 和用户身份。
2. Web API 或 Bot service 调用 `process_and_submit_task(...)`，完成配额/权限、扣费、输入准备和持久化。
3. core 通过 provider/dependencies 提交 Central。Central 维护队列、状态和 worker 协议，不负责 UI/FSM 语义。
4. Worker 根据 `SUPPORTED_TASK_TYPES` 拉取任务，下载输入，选择 workflow/runtime profile，调用 ComfyUI，materialize 结果并上报 complete/status。
5. Web monitor、Bot completion 或恢复流程观察终态，持久化 History/extra outputs、释放锁、退款或清理运行态。

QQCC 私有 Bot 不改变这条生成主链。访客按自己的 `internal_user_id` 计费；租户仅通过 `client_type=bot:qqcc-private:<private_bot_id>` 标记。恢复必须 exact match private ID，经 Application resolver 交回对应 Bot；`bot`、`bot:qqcc` 和其它 private ID 都不能串恢复。owner/admin 暂停或禁用只阻止新任务，已扣费任务继续进入既有终态/退款语义。

私有 Bot 提交必须使用 `private_bot_task_submissions` 持久账本。owner fence 要在并发占位前落盘，扣费日志与 `debit_confirmed_at` 必须同事务，扣费/退款/并发释放都要用 registry task 派生的稳定 key。TaskRegistry 持久 `concurrency_acquisition_key`；终态按字段存在/缺失自动区分新 keyed release 与升级前 unkeyed 任务的一次 legacy DECR，不要求人工 drain。retention 只能有界删除超期、无 active registry 引用且补偿已完成的安全终态；最少保留 30 天，不得删除可恢复/可退款行。

私有 Bot 的任务必须把 Bot presentation contract 写入 active registry，恢复时按原始 `send_result`、结果类型/prompt、输入索引和结果 metadata 处理。多阶段 QQCC continuation 由 `private_qqcc_continuation_service.py` 在 Redis 持久化原始输入、JSON stage plan、阶段序号、确定性 registry ID、当前输出和 `ready|running|delivery_pending|completed|failed` 状态；固定价链还要持久化 `billing_id`、根 registry ID、实际扣费额和退款完成标志。每阶段必须先 CAS 写入结果再清理 registry，中间阶段才可进入下一步。生成失败的 `failed` 只能由匹配 stage/registry/executor token 的当前 `running` 阶段 CAS 写入；最终投递失败可由同一 fence 从 `delivery_pending|partial_delivery_pending` 转为 `failed`，严禁覆盖已 advance 的 `ready` 或 `completed`。最终可见阶段先进入 `delivery_pending`，由持有续跑租约的 delivery owner 发送 Telegram，成功后再 CAS 标记 delivered；checkpoint 写失败时必须保留 active registry/用户锁且不得先发送。恢复扫描即使 TaskRegistry 为空也要继续扫描 ready/delivery checkpoint，并重试尚未落退款完成标志的固定价 failed checkpoint；running 且无 active registry 的阶段只能在旧续跑锁失效后 rewind。owner/admin 暂停或禁用只挡新 update，已接纳 continuation 可绕过新任务状态门禁继续，但永久解绑后必须停止。

私有 webhook stream 的消费同样属于任务入口可靠性边界：worker 的全局 inflight、单 Bot prefetch、deferred message ID 必须有界（当前默认 `64/8/1024`），body 保留在 Redis stream/PEL；启动要完整 `XAUTOCLAIM` 前任 PEL，并在 catch-up 完成前禁止读取新 `>` update，避免同租户消息越序。容量耗尽应停止读取并让 Redis 背压，不能创建无界内存队列或丢弃已接纳 update。管理员 metrics 应同时观察 stream backlog/pending、inflight/deferred、处理/DLQ/恢复失败。

私有 update 的全局 error handler 自身失败时必须标记 admission failed，禁止 worker 误 ACK。generic/manual `clean_zombies()` 无论是否传 `client_type` 都必须跳过 `bot:qqcc-private:<id>`；私有任务只能走 `clean_private_qqcc_zombies()` 的 ledger + monitor lease + tenant Application 收口。owner/admin 暂停后的 Application 若仍有已扣费 `bg_tasks`，不得因随后到达的 inactive update 被 stop/shutdown，待后台投递完成后再 idle 回收。

分层职责必须保持：入口层负责体验和平台适配；core 负责业务编排；Central 负责队列和执行状态；Worker 负责运行时素材、workflow 和结果上报。

## 5. 任务类型变更清单

- `src/domain_config/task_type_registry.py` 是只读事实表和一致性门禁。它记录 public type、legacy alias、execution type、Central type、workflow filename、RunPod profile、Gallery/apply 和成本字段。
- 新增/调整类型时同步检查：入口 request model、Web payload builder、Bot FSM、`backend/app/main_simple_task_routes.py`、`src/workflow_mapping_validation.py`、worker `SUPPORTED_TASK_TYPES`、workflow 文件、billing cost、History/Gallery 展示。
- Web 入口可以在 `src/web_api/services/task_submission_service.py` 做入口级禁用，不代表 core/dispatcher/worker 删除能力；当前 `i2i_draw` 局部重绘已在 Web 端关闭，会在生成 Web `task_id`、扣费和入队前拒绝。
- Wan22 旧图生视频、`video_insert`、`video_edit` 和懒人动图的差异应尽量停留在入口 payload 或 patcher，不要复制新 workflow 或新执行类型。
- LTX 当前用户入口主要是单首帧和首尾帧；`ltx_video_v2v_audio` 仍是历史/队列兼容执行类型。LTX 扩展链要保留 `ltx_prev_task_id`、`ltx_chain_task_ids`、`extra_outputs.last_frame` 和 stitch 语义；Bot 扩展 seed 与拼接链 histories 恢复优先改 `src/services/ltx_video_extension_service.py` 并补 focused tests。
- LTX 的可选 `negative_prompt` 必须先 trim，非空才进入任务 `inputs`；空值/缺失完全省略，确保 worker 的节点 29 默认值不被覆盖。QQCC AI视频尾帧链在最终 LTX 阶段前统一预检总费用，中间阶段失败不得提交最终视频。
- Wan22 AIO Bot 扩展/重生成/拼接链覆盖旧图生视频 `custom_video` / `video_lora` 与图生视频 v2，必须保留 `wan22_prev_task_id`、`wan22_chain_task_ids`、`extra_outputs.last_frame` 和 stitch 语义；Bot 扩展/重生成 seed 与拼接链 histories 恢复优先改 `src/services/wan22_video_v2_extension_service.py` 并补 focused tests。
- Bot 高级视频入口的提交计划事实源是 `src/services/advanced_video_submission_service.py`；`image_to_video_fsm.py`、`wan22_video_v2_fsm.py`、`ltx_video_fsm.py` 只做 Telegram 编排和额度检查。LTX Bot payload 的分辨率、时长和模式必须显式传给 `process_ltx_video_task(...)`，不要借用 `context.user_data` 顶层键桥接后台任务参数。修改旧图生视频/Wan22 v2/LTX Bot payload 时优先覆盖该 service 的 focused tests，再跑 handler 回归。
- SCAIL-2 用户侧任务类型包括 `scail2_action_transfer`、`scail2_video_replacement`、`scail2_face_swap_v2`；内部仍保留 `scail2_action_transfer_long` 执行类型承接动作迁移 10/15/20s。公开动作迁移允许 5/8/10/15/20s，业务/History 仍记 `scail2_action_transfer`；dispatcher 按时长选择短 workflow 或隐藏 Context Windows workflow。时长、成本、驱动视频大小、默认 prompt、History type 长度和 LAN/RunPod 承接差异都必须按文档核对。
- 图片换脸执行类型必须分流：旧 `face_swap` 固定使用 `face_swap.json`、默认成本 1，只由旧 V1 容量（正式启用容量为 `worker_remote_02`）承接；新 `face_swap_v2` 使用 `face_swap_v2.json`、默认成本 2，并归属 `i2i_pro` runtime profile。快速/随机换脸继续提交 V1；自由P图 v3 第二阶段和 QQCC 原脸恢复提交 V2，但组合业务不得因内部 V2 再次扣费。
- `i2i_pro` 是 RunPod runtime profile，同时也是既有幻想换脸业务类型。profile 可承接 `i2i_pro`、`t2i-pornmaster-turbo`、`face_swap_v2` 等执行映射，workflow override 要跟随 worker 配置；幻想换脸仍提交 `i2i_pro` 并按 6 灵石计费，不能机械改成双图契约的 `face_swap_v2`。

## 6. 排障路由

- 提交失败：查权限/余额、payload normalization、provider 选择、扣费补偿、Central response 和 `backend_task_id` 写入。
- Central Redis 瞬断：先查 Redis 连接 factory 参数、QueueManager retry 日志、Central 503 数量和 Bot/Web breaker key；状态轮询 breaker 不应阻断提交 breaker。
- pending 卡住：查 Central 队列、worker 在线状态、`SUPPORTED_TASK_TYPES`、profile capacity、drain/maintenance 标志和任务类型映射。
- running 卡住：查 worker 日志、ComfyUI health、workflow patcher、result materialization、complete/status 上报和 runtime cleanup。
- Web 卡锁：查 side-effect monitor、终态轮询、取消路径、用户锁 key、异常分支是否释放。
- 结果不可见：查 History 插入、`History.type` 长度、extra_outputs、Bot binding、Gallery/apply eligibility、R2/MinIO URL。
- 僵尸任务：先建立可复现反馈环，再用恢复/清理脚本按状态分组处理；不要直接删 Redis 或数据库记录。

## 7. 测试与验证

- core 改动：用 provider/dependencies seam 测提交、补偿、异常、幂等和 runtime cleanup。
- Web 改动：测 API 提交、side-effect monitor、取消/超时、结果轮询和锁释放。
- Worker/Central 改动：测 queue pop、complete/status、workflow mapping validation、unsupported task type 和重复上报。
- 私有 webhook worker 改动：测有界 inflight/prefetch/deferred、同 Bot 顺序、startup PEL catch-up 不被新消息超越、重复 claim 不重复处理及 metrics freshness。
- 新任务类型：至少补 registry 一致性测试、payload builder/入口测试、worker mapping/patcher 测试和一条端到端黄金路径。
- 部署前：测试优先更新云测试控制面；正式发布必须用户明确确认，并说明 pending/running 处理策略。

## 8. 交付要求

- 修改任务生命周期后，同步必要的 `/docs`、`.codex/skills` 和 `docs/knowledge_base_audit_matrix.md`。
- 最终回复列出：触达入口、任务类型、队列/worker 影响、测试命令、是否涉及扣费/退款、是否需要云测试或正式部署。
- 如果本技能正文再次接近 20KB，把低频 checklist 或排障案例拆到 `references/` 或子模块文档。
