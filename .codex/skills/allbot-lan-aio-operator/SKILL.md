---
name: "allbot-lan-aio-operator"
description: "本地主服务器 LAN AIO 运维操作员。管理局域网 GPU 节点的 LAN AIO 当前态、缓存态、候选切换、单卡 takeover/recover/restart、镜像拉取和模型热缓存时使用；必须通过 fleet 配置和 scripts/lan_aio_fleet_prod_ops.py，禁止自由 compose、自由镜像或跨 slot 批量操作。"
---

# AllBot LAN AIO Operator

GPU profile 发布产物必须先有 canonical digest；LAN registry 只通过 `scripts/copy_canonical_image_to_lan_registry.sh` 做保 digest 复制与复核。禁止为同一 release/profile 在 LAN 现场重新 build。

正式 profile 镜像已烘焙 `/opt/allbot/runtime/remote_workers`；operator 不再把仓库 `remote_workers` 打包/同步到 GPU 主机，也不得用 host bind mount 覆盖镜像内代码。

本技能用于在本地主服务器上稳定管理 LAN AIO。它只记录操作规则和事实源路由，不把频繁变化的 GPU 当前态硬编码进技能正文。

## 1. 必读入口

每次处理 LAN AIO 前按顺序读取：

1. `.codex/skills/allbot-ops-deployment/SKILL.md`
2. `ops/gpu_pool_controller/config/lan_aio_prod_slots.yml`
3. `${XDG_STATE_HOME:-~/.local/state}/allbot/lan-aio/current.yml`
4. 必要时读取 `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md` 和 `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`

事实源分工：

- `lan_aio_prod_slots.yml`：Git 声明式 catalog，只保存物理卡/端口、候选 profile、镜像与模型 manifest、稳定阻断策略；catalog v2 的 legacy `enabled/phase/old_runtime` 字段不再表示 current。
- XDG `current.yml`：本地主 operator 的 last-known 运行态账本，记录 current、cache、最近验证与 operation ID；`history/<operation-id>.json` 保存成功、失败和回滚审计。
- live status：观测现实，不是自动覆盖源。live、ledger、catalog 的不一致会记录为 drift 审计，但不阻断已经明确授权的单 slot mutation；live 不可达时 ledger 只显示 last-known。
- `lan_aio_fleet_state.legacy.yml`：只供首次 `state-init` 的冻结迁移种子，普通操作绝不更新。

发布与 CI 边界：

- GPU↔LAN 当前映射、cache marker、最近验证时间以及 RunPod 当前数量都是易变运行态，只写 XDG ledger、provider/operation store 或后台观测，不写 Git，不因漂移触发代码发布。
- 仅修改 `scripts/lan_aio_*.py|sh`、`scripts/lan_*_aio_*.sh` 这类宿主 helper 时，CI 使用聚焦的 `operator` scope；它不构建或部署任何 control-plane/GPU artifact，合入后仍须在获授权的单槽操作中显式使用新 helper。
- 修改 `ops/gpu_pool_controller/**`、`scripts/gpu_pool_controller.py`、`scripts/gpu_release_rollout.py` 或 `scripts/runpod_prod_ops.sh` 时，同样只跑 operator 测试，但可信 main bundle 最多重建 `dashboard-backend`；不会因此构建、canary 或替换 GPU 镜像，也不会改动现有 Pod/LAN 容器。
- 修改 `remote_workers/**`、`deploy/release-artifacts-v2.json` 中的 GPU release artifact/profile、GPU Dockerfile、模型 manifest 或真实 GPU 基础依赖时，必须恢复全量 CI、同 SHA artifact attestation，并按策略执行 canary/operator；不得借 operator scope 规避。

## 2. 固定命令

只使用 fleet helper 管理 LAN AIO：

```bash
python scripts/lan_aio_fleet_prod_ops.py list --include-disabled
python scripts/lan_aio_fleet_prod_ops.py status --include-disabled
python scripts/lan_aio_fleet_prod_ops.py state-init --legacy-state-file ops/gpu_pool_controller/config/lan_aio_fleet_state.legacy.yml --execute
python scripts/lan_aio_fleet_prod_ops.py state-reconcile --reason <reason> --execute
python scripts/lan_aio_fleet_prod_ops.py state-reconcile --physical-slot <node>:gpuN --reason <confirmed-empty-reason> --execute
python scripts/lan_aio_fleet_prod_ops.py candidate-plan --node-id <node> --profile <profile> --replace-slot <current-slot>
python scripts/lan_aio_fleet_prod_ops.py render --slot <slot> --include-disabled
python scripts/lan_aio_fleet_prod_ops.py preflight --slot <slot> --include-disabled --execute
python scripts/lan_aio_fleet_prod_ops.py pull-image --slot <slot> --include-disabled --execute
python scripts/lan_aio_fleet_prod_ops.py warm-cache --slot <slot> --include-disabled --execute
python scripts/lan_aio_fleet_prod_ops.py canary-start-disabled --slot <slot> --profile <profile> --release-index <release-index.json> --sha <full-sha> --strategy direct|standard --include-disabled --execute
python scripts/lan_aio_fleet_prod_ops.py canary-stop-disabled --slot <slot> --include-disabled --execute
python scripts/lan_aio_fleet_prod_ops.py takeover --slot <slot> --replace-slot <current-slot> --include-disabled --failure-policy auto_rollback --execute
python scripts/lan_aio_fleet_prod_ops.py recover --physical-slot <node>:gpuN --slot <slot> --prefer old|candidate --execute
python scripts/lan_aio_fleet_prod_ops.py restart-aio --slot <slot> --execute
python scripts/lan_aio_fleet_prod_ops.py release-rollout --slot <slot> --profile <profile> --release-index <release-index.json> --sha <full-sha> --strategy direct|standard [--rollback-ref <same-repo@sha256:...>] --execute
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
- `release-rollout` 必须从 release index 解析精确 digest：先 disabled/drain，验证容器实际 image、OCI revision、进程健康和 disabled heartbeat 后才 enable；失败立即停止后续 slot 并恢复该 slot 的旧镜像，恢复无法验证时保持 disabled。
- release index 若引用 GHCR canonical 仓库，而当前 LAN profile 使用 LAN registry mirror，helper 只把同一 release digest 映射到当前 profile 的 repository；必须先用 `scripts/copy_canonical_image_to_lan_registry.sh` 保摘要复制 canonical manifest，禁止改 digest 或现场 build。
- 目标节点尚未配置 HTTP LAN registry 且没有 Docker daemon 维护窗口时，Git catalog 可直接固定 release index 的 canonical GHCR 完整 digest，禁止改用 tag；显式 exact rollback ref 会在停接/等待空闲前由 helper 预拉，确保回滚镜像真实可用。
- 历史 LAN 镜像若由 tar 导入、旧 tag 没有 `RepoDigests`，只能在独立核验当前 tag 的 registry digest 后传 `--rollback-ref <same-repo@sha256:...>`；helper 拒绝 mutable 或跨仓库回滚引用，不能用该参数自由指定运行镜像。
- 不手写 Docker Compose，不自由指定镜像或 manifest，不绕过 `lan_aio_prod_slots.yml`。
- 不调用 Dashboard `/api/runpod/lan-aio/slots*` 或 `/profiles` 管理 LAN AIO；这些 Web slot 管理 API 已废弃，候选切换、恢复和缓存预热只走本地主 AI operator/CLI。
- 不 reboot GPU 主机，不 restart Docker daemon，除非用户明确要求维护窗口。
- 切换前必须确认当前 slot 无 running task；等待自然空闲，不强杀任务。
- `blocked_*`、`maintenance_disabled`、`blocked_host_service_runtime` 与 OOM/Xid 记录仅作为 catalog 审计信息，不阻断显式 slot 操作。
- profile 的最低显存与实际显存只作为 canary 遥测，不构成启动或接单门禁。
- helper 返回 drift、host port owner 冲突、cache missing、disabled heartbeat 缺失时报告；容器、Central 与 ComfyUI 健康验证仍必须执行。
- `takeover/recover/restart-aio/warm-cache/pull-image/canary-start-disabled/canary-stop-disabled` 等 mutation 仍持有本地单实例锁；live/ledger/catalog 差异和未完成 operation 会写入审计，但不会阻止后续显式单 slot mutation。
- `drain-legacy/stop-old/start-disabled/rollback` 不再允许作为独立 `--execute` 链路；使用事务化 `takeover` 或精确 `recover`，避免账本停在中间态。
- 只做本地验收且禁止 intake 的候选必须使用成对的 `canary-start-disabled` / `canary-stop-disabled`。对 release artifact 必须同时传 `--profile/--release-index/--sha`，helper 从 index 解析精确 digest，执行 preflight、pull、warm-cache、disabled heartbeat、实际 image/OCI revision/runtime contract 校验后仍保持 Central control disabled；不带 release 参数只用于 catalog 已经固定精确镜像的候选。后者同时等待 worker 与 Comfy `/queue` 为空，停止精确候选容器并把物理槽原子恢复为 `intentionally_empty`。不得用 `recover/takeover` 替代，因为它们成功后会 enable intake。
- ledger 明确记录 `intentionally_empty` 时，允许对同一物理槽的指定候选执行只读 `preflight --execute`，用于读取逐项门禁；该例外不扩展到 pull、warm-cache 或其它 mutation。`configure-registry` 必须同时维护 daemon `insecure-registries` / `proxies.no-proxy` 与 systemd `NO_PROXY/no_proxy`，保留既有代理端点；重启 Docker 后只等待重启前已运行的候选恢复，本来停止的候选必须保持停止。

## 4. 标准流程

### 查看当前状态

1. 读 XDG `current.yml` 找目标 `node_id + gpu_index`；首次迁移才读 legacy seed。
2. 跑 `list --include-disabled` 和 `status --include-disabled`；确认 `state.status=passed`。
3. 对目标端口查 `/queue`、`/system_stats`。
4. 对照 ledger：current profile、agent、container、host port、cache state 必须一致；不一致时停止，确认 live 后显式 `state-reconcile --reason ... --execute`，不得静默覆盖。若目标物理槽因故障隔离而明确保持停机，且 live 探测成功证明没有任何 running catalog container，可额外传精确 `--physical-slot <node>:gpuN` 把该槽记录为 `intentionally_empty`；该参数不能忽略 SSH/探测错误，也不能放宽其它物理槽的唯一 live 要求。若目标应恢复产能，继续使用精确单槽 `recover`，不得借空槽收口跳过恢复门禁。

### 新增候选

1. 跑 `candidate-plan --node-id <node> --profile <profile> --replace-slot <current-slot>`。
2. 把生成的 YAML 合入 `lan_aio_prod_slots.yml`，只保留 Git 可审计的非敏感字段。
3. 跑 `render` 验证 compose 元数据，不打印敏感 env；候选尚未缓存时由 ledger/status 显示 missing。

### 镜像和模型热缓存

1. 若目标节点缺镜像，跑 `pull-image --execute`。helper 会优先远端 pull；若 HTTP registry 不可用且 runner 本地有镜像，可走 `docker save | ssh docker load` 兜底。
2. 跑 `warm-cache --execute` 同步模型 manifest 到目标 workspace。
3. 确认 `model-cache-marker.json` ready；helper 成功后原子更新 XDG ledger 的 cached profile 并写 history。

### 单 slot takeover

1. 跑 `preflight --execute`。
2. 等当前 slot 空闲：Central worker 不是 running，`current_task_type` 为空，ComfyUI `/queue` 无 running。
3. 执行 `takeover --failure-policy auto_rollback --execute`。
4. 验证新容器 healthy、disabled heartbeat gate、enable 后 Central worker profile/task types 正确。
5. helper 在 post-switch live 验证通过后原子更新 `current.yml`，并将 operation 收口为 `succeeded`；失败/回滚也必须留下 history。
6. 普通 profile 切换不改 Git catalog/docs；只有新增候选、换卡/UUID、digest/manifest、稳定阻断策略变化才走 PR 并同步必要知识库。

### Disabled canary 验收

1. 目标物理槽必须由 live/ledger 明确证明为 `intentionally_empty`；catalog 中的 `maintenance_disabled`、`blocked_*`、OOM/Xid 和容量记录继续作为显式单 slot canary 的审计信息，不替代实际 preflight 与运行健康验证。
2. 用 `canary-start-disabled --slot <slot> --include-disabled --execute` 完成镜像、模型缓存、容器健康和 disabled heartbeat 闭环；该事务绝不执行 `enable-aio`。
3. 验收任务结束并确认结果后，用 `canary-stop-disabled --slot <slot> --include-disabled --execute` 收口；它会等待 Central worker 与 Comfy queue 均空闲，再停止容器并恢复本地账本的 `intentionally_empty`。
4. 任一门禁失败都停止，不允许退回独立 `start-disabled`、手工 Docker 或先 enable 再 disable。

### 恢复失败现场

只使用：

```bash
python scripts/lan_aio_fleet_prod_ops.py recover --physical-slot <node>:gpuN --slot <slot> --prefer old|candidate --execute
```

恢复后重新跑 `status --include-disabled`；helper 自动把 recovery result 写入 XDG history/current，避免只留下远端现场。若失败 rollout 已通过只读检查确认该物理槽没有任何 running catalog container，先用精确 `state-reconcile --physical-slot <node>:gpuN --reason ... --execute` 记录 intentionally-empty，再显式选择 `--slot` recover；既有 intentionally-empty sibling 必须原样保留。recover 发现 exited/created 容器的 image ref 与 catalog 不一致时必须安全重建，不得直接启动旧镜像。

## 5. 交付格式

交付必须说明：

- 本轮读取的 XDG current 时间、operation ID 和 live status 时间。
- 改动的 catalog/docs/skill 文件；普通切换应明确说明 Git 未变更。
- 是否执行了生产 mutation；如果执行，列出目标 node/GPU/slot/profile。
- 验证结果：container health、Central worker、task types、ComfyUI health/queue、cache marker。
- 未解决 drift、blocked profile 或需要另开维护窗口的事项。
