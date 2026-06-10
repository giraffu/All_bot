---
name: "allbot-task-engine"
description: "处理任务提交流程、provider/capability 装配、双 ID 运行态清理、Web side-effect monitor 与队列/僵尸任务收口。开发或修改任务生命周期逻辑时必须调用本技能。"
---

# AllBot 任务引擎与调度 (Task Engine)

本技能覆盖 AllBot 中最核心的任务生命周期逻辑，适用于任务提交、排队、监控、取消、恢复、清理、并发锁与运行态状态同步相关开发。

## 0. 使用前先看什么
- 若需求涉及“生成任务从前端到 worker 的完整链路”，优先联读 `docs/子模块_生成任务全链路_task_full_chain.md`
- 若需求聚焦 `task_core` 的 provider/dependencies、monitor、runtime cleanup，联读 `docs/子模块_任务调度_task_scheduler.md`
- 若需求聚焦执行面与 worker 通信，联读 `docs/子模块_中控API与节点通信_central_api.md`
- 排障时不要只盯某一层；必须先判断问题位于前端提交、Web API、task core、执行面还是 worker/workflow

## 1. 模块功能描述
- **Facade + Provider 架构**：`src/core/task_core.py` 仅保留稳定 facade；真实默认装配由 `task_core_service_providers.py`、`task_core_default_dependencies.py`、`task_core_submission.py`、`src/services/task_web_side_effects.py`、`src/services/task_web_lifecycle_monitor.py`、`src/services/task_web_terminal_finalization.py`、`task_core_runtime.py` 承担。runtime-specific persistence 默认装配在 `src/task_core_persistence_defaults.py`，core 仅依赖 `src/core/user_logger_protocol.py`。
- **统一任务提交**：`process_and_submit_task(...)` 负责并发锁、扣费、输入准备、Saga 提交、side effect 挂载与失败补偿。
- **双 ID 生命周期**：系统同时区分 `registry_task_id` 与 `backend_task_id`；恢复、取消、强制终止、僵尸任务清理都必须显式区分两者。
- **Web side-effect monitor**：Web 提交成功后会异步挂载 monitor，负责成功持久化、取消退款、失败退款与 runtime cleanup。
- **成功持久化命令对象**：成功历史落库优先使用 `TaskSuccessPersistenceCommand` + `persist_successful_task_result_command(...)`；旧 `persist_successful_task_result(...)` 签名保留为薄兼容层，新增测试优先传 command / dependencies 对象。
- **僵尸任务自愈**：后台会扫描运行态 registry，执行 best-effort backend cancel、释放并发锁、清理注册表并处理退款/补偿。

## 2. 输入输出规范
### `process_and_submit_task`
- **输入**：`user_id`、`username`、`task_type`、`inputs`、`task_id`
- **可选输入**：`client_type`、`deduct_quota`、`check_lock`、`source_post_id`、`submission_side_effect_plan`、`dependencies`
- **输出**：返回 `registry_task_id`、`backend_task_id`、`cost` 与 `saved_inputs`
- **异常**：`ConcurrencyLimitError`、`InsufficientCreditsError`、`CoreDomainError`
- **红线**：Facade 层只允许消费 capability/provider 或显式 `dependencies`，禁止重新直连基础设施实现。

### `cleanup_task_runtime_state`
- **输入**：`internal_user_id`、`registry_task_id`、`release_lock`，可选 `release_concurrency_lock_func` / `remove_task_func`
- **输出**：无返回值，负责运行态清理
- **红线**：必须允许通过显式依赖注入覆写默认行为，避免测试或离线场景强依赖 provider 已注册。

### `monitor_task_and_release_lock_default`
- **职责**：Web 侧运行态监控默认入口
- **语义**：负责把 done / error / cancelled 终态路由到成功持久化、失败退款或取消退款，并完成 runtime cleanup

## 3. 核心红线
- 任务进入 core 后，`core` 目录禁止直接 import `src.services.*` 基础设施实现，必须经 provider/capability 获取。
- `core` 目录禁止直接 import `src.logger.UserLogger`；需要用户日志时通过 `UserLoggerProtocol` 与显式 dependency 注入。
- 任何失败补偿必须与并发锁释放一起考虑，不能只退款不清 runtime。
- 任何需要访问运行态或终止任务的地方，都必须显式区分 `registry_task_id` 与 `backend_task_id`。
- Web 任务完成后的历史持久化、R2 warmup、runtime cleanup 不应由 router 或页面逻辑承担，应收口到 monitor / persistence 链。
- Web finalizer 在多 worker 下可能并发扫描 pending 队列；拿到 Redis lock 后必须重新读取单条 pending record，不能使用 `hgetall` 的旧快照继续收口。
- Web 成功历史落库必须对 `user_id + task_id + source` 幂等；重复收口时不能重复插入 `History`，也不能重复触发 Web history R2 warmup。
- 默认依赖构造必须保持惰性，只在缺失且确实需要时才解析 provider，避免测试被误伤。
- `build_default_task_core_process_dependencies(...)` 已按 input、billing、submission、side-effect builder 拆分；后续扩展优先加在对应 builder，避免继续膨胀总装配函数。
- `TaskCoreServiceProviders` 与主要 capability 已补强 `Protocol` / 精确 `Callable` 类型；新增 provider/capability 时继续保持显式契约，不要扩大弱类型字段。
- provider 注册依赖模块级全局状态；测试和离线路径优先显式传入 `dependencies`，避免继续把模块级 monkeypatch 当成主路径。

## 4. 边界条件处理
- **客户端断连**：若客户端断连，仍需保证未成功提交的任务释放并发锁；已提交成功的 Web 任务由 side-effect monitor 继续收口。
- **提交失败**：Saga 失败时需补偿扣费，并释放并发锁。
- **backend 任务缺失**：best-effort cancel 收到 404 时视为后端已清理，不应阻断本地 runtime cleanup。
- **history / stream fallback**：运行态 not-found 需要转明确 fallback/terminal 语义，不能继续无界轮询。

## 5. 测试要求
- `process_and_submit_task(...)` 同时覆盖默认装配与显式 `dependencies` 路径。
- `cleanup_task_runtime_state(...)`、`force_terminate_task(...)` 覆盖双 ID 与 cleanup seam。
- Web monitor 覆盖成功持久化、取消退款、失败退款三条主分支。
- 成功持久化需覆盖旧签名和 `TaskSuccessPersistenceCommand` 两条调用路径。
- 任务提交、history fallback、stream terminal payload 与 Bot 主链回归应纳入黄金路径回归集。

## 6. 当前生成任务全链路口径
当前更准确的生成任务主链是：

`Frontend -> /api/tasks/generate -> task_submission_service -> task_core.process_and_submit_task(...) -> task_core_submission / task_dispatcher / image_service / api_client -> Central API / QueueManager -> comfy_agent（可经 local relay/sidecar）-> ComfyUI -> status/complete 回流 -> Web monitor / history / result / SSE`

实践中应始终按下面分层定位：
- **前端层**：页面表单、payload 构造、`useTaskStream` 提交、`tasksStore` 的 SSE 与结果轮询
- **Web API 层**：`src/web_api/routers/tasks.py` 与 `task_submission_service.py`
- **业务编排层**：`task_core.py` facade、submission、runtime、web monitor、persistence
- **派发层**：`task_dispatcher.py`、`image_service.py`、`api_client.py`
- **执行面**：Central API、QueueManager、agent router。`/api/agent/task/peek?types=...&limit=1` 是只读预取 hint，不能移除 pending、不能写 running、不能更新 status/heartbeat；真实执行仍必须走 `/pop`。V2 worker 可用 `/api/agent/task/pop?cancel_lock=true` 真实接单并写 `cancel_locked=1`、`execution_phase=preparing`；pending 仍可取消，locked running 返回不可取消，legacy 未锁 running 保留 `cancel_requested` 兼容语义。
- **节点层**：`workers/comfy_agent/agent_main.py` 已拆出输入准备、工作流执行、结果物化、结果上传/回报 helper；旧 `process_task(...)` 保留串行兼容路径，双槽主链由 `_launch_pipeline_task(...)`、`_prepare_and_submit_task(...)` 与 `_finalize_execution(...)` 协作完成。`workers/local_relay/relay_main.py` 是本地 worker 网关与上传 sidecar：非终态 status 可合并转发，`pop/check/complete/failed/cancelled` 必须同步转发，`/health` 是轻量存活检查，`/ready` 会探测 Central 与上传 client。新增输出类型、失败补偿、取消检查、重试策略、预取、pipeline、健康检查或上报语义时，优先下沉到 `agent_input_preparation.py`、`agent_workflow_execution.py`、`agent_result_materialization.py`、`agent_result_reporting.py` 等阶段模块，并补 Worker focused tests。
- **Worker 健康态**：Comfy Agent heartbeat 状态包含 `idle`、`running`、`error`、`quarantined`；`active_workers` 只表示有心跳，`healthy_workers` 才表示可接单。Comfy 探活持续失败进入 `error`，连续基础设施类任务失败进入 `quarantined`。Agent 到 relay/Central 的控制面请求连续失败默认达到 12 次且持续 300 秒时会以退出码 75 退出，让 Docker restart 接管；这不替代 task heartbeat zombie 清理。Dashboard 必须按健康字段展示故障而不是当作空闲。
- **Worker drain 控制**：新版 worker 会在 `/api/agent/task/pop` 携带 `agent_id`，Central 可通过 agent control 键将单个 worker 置为 `draining/disabled`，使其不再接新单但不影响其它 worker；旧 worker 不传 `agent_id` 时保持兼容。heartbeat 可选携带 GPU pool 元数据用于资源池观测。
- **Central 观测态**：`/system/status` 与 `/system/workers` 是高频观测接口，使用共享 Redis 客户端和短 TTL/stale 快照缓存；它们不参与真实任务分发、Worker `pop`、状态上报或完成回流。排障时不要把 Dashboard/观测接口延迟直接等同于队列调度卡住。
- **Worker 回报语义**：`/api/agent/task/complete` 是成功收口硬依赖，必须有限重试并在失败后进入失败路径；`/api/agent/task/status` 是运行态观测回报，允许轻量重试且重试耗尽只记录错误，不应直接让当前生成任务失败。
- **Worker 预取/上传/pipeline 语义**：预取只能在当前 ComfyUI 执行期间通过只读 `peek` 下载/规范化/上传同类型下一单输入；真实 `/pop` 的 `task_id` 命中才可复用，miss 必须丢弃缓存。开启 `PIPELINE_ENABLED` 时，每个 worker 默认最多 2 个 Central running 任务：一个 ComfyUI active/queued，一个 finalizing；WS 必须按 `prompt_id` 路由，heartbeat 必须覆盖所有本地 running/finalizing context。使用上传 sidecar 时，worker 必须等待 R2/S3 put 成功后才 `/complete`，sidecar 上传失败按当前任务失败上报。

重要边界：
- Web 主入口是 `POST /api/tasks/generate`，不是旧 generation params 口径
- `task_core` 是业务编排门面，Central API 只是执行面
- Worker 是通过 `pop` 主动拉取任务，不是上游直推 workflow
- Wan22 AIO 视频配置事实源是 `src.domain_config.wan22_aio_video`：`custom_video` / `video_lora` -> execution `image_to_video` -> `legacy_image_to_video` profile；`wan22_video_v2` -> execution `wan22_video_v2` -> `wan22_video_v2` profile。前端入口与历史 task type 不因底层合并而改名。

## 7. 新任务类型添加 Checklist
新增任务类型时，默认按以下顺序检查，不要只改单点：

### 7.1 前端
- 是否需要独立页面、入口卡片、路由
- 是否补了 payload 构造和 `task_type`
- 是否需要进入历史、详情、收藏、投稿、Gallery、i18n

### 7.2 task core / dispatcher
- `src/constants.py` 是否补了 mode、成本、名称映射
- `task_dispatcher.py` 是否接入对应策略与提交方法
- `image_service.py` / `api_client.py` 是否已新增底层提交调用
- 是否需要 provider/capability 注入或 side-effect 调整
- 若新增 provider/capability，是否继续使用显式 `Protocol` / 精确 `Callable`，并优先提供可测试的 dependencies seam

### 7.3 执行面
- 若走标准 simple route，检查 `backend/app/main_simple_task_routes.py`
- 若走 legacy bridge，明确桥接任务名与真实 backend task type
- 确认 QueueManager 能识别并分发该类型

### 7.4 Worker / workflow
- `src/workflow_mapping_validation.py` 是否补了 workflow 文件映射
- workflow JSON 是否已提供
- `workers/comfy_agent/workflows/mappings.json` 是否补了参数节点映射
- `workflow_patcher.py` 是否支持新增参数
- 目标环境 `SUPPORTED_TASK_TYPES` 是否包含该类型
- 是否确认 workflow 已落在唯一事实源 `workers/comfy_agent/workflows`，并且目标 Worker 会加载该 task type

### 7.5 结果与回归
- `task_result_service.py` 是否能返回结果：Web owner result 优先 R2，延迟敏感路径必须用 R2 公网 HEAD 快探测且不持有 DB 只读事务等待对象存储；R2 未 warmup 时图片可短签 MinIO fallback，视频必须返回 `pending_result` 等 R2；前端 `pollTaskResult` 等待窗口需覆盖分钟级 R2 warmup，避免 99% 阶段网络失败或过早停止轮询
- Web monitor / persistence 是否能落历史并完成 cleanup
- focused tests、SSE/result/history 回归、热点门禁是否已补齐

## 8. 运维排障 Checklist
### 8.1 提交即失败
- 看 `/api/tasks/generate` 返回码
- 区分 402 灵石不足、429 并发限制、400 领域错误、500 系统异常
- 确认 `task_submission_service.py` 是否正确把 prompt/inputs 注入提交

### 8.2 一直 pending
- 看 Central API 是否收到任务
- 看 queue 是否堆积
- 看是否存在支持该 `task_type` 的 Worker
- 看 worker heartbeat、`healthy_workers`、节点 `error/quarantined` 状态与 `SUPPORTED_TASK_TYPES`
- 看本地 relay `/ready` 与 watchdog dry-run；生产只观测，不要让自动恢复直接 execute，除非用户明确确认。`/ready` 返回 404 通常表示运行中的 relay 还是旧版本，watchdog 应记录 `relay_ready_endpoint_missing` 而不是反复重启。
- 看 `/system/status` 是否只是观测缓存滞后；真实判断还要结合 worker 日志、Central `pop`/status/complete 日志和队列指标

### 8.3 running 卡死
- 查 worker 日志与 ComfyUI WebSocket
- 查 `task_heartbeat` 是否继续更新
- 查 workflow / mappings 是否正确
- 查是否取消请求未被 worker 轮询到；若任务已有 `cancel_locked=1`，用户取消应表现为不可取消而不是 `cancel_requested`
- Worker 等待 ComfyUI 完成时不应只依赖 WebSocket：`wait_for_task_completion(...)` 当前以 WS 终态为快路径，并在提交后约 45 秒开始每约 12 秒主动探测 `/history/{prompt_id}`；history 已有结果时立即收口，硬超时约 30 分钟后才做最终 fallback / 失败处理。
- 日志中 `Task result not set via WS, checking history` 通常说明 worker 正在用 `/history/{prompt_id}` 补偿 WebSocket 终态缺失；这类本地 GPU/ComfyUI 短暂停顿不是 Central `/system/status` 延迟的同一根因。

### 8.4 SSE 或取消异常
- 先确认当前用的是 `registry_task_id` 还是 `backend_task_id`
- 对外接口和历史通常围绕 `registry_task_id`
- 执行面查询、best-effort cancel、worker status 更多围绕 `backend_task_id`
- 任何双 ID 混用都可能表现为“任务不存在或无权限”或 cancel 不生效

### 8.5 结果不可见
- 看 worker 是否已成功 `/complete`
- 看 history 是否已落库
- 看 R2 公网结果地址是否可解析；若 R2 未 ready，确认图片 owner result 是否返回 MinIO 短签 fallback、视频 owner result 是否继续 `pending_result`，并检查 R2 公网 HEAD 快探测短超时和前端 99% 结果轮询窗口是否生效
- 看 `/result` 返回的是成功态还是 `pending_result`
- 若 worker 已上传对象但 Central 未收到 `complete`，优先查完成回报重试日志；不要只凭 worker 本地“uploaded”日志判定任务已成功收口。

## 9. 交付要求
- 若本轮修改改变了任务提交主链、双 ID 语义、provider 注册入口、worker 支持类型或 workflow 绑定，必须同步更新：
  - `docs/子模块_生成任务全链路_task_full_chain.md`
  - `docs/子模块_任务调度_task_scheduler.md`
  - `docs/子模块_中控API与节点通信_central_api.md`
- 若改动影响知识沉淀，继续调用 `allbot-kb-auto-updater`
