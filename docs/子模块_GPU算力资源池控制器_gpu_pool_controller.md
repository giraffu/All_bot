# 子模块：GPU 算力资源池控制器

本文是 GPU Pool、RunPod 与 LAN AIO 的当前导航和稳定操作边界。完整历史
profile、canary、现场故障与某次节点状态已归档；实时数量和 current mapping
必须从 provider、Central 与 XDG ledger 读取。

## 1. 事实源

| 事实 | 唯一来源 |
| --- | --- |
| task type、workflow、profile 映射 | `src/domain_config/task_type_registry.py`、worker mapping |
| GPU artifact/profile contract | `deploy/release-artifacts-v2.json`、同 SHA release manifest |
| controller 与 provider | `ops/gpu_pool_controller/`、`scripts/gpu_pool_controller.py` |
| RunPod 手工操作 | `scripts/runpod_prod_ops.sh` 与 provider operation store |
| LAN 候选 catalog | `ops/gpu_pool_controller/config/lan_aio_prod_slots.yml` |
| LAN current/cache/history | `${XDG_STATE_HOME:-~/.local/state}/allbot/lan-aio/` |
| worker 在线与任务状态 | Central `/system/workers` 当次快照 |
| 模型/workflow 规则 | `allbot-comfy-models` 与 Comfy 专项文档 |

Git catalog 声明“允许管理什么”，不表示当前运行什么。live、ledger、catalog
不一致必须报告 drift；不得把一次探测结果写成本文件的长期事实。

## 2. 组件职责

- GPU Pool Controller 解析 profile、provider、release pin 和 operation，编排
  RunPod/LAN helper，不执行用户任务。
- Dashboard 展示队列与 worker 状态，并可提交受控 RunPod operation；不能
  自行拼接 provider API 或 LAN Compose。
- Worker Agent 从 Central 领取支持的 task type，调用同容器/目标 ComfyUI，
  上传结果并在 `/complete` 前确认交付成功。
- RunPod 是云端弹性 adapter；LAN AIO 是单物理卡受控容器 adapter。二者都
  必须使用 exact digest 和 baked `workers/runpod_runtime`，不能主机源码覆盖。

## 3. 不可变产物

- GPU 代码、workflow、模型 manifest 或真实基础依赖变化必须由受保护 main
  的同 SHA GPU manifest 提供 artifact、OCI revision 和模型证据。
- 未变化 profile 可以从可信完整祖先 manifest 继承 exact digest/source
  证据；不能重新标记旧镜像冒充当前 SHA 构建。
- LAN registry 只镜像 canonical digest；禁止在 LAN 主机现场 build 同一
  release/profile。
- Dashboard 手动池 profile catalog 包含独立 `ltx_t2v`，对应
  `ltx_t2v,ltx_t2v_ic`。创建后的 worker 默认 disabled，支持开启、暂停、重启、
  锁定和删除；该 profile 的 `autoscaler_enabled=false`，不会被自动扩缩容。
- release index 必须包含 Dashboard/autoscaler 需要的完整 profile pin 集。
  mutable tag、缺 profile、冲突 digest 或 incomplete manifest 一律 fail closed。
- workflow 只维护 `workers/comfy_agent/workflows/` 和相应 baked
  `workers/runpod_runtime` bundle；Central 不携带 workflow。

## 4. RunPod 边界

- 先读取 provider 状态、operation store、Central worker 和目标 profile
  release pin，再决定 status/add/down/restart/rollout。
- Pod 内诊断优先使用 Dashboard 提供的 `ssh.runpod.io` 代理入口；连接、有限重试、
  PTY 与标准输入命令模板见 `allbot-ops-deployment` 的
  `references/runpod-lan-runtime.md`。当次 Pod 页面是用户名和直连端口的事实源，
  不把临时连接信息写入 Git。
- 真实 create/start/stop/restart/delete/scale 同时要求运行开关、`--execute`
  和用户明确的生产确认。
- rollout 先 disabled 验证 exact image、OCI revision、runtime contract、
  ComfyUI health 和 heartbeat，再允许接单；失败恢复旧 exact digest。
- autoscaler 使用 leader lease、profile 阈值和 operation store，不能绕过
  provider 门禁或直接操作 LAN worker。
- 删除操作需要 deletion tombstone，避免残留 heartbeat 自动重新 enable；
  手工锁定的 worker 不能被 autoscaler down/cleanup。
- current Pod 数量、slot ID、临时公网地址和实时队列不进入 Git 或文档。

## 5. LAN AIO 边界

任何 current/cache/candidate/takeover/recover/restart 操作先加载
`allbot-lan-aio-operator`，只使用：

```bash
python scripts/lan_aio_fleet_prod_ops.py <command>
```

- 一次只操作一个 physical GPU/slot，不自由 Compose、不自由镜像、不跨卡批量。
- mutation 前读取 catalog、XDG ledger 和 live status，确认目标队列/任务状态。
- candidate 先生成声明式 patch，再由 Git 合入；普通 current profile 切换只
  更新 XDG ledger，不改 Git。
- takeover 使用事务化 drain/disabled canary/enable/rollback；禁止独立拼接
  stop-old/start-disabled 等中间 mutation。
- 只做验收的候选使用成对 disabled canary start/stop，不能先 enable 再 disable。
- 失联或隔离只允许专用 quarantine 流程，并要求 Central/control 状态满足
  空任务门禁；不能强杀运行任务。
- 单卡异常不得 reboot 主机、restart Docker daemon 或影响 sibling GPU，除非
  用户明确授权独立维护窗口。

## 6. 任务/profile 变更

新增或修改能力时按顺序核对：

1. 用户/public task type 与 billing/History/Gallery。
2. execution/Central type 与 request model/route。
3. worker supported types、mapping、patcher 和 workflow JSON。
4. profile 的镜像、模型 manifest、环境和运行资源。
5. RunPod create request、LAN catalog 候选和 Dashboard pin。
6. 同 SHA artifact validation、disabled canary 和目标 runtime smoke。

能复用已有 execution/profile 时不要新增。legacy alias 只用于历史兼容，不能
扩成新的用户入口或独立 workflow。

## 7. 故障排查

- pending：Central queue score、worker enabled/health、supported type、
  profile capacity、drain/maintenance。
- running：ComfyUI `/queue`/`system_stats`、workflow patcher、GPU OOM/Xid、
  result materialization、R2 upload 和 `/complete`。
- provider：operation store、API 状态、release pin、deletion tombstone 和
  autoscaler leader。
- LAN：catalog/ledger/live drift、port owner、image digest、cache marker、
  disabled heartbeat 和 sibling slot。

先建立可复现反馈环；不要直接删 Redis/provider state、重启整机或手工修改
ledger。

## 8. 验证与交付

- 代码：registry/mapping 一致性、provider dry-run、operator focused tests。
- artifact：exact digest、OCI revision、模型/workflow manifest 和环境中立扫描。
- runtime：目标 ComfyUI health/queue、Central heartbeat/task types、R2 上传后
  complete，以及非目标 slot 未变化。
- operation：记录目标 node/provider/profile/slot、是否 mutation、用户授权、
  old/new digest、结果与回滚状态。
- 区分代码支持、本地/disabled canary、测试环境和正式接单；未执行的运行态
  不能写成已上线。
