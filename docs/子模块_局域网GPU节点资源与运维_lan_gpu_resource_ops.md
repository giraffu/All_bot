# 子模块: 局域网 GPU 节点资源与运维 (LAN GPU Resource Ops)

## 1. 目标与范围

本文档记录武汉局域网 GPU 节点的硬件资源、容器布局、ComfyUI 实例、模型挂载、生产 worker 对应关系和安全运维边界。它用于后续研发、模型更新、ComfyUI 排障、worker 灰度和容量规划。

本文档不是实时监控面板。GPU 利用率、显存占用、队列长度和磁盘剩余空间都是采集时快照；做停机、扩容、清理或升级前必须重新采集。

最近一次资源快照更新：2026-06-18 03:06，Asia/Shanghai。
最近一次 ComfyUI 素材清理：2026-06-08，Asia/Shanghai。
最近一次 gpu-226 LTX 运行时补齐：2026-06-15，Asia/Shanghai。
最近一次 gpu-002 LAN RunPod 化一体容器生产接管：2026-06-16，Asia/Shanghai。
最近一次 LAN AIO fleet 泛化脚手架更新：2026-06-18，Asia/Shanghai。
最近一次 gpu-177/gpu0 LAN AIO 生产 canary 复启：2026-06-18，Asia/Shanghai。
最近一次 gpu-252/worker05 LAN AIO 生产接管：2026-06-18，Asia/Shanghai。
最近一次 gpu-002/gpu1 PornMaster Flux2 edit 替换接管：2026-06-29 23:17，Asia/Shanghai。
最近一次 gpu-002/gpu1 image_to_video 回切候选配置修正：2026-06-30，Asia/Shanghai。
最近一次 gpu-177/gpu0 live/configured 口径修正：2026-06-30，Asia/Shanghai。
最近一次 gpu-252/gpu1 maintenance disabled 当前态修正：2026-06-30，Asia/Shanghai。
最近一次 LAN AIO 安全切换与候选生成口径修正：2026-06-30，Asia/Shanghai。
最近一次 LAN AIO Dashboard 空卡巡检与恢复入口修正：2026-06-30，Asia/Shanghai。
最近一次 LAN AIO host port owner 门禁修正：2026-07-02，Asia/Shanghai。
最近一次 gpu-226 image_to_video LAN AIO 正式接管：2026-07-02，Asia/Shanghai。
最近一次 gpu-252/gpu0 i2i_pro LAN AIO 正式接管：2026-07-04 01:17，Asia/Shanghai。
最近一次 gpu-252/gpu1 返修卡 SCAIL-2 Xid 隔离：2026-07-04 19:19，Asia/Shanghai。
最近一次 gpu-252/gpu1 PornMaster Flux2 edit LAN AIO 正式接管：2026-07-04 19:41，Asia/Shanghai。
最近一次 gpu-226/gpu0 SCAIL-2 LAN AIO 正式切换与 xformers sm_120 镜像更新：2026-07-04 23:55，Asia/Shanghai。
最近一次 gpu-226/gpu0 image_to_video LAN AIO 回切：2026-07-05 00:51，Asia/Shanghai。

## 2. 总体拓扑

正式生产控制面在云端，生产 worker/relay 在本地主服务器，真实 GPU 推理由 4 台局域网 GPU 节点上的 ComfyUI 提供：

| 层级 | 承担功能 | 入口 |
| :--- | :--- | :--- |
| 云控制面 | `cloud-central-api-prod`、Web API、Payment、Dashboard、Bot、imgproxy | `ssh allbot-do-sgp1-control` |
| 本地主服务器 | `cloud-prod-worker-relay`、本地 `cloud-prod-comfy-agent-1..7` compose、结果 spool、legacy MinIO/Postgres/Redis 保留；线上实际 worker 还可能包含 LAN AIO、`remote_workers` 与手动 RunPod | 本机 `/home/hfy/APP/All_bot` |
| GPU 节点 | ComfyUI 推理、模型文件、输入输出缓存、DCGM/node exporter | `allbot-gpu-226/177/252/002` |

生产 worker 容器不在 GPU 节点上；它们在本地主服务器运行，通过局域网 HTTP/WS 调用各 GPU 节点的 ComfyUI。

## 3. 服务器总览

| 服务器 | SSH Host | CPU | 内存 | GPU | 磁盘快照 | 主要功能 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 主服务器 `hfy-FAEX9` | 本机 | Ryzen AI MAX+ 395，16C/32T | 62GiB | 无独立推理 GPU | `/` 3.6T，已用 1.6T，可用 1.9T | worker/relay、spool、legacy 数据、开发运维 |
| 云控制面 `allbot-do-sgp1-control-01` | `allbot-do-sgp1-control` | DO-Regular，8 vCPU | 约 15GiB | 无 | `/` 309G，已用 125G，可用 185G | 正式控制面 |
| `192.168.1.226` | `allbot-gpu-226` | Ryzen 9 9950X，16C/32T | 60GiB | 1 x RTX 5090 32G | `/` 1.8T，已用约 918G，可用约 821G | PornMaster Flux2 BF16 LAN AIO `8190`；image_to_video/SCAIL-2 为同卡回切候选；旧宿主机 ComfyUI `8188` / worker 01 为 stopped rollback 元数据 |
| `192.168.1.177` | `allbot-gpu-177` | Ryzen 7 9700X，8C/16T | 60GiB | 2 x RTX 5090 32G | `/` 915G，已用 190G，可用 680G | LAN AIO `8190/8191` only；legacy 02/03 已退役 |
| `192.168.1.252` | `allbot-gpu-252` | Ryzen 7 9700X，8C/16T | 60GiB | 2 x RTX 4090 48G visible，2 x production active | `/` 937G，已用约 705G，可用约 232G | LAN AIO `8192` 固定 UUID `GPU-09b7ea85-23df-a9b8-19d9-703534e47666`，`8191` 固定 RMA replacement UUID `GPU-8153a439-e3f6-8922-039d-dc13e97da6d7`；两者均承载 `i2i_pro,t2i-pornmaster-turbo,face_swap`。旧 UUID 已退役，历史 SCAIL-2/Wan22 槽位仍 maintenance-disabled |
| `192.168.1.2` | `allbot-gpu-002` | Ryzen 7 9700X，8C/16T | 60GiB | 2 x RTX 4090 48G | `/` 936G，已用 455G，可用 442G | slot0 SCAIL-2 LAN AIO `8190`，slot1 PornMaster Flux2 edit LAN AIO `8191`；image_to_video AIO stopped rollback |

容量警戒：

- 2026-06-08 已清理各 GPU 节点 ComfyUI 旧素材，`192.168.1.177` 从高风险的约 `14G` 可用恢复；2026-06-18 快照可用约 `243G`，已回升到约 73% 使用率，模型下载和大视频压测前应重点复查。
- ComfyUI `input/output/temp` 仍会随视频任务快速增长；每次模型下载、Docker pull/build 或大视频压测前都要重新检查 `df -h`。
- `192.168.1.226` 与 `192.168.1.252` 曾观察到 swap 使用较高，排查慢响应时要同时看内存压力、ComfyUI 任务和 Docker stats。
- 2026-06-18 03:06 云正式 Central 快照为 `queue_size=49`、`active_workers=13`、`healthy_workers=13`、`error_workers=0`、`quarantined_workers=0`。13 个 worker 是当时本地 agent、LAN AIO、`remote_workers` 与手动 RunPod 的混合运行态，不代表固定长期容量。
- GPU 利用率要和显存、ComfyUI `/queue`、worker heartbeat 一起看。显存高但 GPU 利用率低可能是模型常驻、加载、等待、后处理或 IO；单看 `memory.used` 不能判断“算力拉满”。

## 4. 本地主服务器 Worker 容器

本地主服务器运行云正式 worker 和 relay：

| 容器 | 角色 | 目标 ComfyUI | 支持任务 |
| :--- | :--- | :--- | :--- |
| `cloud-prod-worker-relay` | 本地 worker relay 与上传 sidecar，端口 `127.0.0.1:8013` | 云 Central `100.107.220.127:8003` | agent API 转发、R2 上传 sidecar |
| `cloud-prod-comfy-agent-1` | 旧 Worker 01，stopped rollback | 原 `192.168.1.226:8188` | 当前由 `lan_aio_prod_gpu226_gpu0_image_to_video_01` / AIO `8190` 承接 `image_to_video` / `video_insert` / `video_edit`；SCAIL-2 为同卡回切候选，旧综合 face/i2i/t2i 能力不再作为当前容量 |
| `cloud-prod-comfy-agent-2` | Worker 02，已退役 | 原 `192.168.1.177:8188` | 已由 `lan_aio_prod_gpu177_gpu0_image_to_video_01` 替换；容器已删除，control `disabled` |
| `cloud-prod-comfy-agent-3` | Worker 03，已退役 | 原 `192.168.1.177:8189` | 已由 `lan_aio_prod_gpu177_gpu1_ltx_video_01` 替换；容器已删除，control `disabled` |
| `cloud-prod-comfy-agent-4` | 旧 Worker 04，AIO 接管元数据 | 原 `192.168.1.252:8188` | 已由 `lan_aio_prod_gpu252_gpu0_i2i_pro_01` / AIO `8192` 接管 `i2i_pro,t2i-pornmaster-turbo,face_swap`；旧本地主 agent 不应与 AIO 同时运行 |
| `cloud-prod-comfy-agent-5` | 旧 Worker 05，stopped rollback | 原 `192.168.1.252:8189` | 已由 RMA replacement 卡上的 `lan_aio_prod_gpu252_gpu1_i2i_pro_01` / AIO `8191` 接管 `i2i_pro,t2i-pornmaster-turbo,face_swap`；旧 UUID 对应的 PornMaster/SCAIL-2/Wan22 AIO 保持 maintenance-disabled |
| `cloud-prod-comfy-agent-6` | Worker 06，stopped rollback | 原 `192.168.1.2:8188` | 已由 gpu-002 slot0 SCAIL-2 AIO 接管；旧 img2img_lora AIO 也为 stopped rollback |
| `cloud-prod-comfy-agent-7` | Worker 07，stopped rollback | 原 `192.168.1.2:8189` | 本地主 legacy agent 保持 disabled；gpu-002 slot1 当前由 `lan_aio_prod_gpu002_gpu1_pornmaster_flux2_edit_01` 承接 PornMaster Flux2 edit，image_to_video AIO 只作同卡回切候选 |

`video_insert` / `video_edit` 在 worker 能力列表中只表示 legacy alias，canonical 执行面类型是 `image_to_video`。排障或扩容时不要为它们新建独立 workflow、模型 profile 或 RunPod manifest。

SCAIL-2 动作迁移 / 视频换人 / 视频换脸 v10 有测试与正式链路，不能混用桶和 worker。云测试链路由 `cloud_worker_test_08` 指向 LAN AIO SCAIL-2 runtime `http://192.168.1.2:8190`，可声明 `scail2_action_transfer,scail2_action_transfer_long,scail2_video_replacement,scail2_face_swap_v2` 并通过测试 env 覆盖到 audio/context-window/v10 workflow；视频换脸会先调用 `192.168.1.226:8188` 的 `face_swap_v2.json` 对驱动视频第一帧做图片换脸。测试 runtime 容器 `allbot-lan-aio-gpu-002-gpu0-scail2-test` 本身只跑 ComfyUI、模型同步与 workflow 资产，不注册 Central worker。云正式 SCAIL-2 LAN worker 当前以 `gpu-002-gpu0-scail2` 为主；`gpu-226-gpu0-scail2` 在 2026-07-05 回切到 image_to_video 后保留为同卡候选，使用源码编译 xformers sm_120 的镜像 `192.168.1.115:5000/allbot/comfy-runpod-scail2:20260704-sm120-xformers-pr1262`，但该 RTX 5090 32G 低于 profile catalog 的 48G 偏好容量，未来再启用仍需观察 OOM/status 137。`gpu-252-gpu1-scail2` 固定返修 UUID `GPU-33de1af6-ca27-7eeb-ae46-6a9f4f89523e` 与 host `8191`，2026-07-04 虽通过 preflight、warm-cache、disabled heartbeat、`/system_stats`、`/object_info` 模型枚举、direct canary 和短 CUDA smoke，但真实 SCAIL-2 face-swap workload 复现 Xid 119/154，当前保持 maintenance-disabled，不计入 SCAIL-2 正式容量。该返修卡同日改承接低负载 `pornmaster_flux2_edit`，不代表 SCAIL-2/Wan22 解封。`gpu-177-gpu1-scail2` 已验证可启动并保留为同卡候选，但 2026-07-02 又切回 LTX 当前态；`gpu-252-gpu0-scail2` 在 2026-07-04 切到 i2i_pro 后保留为同卡回滚候选。正式 LAN SCAIL-2 worker 必须写正式 Central 与 `user-data-prod`，不要把它误判为测试 `cloud_worker_test_08` 能力；正式 RunPod `scail2` 仍保持两任务声明。

所有 worker 挂载：

- `/home/hfy/APP/All_bot/workers/comfy_agent/workflows -> /app/worker/workflows`
- `/home/hfy/APP/All_bot/src -> /app/src`
- `/home/hfy/APP/All_bot/logs/workers-cloud-prod -> /app/logs`
- `/home/hfy/APP/All_bot/logs/worker-spool-cloud-prod -> /app/spool`

`PIPELINE_ENABLED=true`，`PIPELINE_MAX_RUNNING_TASKS=2`。worker 重建只影响对应 agent；不会自动重启目标 GPU 节点的 ComfyUI。

GPU pool 相关环境变量只描述 Worker Agent 的观测和期望能力，不能直接推断底层 ComfyUI runtime：

| 字段 | 含义 | 运维判断 |
| :--- | :--- | :--- |
| `POOL_IMAGE_REF` / `image_ref` | 期望 profile 或镜像引用 | 对宿主机 ComfyUI 仅为声明；不是运行中 ComfyUI 镜像 digest |
| `runtime_profile` | Worker 声明的任务运行 profile | 可用于任务类型分配和 canary 选择 |
| `comfy_runtime_kind` | `host_service` 或 `docker_container` | 决定是否能生成 Docker 操作计划 |
| `comfy_runtime_managed` | Controller 是否允许直接改 runtime | `gpu-226:8188` 旧宿主机服务仍为 `false`；`gpu-226-gpu0-image_to_video` 与同卡回切候选 `gpu-226-gpu0-scail2` 均只可由 fleet helper 管理 |

2026-06-10 正式更新已验证的是 Worker Agent 新协议：7 个 `cloud-prod-comfy-agent-*` 均能携带 `agent_id`、GPU pool heartbeat 元数据并通过 relay `/ready`。这不表示 7 个底层 ComfyUI 都是容器；截至 2026-07-05，`cloud-prod-comfy-agent-1` 已停止作为回滚元数据，`gpu-226` 当前接单 runtime 是 `gpu-226-gpu0-image_to_video` LAN AIO。

Controller 已补 `runtime-plan` / `runtime-render` dry-run 入口与 runtime schema。`gpu-226` 已在 2026-07-05 通过 `gpu-226-gpu0-image_to_video` LAN AIO slot 回切承接 image_to_video，`gpu-226-gpu0-scail2` 保留同卡回切候选；旧 host-service `cloud_prod_worker_01` disabled/stopped，宿主机 `8188` 只作手工回滚元数据。`gpu-002` 已完成第一阶段生产 AIO 接管，GPU0 SCAIL-2 和 GPU1 PornMaster Flux2 edit 都必须在 fleet 配置中声明后才进入 fleet/operator 当前态管理；`gpu-177` 已通过 `scripts/lan_aio_fleet_prod_ops.py` 整机进入 `prod_enabled`。`gpu-252` GPU0/GPU1 当前分别由 `gpu-252-gpu0-i2i_pro` `8192` 与 `gpu-252-gpu1-i2i_pro` `8191` 承接 `i2i_pro,t2i-pornmaster-turbo,face_swap`，并固定各自 UUID；旧 GPU1 PornMaster/SCAIL-2/Wan22 槽位仍 maintenance-disabled。

LAN AIO 当前态、候选和缓存状态不再在本文维护静态 slot 表。先读 `ops/gpu_pool_controller/config/lan_aio_fleet_state.yml`，再跑 `python scripts/lan_aio_fleet_prod_ops.py list --include-disabled` 和 `status --include-disabled` 做 live 仲裁；若 state 与 live 冲突，停止 mutation 并先收口 drift。

每个 slot 必须先 `preflight`、准备目标镜像、预拉或加载镜像、`start-disabled` 验收 disabled heartbeat，最后才小窗口 `enable-aio`。`preflight` 的 legacy `/system_stats` 与 `/queue` 对刚重启的 ComfyUI 会短重试，只有连续失败才阻断切换；镜像门禁接受目标节点已配置 Docker insecure registry、目标镜像已存在，或本地主 runner 已有同 tag 镜像可通过 `docker save | ssh docker load` 流式加载。`preflight` 还会检查 host port 的 Docker published owner，只允许当前目标容器或声明的 `old_runtime_container` 占用；若同卡残留旧 prod/canary 容器占用端口，必须先人工确认队列、agent 与容器归属，再清理残留容器后重试。禁止一次性接管整台节点或跨节点批量启用。新增候选不由 Dashboard 直接写生产配置，先用 `scripts/lan_aio_fleet_prod_ops.py candidate-plan --node-id <node> --profile <profile> --replace-slot <current-slot>` 生成 YAML patch、渲染摘要和预检命令，审阅并提交 `lan_aio_prod_slots.yml` 后再由本地主 AI operator/CLI 执行后续管理。

`takeover` 默认 `--failure-policy auto_rollback`：`stop-old` 后若新候选启动、disabled heartbeat 或 enable gate 失败，helper 会 disable 新候选、停止新候选容器、启动旧 runtime 并恢复旧 agent control，operation 仍按失败记录并带 `recovery_status`。`pull-image` 会先尝试目标节点 `docker pull`；若节点未配置 HTTP registry 但 runner 本地已有目标镜像，会自动流式 `docker save | ssh docker load` 到目标节点，避免为了单个镜像重启 Docker daemon。`warm-cache` 会先尝试用 SSH 用户创建 workspace；若 retarget 后的 `/srv/allbot/runpod-runtime/...` 目录为 root-owned 导致 `mkdir` 权限不足，会临时使用目标镜像挂载 workspace parent 创建目录，再继续模型同步和 marker 写入。`start-disabled` 会在 compose up 前清理同名 `exited/created/dead/removing` 候选容器，并复查 host port 此刻必须没有 Docker owner；若同名容器正在运行、inspect 结果不匹配，或端口仍被任何容器占用，直接阻断，不误删。失败现场手工入口为 `recover --physical-slot <node>:gpuN --slot <slot-id> --prefer old|candidate`，只恢复一个物理 GPU；live/container/cache/control 巡检与恢复提交都只从本地主 AI operator/CLI 发起。

2026-06-18 `gpu-177` 进入整机 LAN AIO 接管，2026-06-20 已执行安全素材清理并退役旧本地链路：`cloud_prod_worker_02/03` control 固定 `disabled`，本地主 `cloud-prod-comfy-agent-2/3`、GPU 节点 `comfy0/comfy1`、旧 `/data/comfy` 模型/实例目录和旧镜像已删除；gpu-177 不再有本地旧链路回滚。2026-07-02 operator 校准后，GPU0 live/catalog/state 收敛为 `wan22_video_v2` 当前 slot，`gpu-177-gpu0-image_to_video` 为同卡回切候选；GPU1 曾切到 `image_to_video`，但真实任务多次触发 ComfyUI status 137 / restart，随后已回滚到 LTX，并把 `gpu-177-gpu1-image_to_video` 标为 `blocked_oom_32gb`。同日 GPU1 曾短暂切到 `gpu-177-gpu1-scail2`，验证 SCAIL-2 容器 healthy 与 cache ready 后，又按明确操作请求切回 `gpu-177-gpu1-ltx_video` 继续接 LTX 任务；`gpu-177-gpu1-scail2` 现在是同卡候选。2026-07-01 正确目标 `gpu-177-gpu1-ltx_video` 的 Wan22 takeover 曾成功，但第一笔真实 `wan22_video_v2` 任务在 RTX 5090 32GB 上 OOM kill ComfyUI（status 137），随后已恢复；`gpu-177-gpu1-wan22_video_v2` 现在也是 `blocked_oom_32gb` / `retargetable=false`，不作为 AI operator/CLI takeover 候选。SCAIL-2 profile catalog 仍偏向 48GB 容量，177 GPU1 是 32GB，未来若再切 SCAIL-2 要重点观察 status 137/OOM。

2026-06-27 新增 PornMaster Flux2 single/multiple image-edit profile：workflow API 文件同步在 `workers/comfy_agent/workflows/` 与 `remote_workers/comfy_agent/workflows/`，task type 为 `pornmaster_flux2_single_edit` / `pornmaster_flux2_multi_edit`，运行时镜像入口为 `remote_workers/docker/runpod_profiles/pornmaster_flux2_edit/Dockerfile`。本地主服务器已使用 `192.168.1.115:5000/allbot/comfy-runpod-pornmaster-flux2-edit:20260628-pornmaster-flux2-edit-cu128-smallvae1`。当前正式 LAN 接单 fleet slot 为 `gpu-002-gpu1-pornmaster_flux2_edit`；GPU252 GPU1 已于 2026-07-17 切为 i2i_pro，旧 PornMaster slot 不再接单。cloud-test 专项验证仍可用 `scripts/lan_pornmaster_flux2_edit_aio_test.sh`。

2026-07-12 gpu-226 GPU0 已准备不启用的 `gpu-226-gpu0-pornmaster_flux2_edit_bf16` cache-only slot。fleet helper 已把 PornMaster LAN 镜像加载到 gpu-226，并把 `pornmaster_flux2_edit_bf16/2026-07-12/manifest.json` 的 V4 turbo BF16 UNet、Qwen fp8 text encoder 与 small-decoder VAE同步到独立 PornMaster workspace；marker 为 ready。slot 的 `SUPPORTED_TASK_TYPES` 现为 `pornmaster_flux2_edit_bf16,pornmaster_flux2_multi_edit_bf16`，分别复用 single/multiple workflow并切换 BF16 UNet，因而不会抢现有 fp8 自由P图 v2 的 single/multi 队列。slot 当前仍为停用回切候选；任何启动、takeover 或 canary 必须另开明确窗口。

同日 14:10 Asia/Shanghai 已执行获批 takeover：在途 `image_to_video` 任务自然结束后，BF16 容器通过 health 与 disabled heartbeat gate 并启用；当前容器为 `allbot-lan-aio-gpu-226-gpu0-pornmaster_flux2_edit_bf16-prod`，host `8190`，唯一队列类型 `pornmaster_flux2_edit_bf16`。第一次接管因 heartbeat gate 错把 slot profile id 当 runtime profile 而自动回滚，修复门禁并补回归测试后第二次成功。未运行生成 canary，`image_to_video` 保留为同卡 rollback candidate。

2026-06-18 `gpu-252-gpu1-wan22_video_v2` 已替换 `cloud_prod_worker_05`：AIO agent `lan_aio_prod_gpu252_gpu1_wan22_video_v2_01` 监听 host `8191`，只接 `wan22_video_v2`。2026-06-20 交叉换槽确认 Xid 119/154 跟随实体卡 `GPU-33de1af6-ca27-7eeb-ae46-6a9f4f89523e`，该卡随后拆除返修；2026-07-04 回装后 host index 漂移为 GPU0 / PCI `00000000:01:00.0`，只允许用稳定 UUID 绑定。返修卡先通过短 CUDA smoke、SCAIL-2 preflight、镜像确认/拉取、warm-cache、start-disabled、`/system_stats`、`/object_info` 模型枚举、direct canary 与 `enable-aio`，但真实 SCAIL-2 face-swap workload 随后复现 Xid 119/154 / GPU Reset Required，ComfyUI 返回 CUDA unknown error，容器无法正常 stop/kill；主机 2026-07-04 19:12 Asia/Shanghai 重启后，隔离 CUDA smoke 触碰约 20.5 GiB 显存并计算约 120 秒未见新 Xid/NVRM。该结果只说明重启后普通 CUDA 路径可用，不等于生产 SCAIL-2 cleared。随后该卡切到低负载 `gpu-252-gpu1-pornmaster_flux2_edit`，完成模型缓存、disabled heartbeat、节点/模型枚举和多笔正式 `pornmaster_flux2_single_edit` 任务且未见新 Xid/NVRM；`gpu-252-gpu1-scail2` 和 `gpu-252-gpu1-wan22_video_v2` 仍保持 maintenance disabled，RunPod 和其它 SCAIL-2 容量继续兜底。

2026-06-20 `gpu-252-gpu0-img2img_lora` 在拆除故障卡后恢复 LAN AIO：健康卡 `GPU-09b7ea85-23df-a9b8-19d9-703534e47666` 最初枚举为 GPU0，新 AIO agent 为 `lan_aio_prod_gpu252_gpu0_img2img_lora_01`，容器 `allbot-lan-aio-gpu-252-gpu0-img2img_lora-prod` 最初监听 host `8190`，按 `img2img_lora` profile 承接 `img2img` 与 `img2img_lora`。2026-06-28 起 GPU0 曾切到 `gpu-252-gpu0-pornmaster_flux2_edit`，2026-07-03 按 fleet 单卡 takeover 切到 `gpu-252-gpu0-i2i_pro` 并改用 host `8192`；2026-07-04 返修卡回装导致 host index 漂移后，所有 GPU0 slot 都已固定健康 UUID `GPU-09b7ea85-23df-a9b8-19d9-703534e47666`。当前 `gpu-252-gpu0-i2i_pro` 接 `i2i_pro,t2i-pornmaster-turbo,face_swap`；`img2img_lora`、`image_to_video`、PornMaster Flux2 edit 与 SCAIL-2 只保留为同卡回切候选/回滚目标，不计入当前容量。旧 `comfy0` 和本地主 `cloud-prod-comfy-agent-4` 已停止保留为回滚基线，不应再与 AIO 同时运行或 enabled。

## 5. GPU 节点明细

### 5.1 `allbot-gpu-226` / `192.168.1.226`

硬件与系统：

- Ubuntu 24.04.4 LTS，kernel `6.17.0-20-generic`
- Ryzen 9 9950X，16C/32T
- 内存 60GiB
- 1 x RTX 5090 32G，driver `590.48.01`
- Docker 29.1.3，Compose 2.37.1

容器：

- `allbot-lan-aio-gpu-226-gpu0-pornmaster_flux2_edit_bf16-prod`：当前正式 AIO，GPU0，host `8190`，只接 `pornmaster_flux2_edit_bf16`
- `allbot-lan-aio-gpu-226-gpu0-image_to_video-prod`：同卡回滚候选，恢复后接 `image_to_video` / `video_insert` / `video_edit`
- `allbot-lan-aio-gpu-226-gpu0-scail2-prod`：同卡回切候选，host `8190`，接 SCAIL-2 四任务
- `portainer_agent`
- `dcgm_exporter`
- `monitor_node_exporter`

ComfyUI：

- 当前接单 runtime 是 Docker LAN AIO `allbot-lan-aio-gpu-226-gpu0-pornmaster_flux2_edit_bf16-prod`，host `8190`
- 旧宿主机进程不是 Docker Comfy 容器，当前 systemd service 仍 active/idle 且只保留为回滚元数据
- 旧端口：`8188`
- 进程 cwd：`/home/ubantu/comfyui`
- 当前服务：系统级 `/etc/systemd/system/comfyui.service`
- 当前启动命令：`/home/ubantu/miniforge3/envs/comfyui/bin/python main.py --listen 0.0.0.0`
- 模型目录：`/home/ubantu/comfyui/models`，约 `325G`
- 旧对应 worker：`cloud-prod-comfy-agent-1` / `cloud_prod_worker_01`，当前 stopped + Central disabled

2026-07-04 SCAIL-2 LAN AIO 接管与 xformers sm_120 镜像（现为同卡回切候选）：

- 候选 agent：`lan_aio_prod_gpu226_gpu0_scail2_01`
- 候选容器：`allbot-lan-aio-gpu-226-gpu0-scail2-prod`
- 端口：host `8190` -> container `8188`
- 工作区：`/home/ubantu/allbot-runpod-runtime/slots/gpu-226-gpu0/profiles/scail2/workspace`
- 模型 manifest：`scail2/2026-06-17-test/manifest.json`，cache marker 已 ready
- 镜像：`192.168.1.115:5000/allbot/comfy-runpod-scail2:20260704-sm120-xformers-pr1262`，保留 xformers，使用源码编译的 sm_120 attention kernel 适配 RTX 5090
- 切换验证：fleet `preflight`、镜像加载、warm-cache、drain/wait-idle、stop-old、start-disabled、disabled heartbeat、enable-aio 与 helper restart 均通过。旧 xformers wheel 在真实任务中触发 `memory_efficient_attention_forward` NotImplementedError 后，已改为新镜像而非关闭 xformers；首笔真实 `scail2_video_replacement` 任务 `e623a3a9-65f0-488d-917f-efc9b429781f` 完成并上传，日志显示 `Using xformers attention`，未复现 NotImplementedError/OOM。RTX 5090 32G 仍低于 profile catalog 的 48G 偏好容量，长队列期间继续观察显存峰值和 status 137。

2026-07-02 image_to_video LAN AIO 接管；2026-07-05 回切为当前态：

- 当前 agent：`lan_aio_prod_gpu226_gpu0_image_to_video_01`
- 当前容器：`allbot-lan-aio-gpu-226-gpu0-image_to_video-prod`
- 端口：host `8190` -> container `8188`
- 工作区：`/home/ubantu/allbot-runpod-runtime/slots/gpu-226-gpu0/profiles/image_to_video/workspace`
- 模型 manifest：`image_to_video/2026-06-13-test/manifest.json`，cache marker 已 ready
- 切换验证：2026-07-02 disabled heartbeat、Comfy `/system_stats`、队列、RIFE 热缓存、5s canary、Web result/last_frame 和后续真实队列任务均通过；2026-07-05 从 SCAIL-2 回切时，fleet `preflight`、镜像存在、warm-cache、drain/wait-idle、stop-old、start-disabled、RIFE 热缓存复制、disabled heartbeat 与 enable-aio 均通过，切后容器 healthy 且 `/queue` 已接受真实 image_to_video prompt。RTX 5090 32G 仍需在长队列期间持续观察显存峰值。

2026-06-15 LTX 补齐：

- 已安装 `ComfyLiterals`，使 `LTX 2.3 I2V 6.1.json` 所需的 `Float` 节点可用。
- 已补齐 `models/diffusion_models/LTX 2.3/ltx2310eros_v1.safetensors`，与当前 LTX workflow 主模型节点匹配。
- `cloud-prod-comfy-agent-1` 在原有任务类型基础上追加 `ltx_video`，用于补充 LTX 产能；不要改成只支持 `ltx_video`，否则会移走 worker 01 原有 face/i2i/t2i 能力。
- `ubantu` 用户级 `comfyui.service` 也存在但已停止，避免与系统级 service 抢占 `8188`；如需统一为 `--enable-manager` 口径，需要具备系统级 service 的 sudo 操作窗口。

2026-06-18 LTX LAN AIO 镜像：

- 已构建并推送 LTX 专用最小 AIO 镜像 `192.168.1.115:5000/allbot/comfy-runpod-ltx-video:20260618-ltx-min-cu128-sageattn1`；镜像只面向 `LTX 2.3 I2V 6.1.json`，baked `sageattention==1.0.6`，不 baked 模型权重，模型仍同步 `allbot-model-cache/ltx_video/2026-06-10/manifest.json`。
- `gpu-177-gpu1-ltx_video` 使用 LTX 最小 AIO 镜像 `192.168.1.115:5000/allbot/comfy-runpod-ltx-video:20260618-ltx-min-cu128-sageattn1`；它只面向 `LTX 2.3 I2V 6.1.json`，保持 workflow `sage_attention=auto`，不 baked 模型权重，模型仍同步 `allbot-model-cache/ltx_video/2026-06-10/manifest.json`。

2026-06-22 LTX 10Eros v1.2 canary 模型：

- `gpu-177-gpu1-ltx_video` 的 AIO `/workspace` 挂载来自宿主机 `/srv/allbot/runpod-runtime/slots/gpu-177-gpu1/profiles/ltx_video/workspace`，模型应落在容器内 `/workspace/ComfyUI/models/diffusion_models/LTX 2.3/`。
- 10Eros v1.2 canary workflow 期望模型文件 `10Eros_v1.2_fp8mixed_learned.safetensors`。该模型仍不应 baked 到镜像；云端 R2 `allbot-model-cache/ltx_video/2026-06-10/manifest.json` 当前为 v1.2-only，正式 RunPod 不再依赖旧 v1 回退。AIO 重建应从目标 model-cache 恢复 v1.2 权重，而不是依赖运行中容器的临时文件。

运维边界：

- 不要对 `comfy0/comfy1` 执行 Docker 操作；本机没有这类 Comfy 容器。
- `gpu-226-gpu0-image_to_video` 的日常启停/重启只走 `scripts/lan_aio_fleet_prod_ops.py` 或 Dashboard LAN AIO worker 卡片；`gpu-226-gpu0-scail2` 只作为同卡回切候选处理。
- 旧 `8188` 宿主机 ComfyUI 如需回滚，先确认 `cloud-prod-comfy-agent-1`、Central control 和 systemd sudo 维护窗口；不要用 AIO helper 对 systemd 服务做 Docker 操作。

### 5.2 `allbot-gpu-177` / `192.168.1.177`

硬件与系统：

- Ubuntu 24.04.4 LTS，kernel `6.17.0-29-generic`
- Ryzen 7 9700X，8C/16T
- 内存 60GiB
- 2 x RTX 5090 32G，driver `580.159.03`
- Docker 29.1.3，Compose 2.37.1
- 2026-06-20 清理后根分区 `/` 可用约 `680G`，使用率约 22%；外置盘需操作前重新采集

容器：

- `allbot-lan-aio-gpu-177-gpu0-wan22_video_v2-prod`：正式 AIO，GPU0，host `8190`，live profile `wan22_video_v2`
- `allbot-lan-aio-gpu-177-gpu0-image_to_video-prod`：GPU0 stopped rollback candidate，host `8190`
- `allbot-lan-aio-gpu-177-gpu1-ltx_video-prod`：正式 AIO，GPU1，host `8191`，live profile `ltx_video`
- `allbot-lan-aio-gpu-177-gpu1-scail2-prod`：GPU1 stopped rollback candidate，host `8191`
- `allbot-lan-aio-gpu-177-gpu1-image_to_video-prod`：GPU1 stopped / `blocked_oom_32gb`，host `8191`
- `allbot-lan-aio-gpu-177-gpu1-wan22_video_v2-prod`：`blocked_oom_32gb` 停用配置，GPU1，host `8191`；2026-07-01 首单 OOM 后不再作为 takeover 候选
- 旧 `comfy0/comfy1`：2026-06-20 已删除，原端口 `8188/8189` 不再提供本地回滚
- `portainer_agent`
- `dcgm_exporter`
- `monitor_node_exporter`

ComfyUI 实例：

| 容器 | GPU | Host 端口 | 容器端口 | 模型目录 | 独立目录 | 对应 worker |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `allbot-lan-aio-gpu-177-gpu0-wan22_video_v2-prod` | GPU `0` | `8190` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 Wan22 v2 manifest 同步/挂载） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu177_gpu0_wan22_video_v2_01` |
| `allbot-lan-aio-gpu-177-gpu0-image_to_video-prod` | GPU `0` | `8190` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 image_to_video manifest 同步/挂载） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu177_gpu0_image_to_video_01`，stopped rollback |
| `allbot-lan-aio-gpu-177-gpu1-image_to_video-prod` | GPU `1` | `8191` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 image_to_video manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu177_gpu1_image_to_video_01`，stopped / blocked_oom_32gb |
| `allbot-lan-aio-gpu-177-gpu1-ltx_video-prod` | GPU `1` | `8191` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 LTX manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu177_gpu1_ltx_video_01` |
| `allbot-lan-aio-gpu-177-gpu1-scail2-prod` | GPU `1` | `8191` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 SCAIL-2 manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu177_gpu1_scail2_01`，stopped rollback |
| `allbot-lan-aio-gpu-177-gpu1-wan22_video_v2-prod` | GPU `1` | `8191` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 Wan22 v2 manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu177_gpu1_wan22_video_v2_01`，blocked |

旧 `/data/comfy/models`、`/data/comfy/inst0`、`/data/comfy/inst1` 已在 2026-06-20 删除；配置中的旧路径只保留为历史映射，不是可用运行目录。

旧回滚基线退役记录：

- `cloud_prod_worker_02/03`：Central control 已置为 `disabled`。
- `cloud-prod-comfy-agent-2/3`：本地主服务器容器已删除。
- `comfy0/comfy1`、`yanwk/comfyui-boot:cu130-slim`、旧 LTX 一次性 tag 和 `/data/comfy`：已从 `allbot-gpu-177` 删除。

运维边界：

- 日常先读 `ops/gpu_pool_controller/config/lan_aio_fleet_state.yml`，再跑 `python scripts/lan_aio_fleet_prod_ops.py status --include-disabled` 仲裁当前态；不要只凭本文容器表判断哪张卡当前接单。
- 当前态、回切候选、缓存 marker 与 blocked 原因由 `lan_aio_fleet_state.yml` 维护；2026-07-02 校准后 GPU0 当前为 `wan22_video_v2`，GPU1 当前为 `ltx_video`，SCAIL-2 是同卡回切候选，GPU1 `image_to_video` 与 `wan22_video_v2` 都因 32GB status 137 标为 blocked。
- 日常只通过 `scripts/lan_aio_fleet_prod_ops.py` 操作目标 slot；旧 `comfy0/comfy1` 和 `cloud-prod-comfy-agent-2/3` 不再存在，不得按旧回滚链路操作。
- LAN AIO compose 渲染 `restart: unless-stopped`，并由 entrypoint 监管 ComfyUI、relay 与 agent；任一关键进程退出时容器会退出，让 Docker restart policy 拉起干净进程树，避免“agent 心跳仍在但本地 ComfyUI 已死”的半活状态。
- 不要对 gpu-177 执行 `rollback --slot ... --execute`；旧 runtime 已删除，恢复只能走 AIO restart/recreate 或外部容量兜底。
- 模型下载、Docker pull/build、临时输出前仍要先检查磁盘。

### 5.3 `allbot-gpu-252` / `192.168.1.252`

硬件与系统：

- Ubuntu 24.04.3 LTS，kernel `6.17.0-29-generic`
- Ryzen 7 9700X，8C/16T
- 内存 60GiB
- 2 x RTX 4090 48G visible，driver `580.159.03`；生产 `8192` 固定绑定健康 UUID `GPU-09b7ea85-23df-a9b8-19d9-703534e47666`，返修 UUID `GPU-33de1af6-ca27-7eeb-ae46-6a9f4f89523e` 暂不接单
- Docker 29.4.0，Compose v5.1.2
- 2026-06-18 根分区 `/` 可用约 `647G`；外置盘需操作前重新采集

容器：

- `comfy0`：旧回滚基线，停止保留，原端口 `8188`
- `allbot-lan-aio-gpu-252-gpu0-i2i_pro-prod`：当前正式 AIO，host `8192`，固定健康 UUID `GPU-09b7ea85-23df-a9b8-19d9-703534e47666`，接 `i2i_pro/t2i-pornmaster-turbo/face_swap`
- `allbot-lan-aio-gpu-252-gpu1-i2i_pro-prod`：RMA replacement 当前正式 AIO，host `8191`，固定 UUID `GPU-8153a439-e3f6-8922-039d-dc13e97da6d7`，接 `i2i_pro/t2i-pornmaster-turbo/face_swap`
- `allbot-lan-aio-gpu-252-gpu0-img2img_lora-prod`：同卡回切候选，host `8192`，接 `img2img/img2img_lora`
- `allbot-lan-aio-gpu-252-gpu0-image_to_video-prod`：同卡回切候选，host `8192`，接 `image_to_video/video_insert/video_edit`
- `allbot-lan-aio-gpu-252-gpu0-pornmaster_flux2_edit-prod`：同卡回切候选，host `8192`，接 `pornmaster_flux2_single_edit/pornmaster_flux2_multi_edit`
- `allbot-lan-aio-gpu-252-gpu0-scail2-prod`：同卡回切候选，host `8192`，接 SCAIL-2 四任务
- `allbot-lan-aio-gpu-252-gpu0-pornmaster-flux2-edit-test`：临时 cloud-test PornMaster Flux2 AIO，仅在 `scripts/lan_pornmaster_flux2_edit_aio_test.sh start --execute` 窗口存在；不得与正式 prod 容器同时占用 GPU0/8192
- `allbot-lan-aio-gpu-252-gpu1-wan22_video_v2-prod`：maintenance disabled，host `8191`，固定返修 UUID `GPU-33de1af6-ca27-7eeb-ae46-6a9f4f89523e`，只保留配置和修复后验收入口
- `allbot-lan-aio-gpu-252-gpu1-scail2-prod`：maintenance disabled，host `8191`，固定返修 UUID `GPU-33de1af6-ca27-7eeb-ae46-6a9f4f89523e`，接 SCAIL-2 四任务；cache / disabled heartbeat / direct canary 曾通过，但真实 workload 复现 Xid 119/154，当前容器 exited 且不接单
- `comfy1`：旧回滚基线，停止保留，原端口 `8189`
- `dcgm_exporter`
- `node_exporter`

ComfyUI 实例：

| 容器 | GPU | Host 端口 | 容器端口 | 模型目录 | 独立目录 | 对应 worker |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `comfy0` | GPU `0`（历史口径） | `8188` | `8188` | `/home/user/APP/data/models` | `/home/user/APP/data/inst0/{input,output,temp,custom_nodes,workflows}` | 旧 `cloud-prod-comfy-agent-4`，stopped rollback |
| `allbot-lan-aio-gpu-252-gpu0-i2i_pro-prod` | Docker device UUID `GPU-09b7ea85-23df-a9b8-19d9-703534e47666` | `8192` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 i2i_pro manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu252_gpu0_i2i_pro_01` |
| `allbot-lan-aio-gpu-252-gpu1-i2i_pro-prod` | Docker device UUID `GPU-8153a439-e3f6-8922-039d-dc13e97da6d7` | `8191` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 i2i_pro manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu252_gpu1_i2i_pro_01` |
| `allbot-lan-aio-gpu-252-gpu0-img2img_lora-prod` | Docker device UUID `GPU-09b7ea85-23df-a9b8-19d9-703534e47666` | `8192` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 img2img_lora manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu252_gpu0_img2img_lora_01`，stopped/候选 |
| `allbot-lan-aio-gpu-252-gpu0-image_to_video-prod` | Docker device UUID `GPU-09b7ea85-23df-a9b8-19d9-703534e47666` | `8192` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 image_to_video manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu252_gpu0_image_to_video_01`，stopped/候选 |
| `allbot-lan-aio-gpu-252-gpu0-pornmaster_flux2_edit-prod` | Docker device UUID `GPU-09b7ea85-23df-a9b8-19d9-703534e47666` | `8192` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 PornMaster Flux2 manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu252_gpu0_pornmaster_flux2_edit_01`，stopped/候选 |
| `allbot-lan-aio-gpu-252-gpu0-scail2-prod` | Docker device UUID `GPU-09b7ea85-23df-a9b8-19d9-703534e47666` | `8192` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 SCAIL-2 manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu252_gpu0_scail2_01`，stopped/候选 |
| `allbot-lan-aio-gpu-252-gpu0-pornmaster-flux2-edit-test` | Docker device `0` | `8192` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 PornMaster Flux2 manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_test_gpu252_gpu0_pornmaster_flux2_edit_01`，临时测试 |
| `allbot-lan-aio-gpu-252-gpu1-wan22_video_v2-prod` | Docker device UUID `GPU-33de1af6-ca27-7eeb-ae46-6a9f4f89523e`（maintenance disabled） | `8191` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 Wan22 v2 manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu252_gpu1_wan22_video_v2_01` |
| `allbot-lan-aio-gpu-252-gpu1-scail2-prod` | Docker device UUID `GPU-33de1af6-ca27-7eeb-ae46-6a9f4f89523e`（maintenance disabled） | `8191` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 SCAIL-2 manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu252_gpu1_scail2_01`，disabled |
| `comfy1` | GPU `1`（历史口径） | `8189` | `8189` | `/home/user/APP/data/models` | `/home/user/APP/data/inst1/{input,output,temp,custom_nodes,workflows}` | 旧 `cloud-prod-comfy-agent-5`，stopped rollback |

共享模型目录：`/home/user/APP/data/models`，约 `121G`。

运行备注：

- `comfy0` CLI 包含 `--fp8_e4m3fn-text-enc`。
- `comfy0`/旧 `comfy1` 的模型目录共享，实例目录分离。
- `gpu-252-gpu0-i2i_pro` 正式 AIO 使用 LAN registry 镜像 `192.168.1.115:5000/allbot/comfy-runpod-i2i-pro:20260614-i2ipro-b75c6a9-cu128-min5-ssh`，模型从 `allbot-model-cache/i2i_pro/2026-06-14-test/manifest.json` 同步；`gpu_device_id` 固定健康 UUID，禁止回退到易漂移 host index。
- `gpu-252-gpu1-i2i_pro` 是 RMA replacement 卡的正式生产槽位，固定 UUID `GPU-8153a439-e3f6-8922-039d-dc13e97da6d7`、端口 `8191` 与 LAN 镜像 `192.168.1.115:5000/allbot/comfy-runpod-i2i-pro:v2-47c1219f-i2ipro`。2026-07-17 已完成 canonical image、preflight、六文件 warm-cache、start-disabled、health/heartbeat、节点/模型枚举和 `enable-aio`；Central enabled、容器 healthy，并在真实正式负载下运行且无新 Xid。
- `gpu-252-gpu0-img2img_lora`、`gpu-252-gpu0-image_to_video`、`gpu-252-gpu0-pornmaster_flux2_edit` 与 `gpu-252-gpu0-scail2` 当前只作为回切候选，切换前必须由 AI operator/CLI 明确指定同服务器替换目标并先 drain 当前 `i2i_pro`。
- PornMaster Flux2 测试 AIO 使用同一 PornMaster Flux2 镜像和 manifest；它只用于 cloud-test，启动前必须 drain/disable 目标正式 GPU0 产能，结束后必须 `restore --execute` 恢复正式产能。
- `gpu-252-gpu1-pornmaster_flux2_edit` 正式 AIO 使用 LAN registry 镜像 `192.168.1.115:5000/allbot/comfy-runpod-pornmaster-flux2-edit:20260628-pornmaster-flux2-edit-cu128-smallvae1`，模型从 `allbot-model-cache/pornmaster_flux2_edit/2026-06-27/manifest.json` 同步；2026-07-04 通过 preflight、warm-cache、disabled heartbeat、`/system_stats`、`/object_info` 节点/模型枚举后 enable-aio，并连续完成正式 `pornmaster_flux2_single_edit` 任务，未见新 Xid/NVRM。该结论只适用于 PornMaster Flux2 edit。
- `gpu-252-gpu1-wan22_video_v2` AIO 使用 LAN registry 镜像 `192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd`，该 tag 已 baked `rife49.pth` 两处缓存；启动参数包含 `--disable-dynamic-vram`，模型从 `allbot-model-cache/wan22_video_v2/2026-06-13-test/manifest.json` 同步；返修卡已重新可见但保持 disabled，不计入可用容量。
- `gpu-252-gpu1-scail2` AIO 使用 LAN registry 镜像 `192.168.1.115:5000/allbot/comfy-runpod-scail2:20260617-scail2-cu128-a492b2b-proddeps1`，模型从 `allbot-model-cache/scail2/2026-06-17-test/manifest.json` 同步；cache marker、disabled heartbeat、`/system_stats`、`/queue`、`/object_info` 与 direct canary 曾通过，但真实 SCAIL-2 face-swap workload 复现 Xid 119/154，当前必须保持 disabled/exited，不得只凭短 CUDA smoke 通过而 enable。
- `gpu-252-gpu1-wan22_video_v2` 同样依赖 `FL_RIFE` 后处理；slot 配置仍可从宿主机旧 `inst1` 路径 `/home/user/APP/data/inst1/custom_nodes/ComfyUI_Fill-Nodes/nodes/cache/rife_models/rife49.pth` 预置到 AIO 内两处 RIFE 缓存路径，作为旧镜像回滚/热缓存兜底，避免运行时访问 HuggingFace。
- 目标用户无免密 sudo 时，镜像可由本地主服务器 `docker save ... | ssh allbot-gpu-252 docker load` 预置，避免为了配置 insecure registry 重启整台 Docker daemon。

运维边界：

- 只处理当前 `img2img/img2img_lora` 相关问题时，优先定位 `allbot-lan-aio-gpu-252-gpu0-img2img_lora-prod` 与 `lan_aio_prod_gpu252_gpu0_img2img_lora_01`；旧 `comfy0` / `cloud-prod-comfy-agent-4` 只用于更早的 legacy 回滚。
- 只处理 `pornmaster_flux2_single_edit/pornmaster_flux2_multi_edit` 正式接单时，当前定位 gpu-002 GPU1 的 PornMaster AIO；gpu-252 两张卡当前都运行 i2i_pro，历史 PornMaster slot 不应启用。
- 只处理 `wan22_video_v2` 相关问题时，当前优先定位 RunPod `runpod_prod_wan22_video_v2_manual_01`；`allbot-lan-aio-gpu-252-gpu1-wan22_video_v2-prod` 只用于重新安装健康 GPU 后的 disabled 验收，旧 `comfy1` / `cloud-prod-comfy-agent-5` 只用于回滚。普通 `image_to_video` 和 `video_edit` 不应路由到该 AIO。
- 排查 `gpu-252` GPU1 SCAIL-2 时，只定位 `gpu-252-gpu1-scail2` / `allbot-lan-aio-gpu-252-gpu1-scail2-prod` / `lan_aio_prod_gpu252_gpu1_scail2_01`，并保持 GPU0 `8192` i2i_pro 不动；解除隔离前必须有 workload-specific burn-in 或明确厂商/驱动处理结论，且重新完成 disabled heartbeat、SCAIL-2 canary 和真实任务观察。
- 修改共享模型目录会同时影响两个 worker；修改 `inst0/inst1` 下 custom_nodes/workflows/input/output/temp 只影响对应容器。

### 5.4 `allbot-gpu-002` / `192.168.1.2`

硬件与系统：

- Ubuntu 24.04.4 LTS，kernel `6.8.0-124-generic`
- Ryzen 7 9700X，8C/16T
- 内存 60GiB
- 2 x RTX 4090 48G，driver `580.159.03`
- Docker 29.1.3，Compose 2.40.3
- 2026-06-18 根分区 `/` 可用约 `442G`

容器：

- `allbot-lan-aio-gpu-002-gpu0-scail2-prod`：正式 SCAIL-2 AIO，GPU0，host `8190`
- `allbot-lan-aio-gpu-002-gpu1-pornmaster-flux2-edit-prod`：正式 PornMaster Flux2 edit AIO，GPU1，host `8191`
- `allbot-lan-aio-gpu-002-gpu1-image_to_video-canary`：image_to_video 回切候选，GPU1，host `8191`，stopped rollback
- `comfy0` / `comfy1`：旧 `yanwk/comfyui-boot:cu128-slim`，stopped rollback
- `dcgm_exporter`
- `node_exporter`

ComfyUI 实例：

| 容器 | GPU | Host 端口 | 容器端口 | 模型目录 | 独立目录 | 对应 worker |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `allbot-lan-aio-gpu-002-gpu0-scail2-prod` | Docker device `0` | `8190` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 SCAIL-2 manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu002_gpu0_scail2_01` |
| `allbot-lan-aio-gpu-002-gpu1-pornmaster-flux2-edit-prod` | Docker device `1` | `8191` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 PornMaster Flux2 manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu002_gpu1_pornmaster_flux2_edit_01` |
| `allbot-lan-aio-gpu-002-gpu1-image_to_video-canary` | Docker device `1` | `8191` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 image_to_video manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu002_gpu1_image_to_video_01`，stopped rollback |
| `comfy0` | GPU `0` | `8188` | `8188` | `/data/comfy/models` | `/data/comfy/inst0/{input,output,temp,custom_nodes,workflows}` | 旧 `cloud-prod-comfy-agent-6`，stopped rollback |
| `comfy1` | GPU `1` | `8189` | `8188` | `/data/comfy/models` | `/data/comfy/inst1/{input,output,temp,custom_nodes,workflows}` | 旧 `cloud-prod-comfy-agent-7`，stopped rollback |

共享模型目录：`/data/comfy/models`，约 `85G`。

运维边界：

- gpu-002 GPU0 当前由 fleet 配置 `gpu-002-gpu0-scail2` 纳入 fleet/operator 管理，`scripts/lan_scail2_aio_prod.sh` 只保留 SCAIL-2 低层启动/重建/回滚入口；GPU1 当前由 fleet 配置 `gpu-002-gpu1-pornmaster_flux2_edit` 作为当前可操作 AIO slot 展示，`gpu-002-gpu1-image_to_video` 是同卡回切候选。
- `cloud_prod_worker_07` 保持 disabled；`lan_aio_prod_gpu002_gpu1_image_to_video_01` 只在回切窗口启用，不应与 PornMaster AIO 同时 enabled 或同卡占用显存。
- 可只重启目标 AIO/Comfy 容器；不要因为一个容器异常而重启整台 GPU 节点。

LAN RunPod 化一体容器试点：

- 第一轮只允许 slot0 / `img2img_lora`，临时 agent 为 `lan_aio_test_gpu002_gpu0_img2img_lora_01`。
- canary 宿主机端口固定 `8190:8188`，不得占用或替换原 `8188` 的 `comfy0`。
- runtime root 固定 `/srv/allbot/runpod-runtime`；slot0 workspace 为 `/srv/allbot/runpod-runtime/slots/gpu-002-gpu0/profiles/img2img_lora/workspace`。
- 容器内 ComfyUI 走 `127.0.0.1:8188`，remote relay 走 `127.0.0.1:8013`，Central 必须使用 `https://worker-central-test.aivison.it.com`。
- 模型同步只写 `/workspace/ComfyUI/models`，模型源为本地主服务器 LAN cache `http://192.168.1.115:9010/allbot-model-cache`。
- 受控入口为 `scripts/lan_runpod_aio_canary.sh`；默认 dry-run，`--execute` 才会复制 compose/env 到 `allbot-gpu-002` 或修改 agent control。
- heartbeat-only 阶段必须保持临时 agent control 为 `disabled`。真实 canary 窗口才临时 disable `cloud_worker_test_06` 并 enable 临时 agent；结束后恢复 `cloud_worker_test_06`、disable 临时 agent、停止 canary 容器。

Dashboard 不再提供生产 `LAN AIO 管理` slot 面板，也不再暴露 profile/slot 列表、候选切换、恢复、巡检或 warm-cache API。Dashboard 只从 `/api/system/workers` 展示 LAN AIO worker 状态和当前任务，并在 Worker 卡片保留 `暂停/开启/重启` 基础操作；后端只允许 `disable-aio|enable-aio|restart-aio`。slot/candidate 管理、`render`、`preflight`、`pull-image`、`warm-cache`、`takeover`、`recover`、retarget 与 live/container/cache/control 巡检都回到本地主 AI operator/CLI，通过 `scripts/lan_aio_fleet_prod_ops.py` 和 fleet state/catalog 执行。

生产灰度入口为 `scripts/lan_runpod_aio_prod_canary.sh`，只允许 gpu-002 固定映射：slot0 `cloud_prod_worker_06 -> lan_aio_prod_gpu002_gpu0_img2img_lora_01`，端口 `8190`；slot1 `cloud_prod_worker_07 -> lan_aio_prod_gpu002_gpu1_image_to_video_01`，端口 `8191`。生产灰度必须使用 `--environment cloud-prod` 渲染出的 compose，写入 `user-data-prod`，并在启动前确认 compose 不含 `cloud-test` / `user-data-test`。首次拉取 LAN mirror 前需要维护窗口配置 Docker insecure registry `192.168.1.115:5000`，该操作会重启 Docker，必须先将 `cloud_prod_worker_06/07` 置为 `draining` 并等 `8188/8189` 队列清空。heartbeat-only 成功标准不是容器健康，而是 Central 能看到临时 agent 在 `disabled` control 下无 `current_task_type` 且 status 非 `running`，并携带 `node_id=gpu-002`、`provider=lan_ssh`、`runtime_profile`、`pool_managed=true`；Central 若残留旧 `current_task_id` 但 worker 已 `idle` 且无 `current_task_type`，不视为正在运行。缺任一项都应视为镜像或 remote_workers bundle 不可控，不能进入 `enable-canary`。helper 只使用 profile 镜像中烘焙的 `remote_workers` revision，并拒绝宿主机源码挂载；模型仍按 manifest 同步到 `/workspace/ComfyUI/models`，slot1 `image_to_video` 启动后还必须从宿主机 `/data/comfy/inst1/custom_nodes/ComfyUI_Fill-Nodes/nodes/cache/rife_models/rife49.pth`（或共享模型 fallback `/data/comfy/models/upscale_models/rife49.pth`）预置到 AIO 内 `ComfyUI_Fill-Nodes` 与 `ComfyUI-Frame-Interpolation` 两处 RIFE 缓存路径，不能在正式任务后处理阶段访问 HuggingFace。达到目标接单数后先 `drain-temp --execute`，再等任务终态并 `restore --execute`。

2026-06-16 已完成 slot1 生产灰度：`image_to_video`、`video_insert`、`video_edit` 均由临时 agent `lan_aio_prod_gpu002_gpu1_image_to_video_01` 接单并以 canonical `image_to_video` 执行成功。灰度结束后必须恢复 `cloud_prod_worker_07`，停止 AIO 容器，保留原 `comfy1` / `8189` 作为生产基线。

2026-06-16 已将 gpu-002 slot0/slot1 切到生产 AIO 接新单：`cloud_prod_worker_06/07` 先 drain 并等待自然空闲，再 disable legacy worker、enable `lan_aio_prod_gpu002_gpu0_img2img_lora_01` 与 `lan_aio_prod_gpu002_gpu1_image_to_video_01`。切换时原 `comfy0/comfy1` 容器继续运行在 `8188/8189`，本地主服务器 `cloud-prod-comfy-agent-6/7` 也继续保留，作为热回滚基线；AIO 观察到 slot0 多单成功、slot1 视频单成功后，已执行 `docker stop comfy0 comfy1` 与 `docker stop cloud-prod-comfy-agent-6 cloud-prod-comfy-agent-7` 释放资源，容器未删除。回滚顺序是先 `docker start comfy0 comfy1`，确认 `8188/8189` `/system_stats` 与 `/queue` 正常，再启动 `cloud-prod-comfy-agent-6/7`，最后用 helper `restore --slot slot0|slot1 --execute` 恢复 `cloud_prod_worker_06/07`。

SCAIL-2 正式 slot0 接管会牺牲原 slot0 `img2img_lora` AIO 产能；slot1 当前用于 PornMaster Flux2 edit AIO。fleet/operator 的事实源是 fleet slot `gpu-002-gpu0-scail2`；SCAIL-2 低层维护入口仍是 `scripts/lan_scail2_aio_prod.sh`，默认 dry-run，真实执行必须加 `--execute`。`start-disabled --execute` 只 drain 旧 slot0 AIO agent `lan_aio_prod_gpu002_gpu0_img2img_lora_01` 并等待自然空闲，停止旧 slot0 容器 `allbot-lan-aio-gpu-002-gpu0-img2img_lora-canary` 后启动 `allbot-lan-aio-gpu-002-gpu0-scail2-prod`，先保持 `lan_aio_prod_gpu002_gpu0_scail2_01` 为 disabled heartbeat；已在运行的正式 SCAIL-2 更新用 `restart-disabled --execute` 原地重建。验收时必须确认 `http://192.168.1.2:8190/system_stats`、`/queue`、`/object_info` 中的 `WanSCAILToVideo` / `SCAIL2ColoredMask` / `SAM3_VideoTrack` / `WanContextWindowsManual` / `VHS_LoadVideo` / `VHS_VideoCombine`，并确认主模型、SAM、CLIP Vision、Wan VAE、UMT5 和 LightX2V LoRA 枚举齐全，以及 compose/env 中只有 `cloud-prod`、正式 Central、`user-data-prod`、四任务 `SUPPORTED_TASK_TYPES`、audio/context-window/v10 workflow override 与 `SCAIL2_FACE_SWAP_V10_*` 预处理。回滚执行 `scripts/lan_scail2_aio_prod.sh rollback --execute`，只恢复旧 slot0 img2img_lora AIO，不删除 SCAIL-2 workspace、模型缓存、旧 img2img workspace、slot1 或其它 GPU 节点。

2026-06-28 `gpu-002-gpu1-pornmaster_flux2_edit` 曾通过 `scripts/lan_aio_fleet_prod_ops.py` 接管 slot1：drain 旧 `lan_aio_prod_gpu002_gpu1_image_to_video_01`，等待 `image_to_video` 任务自然完成，停止 `allbot-lan-aio-gpu-002-gpu1-image_to_video-canary`，预拉并启动 `allbot-lan-aio-gpu-002-gpu1-pornmaster-flux2-edit-prod`。2026-06-29 曾回切到 image_to_video；同日 23:17 Asia/Shanghai 后又通过当时的 fleet Web 入口切回 PornMaster。当前 `gpu-002-gpu1-pornmaster_flux2_edit` 是 fleet 中的当前可操作 slot，`gpu-002-gpu1-image_to_video` 是同卡候选回切 slot；回切时先 drain/disable PornMaster agent，等待当前任务自然结束，停止 `allbot-lan-aio-gpu-002-gpu1-pornmaster-flux2-edit-prod`，再启动 `allbot-lan-aio-gpu-002-gpu1-image_to_video-canary` 并补齐 RIFE 热缓存。不得让两个 8191 容器或两个 GPU1 agent 同时 enabled。

gpu-002 AIO 正式日常入口为 `scripts/lan_aio_prod_ops.sh`，底层 `scripts/lan_runpod_aio_prod_canary.sh` 仅作为高级灰度/排障入口。日常命令默认 dry-run，真实执行必须加 `--execute`：

| 动作 | 命令 | 注意事项 |
| :--- | :--- | :--- |
| 查状态 | `scripts/lan_aio_prod_ops.sh status` | 只读汇总 AIO、legacy worker、旧 ComfyUI 与旧 agent 状态 |
| AIO 接新单 | `scripts/lan_aio_prod_ops.sh enable-aio --execute` | 会先 drain/wait idle 旧 worker，再 enable 两个 AIO agent |
| AIO 停接 | `scripts/lan_aio_prod_ops.sh disable-aio --execute` | 等当前 AIO 任务完成后保持 AIO disabled，不自动恢复 legacy |
| 回滚旧链路 | `scripts/lan_aio_prod_ops.sh rollback --execute` | 启动旧 `comfy0/comfy1` 与旧 agent，再 restore `cloud_prod_worker_06/07` |
| 停旧容器 | `scripts/lan_aio_prod_ops.sh stop-old --execute` | 仅在 AIO healthy 且 legacy disabled 时停止旧容器；不删除 |

禁止用手工组合命令跳过 wrapper 的安全检查来停旧容器或回滚；若需要单独渲染、配置 registry、拉镜像或启动 heartbeat-only，再切到底层 helper。

## 6. 双卡节点安全操作红线

双卡 GPU 服务器的两个 ComfyUI 服务是独立容器，但不是完全隔离：

独立部分：

- Docker 容器：`comfy0` / `comfy1`
- GPU：`DeviceIDs ["0"]` / `DeviceIDs ["1"]`
- Host 端口：通常 `8188` / `8189`
- 输入目录：`inst0/input` / `inst1/input`
- 输出目录：`inst0/output` / `inst1/output`
- 临时目录：`inst0/temp` / `inst1/temp`
- 自定义节点目录：`inst0/custom_nodes` / `inst1/custom_nodes`
- workflow 目录：`inst0/workflows` / `inst1/workflows`

共享部分：

- 模型目录：`models`
- 模型 cache：`cache`
- Docker daemon
- 宿主机磁盘、CPU、内存、网络
- DCGM/node exporter 监控容器

因此：

- 处理单个 worker/Comfy 问题时，只重启对应 `cloud-prod-comfy-agent-N` 或对应 GPU 节点上的 `comfy0/comfy1`。
- 不要执行整机 reboot、`docker compose down`、无 service 名 `docker compose up -d` 或批量 `docker rm`。
- 修改共享模型目录前，要确认另一张卡没有正在使用同一模型文件。
- 删除 output/temp 可以按 `inst0` 或 `inst1` 定向清理；不要清理整个 `models` 或整个 `/data/comfy`。
- 更新 custom nodes 时优先只更新目标实例的 `custom_nodes`，验证通过后再同步另一实例。

## 7. ComfyUI 素材清理策略

2026-06-08 检查结果：4 台 GPU 节点只有系统默认 `systemd-tmpfiles-clean`、`logrotate`、apt/sysstat 等基础清理机制，没有发现针对 ComfyUI `input/output/temp` 的 cron、systemd timer 或项目级清理服务。因此此前旧图片、视频和临时文件会长期堆积。

当前推荐保留策略：

| 目录 | 推荐清理窗口 | 原因 |
| :--- | :--- | :--- |
| `output` | 删除 60 分钟以前文件 | Worker finalizer 正常会在任务完成后立即取回结果并上传 R2，旧输出主要是本地残留 |
| `temp` | 删除 60 分钟以前文件 | ComfyUI 中间产物，可按实例定向清理 |
| `input` | 删除 24 小时以前文件 | 已 pop/已 queue 的 ComfyUI prompt 仍可能引用输入文件，不能简单只保留 1 小时 |

不要清理：

- `models`
- `custom_nodes`
- `workflows`
- HuggingFace/Torch cache，除非明确是在做模型/缓存专项整理
- 当前 `/queue` 中 prompt 引用的输入文件

项目提供干跑优先脚本：

```bash
cd /home/hfy/APP/All_bot
scripts/cleanup_lan_comfy_artifacts.sh
scripts/cleanup_lan_comfy_artifacts.sh --host allbot-gpu-252
scripts/cleanup_lan_comfy_artifacts.sh --execute
```

脚本默认：

- 不带 `--execute` 只扫描不删除。
- `output/temp` 删除 60 分钟以前文件。
- `input` 删除 24 小时以前文件。
- `input` 保留窗口短于 360 分钟时必须显式加 `--force-short-input`，生产环境一般不要这么做。
- `allbot-gpu-226` 走宿主机路径 `/home/ubantu/comfyui/{input,output,temp}`。
- `allbot-gpu-252/002` 优先通过对应 `comfy0/comfy1` 容器内部 `/root/ComfyUI/{input,output,temp}` 清理，避免宿主权限导致 root-owned 文件残留；若旧 rollback 容器已停止，脚本会从 `docker inspect` 读取 bind mount，并在宿主机挂载路径上执行同一 dry-run/清理策略，不需要为了清理旧素材而启动旧 ComfyUI。`allbot-gpu-177` 的旧 `/data/comfy` 已删除，后续不再作为素材清理目标。

手工清理前后必须验证：

```bash
for base in \
  http://192.168.1.226:8188 \
  http://192.168.1.177:8190 \
  http://192.168.1.177:8191 \
  http://192.168.1.252:8188 \
  http://192.168.1.252:8189 \
  http://192.168.1.2:8188 \
  http://192.168.1.2:8189
do
  curl -fsS "$base/system_stats" >/dev/null
  curl -fsS "$base/queue" >/dev/null
done
curl -fsS http://100.107.220.127:8003/system/status
```

2026-06-08 人工清理结果：

| 节点 | 清理后磁盘 | 主要释放来源 |
| :--- | :--- | :--- |
| `allbot-gpu-226` | `/` 1.8T，已用 573G，可用 1.2T | host ComfyUI `output` 旧文件约 387G，`input` 24h 前文件约 135G |
| `allbot-gpu-177` | `/` 915G，已用 508G，可用 361G | `inst0/inst1 output` 旧文件约 266G，`input` 24h 前文件约 80G |
| `allbot-gpu-252` | `/` 937G，已用 178G，可用 712G | `inst0 temp/input`、`inst1 output/input` 等旧文件约 392G |
| `allbot-gpu-002` | `/` 936G，已用 171G，可用 726G | `inst0 temp/input`、`inst1 output/input` 等旧文件约 276G |

2026-06-20 gpu-177 追加清理结果：

- 先执行安全素材清理，删除旧 `inst0/inst1` output 60 分钟前文件约 `85.54GiB`、input 24 小时前文件约 `41.09GiB`，根分区可用从 `89G` 增至 `216G`。
- 用户确认不再保留本地旧链路回滚后，删除旧 `comfy0/comfy1`、本地主 `cloud-prod-comfy-agent-2/3`、旧 `/data/comfy`、`yanwk/comfyui-boot:cu130-slim`、旧 LTX 一次性 tag 和孤儿卷；根分区最终约 `190G` 已用、`680G` 可用。

长期建议：先用脚本 dry-run 纳入例行巡检，确认 1-2 周无误删后，再考虑为各 GPU 节点安装 systemd timer。启用 timer 前要保留 `input` 的长窗口，或者增加 `/queue` 文件引用排除逻辑。

## 8. 标准排障路径

从 Central 到 GPU 的定位顺序：

1. Central：`curl -fsS http://100.107.220.127:8003/system/workers`
2. Central Redis：统计 `comfy:queue:pending`、`comfy:queue:running`、pending 最老等待时间、`comfy:task_heartbeat:*` TTL
3. 本地主服务器 worker：`docker logs --since 5m cloud-prod-comfy-agent-N`
4. 目标 ComfyUI：`curl -fsS http://<gpu-ip>:<port>/system_stats`
5. 目标 ComfyUI 队列：`curl -fsS http://<gpu-ip>:<port>/queue`
6. 目标 GPU 节点：`ssh allbot-gpu-xxx 'nvidia-smi; docker ps'`
7. 目标 Comfy/AIO 容器：`docker logs --since 5m comfy0`、`comfy1` 或目标 `allbot-lan-aio-*` 容器

不要跳过 worker 到 Comfy 的对应关系。比如当前 `wan22_video_v2` 正式兜底路径是 RunPod `runpod_prod_wan22_video_v2_manual_01`；`lan_aio_prod_gpu252_gpu1_wan22_video_v2_01` -> `192.168.1.252:8191` / `allbot-lan-aio-gpu-252-gpu1-wan22_video_v2-prod` 只用于重新安装健康 GPU 后的 disabled 验收。旧 `cloud-prod-comfy-agent-5` -> `192.168.1.252:8189` / `comfy1` 只是 stopped rollback，不应该为 Wan22 v2 排障去重启 `comfy0`。

## 9. Worker 自动恢复边界

本地主服务器提供宿主机 watchdog：

```bash
scripts/watch_cloud_worker_recovery.sh --env cloud-test --mode dry-run
scripts/watch_cloud_worker_recovery.sh --env cloud-prod --mode dry-run
```

安全边界：

- 云测试可在故障注入时显式使用 `--mode execute` 精确恢复 `cloud-worker-relay-test` 或单个 `cloud-comfy-agent-test-*`。
- 云正式默认只运行 dry-run；真实 execute 必须另行确认。
- watchdog 只恢复本地主服务器上的 relay/agent 容器，不重启 GPU 节点、不重启 `comfy0/comfy1` 或 `allbot-gpu-226` 宿主机 ComfyUI、不执行全量 compose。
- 若 Central 与多个 ComfyUI 同时不可达，判定为网络中断，等待网络恢复，不做容器重启动作。
- relay `/ready` 返回 404 代表当前运行 relay 仍是旧版本，watchdog 只记录 `relay_ready_endpoint_missing`，不通过重启替代部署升级。

## 10. 单容器更新流程

更新某个仍保留传统 Comfy 容器的 GPU 节点时：

```bash
ssh allbot-gpu-252
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -fsS http://127.0.0.1:8188/queue
docker logs --since 5m comfy0
docker restart comfy0
curl -fsS http://127.0.0.1:8188/system_stats
```

注意：

- 上例只适合仍保留传统容器的节点，例如 `192.168.1.252:8188` / `comfy0`；`gpu-177` 已是 AIO only，不能再按 `comfy0/comfy1` 回滚或重启。
- 如果该 ComfyUI 正在执行任务，重启会中断当前任务。
- 如果 Central 中对应 worker 仍健康，优先等任务自然完成；紧急恢复时再中断。
- 对 `comfy0`/`comfy1` 执行 Docker 操作前，先确认当前所在 SSH Host，避免在错误机器上操作同名容器。

gpu-177 AIO 原地恢复使用 fleet helper，不触碰旧容器：

```bash
python scripts/lan_aio_fleet_prod_ops.py restart-aio --slot gpu-177-gpu0-wan22_video_v2 --execute
python scripts/lan_aio_fleet_prod_ops.py restart-aio --slot gpu-177-gpu1-image_to_video --execute
```

本地主服务器 worker 只更新某个 agent 时：

```bash
cd /home/hfy/APP/All_bot/workers
set -a; source ../.env.cloud.prod; set +a
docker-compose -f docker-compose-cloud-prod-worker.yml build cloud-prod-comfy-agent-5
docker rm -f cloud-prod-comfy-agent-5 2>/dev/null || true
docker-compose -f docker-compose-cloud-prod-worker.yml up -d --no-deps cloud-prod-comfy-agent-5
```

这只替换 worker 容器，不会重启 GPU 节点上的 `comfy1`。

## 11. 采集命令

硬件与容器：

```bash
for host in allbot-gpu-226 allbot-gpu-177 allbot-gpu-252 allbot-gpu-002; do
  ssh "$host" 'hostname; lscpu | grep -E "Model name|^CPU\\(s\\)"; free -h; df -hT -x tmpfs -x devtmpfs; nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu,utilization.memory,power.draw,temperature.gpu --format=csv,noheader,nounits; docker ps'
done
```

Central 队列与 heartbeat：

```bash
curl -fsS http://100.107.220.127:8003/system/status
curl -fsS http://100.107.220.127:8003/system/workers
```

若需要更准确的 pending 年龄与 heartbeat TTL，可在云 Central 容器内用 Redis 客户端做只读聚合；输出时只保留计数、类型、年龄分位和 TTL，不输出连接串或任务参数。

ComfyUI 节点能力：

```bash
for base in \
  http://192.168.1.226:8188 \
  http://192.168.1.177:8190 \
  http://192.168.1.177:8191 \
  http://192.168.1.252:8188 \
  http://192.168.1.252:8189 \
  http://192.168.1.2:8188 \
  http://192.168.1.2:8189
do
  curl -fsS "$base/system_stats"
  curl -fsS "$base/queue"
done
```

ComfyUI 队列判读：

- 7 个 ComfyUI `/queue` 都能毫秒级返回，且 Central heartbeat TTL 正常：节点未挂死。
- 某个 ComfyUI `running=1` 且 GPU 利用率持续 100%：该卡正在满载推理。
- 某个 ComfyUI `running=1` 但 GPU 利用率接近 0、显存高：先看 worker 日志是否处于上传、history 补偿、模型加载或等待阶段，再考虑单容器排障。
- Central pending 某类任务堆积，但对应 worker healthy：优先考虑该任务类型耗时长或 worker 数量不足，而不是重启全部 worker。

模型挂载：

```bash
ssh allbot-gpu-177 'docker inspect allbot-lan-aio-gpu-177-gpu0-image_to_video-prod allbot-lan-aio-gpu-177-gpu1-ltx_video-prod --format "{{.Name}} {{range .Mounts}}{{println .Source \"->\" .Destination}}{{end}}"'
ssh allbot-gpu-252 'docker inspect comfy0 comfy1 --format "{{.Name}} {{range .Mounts}}{{println .Source \"->\" .Destination}}{{end}}"'
ssh allbot-gpu-002 'docker inspect comfy0 comfy1 --format "{{.Name}} {{range .Mounts}}{{println .Source \"->\" .Destination}}{{end}}"'
```

## 12. 文档维护规则

以下事件发生后应更新本文档和 `docs/子模块_系统资源与容量画像_resource_inventory.md`：

- GPU 节点新增、下线、换卡或换 IP。
- ComfyUI 端口、容器名、模型目录或实例目录变化。
- worker `SUPPORTED_TASK_TYPES` 或 `COMFY_API_URL` 调整。
- ComfyUI 从宿主机进程迁移为容器，或反向迁移。
- 共享模型目录改路径。
- 远端磁盘低于 10% 可用空间并完成清理/迁移。
