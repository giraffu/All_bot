# P1 Central Redis 韧性、失败窗口任务核对与容量升配方案

生成时间：2026-06-16 03:23 Asia/Shanghai  
范围：方案与只读采样结论；未执行任何生产变更、重启、扩容或账务写操作。

## 0. 结论先行

1. `P1 后端` 要做，但不能只给所有 Redis 调用粗暴套 retry。Central 的 `pop` 当前存在多步 Redis 写入：先从 pending 移除，再标记 running/heartbeat。这里如果在中间断连，单纯重试可能二次出队或造成任务游离。P1 修复应同时包含：
   - Redis 关键读写的有限 retry/reconnect。
   - `pop/dequeue` 的原子化或可恢复 claim 设计。
   - `/status/{task_id}`、`task_heartbeat`、`agent status/heartbeat`、`complete` 的 focused tests。

2. `P1 运维` 先做只读核对，再做幂等补偿。02:45-02:49 窗口不是“任务全部丢失”。已有初筛显示：Central 任务 76 个，`done=54`、`error=22`、`missing_everywhere=0`；其中有一批 `done + result_path` 但 Web history/finalizer 未收口，优先按“补 history/finalizer，不重跑、不退款”处理。

3. 按你补充的峰值口径重新评估：`pending≈200`、`worker≈16`、pipeline 下 `running≈16-32`。原先 `8 vCPU / 16GB RAM` 只能算云主控制面的最低生产线；更稳妥的长期规格是 `8 vCPU / 32GB RAM`，或把 Bot/Web API/Dashboard 拆到第二台节点。Valkey 这边，1GB 实例低峰长期约 70-75% memory usage，且 eviction policy 是 `noeviction`，建议把主节点从 `$15/mo 1GB` 升到 `$30/mo 2GB`；PG 当前 `max_connections=50` 且已约 37 连接，峰值下应优先升连接/IO 档位或加 PgBouncer。

## 1. 当前只读快照

采样时间约 2026-06-16 03:21 Asia/Shanghai。

| 项目 | 当前值 | 判断 |
| :--- | :--- | :--- |
| 云控制面 load average | `1.55 / 1.46 / 1.60`，4 vCPU | CPU 未打满 |
| 云控制面内存 | `7.8GiB total / 6.0GiB used / 1.7GiB available` | 高峰和发布余量偏紧 |
| 云控制面磁盘 | `154G total / 91G used / 64G avail`，59% | 暂未到磁盘告警 |
| `cloud-web-api-prod` | CPU 约 27%，内存约 2.0GiB | 主要内存使用者之一 |
| `cloud-tg-bot-prod` | CPU 约 22%，内存约 2.7GiB | 主要内存使用者之一 |
| `cloud-central-api-prod` | CPU 约 8%，内存约 144MiB | Central 本身非内存大户 |
| Central 队列 | `queue_size=55`，`healthy_workers=8`，`running=6`，`idle=2` | Worker 不是全停，仍在消化 |
| Redis/Valkey | 应用 `INFO` 样本曾见 `used_memory=75.66MB`、`connected_clients=71`、`blocked_clients=0`、`evicted_keys=0`；DigitalOcean 节点图显示 1GB 实例低峰 memory usage 长期约 70-75% | Redis key 数据量不大，但托管节点总内存余量偏薄，且 `noeviction` 接近上限会直接导致写失败 |
| PostgreSQL | DB `3286 MB`，`max_connections=50`，连接约 37，`waiting_locks=0`，`idle_in_transaction=0` | 无锁灾难，但连接余量偏小 |

Central 队列分布：`img2img=32`、`img2img_lora=8`、`wan22_video_v2=13`、`i2i_pro=1`、`face_swap=1`。瓶颈更集中在任务类型容量和长耗时任务，而不是 Central CPU。

### 1.1 峰值容量假设与修正

你补充的真实峰值应作为容量规划基线，而不是上面的只读快照：

| 指标 | 快照值 | 峰值规划值 | 容量含义 |
| :--- | ---: | ---: | :--- |
| pending queue | 约 55 | 约 200 | Redis 内存压力仍小，但队列扫描、Dashboard 观测和用户等待会放大 |
| healthy workers | 8 | 约 16 | Worker heartbeat、task heartbeat、complete/status 回流约翻倍 |
| Central running | 6 | 约 16-32 | pipeline 默认最多 2 个 Central running / worker，需按 32 估算僵尸扫描和 task heartbeat |
| 用户侧轮询/SSE | 未按峰值采样 | 可能接近 pending 数量 | Web API、Redis Pub/Sub、PG history/result 查询压力上升 |
| 结果上传/回查 | 8 worker 口径 | 16 worker 口径 | R2 上传、HEAD 探测、Web result 轮询会成为用户体感瓶颈 |

粗略控制面写入量估算：
- Worker agent heartbeat：`16 workers / 15s`，约 64 次/分钟。
- Task heartbeat：`16-32 running / 15s`，约 64-128 次/分钟。
- `complete/failed/status`：取决于任务完成频率和进度上报，正常不应压垮 Redis。
- `/system/status`：已有 10 秒 TTL/stale cache；即使 pending 200，每次 zrange/hget 类型统计也还在轻量范围。

所以峰值 200/16 的主要硬件压力不在 Central 队列数据量本身，而在：
- 云主控内存余量不足，Bot/Web API/Dashboard 同机竞争。
- PG 连接数、history/result 查询和日志表增长。
- Redis/Valkey 低规格实例的连接稳定性和延迟尾部。
- R2 结果探测、用户 result 轮询和媒体分发。
- 算力面任务类型不均衡导致队列堆积，尤其视频和 img2img 高峰。

## 2. P1 后端：Central Redis retry/reconnect 修复

### 2.1 目标

在 Redis/Valkey 短暂 reset、timeout、连接池拿到坏连接时，Central 不应把瞬时故障放大成：
- `/status/{task_id}` 500。
- Worker `task_heartbeat` / `status` 500。
- Worker `complete` 回报失败。
- pending 任务从队列移除但未进入 running 的游离状态。

### 2.2 修改落点

优先集中在 Central 执行面：
- `backend/app/queue_manager.py`
- `backend/app/queue_manager_flow_helpers.py`
- `backend/app/main_response_helpers.py`
- `backend/app/agent_router_helpers.py`
- `backend/app/main_bootstrap.py`
- `backend/app/dependencies.py`

建议新增小模块：
- `backend/app/redis_resilience.py`

### 2.3 实现策略

1. 新增统一 Redis 韧性 helper。
   - 默认 `attempts=3`，初始退避 `50ms`，指数退避加少量 jitter，最大不超过 `250ms`。
   - 只捕获连接类瞬时错误：`redis.exceptions.ConnectionError`、`redis.exceptions.TimeoutError`、`ConnectionResetError`、`OSError` 中的连接断开类错误。
   - 捕获后调用连接池断开坏连接，例如 `await redis.connection_pool.disconnect(inuse_connections=True)`，然后重试。
   - 记录聚合日志字段：`op_name`、`attempt`、`exception_type`、`reconnected=true`，不记录任务 prompt、URL、token 或连接串。

2. 按幂等性分层接入 retry。
   - 可安全 retry：`hgetall`、`hget`、`exists`、`zcard`、`zrange`、`zrank`、`scan`、`smembers`、`setex heartbeat`、`hset heartbeat/status metadata`、`expire`。
   - 可接受重复事件但要依赖下游幂等：终态 `hset + srem + publish`。Web finalizer/history 已要求 `user_id + task_id + source` 幂等，仍需补测试确认重复 event 不会重复落 history 或重复退款。
   - 不可粗暴 retry：`zpopmin`、`zrem -> mark running`、`cancel pending` 这类“从一个集合移到另一个状态”的多步操作。

3. `dequeue/pop` 必须单独加固。
   - 最低要求：把 pending -> running -> task status -> task heartbeat 的状态迁移收敛成一个原子操作，优先 Lua 脚本或 Redis transaction。
   - 支持 `allowed_types` 过滤时，脚本从 pending 前 N 个任务扫描类型，命中后一次性完成 `zrem`、`sadd running`、`hset status/cancel_locked/execution_phase`、`setex heartbeat`。
   - 如果不做原子化，至少要补“zrem 成功但 mark running 失败”的恢复扫描，把游离任务重新放回 pending 或补齐 running/heartbeat。但 P1 更推荐原子化，简单、可测、后患少。
   - 对 `pop` 不建议在未知成功状态下盲目 retry；如果要 retry，必须有 agent claim/idempotency token 或“同 agent 未确认任务优先返回”的设计。

4. `complete` 回报加固。
   - Worker `complete` 是成功收口硬依赖；Central 侧失败会让已上传结果停在执行面之外。
   - `complete_task_payload` 路径应在 `record_task_worker`、`clear_agent_current_task(compare-and-clear)`、`complete_task` 上具备有限重连能力。
   - 终态事件允许重复，但 history/finalizer 必须幂等；测试要显式覆盖重复 `done` event。

5. 观测接口加固。
   - `/system/status`、`/system/workers` 已有短 TTL/stale cache，继续保留。
   - `/status/{task_id}` 已有 2 秒 cache，但首次 miss 时仍可能 500；需用 Redis retry/reconnect 包住 `get_task_status` 和 `get_queue_position`。

### 2.4 测试清单

必须新增或补强 focused tests：
- `tests/backend/test_queue_manager.py`
  - `get_task_status` 首次 Redis `ConnectionError`，重连后成功。
  - `update_task_heartbeat` 首次 `ConnectionResetError`，重连后成功。
  - `update_agent_heartbeat` 首次 timeout，重连后成功。
  - `complete_task` 重试后只形成一个最终状态，重复事件不破坏幂等。
  - `dequeue_task` 在注入“移除 pending 后失败”的场景下不会丢任务；原子化后应无法出现 pending/running 双空。
  - `peek_pending_tasks` 仍保持只读，不写 pending/running/status/heartbeat。
- `tests/backend/test_agent_router_helpers.py`
  - `task_heartbeat_payload`、`update_status_payload`、`complete_task_payload` 遇到瞬时 Redis 错误时返回成功。
- `tests/backend/test_main_helpers.py`
  - `/status/{task_id}` Redis 首次失败时使用 retry，最终返回 200。

推荐本地命令：

```bash
python -m pytest \
  tests/backend/test_queue_manager.py \
  tests/backend/test_agent_router_helpers.py \
  tests/backend/test_main_helpers.py -q
```

### 2.5 云测试验证

默认只走云测试，不直接发布正式。

1. 部署前：
   - 确认 Alembic 单 head。
   - 跑上述 focused tests。
   - 云测试 `/health`、`/system/status`、`/system/workers` 正常。

2. 云测试部署：

```bash
scripts/safe_deploy_cloud_test.sh
```

3. 云测试验收：
   - 提交 `img2img` 或最短耗时 canary 任务。
   - 同时轮询 `/status/{task_id}` 与 `/system/status`。
   - 验证 worker heartbeat、status、complete 均成功。
   - 如要做 Redis 故障注入，只允许在云测试、低峰、确认无重要测试任务时做；优先用单测故障注入，不建议随手重启 Redis。

### 2.6 正式发布门禁

正式发布必须由用户明确确认。确认后建议只更新 `cloud-central-api-prod`，不做全量 compose。

发布前只读检查：
- `cloud-central-api-prod`、`cloud-web-api-prod`、`cloud-tg-bot-prod` 健康。
- `/system/status` 有 `healthy_workers > 0`。
- 当前 queue/running 快照已保存。
- 无 Alembic 多 head；若无 DB migration，不执行 DB upgrade。

发布方式：
- 优先 `scripts/safe_deploy_cloud_prod.sh --preflight-only`。
- 然后按 SOP 单服务重建或脚本发布 Central。
- 禁止 `--remove-orphans`、全组 compose restart、无 service 名批量操作。

发布后验证：
- 云内 `8003/health`、`8003/system/status`、`8003/system/workers`。
- Worker `pop/status/task_heartbeat/complete` 最近日志无高频 5xx。
- `queue_size`、`running`、`healthy_workers` 趋势正常。
- Web `/api/tasks/{id}/stream` 和 `/result` canary 正常。

回滚：
- 回滚 Central API 上一版本代码/镜像。
- 只重建 `central-api-prod`。
- 回滚后复核 pending/running，必要时运行只读僵尸任务审计。

## 3. P1 运维：02:45-02:49 失败窗口任务核对

### 3.1 时间窗口

北京时间：2026-06-16 02:45:00 至 02:49:59  
UTC：2026-06-15 18:45:00 至 18:49:59

### 3.2 已有初筛结论

已有只读初筛显示：
- Central 窗口任务：76
- Central 状态：`done=54`、`error=22`
- `missing_everywhere=0`
- `done_with_history=38`
- `done_no_history_no_tracker=16`
- `terminal_non_success=22`

解释：
- 不是整批任务丢失。
- 有 16 个任务更像“Worker 已生成且 Central done，但 Web history/finalizer 没收口”。
- 22 个 `error` 需要逐个确认用户端终态和退款/补偿是否已幂等完成。

### 3.3 核对维度

对窗口内每个 backend task 建立一张 reconciliation 表，字段至少包括：
- `backend_task_id`
- `registry_task_id`
- `created_at`
- `task_type`
- `central_status`
- `result_path`
- `worker_id`
- `pending_member`
- `running_member`
- `task_heartbeat_ttl`
- `active_task_registry_present`
- `pending_web_finalizer_present`
- `history_present`
- `history_source`
- `user_log_refund_or_failure_present`
- `recommended_action`

### 3.4 分类与处理动作

| 分类 | 判定 | 动作 |
| :--- | :--- | :--- |
| `done_with_history` | Central `done`，有 `result_path`，history 已落 | 不处理，只记录 |
| `done_no_history_no_tracker` | Central `done`，有 `result_path`，无 history、无 finalizer/active tracker | 不重跑、不退款；走幂等 Web finalizer/history 补落库 |
| `error_refunded` | Central `error`，用户端失败，退款/补偿流水已存在 | 不处理，只记录 |
| `error_refund_missing` | Central `error`，未见补偿流水 | 走既有退款/失败补偿入口，禁止手写 `UPDATE users SET credits` |
| `running_no_heartbeat` | running 仍存在，但 heartbeat TTL 缺失或过期 | 先确认 worker 不再执行；再走 zombie cleanup/失败补偿 |
| `pending_still_queued` | 仍在 pending | 不改状态；确认有支持类型 worker，继续排队或按容量策略扩容 |
| `central_missing_active_present` | Central hash 缺失，但 Web active registry 仍有任务 | 走 Web monitor fallback，必要时标失败并补偿 |

### 3.5 执行方式

建议新增或使用一次性只读审计脚本，默认 `--dry-run`：

```bash
python scripts/audit_prod_failure_window_tasks.py \
  --env cloud-prod \
  --start "2026-06-16T02:45:00+08:00" \
  --end "2026-06-16T02:49:59+08:00" \
  --dry-run
```

输出：
- 明细 CSV：`logs/task_reconciliation_20260616_0245_0249.csv`
- 摘要 Markdown：`logs/task_reconciliation_20260616_0245_0249.md`

安全要求：
- 不输出 prompt、用户敏感输入、R2 presigned URL、token、数据库连接串。
- 只输出 task id、状态、类别、动作建议和聚合数量。

### 3.6 补偿门禁

任何会改用户资产、任务状态或 history 的动作都必须二次确认，并满足：
- 先跑 `--dry-run`，人工确认明细。
- 走项目现有幂等入口：Web finalizer、terminal finalization、billing/refund provider。
- 禁止直接改 `users.credits`。
- 每个补偿动作必须有幂等锚点，例如 `task_id + action_type`。

## 4. 容量与升配建议

### 4.1 总体硬件判断

按 `pending≈200`、`worker≈16`、`running≈16-32` 的峰值口径，当前 `4 vCPU / 8GB RAM` 云主控制面只适合作为过渡规格，不适合长期承接生产高峰。

推荐分三档：

| 档位 | 云主控制面 | 数据面 | 适用判断 |
| :--- | :--- | :--- | :--- |
| 最低生产线 | `8 vCPU / 16GB RAM`，建议 320GB 盘或至少严格 log rotate | Redis/Valkey ≥ 1GB；PG 连接上限 ≥ 100 或 PgBouncer | 能承接 16 worker + 200 pending 的常规峰值，但余量有限 |
| 稳定推荐 | `8 vCPU / 32GB RAM`，或 `8 vCPU / 16GB` + Bot/Web/Dashboard 拆第二台 | Redis/Valkey 1-2GB；PG 升连接/IO 档位 | 更适合每天出现 200 级队列、Dashboard/结果页同时活跃 |
| 大促/持续高峰 | `16 vCPU / 32GB RAM` 或多节点拆分 Web API/Bot/Central | PG 4 vCPU 级别或连接池代理；Redis 高可用/更高连接档 | 适合持续 16+ worker、用户轮询密集、媒体读写高峰 |

结论：我会把“升 8c/16G”从“建议”改成“最低线”；如果你说的 200 队列和 16 worker 是日常高峰，不是偶发，那么更推荐 `8c/32G` 或拆服务。

### 4.2 云主控制面 Droplet

当前风险：
- 8GB 无 swap，快照 available memory 约 1.7GiB。
- `cloud-tg-bot-prod` 约 2.7GiB，`cloud-web-api-prod` 约 2.0GiB，Bot/Web 已经是内存主力。
- 16 worker 不会让 Central CPU 线性翻倍，但会放大 heartbeat、complete、R2 上传回报和用户 result 轮询。
- 200 pending 时，真正容易把主控拖慢的是 Web API/SSE/result 轮询、Dashboard 查询、Bot 消息风暴和日志 IO 叠加。

建议：
- 立即规划从 `4c/8G` 升到至少 `8c/16G`。
- 如果预算允许，直接升 `8c/32G`，或者保留 `8c/16G` 但把 Bot 或 Dashboard/Web API 拆到第二台。
- 增加 2-4GB emergency swap 或 zram 只作为 OOM 缓冲，不能当性能扩容。
- 严格启用 Docker log rotation，当前磁盘 59%，生产峰值下日志和镜像层会继续增长。

升配后目标：
- 高峰 available memory 长期 > 4GiB。
- load average 长期低于 vCPU 数的 60-70%。
- 云内 Web API/Central health p95 仍在几十毫秒到低百毫秒级。

### 4.3 Redis/Valkey

重新评估后，Redis/Valkey 的判断要拆开：

- 从数据量看：200 pending + 32 running 本身很小，不会吃掉 418MB 内存。
- 从生产依赖看：1GB 实例低峰内存长期约 70-75%，作为 Central 队列、worker heartbeat、Web runtime、并发锁、finalizer 的共同依赖，余量偏薄。
- 从故障现象看：这次 P1 的直接问题仍是连接 reset 后应用缺少 retry/reconnect，不是内存满导致。
- 从当前配置看：eviction policy 是 `noeviction`。这对任务队列是正确取向，但也意味着一旦接近 maxmemory，写入会直接失败，不会通过淘汰旧 key 自动缓解。
- 从截图看：CPU 多数在约 10-20%，rejected connections 为 0，ops 通常数百级、尖峰约千级；瓶颈更像内存余量和连接/延迟尾部，不是 CPU。

建议：
- 建议把 `allbot-valkey-sgp1-01` 从 `$15/mo 1 vCPU / 1GB RAM / 10GiB` 升到 `$30/mo 1 vCPU / 2GB RAM / 30GiB`。这不是奢侈扩容，是把低峰 75% 内存压回约 35-40%，给高峰、Redis 碎片、pending finalizer、连接波动留出安全垫。
- P1 代码修复仍优先做，尤其 Central Redis retry/reconnect 和 `pop` 原子化。
- 如果升级到 2GB 后高峰 memory 仍持续 > 70%、connected clients 经常 > 200、p99 latency 抬升或出现 rejected/timeout，再考虑 `$60/mo 2 vCPU / 4GB`。
- 重点看 24h 指标：CPU、p95/p99 latency、connected clients、rejected connections、evicted keys、blocked clients、network in/out。
- 保持 Central 共享 Redis client，不要回退到每请求新建连接。
- 不提高 Dashboard 轮询频率；`/system/status` 10 秒缓存应继续保留。
- 暂不把 standby node 和这次容量升级绑定。加 1 个 standby 会把 2GB 方案从 `$30/mo` 变成约 `$60/mo`，解决的是主节点故障可用性，不解决当前内存 75% 的容量余量；若 Bot/Web 收入链路已高度依赖 Redis 可用性，再单独开 HA。

硬件结论：不是因为“队列 200”本身要升，而是因为 1GB 实例在低峰已经 70-75% 且 `noeviction`。我建议现在升到 2GB；HA standby 另行按可用性预算决定。

### 4.4 PostgreSQL

PG 需要比上一版更积极处理。原因不是 worker 数直接打 PG，而是 200 pending 代表更多活跃用户、更多 SSE/result/history 查询，以及任务完成后更多 history/user_logs/worker_logs 写入。

当前快照已经有风险信号：
- `max_connections=50`
- 当前连接约 37，约 74% 上限
- `history` 约 2.1GB，`user_logs` 约 471MB，`worker_logs` 约 425MB
- 虽然 `waiting_locks=0`、`idle_in_transaction=0`，但连接余量已经不适合峰值扩张

建议：
- 短期先审计 Web API、Bot、Dashboard 的 SQLAlchemy pool 配置，确保总连接池上限不会超过 PG 上限 70%。
- 如果继续使用 `max_connections=50`，建议必须上 PgBouncer；否则 PG 规格升到支持 100-200 连接的档位。
- 打开慢查询/Query Insights，重点看 `/users/history`、Gallery、result、Dashboard stats。
- 给 `history`、`user_logs`、`worker_logs` 做归档或分区计划；日志表无限增长会逐步吃掉缓存命中率和 IO。
- 如果云厂商面板显示 PG CPU/IO/connection 长期高负载，我建议 PG 先升一档，不要等到连接打满再处理。

硬件结论：PG 是比 Redis 更该优先升配或加连接池代理的点。

### 4.5 算力面与 16 worker

16 worker 对 Central 调度不是大问题，但 200 pending 对用户体验是算力容量问题。主控制面升配不会把 200 队列变短，只会让提交、状态、结果回查更稳。

建议按任务类型扩容，而不是只看 worker 总数：
- `img2img/img2img_lora` pending 高时，优先补对应 RunPod profile 或恢复本地 img2img worker。
- `wan22_video_v2` pending 高时，按视频 profile 独立扩容；视频任务耗时长，少量 pending 就能造成很长等待。
- `image_to_video/ltx_video` 要单独看 worker 支持类型，避免 16 个 worker 里很多不能消费某类队列。
- 用触发阈值管理 RunPod：例如某类型 pending > 30 或最老 pending > 20-30 分钟时，启动该 profile 的备用 worker；低峰再 drain/down。

硬件结论：16 worker 只是“并发执行槽”，不是“任意任务都能被 16 个 worker 消化”。队列 200 时，需要按 `queue_by_type` 评估 GPU profile 缺口。

### 4.6 R2 / 对象存储与结果链路

16 worker 同时完成任务时，R2 写入、Web result 探测和用户结果页轮询会放大。此前已经观察过 Web API 中 result URL 探测 timeout 和用户 499，这部分会直接影响“任务完成但用户看不到结果”的体感。

建议：
- Web result 路径继续使用短超时和 `pending_result` 快速返回，不要让请求卡在 R2 HEAD。
- 对 R2 object exists / HEAD 做短 TTL 缓存，避免同一结果被多端反复探测。
- 对视频结果页保留更长轮询窗口，但每次请求要快失败。
- 单独看 Cloudflare R2 request/error/egress analytics；对象存储高负载不能通过升 PG/Redis 解决。

### 4.7 最终升配优先级

按你补充的峰值，优先级调整为：

1. 云主控制面：从 `4c/8G` 升到至少 `8c/16G`；日常 200 队列则优先 `8c/32G` 或拆服务。
2. PostgreSQL：连接上限从 50 提升到 100-200，或加 PgBouncer；同时做慢查询和日志表归档。
3. Redis/Valkey：P1 代码 retry/reconnect 必做；`allbot-valkey-sgp1-01` 建议先从 1GB 升到 2GB，HA standby 单独评估。
4. 算力面：按 `queue_by_type` 给 img/video/wan22 分别补 RunPod 或本地 worker，不按 worker 总数粗判。
5. R2/结果链路：优化 HEAD 探测、缓存和 result 轮询，减少完成后不可见。

## 5. 推荐执行顺序

1. 今天先完成 02:45-02:49 任务只读 reconciliation，产出明细和分类动作。
2. 后端实现 Central Redis retry/reconnect + `pop` 原子化或恢复机制。
3. 本地 focused tests 全绿。
4. 云测试发布与 canary 验证。
5. 用户确认后，正式只发布 `cloud-central-api-prod`。
6. 正式观察 30-60 分钟：Redis error、Central 5xx、queue/running、history/finalizer 收口。
7. 单独安排云主控制面升配；`8 vCPU / 16GB` 是最低线，日常 200 队列建议 `8 vCPU / 32GB` 或拆服务。
8. 采集 PG/Redis 24h 云厂商指标；若 PG 连接长期 > 70% 或 Redis 延迟/连接长期高负载，同步升数据面规格。

## 6. 验收标准

后端 P1：
- Redis 瞬断不会导致 `/status/{task_id}`、`task_heartbeat`、`status`、`complete` 高频 500。
- `pop` 故障注入下不会出现任务 pending/running 双空。
- 终态重复事件不会重复 history、重复退款或重复用户通知。

运维 P1：
- 02:45-02:49 窗口任务都有明确分类。
- `done + result_path` 的任务要么已有 history，要么进入幂等补 history 队列。
- `error` 任务退款/补偿状态明确。
- 无 raw prompt、URL、token、密钥泄露到报告。

容量：
- 主控制面升配后，高峰 available memory 长期保留 > 4GiB；若使用 8c/32G，则目标 > 10GiB。
- PG 连接长期低于上限 70%，慢查询和等待锁不持续出现。
- Redis 无 rejected/evicted/blocked，p95/p99 延迟稳定，连接 reset 经 retry 后不再形成用户可见 5xx。
- 16 worker 峰值下，Central `/system/status`、worker heartbeat、complete 回流保持稳定。
