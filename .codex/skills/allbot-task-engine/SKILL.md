---
name: "allbot-task-engine"
description: "处理 AllBot 任务提交与执行生命周期：facade、provider/dependencies、双 ID、扣费补偿、Central 队列、Worker 接单、pending/running 卡住、取消/zombie、结果不返回、终态持久化与运行态清理。开发任务能力或排查队列积压、Worker 不接单时必须使用。"
---

# AllBot 任务引擎

修改任务提交、排队、执行、完成、取消、退款、恢复或 zombie 清理时必须加载
本技能。线上异常叠加 `allbot-diagnosing-bugs` 和 `ops-log-monitor`；计费
叠加 `allbot-billing-auth`；workflow/profile 叠加 `allbot-comfy-models`；
行为变更叠加 `allbot-tdd`。

## 1. 按需阅读

| 场景 | 必读事实源 |
| --- | --- |
| facade、provider/dependencies、扣费补偿 | `docs/子模块_任务调度_task_scheduler.md`、`src/core/task_core*.py` |
| Web 提交、monitor、取消、结果 | `docs/子模块_生成任务全链路_task_full_chain.md`、`src/web_api/services/*task*` |
| Central 队列与 Worker 协议 | `docs/子模块_中控API与节点通信_central_api.md`、`backend/app/queue_manager.py` |
| 新任务类型与 workflow | `src/domain_config/task_type_registry.py`、`scripts/generate_task_type_contract.py`、`src/workflow_mapping_validation.py`、`allbot-comfy-models` |
| 黄金路径 | `docs/子模块_任务黄金路径回归清单_task_golden_path.md` |

任务类型枚举、profile 深度、某次 worker override 和历史迁移只保留在 registry、
专项文档或归档，不写成 Skill 顶部流水。

## 2. 稳定接口与分层

- `TaskApplication(...).submit(...)` 是提交 seam；command/policy/journal 分别承载
  事实、控制和恢复。注入依赖先归一策略输入，再于扣费/派发前按 registry task ID
  提升 staging；入口不得复制门禁。
- `process_and_submit_task(...)` 只保留为测试/兼容适配层，调用时必须显式提供
  `TaskCoreProcessDependencies`；生产 Web/Bot/QQCC/Dashboard 不得再导入它，也不得
  增加 callback 参数。优先级只影响队列；`user_cancel_allowed=false`
  必须通过 policy 写入 active registry，由 core runtime 权威拒绝取消。
- `cleanup_task_runtime_state(...)` 是成功、失败、取消、finalizer 和恢复脚本
  的统一运行态清理 seam，不复制散落 Redis/DB 删除。
- Web side-effect monitor 使用
  `monitor_task_and_release_lock_default(...)`；request handler 不长时间持有
  终态轮询和锁释放逻辑。
- 成功持久化通过 `TaskSuccessPersistenceCommand`/公开 persistence seam；
  新结果字段同步检查 History、Gallery/apply、Bot presentation 和扩展 context。
- 入口层负责 Telegram/Web 适配；core 负责业务编排；Central 负责队列与执行
  状态；Worker 负责输入、workflow、ComfyUI、结果物化和上报。
- `src/domain_config/task_type_registry.py` 是任务类型唯一人工维护源；前端只读
  `frontend/src/generated/taskTypeContract.ts`。registry 变化后运行生成器并用
  `--check`、Central/Worker/profile 一致性测试防漂移，禁止手改生成文件。
- `src/core/` 只能依赖内部类型、协议和显式 provider/dependencies，禁止
  Telegram `Update`、Web `Request/APIRouter`、基础设施 session 或 Worker
  HTTP 实现。Core 不拼 Redis key；并发计数校准通过 submission outbox 的
  `sync_user_concurrency(...)` capability 执行。

Web、主 Bot、QQCC（含私有 Worker）和 Dashboard 启动入口显式调用
`configure_task_application()`；未装配时 `get_task_application()` fail closed。Web
finalizer intent、Bot recovery identity 和私有 QQCC ledger 分别使用独立 journal。
新增代码只能使用 command/policy/journal，不扩大旧签名或增加模块级 fallback。

## 3. 双 ID 与终态不变量

- `registry_task_id` 是 AllBot 用户态 ID，`backend_task_id` 是 Central/Worker
  执行 ID。锁、状态、History、取消和退款必须明确使用哪一个。
- 多阶段任务保持一个根 registry ID，并使用确定性 backend/stage ID。中间
  stage 不得重复扣费、暴露结果或创建重复 History。
- 扣费与入队是 Saga：扣费成功但提交失败必须补偿；执行失败或取消必须进入
  统一终态/退款；不能静默丢失状态。
- Web 主链在 Central dispatch 前写入 version 2 submission intent，phase 为
  `prepared -> dispatching -> accepted -> terminal`，歧义进入 `reconciling`。
  `dispatching` 落盘后禁止自动退款、删 registry 或重复派发；API 返回
  同一 task ID 和 `submission_state=reconciling`。Central 明确 404 必须连续
  3 次且跨度至少 60 秒才可判定未接纳；超时、5xx 和断网不计数。
- 退款幂等键从根 registry task 派生。Web monitor、取消 API、Bot completion
  和恢复重复看到同一终态时，只允许第一次真正改变账本。
- finalizer 在写终态前重新读取权威状态并保持幂等。内部异常不能阻断 runtime
  cleanup；清理失败需保留可恢复证据。
- Web finalizer Hash 是恢复事实，due-time ZSET 是索引；写 record 同步刷新 score。
  runner 只取到期小批次，禁止 `HGETALL`；处理中保留 member 并用单任务 lease，终态
  原子清理。Pub/Sub 仅提前 due，事件丢失由 ZSET 兜底。
- `task-control-worker` 承载 reconciliation、Web finalizer 和 zombie sweep，三者各用
  leader lease。迁移先启用并确认 health/lease，再关闭旧循环；重叠靠单任务 lease/
  幂等账本，不能同时翻转。
- Central zombie 清理必须把 task heartbeat-lost 归因到已绑定 Worker；明显连续
  失联的单实例通过有界、自动过期的 agent control 临时隔离，不能继续无限 pop，
  也不能借此自动重启或删除 provider/GPU runtime。
- Web 用户锁在派发前失败、确定未接纳、取消和终态时释放；
  `dispatching/reconciling` 期间必须保留 owner，不得因 monitor 超时或断网释放。
- presentation 的 `record_history=false` 只隐藏内部 stage 的 History/计数，
  不跳过结果物化和运行态清理；`send_result=false` 也不能替代 History 语义。
- 人物子图由全局 store 按服务端并发补位、逐图注册悬浮任务，不绑定页面生命周期；
  四个基础槽位 ready 后由服务端自动合成面板。

## 4. provider、队列与 Worker 红线

- provider/dependencies 不在 import 时绑定运行态资源；入口负责注册，core
  不自动注册。测试通过显式 fake provider/queue/persistence seam。
- Central/Redis transient error 按可重试基础设施故障处理。幂等安全写可有界
  retry；真实出队等非幂等操作不能盲重试。耗尽后返回可识别的繁忙/503 并
  进入补偿路径。
- worker pool 容量准入、用户等级豁免、fail-open/fail-closed 条件以任务调度
  文档和当前实现为准；必须在扣费/入队前完成，不能用全局队列总数替代
  profile pressure。
- Worker 只领取 supported、prefetch 与 pipeline policy 的类型交集；preferred 必须
  是 supported 子集。Central claim 是 at-least-once，活跃 backend task 的重投只
  确认 heartbeat/claim，不得重复准备、workflow、finalizer、上传或 complete；
  Worker 重启且本地 execution 不存在时可恢复接纳。
- `gpu_done` 只表示释放 Comfy 槽；结果上传成功且 Central `/complete` 确认后
  才能终态。claimed、execution、delivery 和 reserved 都计入对应有界容量。
- 新 Worker media completion 携带 SHA-256、byte size、content type 和可选实际
  维度。Central 只完整校验 staging 一次（原生 checksum 可零读取），durable
  copy 后只 HEAD；Web 仅在 durable key 与完整可信 metadata 一致时零下载写
  History。`task-results/` 不复制原件到 `history/`，只生成相邻缩略图；legacy
  保留下载和 History 兜底。
- 文本 Worker 的 `text_delta`/snapshot 仅属于可恢复运行态；attempt、sequence、
  owner 和字段契约必须在 Central 原子校验。重复 chunk 不重复追加，跳号用快照
  修复；计费、退款和成功持久化仍只跟随权威终态。
- 不要只改一个 route/map 就宣称任务类型完成。同步核对 request model、
  dispatcher、registry、Central route、worker mapping、supported types、
  workflow、billing、History/Gallery 和结果持久化。
- 用户可见类型、execution type、Central type、workflow 和 profile 必须显式
  映射；不要扩大 legacy alias 或用新 tag 伪装旧镜像能力。

## 5. 多阶段与私有 QQCC

- Web/Bot continuation 必须先持久化版本化 intent/checkpoint，再切 active
  registry 和提交下一阶段。checkpoint 写失败时保留锁与 registry，不能先
  发送结果。
- 私有 QQCC 使用
  `client_type=bot:qqcc-private:<private_bot_id>` exact match；owner 不替
  访客付费。主 Bot、官方 QQCC 和其它租户不能抢恢复。
- 私有提交必须有持久 ledger、owner fence、同事务 debit marker、稳定
  concurrency/refund key 和安全 retention。只清理超期、无 active 引用且
  补偿完成的安全终态。
- continuation 每阶段先 CAS 保存结果，再清理 registry。最终进入
  `delivery_pending` 后由 lease owner 发送，成功再标 delivered；恢复扫描
  不依赖 TaskRegistry 非空。
- 私有 webhook stream 保持全局 inflight、单 Bot prefetch、deferred ID 有界；
  启动先追平 PEL，再读取新消息，同 Bot 保序。容量耗尽通过 Redis 背压，
  不丢弃已接纳 update。
- generic/manual zombie cleaner 必须跳过 private client type；私有任务只走
  tenant-aware cleaner。暂停/禁用不终止已扣费后台任务。

## 6. 排障顺序

- 提交失败：身份/余额 → payload normalization → provider → 扣费补偿 →
  Central response → backend ID 写入。
- pending：队列 score → worker health/enabled → supported type/profile →
  capacity/drain/maintenance。
- running：Worker 日志 → ComfyUI → patcher → materialization → upload →
  complete/status → cleanup。
- Web 卡锁：monitor → authoritative terminal state → cancel/refund →
  lock release。
- 结果不可见：History/persistence → extra outputs → Bot binding →
  Gallery/apply → 当前 R2 媒体。
- zombie：先复现和分类 owner/client/status/lease，再使用受控恢复/清理 seam；
  不直接删除 Redis 或数据库记录。

## 7. 最小验证

- core：提交成功、provider 失败、扣费后提交失败补偿、重复终态幂等、runtime
  cleanup 和用户锁释放；另覆盖“dispatch 成功 + finalizer attach 失败”且不得
  错误退款/删 registry。
- Web：API、monitor、取消/不可取消、超时、结果轮询和退款幂等。
- Central/Worker：queue pop、status/complete、unsupported type、mapping
  validation、重复上报和上传前不得 complete。
- 多阶段：intent/checkpoint 先落盘、stage ID、无重复扣费、中间结果隐藏、
  失败/取消补偿和跨重启恢复。
- private：exact tenant、ledger、bounded stream、PEL catch-up、tenant cleaner
  和 metrics freshness。
- 新任务类型：registry 一致性、入口 payload、billing、worker mapping/patcher
  以及至少一条成功和一条失败/补偿黄金路径。
- 交付列出触达入口、ID/type/profile、扣费退款、队列/Worker、测试命令和
  环境状态；不能把本地代码验证写成已部署。
