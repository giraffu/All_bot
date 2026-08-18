# 子模块：局域网 GPU 节点资源与运维

本文只记录 LAN GPU 的稳定架构、事实源和运维边界。节点当前 profile、容器、
UUID、端口占用、cache marker、故障卡状态和某次 takeover 结果属于易变运行态，
不得从本文推断。旧现场流水的退出说明见
[LAN GPU 运行态历史退役说明](archive/lan-gpu-runtime-history-retirement.md)。

## 1. 事实源

| 事实 | 唯一来源 |
| --- | --- |
| 可管理节点、物理槽、候选 profile 与稳定阻断策略 | `ops/gpu_pool_controller/config/lan_aio_prod_slots.yml` |
| current、previous、cache 与 operation history | `${XDG_STATE_HOME:-~/.local/state}/allbot/lan-aio/` |
| 此刻容器、GPU、端口、ComfyUI 与队列 | fleet helper 和目标节点当次只读探测 |
| Central worker、enabled/health/task | Central `/system/workers` 当次快照 |
| artifact 与模型 manifest | `deploy/module-catalog.json`、catalog 中的 exact digest/manifest |
| SSH host 与密钥边界 | `docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md` |
| 操作命令与授权红线 | `allbot-lan-aio-operator` |

catalog 声明“允许管理什么”，不表示“当前运行什么”。catalog v2 的 legacy
`enabled/phase/old_runtime` 普通字段不再承担 current identity；XDG ledger 是
last-known state，live status 才是现实。三者不一致时记录 drift，不能静默让
任一来源覆盖其它来源。

本资料保持 `runtime-verification-required`。代码、catalog 与 tests 通过不等于
节点在线、模型已缓存、GPU 健康或生产正在接单。

## 2. 组件与隔离

- 一个 physical GPU/slot 同时只能有一个受管 current AIO runtime。
- 每个 runtime 有明确 node、GPU identity、host port、container、agent、
  profile、supported task types、workspace 与模型 manifest。
- sibling GPU 是独立故障域。单卡切换、恢复、隔离或 rollout 不得重启整机、
  Docker daemon 或跨槽操作，除非用户明确授权维护窗口。
- 远端 NVIDIA 节点使用 `lan_ssh + nvidia`；本地主 ROCm 节点可使用
  `lan_local + rocm`。transport 与 accelerator 是独立 seam，不能混用设备
  reservation。
- Worker Agent 只从 Central 领取自己声明的 execution task type。public task、
  billing、History 和 Gallery 语义仍由 task registry/core 决定，不能从 LAN
  profile 反推。

## 3. 不可变 artifact 与模型缓存

- LAN runtime 只消费 canonical `repository@sha256:digest`。同一 release/profile
  不得在目标节点现场 build、改 tag、同步源码或 bind mount 覆盖 baked runtime。
- LAN registry mirror 必须通过
  `scripts/copy_canonical_image_to_lan_registry.sh` 保 digest 复制并复核。
- 模型不进入业务镜像。fleet helper 按 catalog manifest 写入 profile workspace，
  完成 size/SHA-256 校验后原子生成 ready marker。
- current runtime 可继续使用旧的已验证 exact digest，直到操作者明确执行单槽
  rollout。合入 catalog 或构建 artifact 不会自动切换生产。
- 缓存、partial download、磁盘容量与 marker 都必须在目标槽当次检查。历史
  “已缓存”记录不能替代 live marker。

## 4. 只读核对

处理 LAN AIO 前依次：

1. 读取目标 slot 的 catalog 条目。
2. 读取 XDG `current.yml` 和未完成 operation。
3. 运行 fleet `list/status --include-disabled`。
4. 核对目标节点 GPU identity、容器 image/status/port、ComfyUI
   `/system_stats` 与 `/queue`。
5. 核对 Central worker 的 agent/profile/task types、enabled、health 和
   current task。
6. 对比 catalog/ledger/live；有 drift 时停止并报告，只有确认 live 后才可
   显式 `state-reconcile`。

只读命令和脱敏要求以 `allbot-lan-aio-operator` 为准。不得输出 env、token、
R2 key、presigned URL、数据库 URL 或完整 Compose expansion。

## 5. Mutation 路由

所有生产 mutation 都要求用户明确指定目标 node/GPU/slot/profile，并且只通过：

```bash
python3 scripts/lan_aio_fleet_prod_ops.py <command>
```

标准能力：

- candidate：先 `candidate-plan` 生成 Git catalog patch，再评审并合入。
- cache：`pull-image`、`warm-cache`，只准备目标 slot。
- cache GC：`cache-gc --slot <non-current-slot>` 只删除该 slot 的模型
  workspace；current、运行容器挂载或非受管路径一律拒绝，默认 dry-run。
- 验收：空槽使用成对
  `canary-start-disabled` / `canary-stop-disabled`，绝不 enable intake。
- 切换：`takeover --failure-policy auto_rollback`，事务化完成 drain、disabled
  验证、enable、post-check 与 ledger 收口。
- 发布：`release-rollout --artifact <exact-digest>`，失败只恢复目标 slot 的
  previous exact identity。
- 恢复：`recover --physical-slot <node>:gpuN --slot <slot>
  --prefer old|candidate`。
- 故障隔离：只在 Central/control 明确空任务且状态满足门禁时使用
  `isolate-quarantined`。

禁止自由 Compose、手写 Docker lifecycle、自由镜像、跨 slot 批量操作、强杀
运行任务、直接编辑 XDG ledger，或调用已废弃 Dashboard LAN slot API。

## 6. 任务安全与恢复

- mutation 前等待 Central 和 ComfyUI queue 自然空闲。无法证明空闲就停止。
- 人工停接使用无 TTL `disabled` control；只能由后续显式 enable 恢复。
- OOM、status 137、Xid、GPU reset-required、模型缺失、host port owner 冲突、
  heartbeat 缺失或 upload/`/complete` 失败都视为目标 slot 验证失败。
- candidate 失败优先自动恢复 previous；恢复无法验证时保持 disabled，不扩大
  到 sibling slot。
- exited/created 容器恢复时由 managed compose 重建，不能仅 `docker start`，
  否则可能绕过最新 env、挂载、端口或 image。
- GPU 失联且 queue gate 无法执行时，只有专用 quarantine 条件成立才允许隔离；
  该入口不能作为普通强停捷径。

## 7. 存储与清理

ComfyUI `input/output/temp`、模型 cache、runtime workspace 和 operator state 是
不同生命周期：

- 正在运行、pending/running task 引用或回滚所需的文件不得清理。
- 清理必须限定目标节点与明确目录，先 dry-run/统计，再执行受控 helper。
- 不使用宽泛 glob、根目录递归删除或跨节点批量清理。
- 模型 cache 只按 manifest/marker 管理；不能把释放临时媒体空间扩大成删除模型。
- 清理结果、释放容量和某次节点快照进入 logs/archive，不写回活跃 SOP。

## 8. 最小验证

```bash
.venv/bin/python -m pytest -q tests/ops/test_lan_aio_prod.py \
  tests/ops/test_gpu_release_rollout.py \
  tests/ops/test_runpod_bootstrap.py
python3 scripts/doc_quality_checker.py
```

涉及 Worker runtime、workflow 或模型时，再运行对应 worker mapping/patcher 和
manifest tests。运行态交付必须记录：

- 读取的 catalog/XDG/live 时间与 operation ID。
- 是否执行 mutation，以及唯一目标 node/GPU/slot/profile。
- old/new exact digest、cache marker、container/ComfyUI/Central 验证。
- 非目标 slot 未变化。
- 未解决 drift、blocked policy 或需要另开维护窗口的事项。

普通 profile current 切换只更新 XDG/provider state，不修改 Git 文档；只有新增
候选、物理 identity、artifact/manifest 或稳定阻断策略变化才同步 catalog 与知识库。
