# RunPod 动态扩容 ComfyUI 算力落地方案

生成时间：2026-06-10  
目标环境：AllBot 云正式控制面 + 本地局域网 GPU worker + RunPod 弹性 GPU worker

## 1. 目标

在现有 AllBot 任务系统不大改架构的前提下，接入 RunPod GPU 算力作为“按任务类型扩容”的弹性执行面：

- 当某个任务类型的 Central 队列最大等待时间超过 20 分钟时，自动增加 1 台该任务类型专属 RunPod GPU worker。
- 当该任务类型恢复空闲时，优先关闭 RunPod worker，保留本地局域网 GPU 节点作为基础算力。
- RunPod worker 只接指定任务类型，例如 `wan22_video_v2` 或 `ltx_video`，避免抢占其他任务。
- 生产初期必须有总数量、单类型数量、小时成本、冷却时间和人工熔断开关，防止成本失控。

推荐第一阶段使用 **RunPod Pods**，而不是直接上 RunPod Serverless。原因是当前 AllBot 已经是 Central queue + worker 长轮询模型，`remote_workers/` 已经支持远程 GPU 节点通过 worker 专用 Central 域名接入，RunPod Pod 可以直接复用这条链路；Serverless 的原生 `QUEUE_DELAY` 扩容很诱人，但需要把任务提交改造成 RunPod job/request 模式，改造面更大。

## 2. 官方文档依据

本方案按 2026-06-10 查询到的 RunPod 官方文档设计：

- RunPod REST API 可以程序化管理 Pods、Serverless endpoints、Network volumes、Templates，并需要 API key 鉴权：<https://docs.runpod.io/api-reference/overview>
- 创建 Pod API：`POST /pods`，支持 `templateId`、`gpuTypeIds`、`gpuCount`、`env`、`interruptible`、`networkVolumeId`、`dockerStartCmd` 等参数：<https://docs.runpod.io/api-reference/pods/POST/pods>
- 查询 Pod API：`GET /pods`，支持按 `computeType`、`desiredStatus`、`gpuTypeId`、`templateId` 等过滤，响应包含 `id`、`costPerHr`、`gpu`、`env`、`templateId` 等信息：<https://docs.runpod.io/api-reference/pods/GET/pods>
- 启停 Pod API：`POST /pods/{podId}/start` 与 `POST /pods/{podId}/stop`：<https://docs.runpod.io/api-reference/pods/POST/pods/podId/start>、<https://docs.runpod.io/api-reference/pods/POST/pods/podId/stop>
- 自定义 Pod template 可以预装依赖和模型，减少每次启动时重新安装/下载的时间：<https://docs.runpod.io/pods/templates/create-custom-template>
- Pod template 用于保存容器镜像、存储、网络、环境变量等配置，敏感信息应使用 secrets 或安全环境变量：<https://docs.runpod.io/pods/templates/manage-templates>
- RunPod Pods 按秒计费；停止 Pod 后仍可能产生持久卷/网络卷费用，container disk 停止后不计费但会被清除：<https://docs.runpod.io/pods/pricing>
- 停止后再启动的 Pod 可能遇到 GPU 分配变化，官方有 “Zero GPU Pods on restart” 排障说明；生产扩容逻辑不能只依赖重启旧 Pod：<https://docs.runpod.io/pods/troubleshooting/zero-gpus>
- RunPod Serverless endpoint 支持 `QUEUE_DELAY`、`REQUEST_COUNT`、`workersMin`、`workersMax`、`idleTimeout`，可作为第二阶段架构演进：<https://docs.runpod.io/api-reference/endpoints/POST/endpoints>

## 3. 当前系统适配点

现有系统天然适合接入 Pod 型远程 worker：

- Central API 是任务队列事实源，worker 通过 `pop / complete / heartbeat` 语义主动拉取任务。
- 任务类型由 worker 的 `SUPPORTED_TASK_TYPES` 控制；如果没有匹配 worker，任务会持续 pending。
- 生产 worker 已使用 `CANCEL_LOCK_ON_POP=true`、`PIPELINE_ENABLED=true`、`PIPELINE_MAX_RUNNING_TASKS=2`。
- `remote_workers/` 已经提供非 Tailscale 远程 GPU 节点接入方式，可通过 worker 专用 Cloudflare Tunnel 域名访问云 Central，不能复用公开 Web API 域名。
- 结果文件应继续写入生产 R2 路径，RunPod 不应依赖本地主服务器 MinIO。

对 RunPod 来说，它只需要表现为“一个临时远程 GPU worker”：

```text
Central Redis / Central API
        ^
        | worker 专用 Central API 域名
        |
RunPod Pod
  - ComfyUI
  - upload sidecar / remote relay
  - comfy_agent
  - SUPPORTED_TASK_TYPES=wan22_video_v2
```

## 4. 总体架构

新增一个独立控制器：`runpod_capacity_controller`。

建议部署位置：云正式控制面旁边的管理容器或云测试/正式各一份。它只做“观察队列 + 管理 RunPod 生命周期”，不执行任务本身。

核心职责：

- 每 60 秒读取 Central 队列状态、worker 心跳、RunPod Pod 状态。
- 按任务类型计算 backlog 与最长 pending 等待时间。
- 当某任务类型超过扩容阈值时，通过 RunPod REST API 创建或启动专属 Pod。
- 当 RunPod worker 空闲一段时间后，先 drain，再 stop 或 terminate。
- 用 Redis 或数据库保存 RunPod worker 注册表，避免重复创建、遗漏关闭、孤儿 Pod。

推荐组件：

```text
runpod_capacity_controller
  |
  |-- Central Redis
  |     - comfy:queue:pending
  |     - comfy:queue:running
  |     - comfy:task:*
  |     - comfy:agent:heartbeat:*
  |     - comfy:task_heartbeat:*
  |
  |-- Central API
  |     - worker health / system status
  |     - optional worker drain/disable endpoint
  |
  |-- RunPod REST API
        - GET /pods
        - POST /pods
        - POST /pods/{podId}/start
        - POST /pods/{podId}/stop
        - DELETE /pods/{podId}
```

## 5. 队列指标定义

扩容触发必须使用 Central pending 队列等待时间，避免把任务执行时间混进去。

建议定义：

- `pending_wait_seconds`：任务进入 Central pending 队列到当前时间的差值。
- `max_pending_wait_seconds_by_type`：某任务类型所有 pending 任务中最老任务等待时间。
- `p90_pending_wait_seconds_by_type`：某任务类型 pending 任务等待时间 P90。
- `pending_count_by_type`：某任务类型 pending 任务数。
- `running_count_by_type`：某任务类型 running 任务数。
- `healthy_worker_count_by_type`：当前心跳健康且 `SUPPORTED_TASK_TYPES` 覆盖该任务类型的 worker 数。
- `runpod_active_count_by_type`：RunPod 管理的该任务类型 running / booting / warming worker 数。

不要用这些指标直接触发扩容：

- 任务端到端耗时：通常包含排队、worker 拉取、ComfyUI 执行、上传、回写。
- worker 处理耗时 P90：可能包含 worker pipeline 内部等待或上传。
- ComfyUI prompt 完成耗时：更接近 GPU 生成时间，但不能说明 Central 队列是否积压。

对于 `wan22_video_v2`、`ltx_video` 的 p90 超过 2000s 问题，后续监控里应拆成三段：

```text
Central pending wait
  -> worker pop / execution_start
  -> ComfyUI prompt_start / prompt_done
  -> upload_done / central_complete
```

只有第一段超过 20 分钟才触发 RunPod 扩容；如果第三段或 ComfyUI 执行段很长，则应该优化 workflow、模型、上传和单机并发，而不是盲目扩容。

## 6. 扩容策略

每个任务类型独立判断。初期建议只纳入：

- `wan22_video_v2`
- `ltx_video`
- 后续可扩展到 `image_to_video`、`video_edit`、`video_insert`

### 6.1 Scale out

触发条件：

```text
max_pending_wait_seconds_by_type >= 1200
AND pending_count_by_type >= RUNPOD_SCALE_OUT_MIN_PENDING
AND runpod_starting_count_by_type == 0
AND runpod_active_count_by_type < RUNPOD_MAX_PODS_PER_TYPE
AND runpod_total_active_count < RUNPOD_MAX_PODS_TOTAL
AND now >= scale_out_cooldown_until_by_type
AND RUNPOD_AUTOSCALER_ENABLED=true
```

推荐初始参数：

```dotenv
RUNPOD_SCALE_OUT_MAX_PENDING_SECONDS=1200
RUNPOD_SCALE_OUT_MIN_PENDING=2
RUNPOD_SCALE_OUT_COOLDOWN_SECONDS=600
RUNPOD_MAX_PODS_PER_TYPE=1
RUNPOD_MAX_PODS_TOTAL=2
RUNPOD_MAX_HOURLY_COST_USD=5
```

动作：

1. 对目标任务类型加 Redis 分布式锁，例如 `runpod:scale_lock:wan22_video_v2`，TTL 120 秒。
2. 再次读取队列，确认仍满足条件。
3. 调 RunPod `POST /pods` 创建 Pod，或优先启动已停止且配置匹配的 Pod。
4. 写入 `runpod:workers:{agent_id}` 注册表。
5. 进入 `provisioning -> booting -> warming -> healthy` 状态机。
6. 同一任务类型每轮只增加 1 台，观察 10 分钟后再决定是否继续扩容。

### 6.2 Scale in

关闭 RunPod 的条件：

```text
worker_state == healthy
AND worker_current_task_id is empty
AND runpod_worker_running_count == 0
AND pending_count_by_type == 0
AND max_pending_wait_seconds_by_type < 300
AND idle_duration_seconds >= RUNPOD_SCALE_IN_IDLE_SECONDS
```

推荐初始参数：

```dotenv
RUNPOD_SCALE_IN_IDLE_SECONDS=900
RUNPOD_SCALE_IN_COOLDOWN_SECONDS=300
RUNPOD_STOP_MODE=stop
RUNPOD_TERMINATE_AFTER_STOPPED_SECONDS=86400
```

动作：

1. 给目标 RunPod worker 标记 `draining`。
2. 不再允许它 pop 新任务。
3. 等它没有 `current_task_id`、没有 running 任务、心跳显示 idle。
4. 调 RunPod `POST /pods/{podId}/stop`。
5. 如果镜像和模型完全无状态，或停止超过 24 小时，可改为 delete/terminate 降低持久存储费用。

关闭优先级：

1. 优先关闭 RunPod worker。
2. 不自动关闭本地局域网 GPU worker。
3. 不在任务运行中强杀，除非进入人工故障处理。

## 7. RunPod Pod 模板设计

每个任务类型准备一个 template，或准备一个通用镜像 + 启动时传入 `SUPPORTED_TASK_TYPES`。

推荐镜像内容：

- CUDA / PyTorch 基础镜像。
- ComfyUI。
- AllBot `remote_workers/` 或同源 worker agent。
- upload sidecar / remote relay。
- `workers/comfy_agent/workflows`。
- 对应 workflow 依赖的 custom nodes。
- 常用模型文件，或挂载 RunPod network volume 存放模型。

关键原则：

- 不要在 Pod 启动时下载大模型，否则冷启动可能比任务排队还慢。
- RunPod 官方建议用 custom template 预装依赖和模型，提升启动一致性和速度。
- ComfyUI 端口默认不对公网开放；worker 只需要出站访问 Central worker 域名和 R2。
- 敏感变量通过 RunPod secrets 或安全环境变量注入，不写入仓库。

建议环境变量：

```dotenv
ENVIRONMENT=production
AGENT_ID=runpod_wan22_video_v2_${POD_ID}
AGENT_SECRET_TOKEN=<from-secret>
CENTRAL_API_URL=https://worker-central.example.com
COMFY_API_URL=http://127.0.0.1:8188
UPLOAD_SIDECAR_URL=http://127.0.0.1:8013
SUPPORTED_TASK_TYPES=wan22_video_v2
PIPELINE_ENABLED=true
PIPELINE_MAX_RUNNING_TASKS=1
CANCEL_LOCK_ON_POP=true
RUNPOD_MANAGED=true
RUNPOD_TASK_TYPE=wan22_video_v2
```

`PIPELINE_MAX_RUNNING_TASKS` 初期建议设为 1。等确认 RunPod GPU 型号、显存、ComfyUI 内部队列稳定后，再对 `ltx_video` 或轻量任务测试 2。视频类任务如果单机 pipeline 过高，容易把 ComfyUI 内部排队时间算进 worker 处理时间，反而让 p90 变差。

启动顺序：

```text
start ComfyUI
  -> wait until http://127.0.0.1:8188/system_stats ok
  -> start upload sidecar / remote relay
  -> start comfy_agent
  -> send heartbeat to Central
```

## 8. 控制器状态机

RunPod worker 注册表建议保存：

```json
{
  "agent_id": "runpod_wan22_video_v2_abcd",
  "pod_id": "abcd1234",
  "task_type": "wan22_video_v2",
  "state": "warming",
  "template_id": "template_xxx",
  "gpu_type_id": "NVIDIA GeForce RTX 4090",
  "cost_per_hr": 0.74,
  "created_at": "2026-06-10T01:00:00+08:00",
  "last_seen_at": "2026-06-10T01:03:00+08:00",
  "idle_since": null,
  "cooldown_until": "2026-06-10T01:13:00+08:00",
  "stop_mode": "stop"
}
```

状态流转：

```text
requested
  -> provisioning
  -> booting
  -> warming
  -> healthy
  -> draining
  -> stopping
  -> stopped
```

异常状态：

```text
error
orphan
missing_heartbeat
zero_gpu_suspected
cost_guard_blocked
```

## 9. RunPod API 调用示例

创建专属 Pod：

```bash
curl --request POST \
  --url https://rest.runpod.io/v1/pods \
  --header "Authorization: Bearer ${RUNPOD_API_KEY}" \
  --header "Content-Type: application/json" \
  --data '{
    "name": "allbot-wan22-video-v2-burst",
    "computeType": "GPU",
    "gpuCount": 1,
    "gpuTypeIds": ["NVIDIA GeForce RTX 4090", "NVIDIA GeForce RTX 5090", "NVIDIA L40S"],
    "gpuTypePriority": "availability",
    "templateId": "RUNPOD_TEMPLATE_ID_WAN22",
    "interruptible": true,
    "env": {
      "RUNPOD_MANAGED": "true",
      "RUNPOD_TASK_TYPE": "wan22_video_v2",
      "SUPPORTED_TASK_TYPES": "wan22_video_v2"
    }
  }'
```

查询运行中的 Pod：

```bash
curl --request GET \
  --url "https://rest.runpod.io/v1/pods?computeType=GPU&desiredStatus=RUNNING" \
  --header "Authorization: Bearer ${RUNPOD_API_KEY}"
```

停止 Pod：

```bash
curl --request POST \
  --url "https://rest.runpod.io/v1/pods/${POD_ID}/stop" \
  --header "Authorization: Bearer ${RUNPOD_API_KEY}"
```

以上示例只保留占位变量，不能把真实 API key、Central token、R2 secret 写入仓库。

## 10. 配置项建议

新增生产环境变量，实际值只放在部署 secret 或服务器环境里：

```dotenv
RUNPOD_AUTOSCALER_ENABLED=false
RUNPOD_DRY_RUN=true
RUNPOD_API_KEY=<secret>
RUNPOD_ALLOWED_DATACENTERS=US-TX-3,US-GA-1,US-WA-1
RUNPOD_GPU_TYPE_IDS_WAN22=NVIDIA GeForce RTX 4090,NVIDIA GeForce RTX 5090,NVIDIA L40S
RUNPOD_GPU_TYPE_IDS_LTX=NVIDIA GeForce RTX 4090,NVIDIA RTX A5000,NVIDIA L40S
RUNPOD_TEMPLATE_ID_WAN22=<secret-or-config>
RUNPOD_TEMPLATE_ID_LTX=<secret-or-config>
RUNPOD_MAX_PODS_TOTAL=2
RUNPOD_MAX_PODS_PER_TYPE=1
RUNPOD_MAX_HOURLY_COST_USD=5
RUNPOD_SCALE_OUT_MAX_PENDING_SECONDS=1200
RUNPOD_SCALE_OUT_MIN_PENDING=2
RUNPOD_SCALE_OUT_COOLDOWN_SECONDS=600
RUNPOD_SCALE_IN_IDLE_SECONDS=900
RUNPOD_SCALE_IN_COOLDOWN_SECONDS=300
RUNPOD_STOP_MODE=stop
RUNPOD_TERMINATE_AFTER_STOPPED_SECONDS=86400
```

初期强制：

- `RUNPOD_AUTOSCALER_ENABLED=false`
- `RUNPOD_DRY_RUN=true`
- `RUNPOD_MAX_PODS_TOTAL=1`
- `RUNPOD_MAX_PODS_PER_TYPE=1`

通过测试后再逐步打开。

## 11. 成本控制

必须内置多层保护：

- 全局最大 Pod 数。
- 单任务类型最大 Pod 数。
- 全局每小时成本上限，基于 RunPod `costPerHr` / `adjustedCostPerHr` 计算。
- Scale out 冷却时间，避免 20 分钟阈值抖动时重复创建。
- Scale in idle grace，避免刚空闲就关、刚关又开。
- 人工熔断：`RUNPOD_AUTOSCALER_ENABLED=false` 后控制器只允许 scale in，不允许 scale out。
- 每次 create/start/stop/delete 写审计日志。

计费注意：

- On-demand 适合变量负载，资源不会被其他用户抢占，但价格高于长期计划。
- Interruptible 成本更低，但可能被停止，适合可重试的突发任务。
- Stop Pod 后仍可能有 volume / network volume 费用。
- 如果镜像已内置模型且无需持久卷，长时间不用时 delete/terminate 比 stop 更省。

## 12. 故障与容灾设计

| 场景 | 风险 | 处理 |
| --- | --- | --- |
| RunPod 容量不足 | 创建 Pod 失败 | 记录 `capacity_unavailable`，换 GPU 类型或数据中心，进入冷却 |
| Stop 后 Start 出现 0 GPU | worker 无法生成 | 参考官方 zero GPU 排障；自动停用该 Pod，创建新 Pod |
| Interruptible Pod 被回收 | 任务中断 | 依赖 Central 任务心跳、僵尸任务清理、退款/重试机制；关键任务改用 non-interruptible |
| ComfyUI 启动失败 | worker 心跳缺失 | 标记 `warming_timeout`，停止/删除 Pod，不继续扩容同类型直到冷却结束 |
| 模型缺失 | 任务失败率升高 | template canary 必须跑真实 workflow；失败后标记 template unhealthy |
| RunPod API 异常 | 无法扩缩容 | 不影响本地 worker；控制器只报警和重试 |
| 控制器重复创建 | 成本失控 | Redis 分布式锁 + RunPod list pods reconcile + 全局成本上限 |
| Pod 孤儿 | 持续计费 | 每轮 `GET /pods` 按 name/env/template 识别 `RUNPOD_MANAGED=true` 并纳入注册表 |

## 13. 观测与告警

Dashboard / 日志至少展示：

- 每任务类型 `pending_count`、`max_pending_wait_seconds`、`p90_pending_wait_seconds`。
- 每任务类型本地 worker 数、RunPod worker 数、healthy / warming / draining 数。
- RunPod 冷启动耗时：create 到 heartbeat healthy。
- RunPod 任务成功率、失败率、平均生成耗时、P90 生成耗时。
- RunPod 当前小时成本估算。
- 最近 50 条扩缩容动作审计。

建议告警：

- `max_pending_wait_seconds > 1800` 且 RunPod 扩容失败。
- RunPod Pod 创建成功但 10 分钟内没有 worker heartbeat。
- RunPod worker idle 超过 30 分钟但没有被停止。
- RunPod 当前成本超过上限的 80%。
- 同一 template 连续 3 次 canary 失败。

## 14. 分阶段落地计划

### Phase 0：云测试手动 canary

目标：证明 RunPod Pod 能像现有远程 worker 一样接入 Central。

动作：

1. 构建 `allbot-comfy-runpod` 镜像。
2. 创建 `ltx_video` 或 `wan22_video_v2` 专属 RunPod template。
3. 使用云测试 worker 专用 Central 域名。
4. 只放测试 token 和测试 R2/存储配置。
5. 手动启动 1 台 Pod，确认 heartbeat、pop、complete、result upload。
6. 跑 3-5 个真实测试任务，记录冷启动时间、生成时间、失败率。

验收：

- Central 能看到 `runpod_*` worker healthy。
- 任务能完成并回传结果。
- 关闭 Pod 后 Central 不再分配任务给该 worker。

### Phase 1：生产手动 canary

目标：在正式环境验证最小生产链路，不启用自动扩容。

动作：

1. 生产只允许 1 个 RunPod Pod。
2. `SUPPORTED_TASK_TYPES` 只填一个任务类型。
3. 选择低峰时段手动启动。
4. 观察 1 小时：任务成功率、R2 上传、Central complete、成本。
5. 手动 drain + stop。

验收：

- 没有影响本地 worker。
- 没有错误写入测试环境或错误 bucket。
- 任务失败能走现有失败/重试/退款路径。

### Phase 2：控制器 dry-run

目标：控制器只观察，不真实调用 create/start/stop。

动作：

1. 部署 `runpod_capacity_controller`。
2. `RUNPOD_AUTOSCALER_ENABLED=false`、`RUNPOD_DRY_RUN=true`。
3. 每 60 秒输出“如果启用会扩容/缩容”的决策。
4. 对比真实 backlog，验证阈值是否合理。

验收：

- dry-run 触发点符合预期。
- 不会在单个老任务、已无 backlog、worker 心跳误判时乱扩容。

### Phase 3：生产有限自动扩容

目标：开启真实 scale out / scale in，但强限制。

动作：

```dotenv
RUNPOD_AUTOSCALER_ENABLED=true
RUNPOD_DRY_RUN=false
RUNPOD_MAX_PODS_TOTAL=1
RUNPOD_MAX_PODS_PER_TYPE=1
RUNPOD_MAX_HOURLY_COST_USD=2
```

只对一个任务类型开启，例如 `ltx_video`。

验收：

- pending 超过 20 分钟后自动创建 RunPod worker。
- worker healthy 后能接单。
- pending 清空并 idle 15 分钟后自动 stop。
- 24 小时内没有孤儿 Pod。

### Phase 4：多类型扩展

目标：扩大到 `wan22_video_v2`、`ltx_video`、`image_to_video`。

动作：

- 每个任务类型单独 template、GPU 型号、阈值、最大 Pod 数。
- Dashboard 增加 RunPod worker 状态和成本面板。
- 增加 template health registry，失败 template 自动暂停扩容。

## 15. 需要的代码改造

建议新增：

- `src/services/runpod_capacity_controller.py`：扩缩容主循环。
- `src/integrations/runpod_client.py`：RunPod REST API client。
- `src/services/runpod_worker_registry.py`：RunPod worker 注册表和 reconcile。
- `scripts/runpod_autoscaler_dry_run.py`：本地/云测试 dry-run 排查脚本。
- Dashboard 增加 RunPod 状态页：队列等待、Pod 状态、成本、最近动作。

建议增强：

- Central 增加 worker drain/disable 标记。没有这个能力时，scale in 只能在 worker 已 idle 后 stop。
- worker heartbeat 上报 `current_task_id`、`supported_task_types`、`runpod_managed`、`pod_id`、`gpu_type`。
- 任务耗时埋点拆分为 `queued_at`、`popped_at`、`comfy_prompt_started_at`、`comfy_prompt_done_at`、`upload_done_at`、`completed_at`。

伪代码：

```python
for task_type in managed_task_types:
    metrics = collect_queue_metrics(task_type)
    workers = collect_worker_health(task_type)
    pods = reconcile_runpod_pods(task_type)

    if should_scale_out(metrics, workers, pods):
        with redis_lock(f"runpod:scale_lock:{task_type}", ttl=120):
            if should_scale_out(collect_queue_metrics(task_type), workers, pods):
                create_or_start_dedicated_pod(task_type)
                audit("scale_out", task_type)

    for pod in pods:
        if should_scale_in(metrics, pod):
            mark_draining(pod.agent_id)
            if pod_is_idle(pod):
                stop_or_delete_pod(pod)
                audit("scale_in", task_type)
```

## 16. GPU 型号与容量估算

初期建议优先测试这些 GPU：

- `wan22_video_v2`：RTX 4090 / RTX 5090 / L40S / H100 视可用性和模型显存需求决定。
- `ltx_video`：RTX 4090 / RTX A5000 / L40S。

不要直接按本地 GPU 的历史 p90 推断 RunPod 吞吐。RunPod 的 GPU 型号、磁盘、网络、镜像冷启动、模型加载方式都会影响吞吐。

初始估算方式：

```text
单 Pod 每小时产能 = 3600 / 实测 worker_task_duration_p90
有效产能 = 单 Pod 每小时产能 * 成功率 * 0.85
```

如果某任务实测 P90 为 240 秒，则单 Pod 约 15 任务/小时；如果 P90 为 360 秒，则约 10 任务/小时。视频任务建议先按保守值估算。

## 17. 回滚方案

自动扩容出现异常时：

1. 设置 `RUNPOD_AUTOSCALER_ENABLED=false`。
2. 控制器进入只缩不扩模式。
3. 标记全部 RunPod worker 为 draining。
4. 等运行任务结束后 stop。
5. 如成本或故障紧急，人工在 RunPod Console 停止所有 `allbot-*` / `RUNPOD_MANAGED=true` Pod。
6. 本地局域网 worker 不受影响，系统回到原容量。

生产变更原则：

- 功能研发和联调默认先走云测试控制面。
- 正式开启自动扩容前，需要明确确认。
- 不在业务高峰首次启用新 template。

## 18. 最终推荐

第一阶段按以下最小路径执行：

1. 先做 `ltx_video` 或 `wan22_video_v2` 的 RunPod Pod template。
2. 只跑云测试 canary，确认 agent、ComfyUI、R2、Central complete 全链路。
3. 生产手动启动 1 台 RunPod 专属 worker，观察真实任务。
4. 部署 dry-run 控制器，验证“最大 pending 等待超过 20 分钟”触发是否准确。
5. 再开启 `RUNPOD_MAX_PODS_TOTAL=1` 的有限自动扩容。

这样可以最快复用现有 worker 架构，同时把成本风险、生产风险和任务统计口径都控制住。
