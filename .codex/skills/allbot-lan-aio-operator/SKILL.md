---
name: "allbot-lan-aio-operator"
description: "本地主服务器 LAN AIO 运维操作员。管理局域网 GPU 节点的 LAN AIO 当前态、缓存态、候选切换、单卡 takeover/recover/restart、镜像拉取和模型热缓存时使用；必须通过 fleet 配置和 scripts/lan_aio_fleet_prod_ops.py，禁止自由 compose、自由镜像或跨 slot 批量操作。"
---

# AllBot LAN AIO Operator

GPU profile 必须有 canonical digest；LAN registry 只通过 `scripts/copy_canonical_image_to_lan_registry.sh` 保摘要复制。禁止 LAN 现场重建同一产物。

正式 profile 镜像已烘焙 `/opt/allbot/runtime/runpod_worker`；`workers/runpod_runtime/` 只能通过不可变 GPU artifact 构建进入目标主机，operator 不得同步源码或用 host bind mount 覆盖镜像内代码。

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

发布边界：

- GPU↔LAN 当前映射、cache marker、最近验证时间以及 RunPod 当前数量都是易变运行态，只写 XDG ledger、provider/operation store 或后台观测，不写 Git，不因漂移触发代码发布。
- helper、operator、runtime 或 profile 代码进入 main 不自动构建或部署任何
  artifact。focused tests 由任务自行决定，不是 main 合入或发布门禁。
- GPU 构建由操作者显式执行 `release.py build --module <profile> --sha <sha>`，
  只构建该 profile；不读取 change scope、CI、bundle、attestation、canary
  evidence 或其它 profile 状态。

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
python scripts/lan_aio_fleet_prod_ops.py cache-gc --slot <non-current-slot> --include-disabled --execute
python scripts/lan_aio_fleet_prod_ops.py canary-stop-disabled --slot <slot> --include-disabled --execute
python scripts/lan_aio_fleet_prod_ops.py isolate-quarantined --slot <slot> --execute
python scripts/lan_aio_fleet_prod_ops.py takeover --slot <slot> --replace-slot <current-slot> --include-disabled --failure-policy auto_rollback --execute
python scripts/lan_aio_fleet_prod_ops.py recover --physical-slot <node>:gpuN --slot <slot> --prefer old|candidate --execute
python scripts/lan_aio_fleet_prod_ops.py restart-aio --slot <slot> --execute
python scripts/lan_aio_fleet_prod_ops.py retire-legacy --slot <current-slot> --execute
python scripts/lan_aio_fleet_prod_ops.py release-rollout --slot <slot> --profile <profile> --artifact <repo@sha256:digest> [--rollback-ref <same-repo@sha256:...>] --execute
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
- `release-rollout` 直接接收精确 artifact：先 disabled/drain，验证容器实际
  image、进程健康和 disabled heartbeat 后才 enable；失败只恢复该 slot 的旧
  镜像，恢复无法验证时保持 disabled。
- 若 artifact 使用 GHCR canonical 仓库，而当前 LAN profile 使用 LAN registry
  mirror，helper 只映射同一 digest；必须先保摘要复制，禁止改 digest 或现场 build。
- 目标节点尚未配置 HTTP LAN registry 且没有 Docker daemon 维护窗口时，Git catalog 可直接固定 release index 的 canonical GHCR 完整 digest，禁止改用 tag；显式 exact rollback ref 会在停接/等待空闲前由 helper 预拉，确保回滚镜像真实可用。
- 历史 LAN 镜像若由 tar 导入、旧 tag 没有 `RepoDigests`，只能在独立核验当前 tag 的 registry digest 后传 `--rollback-ref <same-repo@sha256:...>`；helper 拒绝 mutable 或跨仓库回滚引用，不能用该参数自由指定运行镜像。
- 不手写 Docker Compose，不自由指定镜像或 manifest，不绕过 `lan_aio_prod_slots.yml`。
- 不调用 Dashboard `/api/runpod/lan-aio/slots*` 或 `/profiles` 管理 LAN AIO；这些 Web slot 管理 API 已废弃，候选切换、恢复和缓存预热只走本地主 AI operator/CLI。
- `lan_resource_manager/` 是本地主 operator 的受限 UI adapter，不属于 Dashboard API。它只允许状态一致时切换 `catalog_ready + enabled + retargetable` 候选，最终仍调用本 helper 的单卡 `takeover/recover`；开发该平台时继续加载 `allbot-lan-resource-manager`。
- 不 reboot GPU 主机，不 restart Docker daemon，除非用户明确要求维护窗口。
- 切换前必须确认当前 slot 无 running task；等待自然空闲，不强杀任务。
- `blocked_*`、`maintenance_disabled`、`blocked_host_service_runtime` 与 OOM/Xid 记录仅作为 catalog 审计信息，不阻断显式 slot 操作。
- profile 的最低显存与实际显存只作为 canary 遥测，不构成启动或接单门禁。
- helper 报告 drift、端口冲突、cache/heartbeat 缺失；仍须验证容器、Central 与 ComfyUI。
- LAN 节点冷启动确需通过本地主 VPN 下载公开依赖时，只允许在本机受限 env 中显式设置 `LAN_AIO_HTTP_PROXY`、`LAN_AIO_HTTPS_PROXY` 与 `LAN_AIO_NO_PROXY`；operator 将其映射为目标容器的大小写 proxy 变量。代理值不得写入 Git catalog、Compose 或日志，默认未配置时运行行为不变。
- `takeover/recover/restart-aio/retire-legacy/warm-cache/pull-image/canary-start-disabled/canary-stop-disabled` 等 mutation 仍持有本地单实例锁；live/ledger/catalog 差异和未完成 operation 会写入审计，但不会阻止后续显式单 slot mutation。
- `disable-aio` 写入无 TTL 的持久 `disabled` control，故障节点只能通过后续显式
  `enable-aio` 恢复接单；不得用会自动过期的临时 control 表示人工停接。
- `drain-legacy/stop-old/start-disabled/rollback` 不再允许作为独立 `--execute` 链路；使用事务化 `takeover` 或精确 `recover`，避免账本停在中间态。`recover` 遇到已停止候选时必须通过 managed compose 重建并重新验收，不能因 image digest 相同直接 `docker start`，否则最新 env、挂载或端口配置不会生效。
- 接管稳定后若旧 worker 的临时 disabled control 已过期，只能对 live/ledger
  一致且健康、intake 已 enabled 的当前 slot 执行 `retire-legacy`。该动作允许
  当前 AIO 继续执行任务，但要求旧 worker 无任务、旧 runtime 已停止；随后把
  旧容器 restart policy 固定为 `no`，并写入无 TTL 的 disabled control。
- GPU/Comfy 已失联、标准 queue-idle 门禁无法执行时，只允许对 Central 明确为 `quarantined|error` 且 `current_task_id/current_task_type` 均为空，或 agent 已注销但 control 已明确为 `disabled` 的单 slot 使用 `isolate-quarantined`。该动作写无 TTL 的 disabled control，先把目标容器 restart policy 固定为 `no` 并复核，再停止目标容器、验证 stopped 并把物理槽记为 intentionally-empty；即使 GPU reset-required 导致 stop 失败，已验证的 `restart=no` 仍保证下次主机启动不会自动拉起该容器。状态不满足时拒绝，不能借此强杀运行中任务或跳过普通 canary stop。
- 只做本地验收且禁止 intake 的候选使用成对的
  `canary-start-disabled` / `canary-stop-disabled`；发布 artifact 本身通过
  `release-rollout --artifact <exact-digest>` 单槽替换，不再读取 release index、
  strategy、attestation 或 canary evidence。
- ledger 明确记录 `intentionally_empty` 时，允许对同一物理槽的指定候选执行只读 `preflight --execute`，用于读取逐项门禁；该例外不扩展到 pull、warm-cache 或其它 mutation。`configure-registry` 必须同时维护 daemon `insecure-registries` / `proxies.no-proxy` 与 systemd `NO_PROXY/no_proxy`，保留既有代理端点；重启 Docker 后只等待重启前已运行的候选恢复，本来停止的候选必须保持停止。

## 4. 标准流程

### 查看当前状态

1. 读 XDG `current.yml` 找目标 `node_id + gpu_index`；首次迁移才读 legacy seed。
2. 跑 `list --include-disabled` 和 `status --include-disabled`；确认 `state.status=passed`。
3. 对目标端口查 `/queue`、`/system_stats`。
4. 对照 ledger：current profile、agent、container、host port、cache state 必须一致；不一致时停止，确认 live 后显式 `state-reconcile --reason ... --execute`，不得静默覆盖。若目标物理槽因故障隔离或换卡而明确保持停机，且 live 探测成功证明没有任何 running catalog container，可额外传精确 `--physical-slot <node>:gpuN` 把该槽记录为 `intentionally_empty`；该 scoped 入口只探测和更新目标物理槽，保留其它槽账本与未完成 operation，不能用无关节点 SSH 故障阻断目标收口，也不能忽略目标自身的 SSH/探测错误。若目标应恢复产能，继续使用精确单槽 `recover`，不得借空槽收口跳过恢复门禁。

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
