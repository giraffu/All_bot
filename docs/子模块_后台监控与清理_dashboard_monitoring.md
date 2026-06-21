# 子模块: 后台监控与清理 (Dashboard & Monitoring)

## 1. 目标与范围
本模块包含面向管理员的 Dashboard 视图与显式管理动作，用于查看系统任务统计、Worker/Queue 运行态、用户与内容大盘，并在异常情况下通过统一 core/runtime 入口执行任务终止与清理。

当前知识口径下，Dashboard 不是“僵尸任务主处理器”；真正的任务运行态治理已收口到：
- `task_core` facade
- `task_core_runtime.py`
- `QueueManager`
- `TaskRegistry`
- `force_terminate_task(...)` / runtime cleanup

## 2. 当前架构图

```mermaid
sequenceDiagram
    autonumber
    participant Admin as 管理员
    participant Dash as Dashboard API
    participant Core as task core / runtime
    participant Queue as QueueManager / Worker 视图
    participant Registry as TaskRegistry
    participant PG as PostgreSQL

    Admin->>Dash: 1. 请求系统统计与任务视图
    Dash->>Core: 2. 获取系统任务统计 / 管理动作能力
    Dash->>Queue: 3. 获取 queue / worker 聚合视图
    Dash->>PG: 4. 获取用户/内容大盘统计
    Dash-->>Admin: 5. 返回管理控制台数据

    Admin->>Dash: 6. 发起强制终止 / 清理动作
    Dash->>Core: 7. 调用 force terminate / runtime cleanup
    Core->>Registry: 8. 清理 registry_task_id
    Core->>Queue: 9. backend_task_id best-effort cancel
    Core-->>Dash: 10. 返回终态 / 补偿结果
```

## 3. 当前职责边界
### 3.1 Dashboard 负责什么
- 系统大盘与管理视图
- task stats、worker/queue 状态聚合
- 管理员显式触发的终止、清理与只读查询
- 用户列表过滤/排序与用户资产迁移预览；用户转移接口支持 `dry_run=true` 先返回迁移计划且不修改数据库
- 管理接口鉴权与审计

### 3.2 Dashboard 不负责什么
- 不定义任务补偿主链
- 不直接把 Redis 手工删键当作标准治理方式
- 不以 `zombie_cleaner_service`、`active_tasks` 哈希、固定 10 分钟阈值作为主文档口径

## 4. 推荐接口语义
### 4.1 系统统计
- 读取聚合后的系统任务统计
- 补充 worker / queue 视图
- 不把旧字段名固定成唯一契约
- Dashboard 大盘 stats 属于高成本查询，后端使用短 TTL 进程内缓存与 single-flight 合并并发请求；前端 stats 请求不得强制附加 `_t` 缓存击穿参数。
- Dashboard 的灵石消耗统计以 `user_logs` 账本为准：生成任务负向流水计入消耗，`refund%` 退款流水抵扣消耗；`history` 仅用于成功生成量、类型分布与小时分布，不再用“视频 6 / 图片 2”硬编码反推灵石。
- Worker 视图区分 `active_workers`、`healthy_workers` 与 `accepting_workers`：前者表示有 heartbeat，`healthy_workers` 表示 heartbeat 状态为 `idle/running`，`accepting_workers` 表示同时健康且 agent control 为 `enabled`、可接新单。
- `comfy_online` 按 `healthy_workers > 0` 判定；全部节点 `error/quarantined` 时必须显示不可用；若 `healthy_workers > 0` 但 `accepting_workers=0`，应展示为“节点健康但接单关闭/维护中”。
- Worker 卡片应展示 `error` / `quarantined`、`control_state`、`control_reason`、最近错误、失败次数、心跳时间与预计恢复时间，不能把故障节点或 `disabled/draining` 节点渲染为空闲可接单
- Worker/queue 监控通过云 Central `/system/status` 与 `/system/workers` 获取短缓存观测快照；这两个接口不是强一致调度入口，管理后台不要用高频轮询压垮 Central/Valkey。
- Dashboard 生产前端已具备云端 Nginx 网关配置：`cloud-dashboard-frontend-prod` 默认绑定云正式 Tailscale IP 的 `8086`，静态资源由云控制面提供，`/api/` 在 Docker 内网直连 `dashboard-backend-prod:8043`。本地局域网 `http://192.168.1.115:8086/` 仍可作为局域网/回退入口，但不再是唯一前端承载方式。
- 前端队列监控默认约 10 秒轮询一次；并发统计约 60 秒刷新一次；活动任务表约 15 秒刷新一次。除非有明确压测证据，不要降到 2 秒或更高频。
- Dashboard Nginx 网关会对 `/api/stats*` 做约 15 秒短缓存，对 `/api/system/status`、`/api/system/workers`、`/api/system/concurrency_stats` 做约 5 秒短缓存；登录、退款、封禁、删除、清理僵尸任务等写操作不得缓存。
- Worker listener 应作为受监督后台循环运行；异常后由外层循环重试，不递归 `create_task`，并且每轮退出都显式关闭 pubsub / Redis client。

### 4.2 强制终止
- Dashboard 应优先调用 core 暴露的系统任务管理入口，如 `force_terminate_task(...)`
- 退款、锁释放、runtime cleanup 与双 ID 清理由 core/runtime 统一完成

### 4.3 用户转移
- 用户列表入口的查询条件应先归一化为 `UserListQuery`，再进入查询与 presenter，保持路由参数和响应字段兼容。
- 用户转移先计算 `UserTransferPlan`，再执行真实迁移；`dry_run=true` 时只返回 before/after、预计 moved_counts 与合并决策，不写库、不写审计日志。
- 真实转移会把历史、模板共建、签到、账本日志、订单、affiliate 流水、广场投稿/评论/互动、提示词解锁、关注关系与邀请关系并入目标用户；`gallery_prompt_unlocks.user_id + post_id`、`user_follows.follower_id + followee_id` 等唯一锚点在迁移前必须先去重，避免删除源用户时触发非空外键或唯一约束错误。
- 真实转移的 `extra_info` 必须包含 before/after 快照、moved_counts，以及 membership / ban / stats 的合并决策，便于后续追溯。

### 4.4 RunPod 管理
- 系统监控页顶部的 `RunPod 管理` 是云正式手动 RunPod 池的 Web 日常入口；后端 API 位于 `dashboard/backend/routers/runpod.py`，执行层收口到 `dashboard/backend/services/runpod_admin_service.py`。
- Dashboard 不直接实现 RunPod 创建/删除逻辑，只异步调用 `scripts/runpod_prod_ops.sh`，继承 CLI 的门禁、无库存重试、disabled heartbeat、自动 enable、drain/delete 语义。
- `POST /api/runpod/scale` 接收多 profile 新增数量，后台拆成 profile 级 `add --count N` operation。旧字段 `desired_count` 只作兼容输入并按新增数量解释，不再代表目标总数；同一请求中同一 profile 不允许重复。
- 当前可管理 profile 为 `img2img`、`image_to_video`、`wan22_video_v2`、`i2i_pro` 与 `scail2 / 视频生视频`。`scail2` 支持正式 `scail2_action_transfer`、`scail2_video_replacement`，但它是手动备用/临时扩容能力，不代表系统里固定常驻一个 RunPod；没有 heartbeat 或已删除的 `runpod_prod_scail2_manual_NN` 不应计入可用容量。
- `POST /api/runpod/workers/{agent_id}/pause` 只提交 `disable` operation，停止目标 RunPod worker 接新单但保留 Pod。
- `DELETE /api/runpod/workers/{agent_id}` 提交 `down` operation，先 disable 并等待 `current_task_id` 清空，再删除 Pod 释放 RunPod 计费资源。
- RunPod operation 状态通过 `RunPodOperationStore` seam 持久化；生产默认使用 Redis，测试可注入 in-memory fake。Redis key 固定为 `dashboard:runpod:operations` sorted set、`dashboard:runpod:operation:{id}` JSON、`dashboard:runpod:active_add:{profile}` active add 锁。
- `GET /api/runpod/operations` 从 store 读取最近 operation，并叠加当前进程仍持有的 process handle 状态；响应保留旧字段，并增加 `owner_id`、`attached`、`can_terminate_reason`。
- `终止` 只允许当前 Dashboard 进程仍能安全控制的 add operation。若 operation 来自旧进程或重启后已 detached，API 返回 409，不按 Redis 里的旧 pid 盲杀进程，避免 PID 复用误杀。
- 默认保留最近 100 条 operation；完成态 Redis JSON TTL 为 24 小时，运行态不主动过期，避免长操作丢失追踪。
- Dashboard RunPod mutation 只打开显式执行门禁：`RUNPOD_DRY_RUN=false`、`RUNPOD_AUTOSCALER_ENABLED=true`。全局 Pod 数、单类型 Pod 数、小时成本上限不再由 Dashboard/API/provider 校验；`RUNPOD_PROD_MAX_MANUAL_SLOTS` 默认按 `100` 作为 manual slot 命名空间。
- Dashboard 容器默认可通过 `DASHBOARD_RUNPOD_ENV_FILE`、`DASHBOARD_RUNPOD_PROD_ENV_FILE`、`DASHBOARD_RUNPOD_OPS_SCRIPT` 覆盖脚本和 env 路径；云正式容器中未存在 `.env.cloud.prod` 文件名时，默认可使用挂载的 `/app/.env`。
- API 响应和 operation log 只保留脱敏命令、状态、pid、退出码与日志尾部，不输出 `.env.*` 内容、RunPod API key、agent token、JWT、R2 key 或 presigned URL。

## 5. 测试要求
- 覆盖 Dashboard 鉴权中间件
- 覆盖系统统计接口的基础返回
- 覆盖 `healthy_workers`、`accepting_workers`、`error_workers`、`quarantined_workers`、`workers_by_status` 与 `workers_by_control_state` 聚合
- 覆盖 Dashboard 对 `error/quarantined` Worker 的红色/隔离态展示
- 覆盖 Dashboard RunPod 管理入口的 profile 校验、新增数量 add 命令、旧 `desired_count` 兼容、`scail2 / 视频生视频` 选项、worker pause/delete slot 解析，以及前端 typecheck / 系统监控页渲染。
- 覆盖管理员强制终止时的：
  - `registry_task_id` 清理
  - `backend_task_id` best-effort cancel
  - runtime cleanup / 锁释放
- 覆盖 worker / queue 视图补齐与异常场景
- 覆盖 stats 缓存命中、single-flight 并发合并、Central proxy 超时兜底与前端不击穿 stats 缓存
- 覆盖用户列表筛选/排序、用户转移 dry-run 无副作用、真实转移审计快照，以及提示词解锁/关注关系迁移去重

## 6. 部署与运维
- Dashboard 随部署脚本更新，但不应被文档描述为“僵尸任务自动自愈中心”。
- 若出现 stuck task，应优先通过 Dashboard 管理动作或 core 暴露的终止入口处理。
- Redis 手工删键只作为极端故障兜底，不作为标准 SOP。
- 管理后台卡顿时先区分三类问题：Dashboard stats 重查询、Central 观测接口慢、GPU/ComfyUI 执行停顿。GPU 生成短暂停顿不等同于 Dashboard worker 监控慢。
- 云测试 Dashboard 前端由 `deploy/docker-compose-cloud-test.yml` 的 `cloud-dashboard-frontend-test` 提供，默认 `http://100.82.124.91:8087/`，用于先验证云端前端体验。
- 云正式 Dashboard 前端由 `deploy/docker-compose-cloud-prod.yml` 的 `cloud-dashboard-frontend-prod` 提供，默认 `http://100.107.220.127:8086/`。生产发布前必须先经云测试验证并由用户确认，且 `CLOUD_PROD_BIND_IP` 不得为 `0.0.0.0`。
- 只更新管理后台系统时，操作范围应限于 `dashboard-backend-prod` / `dashboard-frontend-prod`；如果只改前端展示或 RunPod profile 识别，只重建 `dashboard-frontend-prod`。验证使用 `http://100.107.220.127:8043/api/health` 与 `http://100.107.220.127:8086/api/health`，并确认 Central/Web/Bot/Payment/imgproxy/worker/RunPod 未被重启或重建。
- 面向公网访问管理后台时，必须使用 Cloudflare Tunnel + Cloudflare Access 或等价身份层保护，回源到 `100.107.220.127:8086`；不要把 `8086` 或 `8043` 裸露到公网。
- 本地管理后台入口由 `dashboard/docker-compose-local-gateway.yml` 管理，可作为局域网/回退入口。原本地上线流程是先启动 `dashboard-local-gateway-8085` canary，验证后停止旧 `8086` Vite dev 进程，再启动 `dashboard-local-gateway-8086`；该流程不需要重建云端正式 Dashboard Backend。
- 旧的 `0.0.0.0:8043` SSH 转发只作为临时兼容入口；长期应移除或收紧到 `127.0.0.1`，避免绕过受控网关直连云后端。

## 7. 告警建议
- 任务终态异常率
- runtime cleanup 失败率
- worker 存活率与 queue 堆积
- 恢复失败率与 force terminate 失败率
