# 子模块：GPU 算力资源池控制器

MiniMax H3 使用独立 `minimax_h3` manual-only profile；不加入 autoscaler。当前 25 文件
模型包约 152.7GB，并要求至少 145GiB 空闲模型卷；它同时包含默认
10Eros 与官方 FL2VA/Ref2VA checkpoint。首版 GPU allowlist 为 RTX 5090。REF2V 只扩展正式 LAN
`gpu-177-gpu1-minimax_h3` 的四类 capability；RunPod profile/autoscaler 与
`gpu-177-gpu1-minimax_h3_test` 候选不扩展。LAN 候选只能在 canonical 镜像
digest 构建完成后加入 catalog，并通过单槽 takeover/recover 验收。

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
- 测试 agent 不属于 LAN current slot，也不与正式 Worker 互斥。二者可分别连接
  test/prod Central 并长期共享同一个 ComfyUI；任务消费归属看各自 Central，物理 GPU
  执行顺序看 ComfyUI `/queue`。普通测试任务不触发正式 Worker drain，GPU artifact、
  cache、workflow、ComfyUI 生命周期或 slot mutation 才按单槽维护门禁排空。
- RunPod 是云端弹性 adapter；LAN AIO 是单物理卡受控容器 adapter。二者都
  必须使用 exact digest；镜像从 canonical `workers/comfy_agent`、根 `src`、
  `shared` 与薄 `workers/runpod_runtime` adapter 组合，不能主机源码覆盖。
- LAN AIO transport 与 accelerator 是正交 seam：远端 NVIDIA 节点使用
  `lan_ssh + nvidia`，本地主 Ryzen APU 可使用 `lan_local + rocm`。`lan_local`
  只把同一套受管 operator 命令落到本机 shell/filesystem，不授权自由 compose；
  `rocm` 渲染 KFD/Dri 设备契约，不能携带 NVIDIA reservation。
- 115 GPU0 可在用户明确授权的维护窗口由 Prompt Optimizer 临时接管。接管只能调用
  `scripts/prompt_optimizer_worker_ops.py`，而图生图 slot 的排空、停机、XDG
  `intentionally_empty` 记录与恢复仍全部委托 `lan_aio_fleet_prod_ops.py`。停机前必须
  同时验证 Central 任务与 Comfy 队列为空，并把容器 restart policy 设为 `no`；恢复
  必须按 ledger/catalog 中同一精确 slot 重建，不能自由 compose。

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
- `RUNPOD_ASSET_CONTRACT_VERIFIED_PROFILES` 只登记已在 test 用对应 exact digest
  完成 asset-contract canary 的 Dashboard canonical profile。Dashboard 仅展示
  该 allowlist，并在手动或 autoscaler 的创建、扩容、启用和重启入口再次
  fail closed；禁用、排空和 down 不受此门禁限制，以便安全收敛旧 runtime。
  allowlist 缺失、为空或包含未知 profile 时管理入口返回 `503`，不得退回完整
  catalog。精确镜像 pin 与 canary allowlist 是两项独立证据，只有 pin 不能视为
  canary 已通过。
- 旧 `face_swap` 只是 `i2i_pro` 的兼容任务 alias，复用
  `RUNPOD_IMAGE_NAME_I2I_PRO`，不得在 Dashboard release pins 中保留独立
  `RUNPOD_IMAGE_NAME_FACE_SWAP`。
- release index 必须包含 Dashboard/autoscaler 需要的完整 profile pin 集。
  mutable tag、缺 profile、冲突 digest 或 incomplete manifest 一律 fail closed。
- `img2img_rocm_gfx1151` 是 `img2img_lora_rocm_gfx1151` LAN runtime 的独立
  release module。它与 CUDA `img2img` 共享 task/workflow/model manifest 语义，
  但 artifact、accelerator contract 和验证证据完全分离。
- agent、patcher、workflow 只维护 `workers/comfy_agent/`；profile 构建直接
  复制 canonical package 和根 `src/`，`runpod_runtime` 只留 entrypoint、relay、
  requirements 与运维脚本。镜像 ENV/label 嵌入 Git SHA、package hash 与 mapping
  hash，agent 启动时验证并在 heartbeat 的 `runtime_manifest` 报告；Central 不携带 workflow。
- 每个 RunPod profile 必须同时包含 `shared/`，并在构建阶段 smoke import
  `shared.character_reference_sheet`；否则 `comfy_agent` 会在 ComfyUI 和 relay
  就绪后才因结果物化依赖缺失而退出，且无 heartbeat。
- profile 必须在镜像构建时安装 baked worker 的 `requirements.txt`；bootstrap
  可以复核已满足依赖，但生产重启不能把 PyPI 下载放在健康恢复关键路径。
- 单槽 release 可把精确 digest 从公网仓库切到受信 LAN registry
  `192.168.1.115:5000/allbot/`；其它跨仓库 artifact 仍重写到当前仓库，回滚引用
  始终保持原精确 digest。
- 带独立 `/opt/ComfyUI` 的 profile 必须显式渲染 `COMFYUI_DIR`，不能因持久卷已有
  `main.py` 而启动陈旧 `/workspace/ComfyUI`。外部 `RUNPOD_MODEL_TARGET_DIR` 与 baked
  `models` 路径不同时，只允许 entrypoint 在确认没有业务模型权重后建立链接；基础
  ComfyUI 自带的 `vae_approx/tae*_encoder.pth` / `tae*_decoder.pth` 预览权重会以
  不覆盖方式保留到外部模型目录，其它 `.safetensors` / `.ckpt` / `.pt` / `.pth` /
  `.bin` / `.onnx` 仍 fail-closed。构建 smoke 应通过 `/object_info` 验证 required
  nodes 的实际注册结果。

## 4. RunPod 边界

- 先读取 provider 状态、operation store、Central worker 和目标 profile
  release pin，再决定 status/add/down/restart/rollout。
- 新建 RunPod 通过 `RUNPOD_MODEL_DOWNLOAD_CONCURRENCY` 控制模型文件级并行，
  默认 4、有效范围 1–8；同步器自身在变量缺失时保持串行，避免改变 LAN 调用。
  下载阶段只写各自 `.partial`，全部成功后才按 manifest 顺序串行执行
  size/SHA-256 校验和原子替换。任一文件耗尽重试时取消未开始项、停止活动流并
  保留 partial，整个 bootstrap fail closed。
- 并发配置与 runtime 只在新建 Pod 的精确 digest/env 中生效；不得用 restart
  假定旧 Pod 已获得新代码，也不得为启用并行而批量替换现有 slot。
- 私有镜像必须通过 `RUNPOD_CONTAINER_REGISTRY_AUTH_ID` 引用 RunPod 中已建的
  registry auth；provider 只在显式 `imageName` 请求上注入
  `containerRegistryAuthId`，不将 registry 凭据或 token 放入 Pod env 和日志。
- Pod 内诊断优先使用 Dashboard/RunPod 当前提供的 SSH 入口；先从当次 Pod 页面
  读取用户名、端口和连接方式，再按 `allbot-cloud-ssh` 分段诊断。旧 Skill
  reference 已归档，不能用其中的 profile/track/attestation 快照决定当前操作。
  临时连接信息不得写入 Git。
- RunPod 启动入口必须把实际 ComfyUI `input/output/temp` 目录投影为
  `COMFY_ARTIFACT_*_DIR`。Worker 成功完成后精确清理任务媒体，并周期清理超期孤儿；
  `COMFY_ARTIFACT_MIN_FREE_GB` 默认保留 10 GiB，低于水位的实例以
  `artifact_disk_low` 停止接单。不得用清空 `/workspace`、模型目录或无年龄/任务
  边界的递归删除代替该机制。
- 真实 create/start/stop/restart/delete/scale 同时要求运行开关、`--execute`
  和用户明确的生产确认。
- rollout 先 disabled 验证 exact image、OCI revision、runtime contract、
  ComfyUI health 和 heartbeat，再允许接单；失败恢复旧 exact digest。
- autoscaler 使用 leader lease、profile 阈值和 operation store，不能绕过
  provider 门禁或直接操作 LAN worker。
- profile 的 autoscaler 暂停只阻止自动扩容、恢复和重启；无积压时，心跳新鲜、
  已空闲且未锁定的 disabled/draining RunPod 仍必须允许 down，避免“暂停接单”
  变成持续占用计费资源。enabled Worker 的 down 继续受最低接单容量保护。
- 未暂停的 profile 也只在存在积压时自动 enable 暂停 Worker；没有积压时直接
  down 已空闲的暂停 RunPod，禁止形成 enable 成功、冷却、再次 enable 的循环。
- 删除操作需要 deletion tombstone，避免残留 heartbeat 自动重新 enable；
  手工锁定的 worker 不能被 autoscaler down/cleanup。
- current Pod 数量、slot ID、临时公网地址和实时队列不进入 Git 或文档。

## 5. LAN AIO 边界

任何 current/cache/candidate/takeover/recover/restart 操作先加载
`allbot-lan-aio-operator`，只使用：

```bash
python3 scripts/lan_aio_fleet_prod_ops.py <command>
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
- 旧 profile 在容器启动时仍需在线安装 Python 依赖且链路较慢时，可通过临时
  AIO env 向单次 fleet 操作传 `LAN_AIO_PIP_DEFAULT_TIMEOUT` 和
  `LAN_AIO_PIP_RETRIES`；render 只把它们映射成容器内标准 pip 环境变量，不能
  借此覆盖依赖版本、index 或镜像身份。恢复后不把临时值写入 catalog/current。

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
- 发布模块 id 为 `lan_all`，LAN 运行 profile id 为 `all`；
  `release-rollout` 和 disabled canary 必须通过统一映射接受这对 id，
  不能以字符串不相等拒绝合法的 exact-digest 发布。
- `all` 的 LTX 子栈与 `ltx_unified` 使用同一份
  `ltx_unified/2026-08-01-comfy-fast/manifest.json` 和三份 extracted-10Eros workflow；
  不再同时声明旧 `ltx_video` 与 `ltx_t2v` manifest。多 manifest 同步继续按
  相对路径、大小和 SHA-256 复用既有对象，只补统一 manifest 的真实差集，
  普通 T2V 保留 Sulphur workflow，IC 使用纯官方单阶段 Ingredients
  workflow。
- 仅 baked worker runtime 变化且依赖清单未变时，可使用
  `lan_all_runtime_refresh`：它以已经验证的 LAN `all` exact digest 为基础，
  对旧/新 `requirements.txt` 做固定 SHA-256 双向门禁后完整替换 runtime，
  使用公共多 manifest 同步器并写入新的 main revision。依赖、ComfyUI、custom
  node 或 workflow 资产发生变化时必须回到完整 `lan_all` 构建，不能借 refresh
  绕过节点与依赖验证。
- LAN model cache 可只读合并多个 manifest，以相对路径、size 和 SHA-256
  去重；同路径内容冲突、缺文件、ready marker 不完整或磁盘不足均 fail
  closed。
- runtime 使用单 Comfy 执行、最多两个 claimed slot（执行 + 深度一预取），
  上传和 `/complete` 交付可与下一次 Comfy 执行重叠。
- `PREFERRED_TASK_TYPES` 为空时，Central 仍在全部支持类型中按全局 queue
  score 领取最早任务，不做按类型轮询或亲和。flex Worker 可显式声明
  preferred 子集，让单次原子领取先扫描 preferred 组、无匹配时才取 fallback；
  已经 running 的 fallback 不抢占，下一次领取重新判断。
- `scail2_flex` 是 gpu-002 GPU0 的受限 LAN 候选：supported 只包含四类
  SCAIL-2 加 `img2img,img2img_lora`，preferred 固定为四类 SCAIL-2。
  `PREFETCH_TASK_TYPES` 也只能包含 preferred 四类，禁止预接 fallback。profile
  使用 SCAIL-2 与 img2img_lora 两份 manifest，并在每次提交 workflow 前释放
  Comfy 驻留模型。catalog 与 artifact 就绪不等于授权切换当前 SCAIL-2 slot。
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
