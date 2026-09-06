# 子模块：中控 API 与节点通信（Central API）

## 1. 定位与边界

Central API 是 AllBot 的 backend 执行控制面，代码入口为 `backend/app/`。它接收
上游已经完成权限、计费和输入准备的任务，维护 Redis 队列与执行状态，并向 Worker
提供领取、心跳、进度、完成和控制协议。

稳定调用链是：

```text
Bot / Web -> task core facade -> submission provider -> Central API -> Worker
```

Central 不负责用户身份、额度、扣费退款、History/Gallery 持久化或入口展示。
`registry_task_id` 属于用户任务域，`backend_task_id` 属于 Central/Worker 执行域；
跨层取消、恢复和终态收口必须显式转换，不能混用。

## 2. 代码结构与事实源

| 入口 | 职责 |
| --- | --- |
| `backend/app/main.py` | FastAPI 组合根、路由注册和依赖装配 |
| `backend/app/main_bootstrap.py` | Redis/MinIO 生命周期、认证与基础设施异常映射 |
| `backend/app/main_simple_task_routes.py` | registry 驱动的简单任务路由与请求归一 |
| `backend/app/main_status_result_routes.py` | task status、result、cancel HTTP 路由 |
| `backend/app/main_response_helpers.py` | status/workers 只读快照和响应组装 |
| `backend/app/routers/agent.py` | Worker 协议适配与完成回流指标 |
| `backend/app/agent_router_helpers.py` | Worker route 的协议服务层 |
| `backend/app/queue_manager.py` | Central 稳定 facade、Redis key 与队列/状态能力 |
| `backend/app/queue_selector.py` | score/allowed/preferred 选择、peek、位置与队列指标 |
| `backend/app/worker_registry.py` | Worker heartbeat、control、task binding 与 outcome 视图 |
| `backend/app/queue_manager_flow_helpers.py` | task/worker 状态转换的纯逻辑与可替换 seam |
| `backend/app/result_storage.py` | staging 校验、durable copy 与完成资产契约 |

任务类型唯一人工维护源是 `src/domain_config/task_type_registry.py`。新增或调整任务
类型时必须同步生成前端只读契约，并运行：

```bash
python scripts/generate_task_type_contract.py --write
python scripts/generate_task_type_contract.py --check
pytest -q tests/config/test_task_type_contract.py
```

`QueueManager` 是现有调用方的稳定 facade。队列选择和 Worker registry 已分别下沉
到 `RedisQueueSelector` 与 `RedisWorkerRegistry`，调用方仍只依赖 `QueueManager`。
新增职责不要继续堆入路由；后续只有在 task 状态职责发生变化时，才继续形成内聚的
task store，避免为了文件数量制造浅封装。

## 3. 生命周期与基础设施

- FastAPI lifespan 创建一个共享 Redis client，request dependency 和 zombie 巡检
  复用该连接池；关闭时先取消后台巡检，再关闭 Redis。
- 缺少 app state 的离线/测试调用才允许 dependency 创建临时 Redis client。
- Redis client 统一由 `src.services.redis_connection.build_redis_client(...)` 创建，
  不使用裸 `Redis.from_url(...)`。
- MinIO 初始化失败时 Central 可以启动，但需要资产提升的完成请求会按稳定错误契约
  失败；不能把未验证的 staging 路径直接写成 done。
- Redis 瞬断对安全读取和幂等写入做有限重试；真实出队等非幂等操作不得盲重试。
  重试耗尽由统一异常处理返回 `503` 和 `Retry-After: 2`。

## 4. 队列与任务状态

### 4.1 入队与查询

- simple route 从 registry 派生 Central `TaskType`，请求通过 Pydantic v2
  `model_dump()` 归一后入队。
- 同一 `backend_task_id` 和同一请求指纹重复提交是幂等成功；同 ID 不同请求返回
  admission conflict，不能覆盖原任务。
- `/status/{backend_task_id}` 是单任务观测接口。pending 可返回全局 0-based
  `queue_pos`；显式请求时额外返回同类型 0-based `queue_type_pos`。
- task status 与 system status 使用有界短 TTL/stale 快照吸收轮询；这些缓存只用于
  观测，不得参与 dequeue、CAS 终态或取消判断。

### 4.2 peek、pop 与 preferred types

- `/api/agent/task/peek` 是只读预取 hint，不修改 pending/running/status/heartbeat。
  候选 task hash 按批次通过 Redis pipeline 读取，避免逐任务 `EXISTS + HGETALL`
  放大；结果顺序仍由 pending score 决定。
- `/api/agent/task/pop` 才是权威领取入口，会原子移除 pending 并进入 running。
- `preferred_types` 必须是 `types` 的子集。存在 preferred 时优先最早 preferred，
  否则回退最早 supported task；真实领取在单次原子操作内完成。
- Worker 传 `agent_id` 时，`draining/disabled` control 会阻止新领取。旧 Worker
  未传 `agent_id` 的行为属于协议兼容，不得据此扩大新调用方。
- claim delivery 是 at-least-once。Worker 必须以 `backend_task_id` 作为幂等键；
  活跃 task 的重投只确认绑定，不能重复创建 Comfy prompt、上传或 complete。

### 4.3 取消与终态

- pending task 可直接取消；running task 是否可取消由 `cancel_locked` 和
  `execution_phase` 决定。
- `pop?cancel_lock=true` 表示 Worker 已进入不可安全撤销的准备/执行阶段；此后用户
  取消返回 `not_cancellable`，不得再写 `cancel_requested`。
- legacy 未锁定 running task 保留 best-effort `cancel_requested` 语义，等待执行端
  确认。上游仍负责退款、用户锁和 registry cleanup。
- done/error/cancelled 使用原子终态门禁；迟到 heartbeat/status/fail 不得覆盖终态
  或重新绑定 Worker。

## 5. Worker 协议

### 5.1 心跳与控制

- Worker heartbeat 状态为 `idle`、`running`、`error`、`quarantined`，并可携带
  health reason、最近错误、provider/GPU/runtime/profile 等只读元数据。
- heartbeat key 扫描后由一次 Redis pipeline 批量读取 Worker 明细；running Worker
  的当前任务补充信息再由第二次 pipeline 批量读取，避免按 Worker 产生 N+1 查询。
- `/system/status` 中 `active_workers` 是有 heartbeat 的数量，`healthy_workers`
  是健康运行态数量，`accepting_workers` 还要求 control 为 `enabled`。
- agent control 状态为 `enabled/draining/disabled`。Central 只维护控制键，不直接
  重启、删除或扩缩 provider、Pod、Docker、GPU/LAN runtime。
- task heartbeat 只允许刷新存在且非终态的 task，并确认 delivery、绑定
  `worker_id/current_task_id`。终态或缺失 task 只清理残留绑定，不能创建残缺 hash。
- zombie 巡检复用 lifespan Redis client。heartbeat-lost 会归因到已绑定 Worker；
  达到代码中有界阈值时可写自动过期的 disabled control，但不替代基础设施恢复。

### 5.2 状态、文本流与结果

- `/api/agent/task/status` 只更新运行态；`set_current=false` 可用于流水线阶段更新而
  不覆盖 Worker 当前任务指针。
- `/api/agent/task/text-delta` 是文本任务的可选运行态协议，按 owner、attempt、
  连续 sequence、字段白名单和长度原子校验；重复 sequence 幂等，跳号返回期望值。
- `/api/agent/task/complete` 是成功回流唯一确认点。文本结果可直接使用 text
  contract；媒体结果使用 `result_asset` / `extra_output_assets`。
- 媒体 Worker 先写 `staging/worker-results/{backend_task_id}/...`，上报 SHA-256、
  byte size、content type 和可选媒体维度。Central 校验后服务端复制到
  `task-results/{backend_task_id}/...`，再提交 done。
- 资产提升必须幂等。跨 task key、大小/hash 不符、copy 或 HEAD 复验失败时返回稳定
  `detail.code` 和 `retryable`，不能先写 done。
- 未携带 `result_asset` 的旧媒体完成请求受
  `LEGACY_RESULT_COMPLETION_ENABLED` 门禁保护，并记录
  `compat.central.legacy_media_completion`。退出条件以
  `config/compat_registry.json` 为机器事实源；不能只凭静态搜索删除。

## 6. 观测接口

- `/system/workers`：当前 heartbeat worker 明细及 control 状态。
- `/system/status`：queue size、按类型 pending、最长等待、worker 健康/接单统计和
  profile pressure。它是 Central 执行面视图，不等同于 Dashboard 用户任务聚合。
- `/system/worker-outcomes`：当前 heartbeat worker 的短期终态结果聚合；写入是
  best-effort，遥测失败不得回滚权威 task 终态。各 Worker 的窗口查询通过一次
  pipeline 批量读取，不按 Worker 串行往返 Redis。
- `/api/agent/task/result-storage-metrics`：资产提升失败、完成契约覆盖率和 I/O 计数。
  进程内计数重启会清零，不是持久账本；compat 退出看统一 telemetry。

排查 pending 时按以下顺序：queue score → worker heartbeat/health → control state →
supported type/profile → capacity/drain → 上游 submission。排查 running 时按：Worker
日志 → ComfyUI → patcher → materialization/upload → Central complete/status → 上游
finalizer。不要把状态快照滞后解读为队列事实丢失。

## 7. 兼容与知识治理

- 活跃兼容入口必须先登记 `config/compat_registry.json`，记录 owner、telemetry、替代
  契约、无命中窗口和历史数据退出条件。
- 当前 Central 兼容包括 legacy Wan22 task type 和 legacy media completion；详情以
  registry 为准，不在本文复制可能变化的退出状态。
- 真实 Worker ID、IP、Pod 数量、当前镜像、test/prod 拓扑、canary 结果和某次发布
  动作属于 provider/XDG/日志/归档，不写入当前架构文档。
- route、请求/响应字段、ID、状态机、Redis 生命周期、Worker 协议、compat seam 或
  task type 变化时，同步本文、任务引擎 Skill（若稳定路由变化）、兼容表和审计矩阵。

## 8. 最小验证

- 入队：幂等提交、同 ID 冲突、registry/Central/Worker task type 一致。
- 队列：score 顺序、allowed/preferred、pipeline 批量 peek、原子 pop 和并发不重复。
- 状态机：pending/running/done/error/cancelled、locked cancel、迟到回报和 CAS。
- Worker：heartbeat/control、claim 重投、task heartbeat、zombie 归因和临时隔离。
- 完成：asset/text/legacy 三种契约、校验失败、copy retry、重复 complete 和兼容遥测。
- 生命周期：request 与 zombie loop 共用 Redis，shutdown 先停 loop 再关连接。
- 文档与门禁：`python3 scripts/validate_compat_registry.py`、
  `python3 scripts/doc_quality_checker.py`。

Central 是独立部署模块，但代码验证不等于已发布。构建、test/prod 部署或环境配置
变更必须另行遵守 `allbot-ops-deployment`，本模块重构不得顺带操作运行环境。
