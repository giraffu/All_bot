---
name: "allbot-lan-aio-operator"
description: "本地主服务器 LAN AIO/GPU 单卡运维。用户报告局域网显卡或 ComfyUI 掉线、OOM/Xid、容器停止、显卡空闲但 Worker 不接单，或要求查看 current/cache/drift、拉镜像/热模型、单卡 takeover/recover/restart/canary 时使用；只允许 fleet 配置和 scripts/lan_aio_fleet_prod_ops.py，禁止自由 Compose/镜像或跨 slot 批量操作。"
---

# AllBot LAN AIO Operator

这是低自由度的生产操作 Skill。只通过 fleet catalog、XDG ledger 和固定 helper
管理一个明确 physical GPU/slot；不复制脚本 `--help` 的完整参数表，也不保存易变
current/cache/worker 数量。

## 1. 必读事实源

按顺序读取：

1. `.codex/skills/allbot-ops-deployment/SKILL.md`；
2. `ops/gpu_pool_controller/config/lan_aio_prod_slots.yml`；
3. `${XDG_STATE_HOME:-~/.local/state}/allbot/lan-aio/current.yml`；
4. `python3 scripts/lan_aio_fleet_prod_ops.py <command> --help`；
5. 需要解释边界时再读
   `docs/子模块_GPU算力资源池控制器_gpu_pool_controller.md` 或
   `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`。

事实源分工：

- catalog：物理卡/端口、候选 profile、精确镜像、模型 manifest 和稳定策略；
- XDG ledger/history：last-known current/cache、operation、成功/失败/回滚审计；
- live：容器、Central worker、ComfyUI `/queue`/`system_stats` 和 GPU 现实；
- legacy fleet state：只供首次迁移种子，不是普通 current。

live、ledger、catalog 不一致时记录 drift 并停止自动推断。只在用户授权的精确单
slot 操作中按 helper 契约收口，不静默用 live 覆盖 ledger。

## 2. 唯一操作入口

只使用：

```bash
python3 scripts/lan_aio_fleet_prod_ops.py <command> [exact target/options]
```

| 目标 | 允许的命令族 |
| --- | --- |
| 只读发现 | `list`、`status`、`render`、`candidate-plan` |
| 账本初始化/对账 | `state-init`、`state-reconcile` |
| 镜像和模型 | `preflight`、`pull-image`、`warm-cache`、`cache-gc` |
| 单卡切换/恢复 | `takeover`、`recover`、`restart-aio`、`retire-legacy` |
| disabled 验收 | `canary-start-disabled`、`canary-stop-disabled` |
| 故障隔离 | `isolate-quarantined` |
| 精确 artifact rollout | `release-rollout --artifact <repo@sha256:digest>` |

mutation 必须使用 helper 要求的 `--execute`、精确 node/GPU/slot/profile 和用户
授权。命令参数以当前 `--help` 和 focused tests 为准，禁止从旧文档拼接已退役
子命令。

## 3. 稳定事务边界

- 一次只操作一个 physical GPU/slot；禁止跨节点批量切换。
- 切换前必须证明 Central 与 ComfyUI 都无 running task；等待自然空闲，不强杀。
- `takeover` 负责 drain → disabled candidate → health/heartbeat → enable → ledger
  commit；失败按 helper 的 auto rollback 收口，不能拆成手工 Docker 步骤。
- `recover` 必须给出 physical slot、目标 slot 和 old/candidate 偏好；已停止候选
  通过 managed Compose 重建并重新验收，不能因 digest 相同直接 `docker start`。
- disabled canary 必须成对 start/stop，且物理槽先由 live/ledger 证明为
  `intentionally_empty`；canary 不启用 intake。
- `release-rollout` 只接受 canonical exact digest。若 LAN registry 是 mirror，
  先用 `scripts/copy_canonical_image_to_lan_registry.sh` 保摘要复制；禁止现场 build、
  mutable tag 或跨仓库伪造 rollback ref。
- 镜像、模型 cache 和账本只有在 helper 完成 post-switch 验证后更新；失败也要
  保留 operation history。
- GPU profile runtime 由不可变 artifact 烘焙；不得 rsync
  `workers/runpod_runtime/` 或用 host bind mount 覆盖镜像代码。

## 4. 故障与隔离

- OOM/Xid、容器退出、heartbeat 缺失或不接单先叠加
  `allbot-diagnosing-bugs`/`ops-log-monitor`，区分 GPU、ComfyUI、容器、Central
  control、profile/task types 和 cache。
- 普通故障优先 `status`/`preflight` 后选择 `recover` 或 `restart-aio`；不得用
  reboot 主机、restart Docker daemon 或自由 Compose 作为第一步。
- `isolate-quarantined` 只用于 Central 明确 `quarantined|error` 且无 current
  task，或 agent 已注销但已有持久 disabled control 的单 slot。它必须先把目标
  容器 restart policy 固定为 `no` 再停止；不满足条件时拒绝。
- 账本为空槽对账只允许精确 `state-reconcile --physical-slot ...`，并要求 live
  证明没有 running catalog container；不能因其它节点不可达而改写目标之外状态。
- `blocked_*`、maintenance、显存、OOM/Xid 是审计/遥测，不自动扩大或取消用户
  已明确授权的单 slot 操作；实际 helper preflight 仍必须通过。

## 5. 红线

- 未经用户明确要求，不执行 LAN/GPU 生产 mutation。
- 不手写 Compose，不自由指定 image/manifest，不绕过 catalog/helper，不调用已
  退役 Dashboard LAN slot 管理 API。
- `lan_resource_manager/` 只是受限 UI adapter，最终仍调用同一 helper；开发它时
  叠加 `allbot-lan-resource-manager`。
- 不 reboot GPU 主机或 restart Docker daemon，除非用户明确授权维护窗口并给出
  目标/影响/回滚。
- 不输出 `.env`、Compose 展开、token、agent secret、R2 key、预签 URL、数据库
  URL 或代理值。
- 代理、current/cache、operation、worker 数量和最近验证时间只属受限运行态，
  不写入 Git/Skill。
- 普通 profile 切换不修改 Git；只有 catalog 候选、硬件身份、digest/manifest 或
  稳定策略变化才走代码变更与知识同步。

## 6. 最小验证与交付

```bash
.venv/bin/python -m pytest -q tests/ops/test_lan_aio_prod.py
python3 scripts/doc_quality_checker.py
```

实际操作交付必须列出：授权范围、目标 node/GPU/slot/profile、操作前 ledger/live
时间、精确命令族、artifact digest、container health、Central worker/task types、
ComfyUI health/queue、cache marker、operation ID、回滚结果和残余 drift。未执行
mutation 时明确说明只读。
