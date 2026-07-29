# 子模块：GPU 算力资源池控制器

本文是 GPU Pool、RunPod 与 LAN AIO 的当前导航和稳定操作边界。完整历史
profile、canary、现场故障与某次节点状态已归档；实时数量和 current mapping
必须从 provider、Central 与 XDG ledger 读取。

## 1. 事实源

| 事实 | 唯一来源 |
| --- | --- |
| task type、workflow、profile 映射 | `src/domain_config/task_type_registry.py`、worker mapping |
| GPU artifact/profile contract | `deploy/module-catalog.json`、操作者指定的精确 digest |
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
- Dashboard 的 `RUNPOD_RELEASE_PROFILE_PINS_JSON` 必须与管理 profile catalog
  派生的 image env key 集合精确一致，且每个值都是
  `repository@sha256:<digest>`。`deploy/service-env-contract.yml` 和
  `scripts/runtime_env_contract.py` 在生产服务配置激活前执行该校验；缺少新
  profile、残留已退役 profile 或 mutable tag 均 fail closed，不能等到
  `/api/runpod/scale` 才暴露。
- 旧 `face_swap` 只是 `i2i_pro` 的兼容任务 alias，复用
  `RUNPOD_IMAGE_NAME_I2I_PRO`，不得在 Dashboard release pins 中保留独立
  `RUNPOD_IMAGE_NAME_FACE_SWAP`。
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

## 9. LAN-only `all` profile

`all` 是 LAN AIO 专用聚合 profile，不属于 RunPod provider、autoscaler、
Dashboard RunPod profile 或 Pod 创建链路。它的能力集合必须严格等于
`img2img`、Wan22 AIO、PornMaster BF16、SCAIL-2、LTX Video、`i2i_pro`、
专属换脸和 LTX T2V/IC-LoRA 等现有池展开后的 19 个 execution task type；
不新增 public type、价格或业务身份。

- canonical 镜像由受保护 main 的 exact SHA 构建，包含 workflow/custom node
  依赖并以 digest 固定；模型权重不入镜像。
- 仅 baked worker runtime 变化且依赖清单未变时，可使用
  `lan_all_runtime_refresh`：它以已经验证的 LAN `all` exact digest 为基础，
  对旧/新 `requirements.txt` 做固定 SHA-256 双向门禁后完整替换 runtime，
  重新应用多 manifest 补丁并写入新的 main revision。依赖、ComfyUI、custom
  node 或 workflow 资产发生变化时必须回到完整 `lan_all` 构建，不能借 refresh
  绕过节点与依赖验证。
- LAN model cache 可只读合并多个 manifest，以相对路径、size 和 SHA-256
  去重；同路径内容冲突、缺文件、ready marker 不完整或磁盘不足均 fail
  closed。
- runtime 使用单 Comfy 执行、最多两个 claimed slot（执行 + 深度一预取），
  上传和 `/complete` 交付可与下一次 Comfy 执行重叠。
- `PREFERRED_TASK_TYPES` 为空时，Central 仍在全部支持类型中按全局 queue
  score 领取最早任务，不做按类型轮询或亲和。未来 flex Worker 可显式声明
  preferred 子集，让单次原子领取先扫描 preferred 组、无匹配时才取 fallback；
  已经 running 的 fallback 不抢占，下一次领取重新判断。
- gpu-002 若未来把 SCAIL-2 扩展为 flex，preferred 必须固定为四类 SCAIL-2，
  且 `PREFETCH_TASK_TYPES` 也只能包含这四类，禁止预接 fallback。本协议能力
  上线不等于授权修改当前 profile、镜像、agent env 或启用 flex。
- GPU226 候选只能经 fleet helper 做单卡 drain、takeover、auto rollback；
  任意 OOM/status 137/Xid、workflow、上传或终态错误均恢复旧 exact digest。

## 10. 统一 LTX 执行 profile

`ltx_unified` 是执行层 profile，不替代 `ltx_video` 或 `ltx_t2v` 的逻辑
profile。它固定五个 task type、单 Comfy 执行槽、5GB reserve VRAM、独立
workspace key，并通过 `lan_model_workspace_key: ltx_video` 只复用原模型目录。
镜像必须由 `ltx_unified` 模块从完整 Git SHA 构建并固定精确 digest；LAN
workflow override 只把三类图生视频映射到 extracted-LoRA workflow，T2V 两类
继续使用原 Sulphur/Ingredients workflow。4090/5090 都允许进入候选 catalog，
但每种硬件首次正式承载前分别执行五类串行 canary。
