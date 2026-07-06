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
- `task_core` 只能依赖内部类型、协议和显式 provider/dependencies。不要在 `src/core/` 引入 Telegram `Update`、FastAPI `Request/APIRouter`、SQLAlchemy session 全局对象或 Worker HTTP 细节。
- “双 ID”必须区分：`task_id` 是 AllBot 业务 ID，`backend_task_id` 是 Central/Worker 执行 ID。运行时锁、状态轮询、历史落库和退款日志必须写清使用哪一个。
- `cleanup_task_runtime_state(...)` 是运行态收口入口。取消、失败、成功、恢复脚本和 finalizer 都应走同一类清理语义，不要复制散落删除 Redis/DB 状态。
- Web side-effect monitor 默认入口是 `monitor_task_and_release_lock_default(...)`。Web 提交成功后的锁释放、终态观测和异常收口应通过 monitor，而不是让 request handler 长时间持有业务逻辑。
- 成功结果持久化使用 `TaskSuccessPersistenceCommand` 语义收口。新增结果字段时，同时检查 History、Gallery/apply、LTX/SCAIL-2 extra context 和 Bot completion。

## 3. 高压红线

- Core Isolation：`src/core/` 禁止平台对象和入口层对象。入口层把 Telegram/Web 请求转换为内部 request/context 后再调用 core。
- 扣费与入队是 Saga：扣费成功但提交失败必须补偿；提交成功但后续执行失败必须走终态与退款规则，不得静默丢状态。
- Web 锁必须有释放路径。提交、取消、monitor 超时、finalizer 异常、用户断连都不能让同一用户永久卡住。
- finalizer 处理终态前必须重新读取权威状态并考虑幂等。重复 complete/status、重复 Bot completion、重复 History 插入不得生成多份业务结果。
- 用户取消退款必须使用 `registry_task_id` 派生的账本幂等键；用户取消接口、Web monitor 或恢复流程重复观察到 `cancelled` 时，只允许第一次 `refund_user_cancel` 真正增加灵石。
- finalizer 内部异常不能阻断 runtime cleanup。清理失败要记录并暴露可恢复信息，但不要让任务永远停在 running。
- provider/dependencies 不要在 import 时绑定运行态资源；测试优先显式注入 fake provider、fake queue、fake persistence。
- Central/Redis transient error 应按可重试基础设施故障处理：入队等幂等安全写可有限 retry，真实出队 `zpopmin` 不做盲 retry；Central Redis retry 耗尽返回 503，Bot/Web 应映射为“当前服务器繁忙”并走补偿/收口路径。
- 不要只改 `SIMPLE_TASK_TYPE_MAP` 就宣称新增任务类型完成。必须核对 request model、dispatcher、registry、Central route、worker mapping、SUPPORTED_TASK_TYPES、workflow 和结果持久化。
- 不要在任务类型里继续扩大 legacy alias。用户可见类型、执行类型、Central 类型和 workflow/profile 的映射要明确记录。

## 4. 当前任务链

1. Bot/Web/QQCC 入口收集用户输入，转换为内部 payload 和用户身份。
2. Web API 或 Bot service 调用 `process_and_submit_task(...)`，完成配额/权限、扣费、输入准备和持久化。
3. core 通过 provider/dependencies 提交 Central。Central 维护队列、状态和 worker 协议，不负责 UI/FSM 语义。
4. Worker 根据 `SUPPORTED_TASK_TYPES` 拉取任务，下载输入，选择 workflow/runtime profile，调用 ComfyUI，materialize 结果并上报 complete/status。
5. Web monitor、Bot completion 或恢复流程观察终态，持久化 History/extra outputs、释放锁、退款或清理运行态。

分层职责必须保持：入口层负责体验和平台适配；core 负责业务编排；Central 负责队列和执行状态；Worker 负责运行时素材、workflow 和结果上报。

## 5. 任务类型变更清单

- `src/domain_config/task_type_registry.py` 是只读事实表和一致性门禁。它记录 public type、legacy alias、execution type、Central type、workflow filename、RunPod profile、Gallery/apply 和成本字段。
- 新增/调整类型时同步检查：入口 request model、Web payload builder、Bot FSM、`backend/app/main_simple_task_routes.py`、`src/workflow_mapping_validation.py`、worker `SUPPORTED_TASK_TYPES`、workflow 文件、billing cost、History/Gallery 展示。
- Web 入口可以在 `src/web_api/services/task_submission_service.py` 做入口级禁用，不代表 core/dispatcher/worker 删除能力；当前 `i2i_draw` 局部重绘已在 Web 端关闭，会在生成 Web `task_id`、扣费和入队前拒绝。
- Wan22 旧图生视频、`video_insert`、`video_edit` 和懒人动图的差异应尽量停留在入口 payload 或 patcher，不要复制新 workflow 或新执行类型。
- LTX 当前用户入口主要是单首帧和首尾帧；`ltx_video_v2v_audio` 仍是历史/队列兼容执行类型。LTX 扩展链要保留 `ltx_prev_task_id`、`ltx_chain_task_ids`、`extra_outputs.last_frame` 和 stitch 语义；Bot 扩展 seed 与拼接链 histories 恢复优先改 `src/services/ltx_video_extension_service.py` 并补 focused tests。
- Wan22 AIO Bot 扩展/重生成/拼接链覆盖旧图生视频 `custom_video` / `video_lora` 与图生视频 v2，必须保留 `wan22_prev_task_id`、`wan22_chain_task_ids`、`extra_outputs.last_frame` 和 stitch 语义；Bot 扩展/重生成 seed 与拼接链 histories 恢复优先改 `src/services/wan22_video_v2_extension_service.py` 并补 focused tests。
- Bot 高级视频入口的提交计划事实源是 `src/services/advanced_video_submission_service.py`；`image_to_video_fsm.py`、`wan22_video_v2_fsm.py`、`ltx_video_fsm.py` 只做 Telegram 编排和额度检查。LTX Bot payload 的分辨率、时长和模式必须显式传给 `process_ltx_video_task(...)`，不要借用 `context.user_data` 顶层键桥接后台任务参数。修改旧图生视频/Wan22 v2/LTX Bot payload 时优先覆盖该 service 的 focused tests，再跑 handler 回归。
- SCAIL-2 用户侧任务类型包括 `scail2_action_transfer`、`scail2_video_replacement`、`scail2_face_swap_v2`；内部仍保留 `scail2_action_transfer_long` 执行类型承接动作迁移 10/15/20s。公开动作迁移允许 5/8/10/15/20s，业务/History 仍记 `scail2_action_transfer`；dispatcher 按时长选择短 workflow 或隐藏 Context Windows workflow。时长、成本、驱动视频大小、默认 prompt、History type 长度和 LAN/RunPod 承接差异都必须按文档核对。
- `i2i_pro` 是 RunPod runtime profile，不是默认新增业务类型。它可承接 `i2i_pro`、`t2i-pornmaster-turbo`、`face_swap` 等执行映射，workflow override 要跟随 worker 配置。

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
- 新任务类型：至少补 registry 一致性测试、payload builder/入口测试、worker mapping/patcher 测试和一条端到端黄金路径。
- 部署前：测试优先更新云测试控制面；正式发布必须用户明确确认，并说明 pending/running 处理策略。

## 8. 交付要求

- 修改任务生命周期后，同步必要的 `/docs`、`.codex/skills` 和 `docs/knowledge_base_audit_matrix.md`。
- 最终回复列出：触达入口、任务类型、队列/worker 影响、测试命令、是否涉及扣费/退款、是否需要云测试或正式部署。
- 如果本技能正文再次接近 20KB，把低频 checklist 或排障案例拆到 `references/` 或子模块文档。
