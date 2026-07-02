---
name: "allbot-lan-aio-operator"
description: "本地主服务器 LAN AIO 运维操作员。管理局域网 GPU 节点的 LAN AIO 当前态、缓存态、候选切换、单卡 takeover/recover/restart、镜像拉取和模型热缓存时使用；必须通过 fleet 配置和 scripts/lan_aio_fleet_prod_ops.py，禁止自由 compose、自由镜像或跨 slot 批量操作。"
---

# AllBot LAN AIO Operator

本技能用于在本地主服务器上稳定管理 LAN AIO。它只记录操作规则和事实源路由，不把频繁变化的 GPU 当前态硬编码进技能正文。

## 1. 必读入口

每次处理 LAN AIO 前按顺序读取：

1. `.codex/skills/allbot-ops-deployment/SKILL.md`
2. `ops/gpu_pool_controller/config/lan_aio_prod_slots.yml`
3. `ops/gpu_pool_controller/config/lan_aio_fleet_state.yml`
4. 必要时读取 `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md` 和 `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`

事实源分工：

- `lan_aio_prod_slots.yml`：声明式 slot/catalog，定义哪些 slot 可由 helper 管理。
- `lan_aio_fleet_state.yml`：AI operator 维护的运行态摘要，记录每张物理 GPU 当前 profile、可快速切换候选、已缓存镜像/模型、阻断原因和最后验证时间。
- live status：最终仲裁源。若 live status 与 state 文件冲突，报告 drift 并停止生产 mutation，先收口事实源。

## 2. 固定命令

只使用 fleet helper 管理 LAN AIO：

```bash
python scripts/lan_aio_fleet_prod_ops.py list --include-disabled
python scripts/lan_aio_fleet_prod_ops.py status --include-disabled
python scripts/lan_aio_fleet_prod_ops.py candidate-plan --node-id <node> --profile <profile> --replace-slot <current-slot>
python scripts/lan_aio_fleet_prod_ops.py render --slot <slot> --include-disabled
python scripts/lan_aio_fleet_prod_ops.py preflight --slot <slot> --include-disabled --execute
python scripts/lan_aio_fleet_prod_ops.py pull-image --slot <slot> --include-disabled --execute
python scripts/lan_aio_fleet_prod_ops.py warm-cache --slot <slot> --include-disabled --execute
python scripts/lan_aio_fleet_prod_ops.py takeover --slot <slot> --replace-slot <current-slot> --include-disabled --failure-policy auto_rollback --execute
python scripts/lan_aio_fleet_prod_ops.py recover --physical-slot <node>:gpuN --slot <slot> --prefer old|candidate --execute
python scripts/lan_aio_fleet_prod_ops.py restart-aio --slot <slot> --execute
```

辅助只读检查：

```bash
ssh <gpu-host> 'nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu --format=csv,noheader,nounits'
ssh <gpu-host> 'docker ps -a --format "{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}" | grep -E "allbot-lan-aio|comfy[0-9]|comfyui" || true'
ssh <gpu-host> 'curl -fsS --max-time 5 http://127.0.0.1:<port>/queue'
ssh <gpu-host> 'curl -fsS --max-time 5 http://127.0.0.1:<port>/system_stats'
```

Do not print `.env*`, compose config expansion, tokens, agent secrets, R2 keys, presigned URLs, or database URLs.

## 3. 操作红线

- 未经用户明确要求，不执行生产 mutation。
- 一次只操作一个 physical GPU / slot；禁止跨节点批量切换。
- 不手写 Docker Compose，不自由指定镜像或 manifest，不绕过 `lan_aio_prod_slots.yml`。
- 不 reboot GPU 主机，不 restart Docker daemon，除非用户明确要求维护窗口。
- 切换前必须确认当前 slot 无 running task；等待自然空闲，不强杀任务。
- `blocked_*`、`maintenance_disabled`、`blocked_host_service_runtime` 不允许直接 takeover，除非先通过配置和验证解除阻断。
- `wan22_video_v2` 在 32GB 卡上有 OOM 历史；启用前必须确认 state 文件和 docs 没有阻断说明。
- helper 返回 drift、host port owner 冲突、cache missing、disabled heartbeat 缺失时停止并报告。

## 4. 标准流程

### 查看当前状态

1. 读 `lan_aio_fleet_state.yml` 找目标 `node_id + gpu_index`。
2. 跑 `list --include-disabled` 和 `status --include-disabled`。
3. 对目标端口查 `/queue`、`/system_stats`。
4. 对照 state 文件：current profile、agent、container、host port、cache state 必须一致；不一致先收口 state 或 slot catalog。

### 新增候选

1. 跑 `candidate-plan --node-id <node> --profile <profile> --replace-slot <current-slot>`。
2. 把生成的 YAML 合入 `lan_aio_prod_slots.yml`，只保留 Git 可审计的非敏感字段。
3. 更新 `lan_aio_fleet_state.yml` 的 `fast_switch_candidates`，cache 初始写 `missing`。
4. 跑 `render` 验证 compose 元数据，不打印敏感 env。

### 镜像和模型热缓存

1. 若目标节点缺镜像，跑 `pull-image --execute`。helper 会优先远端 pull；若 HTTP registry 不可用且 runner 本地有镜像，可走 `docker save | ssh docker load` 兜底。
2. 跑 `warm-cache --execute` 同步模型 manifest 到目标 workspace。
3. 确认 `model-cache-marker.json` ready，并更新 `lan_aio_fleet_state.yml` 的 cached profile。

### 单 slot takeover

1. 跑 `preflight --execute`。
2. 等当前 slot 空闲：Central worker 不是 running，`current_task_type` 为空，ComfyUI `/queue` 无 running。
3. 执行 `takeover --failure-policy auto_rollback --execute`。
4. 验证新容器 healthy、disabled heartbeat gate、enable 后 Central worker profile/task types 正确。
5. 更新 `lan_aio_fleet_state.yml`：current、cached、fast_switch_candidates、blocked_profiles、last_verified_at。
6. 同步必要 docs / skills 索引；不要把完整运行态表复制到长文档。

### 恢复失败现场

只使用：

```bash
python scripts/lan_aio_fleet_prod_ops.py recover --physical-slot <node>:gpuN --slot <slot> --prefer old|candidate --execute
```

恢复后重新跑 `status --include-disabled`，并把 recovery result 写入 `lan_aio_fleet_state.yml` 的 notes，避免只留下远端现场。

## 5. 交付格式

交付必须说明：

- 本轮读取的 state 文件时间和 live status 时间。
- 改动的 slot/state/docs/skill 文件。
- 是否执行了生产 mutation；如果执行，列出目标 node/GPU/slot/profile。
- 验证结果：container health、Central worker、task types、ComfyUI health/queue、cache marker。
- 未解决 drift、blocked profile 或需要另开维护窗口的事项。
