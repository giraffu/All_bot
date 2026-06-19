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
| `192.168.1.226` | `allbot-gpu-226` | Ryzen 9 9950X，16C/32T | 60GiB | 1 x RTX 5090 32G | `/` 1.8T，已用 738G，可用 1001G | 单 ComfyUI，worker 01，face/i2i/t2i 与 LTX 补充容量 |
| `192.168.1.177` | `allbot-gpu-177` | Ryzen 7 9700X，8C/16T | 60GiB | 2 x RTX 5090 32G | `/` 915G，已用 626G，可用 243G | 双 ComfyUI，worker 02/03 |
| `192.168.1.252` | `allbot-gpu-252` | Ryzen 7 9700X，8C/16T | 60GiB | 1 x RTX 4090 48G active | `/` 937G，已用 352G，可用 538G | 健康卡 UUID `GPU-09b7ea85-23df-a9b8-19d9-703534e47666` 由 LAN AIO 承载 `img2img/img2img_lora`；故障卡已拆，`wan22_video_v2` 由 RunPod 兜底 |
| `192.168.1.2` | `allbot-gpu-002` | Ryzen 7 9700X，8C/16T | 60GiB | 2 x RTX 4090 48G | `/` 936G，已用 455G，可用 442G | 双 ComfyUI，worker 06/07，LAN AIO/SCAIL-2 试点 |

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
| `cloud-prod-comfy-agent-1` | Worker 01 | `192.168.1.226:8188` | `face_swap,i2i_pro,i2i_draw,face_video,video_edit,image_to_video,t2i-pornmaster-turbo,ltx_video` |
| `cloud-prod-comfy-agent-2` | Worker 02 | `192.168.1.177:8188` | `video_insert,video_edit,image_to_video` |
| `cloud-prod-comfy-agent-3` | Worker 03 | `192.168.1.177:8189` | `ltx_video,image_to_video` |
| `cloud-prod-comfy-agent-4` | Worker 04 | `192.168.1.252:8188` | `img2img,img2img_lora` |
| `cloud-prod-comfy-agent-5` | 旧 Worker 05，stopped rollback | 原 `192.168.1.252:8189` | 已由 `lan_aio_prod_gpu252_gpu1_wan22_video_v2_01` 替换，只保留回滚 |
| `cloud-prod-comfy-agent-6` | Worker 06 | `192.168.1.2:8188` | `img2img,img2img_lora` |
| `cloud-prod-comfy-agent-7` | Worker 07 | `192.168.1.2:8189` | `video_insert,video_edit,image_to_video` |

`video_insert` / `video_edit` 在 worker 能力列表中只表示 legacy alias，canonical 执行面类型是 `image_to_video`。排障或扩容时不要为它们新建独立 workflow、模型 profile 或 RunPod manifest。

SCAIL-2 动作迁移 / 视频换人有测试与正式两条 gpu-002/8190 链路，不能混用桶和 worker。云测试链路由 `cloud_worker_test_08` 指向 LAN AIO SCAIL-2 runtime `http://192.168.1.2:8190`，声明 `scail2_action_transfer,scail2_video_replacement`；测试 runtime 容器 `allbot-lan-aio-gpu-002-gpu0-scail2-test` 本身只跑 ComfyUI、模型同步与 workflow 资产，不注册 Central worker。云正式低影响发布由 `scripts/lan_scail2_aio_prod.sh` 启动 slot0 agent `lan_aio_prod_gpu002_gpu0_scail2_01` 和容器 `allbot-lan-aio-gpu-002-gpu0-scail2-prod`，必须写正式 Central 与 `user-data-prod`，不要把它误判为 `cloud-prod-comfy-agent-6` 或测试 `cloud_worker_test_08` 能力。

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
| `comfy_runtime_managed` | Controller 是否允许直接改 runtime | 第一阶段默认谨慎，`gpu-226` 必须为 `false` |

2026-06-10 正式更新已验证的是 Worker Agent 新协议：7 个 `cloud-prod-comfy-agent-*` 均能携带 `agent_id`、GPU pool heartbeat 元数据并通过 relay `/ready`。这不表示 7 个底层 ComfyUI 都是容器；`cloud-prod-comfy-agent-1` 调用的 `gpu-226:8188` 仍是宿主机 ComfyUI。

Controller 已补 `runtime-plan` / `runtime-render` dry-run 入口与 runtime schema。`gpu-002` 已完成第一阶段生产 AIO 接管；`gpu-177` 已通过 `scripts/lan_aio_fleet_prod_ops.py` 整机进入 `prod_enabled`；`gpu-252` 在拆除故障 RTX 4090 后以单卡 GPU0 恢复 `img2img/img2img_lora` LAN AIO，GPU1 `wan22_video_v2` 当前无本地 GPU 可用并由 RunPod 兜底，不再复制 gpu-002 专用 helper。`gpu-226` 仍是 `host_service`，只允许观测和手工 canary，不能直接套用 Docker AIO 接管。

LAN AIO fleet 首批候选：

| Slot | Legacy worker | AIO agent | Profile | 端口 | 状态 |
| :--- | :--- | :--- | :--- | ---: | :--- |
| `gpu-177-gpu0-image_to_video` | `cloud_prod_worker_02` | `lan_aio_prod_gpu177_gpu0_image_to_video_01` | `image_to_video` | 8190 | `prod_enabled` |
| `gpu-177-gpu1-ltx_video` | `cloud_prod_worker_03` | `lan_aio_prod_gpu177_gpu1_ltx_video_01` | `ltx_video` | 8191 | `prod_enabled` |
| `gpu-252-gpu0-img2img_lora` | `cloud_prod_worker_04` | `lan_aio_prod_gpu252_gpu0_img2img_lora_01` | `img2img/img2img_lora` | 8190 | `prod_enabled` |
| `gpu-252-gpu1-wan22_video_v2` | `cloud_prod_worker_05` | `lan_aio_prod_gpu252_gpu1_wan22_video_v2_01` | `wan22_video_v2` | 8191 | `maintenance_disabled` |

每个 slot 必须先 `preflight`、维护窗口配置 Docker insecure registry、预拉镜像、`start-disabled` 验收 disabled heartbeat，最后才小窗口 `enable-aio`。禁止一次性接管整台节点或跨节点批量启用。

2026-06-18 `gpu-177` 进入整机 LAN AIO 接管：GPU0 由 `lan_aio_prod_gpu177_gpu0_image_to_video_01` 接正式 `image_to_video`，GPU1 由 `lan_aio_prod_gpu177_gpu1_ltx_video_01` 接正式 `ltx_video`。旧 `cloud_prod_worker_02/03` 与旧 `comfy0/comfy1` 只作为 stopped rollback baseline 保留，不应与 AIO 同时 enabled 或同卡占用显存。`gpu-177-gpu0-image_to_video` 的 AIO 容器需预置旧 `comfy0` 内的 `rife49.pth` 到 `ComfyUI_Fill-Nodes` 和 `ComfyUI-Frame-Interpolation` 缓存路径，避免容器运行时访问 HuggingFace 失败。当前稳定 LAN AIO 正式能力包括 `img2img`、`img2img_lora`、`image_to_video`、`ltx_video`、`scail2_action_transfer`、`scail2_video_replacement`。

2026-06-18 `gpu-252-gpu1-wan22_video_v2` 已替换 `cloud_prod_worker_05`：新 AIO agent 为 `lan_aio_prod_gpu252_gpu1_wan22_video_v2_01`，容器 `allbot-lan-aio-gpu-252-gpu1-wan22_video_v2-prod` 监听 host `8191`，只接 `wan22_video_v2`。旧 `comfy1` 和本地主 `cloud-prod-comfy-agent-5` 已停止保留为回滚基线，不应再与 AIO 同时运行或 enabled。2026-06-20 交叉换槽确认 Xid 119/154 跟随实体卡 `GPU-33de1af6-ca27-7eeb-ae46-6a9f4f89523e`，该卡已拆除；当前无本地 GPU1，control 保持 `disabled`，RunPod `wan22_video_v2` 兜底。

2026-06-20 `gpu-252-gpu0-img2img_lora` 在拆除故障卡后恢复 LAN AIO：健康卡 `GPU-09b7ea85-23df-a9b8-19d9-703534e47666` 枚举为 GPU0，新 AIO agent 为 `lan_aio_prod_gpu252_gpu0_img2img_lora_01`，容器 `allbot-lan-aio-gpu-252-gpu0-img2img_lora-prod` 监听 host `8190`，按 `img2img_lora` profile 承接 `img2img` 与 `img2img_lora`。旧 `comfy0` 和本地主 `cloud-prod-comfy-agent-4` 已停止保留为回滚基线，不应再与 AIO 同时运行或 enabled。

## 5. GPU 节点明细

### 5.1 `allbot-gpu-226` / `192.168.1.226`

硬件与系统：
- Ubuntu 24.04.4 LTS，kernel `6.17.0-20-generic`
- Ryzen 9 9950X，16C/32T
- 内存 60GiB
- 1 x RTX 5090 32G，driver `590.48.01`
- Docker 29.1.3，Compose 2.37.1

容器：
- `portainer_agent`
- `dcgm_exporter`
- `monitor_node_exporter`

ComfyUI：
- 宿主机进程，不是 Docker Comfy 容器
- 端口：`8188`
- 进程 cwd：`/home/ubantu/comfyui`
- 当前服务：系统级 `/etc/systemd/system/comfyui.service`
- 当前启动命令：`/home/ubantu/miniforge3/envs/comfyui/bin/python main.py --listen 0.0.0.0`
- 模型目录：`/home/ubantu/comfyui/models`，约 `325G`
- 对应 worker：`cloud-prod-comfy-agent-1`

2026-06-15 LTX 补齐：
- 已安装 `ComfyLiterals`，使 `LTX 2.3 I2V 6.1.json` 所需的 `Float` 节点可用。
- 已补齐 `models/diffusion_models/LTX 2.3/ltx2310eros_v1.safetensors`，与当前 LTX workflow 主模型节点匹配。
- `cloud-prod-comfy-agent-1` 在原有任务类型基础上追加 `ltx_video`，用于补充 LTX 产能；不要改成只支持 `ltx_video`，否则会移走 worker 01 原有 face/i2i/t2i 能力。
- `ubantu` 用户级 `comfyui.service` 也存在但已停止，避免与系统级 service 抢占 `8188`；如需统一为 `--enable-manager` 口径，需要具备系统级 service 的 sudo 操作窗口。

2026-06-18 LTX LAN AIO 镜像：
- 已构建并推送 LTX 专用最小 AIO 镜像 `192.168.1.115:5000/allbot/comfy-runpod-ltx-video:20260618-ltx-min-cu128-sageattn1`；镜像只面向 `LTX 2.3 I2V 6.1.json`，baked `sageattention==1.0.6`，不 baked 模型权重，模型仍同步 `allbot-model-cache/ltx_video/2026-06-10/manifest.json`。
- `gpu-177-gpu1-ltx_video` 使用 LTX 最小 AIO 镜像 `192.168.1.115:5000/allbot/comfy-runpod-ltx-video:20260618-ltx-min-cu128-sageattn1`；它只面向 `LTX 2.3 I2V 6.1.json`，保持 workflow `sage_attention=auto`，不 baked 模型权重，模型仍同步 `allbot-model-cache/ltx_video/2026-06-10/manifest.json`。

运维边界：
- 不要对 `comfy0/comfy1` 执行 Docker 操作；本机没有这类 Comfy 容器。
- 重启 ComfyUI 需要先确认它是由 systemd、tmux、screen、桌面会话还是手工进程管理，再按实际启动方式处理。
- 重启该 ComfyUI 只影响 `cloud_prod_worker_01`。

### 5.2 `allbot-gpu-177` / `192.168.1.177`

硬件与系统：
- Ubuntu 24.04.4 LTS，kernel `6.17.0-29-generic`
- Ryzen 7 9700X，8C/16T
- 内存 60GiB
- 2 x RTX 5090 32G，driver `580.159.03`
- Docker 29.1.3，Compose 2.37.1
- 2026-06-18 根分区 `/` 可用约 `243G`，使用率约 73%；外置盘需操作前重新采集

容器：
- `allbot-lan-aio-gpu-177-gpu0-image_to_video-prod`：正式 AIO，GPU0，host `8190`
- `allbot-lan-aio-gpu-177-gpu1-ltx_video-prod`：正式 AIO，GPU1，host `8191`
- `comfy0`：旧回滚基线，停止保留，原端口 `8188`
- `comfy1`：旧回滚基线，停止保留，原端口 `8189`
- `portainer_agent`
- `dcgm_exporter`
- `monitor_node_exporter`

ComfyUI 实例：

| 容器 | GPU | Host 端口 | 容器端口 | 模型目录 | 独立目录 | 对应 worker |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `allbot-lan-aio-gpu-177-gpu0-image_to_video-prod` | GPU `0` | `8190` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 manifest 同步/挂载） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu177_gpu0_image_to_video_01` |
| `allbot-lan-aio-gpu-177-gpu1-ltx_video-prod` | GPU `1` | `8191` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 LTX manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu177_gpu1_ltx_video_01` |
| `comfy0` | GPU `0` | `8188` | `8188` | `/data/comfy/models` | `/data/comfy/inst0/{input,output,temp,custom_nodes,workflows}` | 旧 `cloud-prod-comfy-agent-2`，stopped rollback |
| `comfy1` | GPU `1` | `8189` | `8188` | `/data/comfy/models` | `/data/comfy/inst1/{input,output,temp,custom_nodes,workflows}` | 旧 `cloud-prod-comfy-agent-3`，stopped rollback |

共享模型目录：`/data/comfy/models`，约 `444G`。

旧回滚基线关键节点差异：
- `8188`：`FL_RIFE` 与 `RIFE VFI` 均存在。
- `8189`：`FL_RIFE` 与 `RIFE VFI` 均存在。2026-06-08 已在 `comfy1` 容器补齐 `socksio` 并重启，使 `comfyui_fill-nodes` 正常加载；Worker 03 不再需要 worker 侧 RIFE 节点类环境变量。

运维边界：
- 日常只操作 `allbot-lan-aio-gpu-177-gpu0-image_to_video-prod` 或 `allbot-lan-aio-gpu-177-gpu1-ltx_video-prod`；旧 `comfy0/comfy1` 和 `cloud-prod-comfy-agent-2/3` 只用于回滚，不得与 AIO 同时 enabled。
- LAN AIO compose 渲染 `restart: unless-stopped`，并由 entrypoint 监管 ComfyUI、relay 与 agent；任一关键进程退出时容器会退出，让 Docker restart policy 拉起干净进程树，避免“agent 心跳仍在但本地 ComfyUI 已死”的半活状态。
- 若回滚旧链路，必须通过 `scripts/lan_aio_fleet_prod_ops.py rollback --slot ... --execute`，让 Central control、旧 ComfyUI 与旧 agent 一起恢复。
- 修改 `/data/comfy/models` 会影响两个 ComfyUI。
- 修改 `/data/comfy/inst0/custom_nodes` 或 `workflows` 只影响 `comfy0`。
- 修改 `/data/comfy/inst1/custom_nodes` 或 `workflows` 只影响 `comfy1`。
- ComfyUI `input/output/temp` 已做一次旧素材清理；模型下载、Docker pull/build、临时输出前仍要先检查磁盘。

### 5.3 `allbot-gpu-252` / `192.168.1.252`

硬件与系统：
- Ubuntu 24.04.3 LTS，kernel `6.17.0-29-generic`
- Ryzen 7 9700X，8C/16T
- 内存 60GiB
- 1 x RTX 4090 48G active，driver `580.159.03`；故障 RTX 4090 已于 2026-06-20 拆除
- Docker 29.4.0，Compose v5.1.2
- 2026-06-18 根分区 `/` 可用约 `647G`；外置盘需操作前重新采集

容器：
- `comfy0`：旧回滚基线，停止保留，原端口 `8188`
- `allbot-lan-aio-gpu-252-gpu0-img2img_lora-prod`：正式 AIO，host `8190`，接 `img2img/img2img_lora`
- `allbot-lan-aio-gpu-252-gpu1-wan22_video_v2-prod`：maintenance disabled，host `8191`，当前无本地 GPU1，只保留配置和回滚/修复后验收入口
- `comfy1`：旧回滚基线，停止保留，原端口 `8189`
- `dcgm_exporter`
- `node_exporter`

ComfyUI 实例：

| 容器 | GPU | Host 端口 | 容器端口 | 模型目录 | 独立目录 | 对应 worker |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `comfy0` | GPU `0`（历史口径） | `8188` | `8188` | `/home/user/APP/data/models` | `/home/user/APP/data/inst0/{input,output,temp,custom_nodes,workflows}` | 旧 `cloud-prod-comfy-agent-4`，stopped rollback |
| `allbot-lan-aio-gpu-252-gpu0-img2img_lora-prod` | Docker device `0` | `8190` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 img2img_lora manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu252_gpu0_img2img_lora_01` |
| `allbot-lan-aio-gpu-252-gpu1-wan22_video_v2-prod` | Docker device `1`（当前无本地 GPU1） | `8191` | `8188` | AIO workspace `/workspace/ComfyUI/models`（由 Wan22 v2 manifest 同步） | `/workspace/allbot-state/{comfy-input,comfy-output,comfy-temp}` | `lan_aio_prod_gpu252_gpu1_wan22_video_v2_01` |
| `comfy1` | GPU `1`（历史口径） | `8189` | `8189` | `/home/user/APP/data/models` | `/home/user/APP/data/inst1/{input,output,temp,custom_nodes,workflows}` | 旧 `cloud-prod-comfy-agent-5`，stopped rollback |

共享模型目录：`/home/user/APP/data/models`，约 `121G`。

运行备注：
- `comfy0` CLI 包含 `--fp8_e4m3fn-text-enc`。
- `comfy0`/旧 `comfy1` 的模型目录共享，实例目录分离。
- `gpu-252-gpu0-img2img_lora` AIO 使用 LAN registry 镜像 `192.168.1.115:5000/allbot/comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946`，模型从 `allbot-model-cache/img2img_lora/2026-06-10/manifest.json` 同步。
- `gpu-252-gpu1-wan22_video_v2` AIO 使用 LAN registry 镜像 `192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd`，该 tag 已 baked `rife49.pth` 两处缓存；启动参数包含 `--disable-dynamic-vram`，模型从 `allbot-model-cache/wan22_video_v2/2026-06-13-test/manifest.json` 同步；当前因故障卡已拆、无本地 GPU1，保持 disabled，不计入可用容量。
- `gpu-252-gpu1-wan22_video_v2` 同样依赖 `FL_RIFE` 后处理；slot 配置仍可从宿主机旧 `inst1` 路径 `/home/user/APP/data/inst1/custom_nodes/ComfyUI_Fill-Nodes/nodes/cache/rife_models/rife49.pth` 预置到 AIO 内两处 RIFE 缓存路径，作为旧镜像回滚/热缓存兜底，避免运行时访问 HuggingFace。
- 目标用户无免密 sudo 时，镜像可由本地主服务器 `docker save ... | ssh allbot-gpu-252 docker load` 预置，避免为了配置 insecure registry 重启整台 Docker daemon。

运维边界：
- 只处理 `img2img/img2img_lora` 相关问题时，优先定位 `allbot-lan-aio-gpu-252-gpu0-img2img_lora-prod` 与 `lan_aio_prod_gpu252_gpu0_img2img_lora_01`；旧 `comfy0` / `cloud-prod-comfy-agent-4` 只用于回滚。
- 只处理 `wan22_video_v2` 相关问题时，当前优先定位 RunPod `runpod_prod_wan22_video_v2_manual_01`；`allbot-lan-aio-gpu-252-gpu1-wan22_video_v2-prod` 只用于重新安装健康 GPU 后的 disabled 验收，旧 `comfy1` / `cloud-prod-comfy-agent-5` 只用于回滚。普通 `image_to_video` 和 `video_edit` 不应路由到该 AIO。
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
- `comfy0`：`yanwk/comfyui-boot:cu128-slim`
- `comfy1`：`yanwk/comfyui-boot:cu128-slim`
- `dcgm_exporter`
- `node_exporter`

ComfyUI 实例：

| 容器 | GPU | Host 端口 | 容器端口 | 模型目录 | 独立目录 | 对应 worker |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `comfy0` | GPU `0` | `8188` | `8188` | `/data/comfy/models` | `/data/comfy/inst0/{input,output,temp,custom_nodes,workflows}` | `cloud-prod-comfy-agent-6` |
| `comfy1` | GPU `1` | `8189` | `8188` | `/data/comfy/models` | `/data/comfy/inst1/{input,output,temp,custom_nodes,workflows}` | `cloud-prod-comfy-agent-7` |

共享模型目录：`/data/comfy/models`，约 `85G`。

运维边界：
- `comfy0` 对应 worker 06，主要处理 `img2img/img2img_lora`。
- `comfy1` 对应 worker 07，主要处理 `image_to_video`，并保留 `video_insert/video_edit` legacy alias。
- 可只重启目标 Comfy 容器；不要因为一个容器异常而重启整台 GPU 节点。

LAN RunPod 化一体容器试点：
- 第一轮只允许 slot0 / `img2img_lora`，临时 agent 为 `lan_aio_test_gpu002_gpu0_img2img_lora_01`。
- canary 宿主机端口固定 `8190:8188`，不得占用或替换原 `8188` 的 `comfy0`。
- runtime root 固定 `/srv/allbot/runpod-runtime`；slot0 workspace 为 `/srv/allbot/runpod-runtime/slots/gpu-002-gpu0/profiles/img2img_lora/workspace`。
- 容器内 ComfyUI 走 `127.0.0.1:8188`，remote relay 走 `127.0.0.1:8013`，Central 必须使用 `https://worker-central-test.aivison.it.com`。
- 模型同步只写 `/workspace/ComfyUI/models`，模型源为本地主服务器 LAN cache `http://192.168.1.115:9010/allbot-model-cache`。
- 受控入口为 `scripts/lan_runpod_aio_canary.sh`；默认 dry-run，`--execute` 才会复制 compose/env 到 `allbot-gpu-002` 或修改 agent control。
- heartbeat-only 阶段必须保持临时 agent control 为 `disabled`。真实 canary 窗口才临时 disable `cloud_worker_test_06` 并 enable 临时 agent；结束后恢复 `cloud_worker_test_06`、disable 临时 agent、停止 canary 容器。

生产灰度入口为 `scripts/lan_runpod_aio_prod_canary.sh`，只允许 gpu-002 固定映射：slot0 `cloud_prod_worker_06 -> lan_aio_prod_gpu002_gpu0_img2img_lora_01`，端口 `8190`；slot1 `cloud_prod_worker_07 -> lan_aio_prod_gpu002_gpu1_image_to_video_01`，端口 `8191`。生产灰度必须使用 `--environment cloud-prod` 渲染出的 compose，写入 `user-data-prod`，并在启动前确认 compose 不含 `cloud-test` / `user-data-test`。首次拉取 LAN mirror 前需要维护窗口配置 Docker insecure registry `192.168.1.115:5000`，该操作会重启 Docker，必须先将 `cloud_prod_worker_06/07` 置为 `draining` 并等 `8188/8189` 队列清空。heartbeat-only 成功标准不是容器健康，而是 Central 能看到临时 agent 在 `disabled` control 下无 `current_task_type` 且 status 非 `running`，并携带 `node_id=gpu-002`、`provider=lan_ssh`、`runtime_profile`、`pool_managed=true`；Central 若残留旧 `current_task_id` 但 worker 已 `idle` 且无 `current_task_type`，不视为正在运行。缺任一项都应视为镜像或 remote_workers bundle 不可控，不能进入 `enable-canary`。helper 会同步并挂载当前 `remote_workers/`，AIO 启动时先安装 `remote_workers/requirements.txt`，再同步 LAN cache manifest 到 `/workspace/ComfyUI/models`，并把 baked ComfyUI 的 `models` 链接到该目录；slot1 `image_to_video` 启动后还必须从宿主机 `/data/comfy/inst1/custom_nodes/ComfyUI_Fill-Nodes/nodes/cache/rife_models/rife49.pth`（或共享模型 fallback `/data/comfy/models/upscale_models/rife49.pth`）预置到 AIO 内 `ComfyUI_Fill-Nodes` 与 `ComfyUI-Frame-Interpolation` 两处 RIFE 缓存路径，不能在正式任务后处理阶段访问 HuggingFace。达到目标接单数后先 `drain-temp --execute`，再等任务终态并 `restore --execute`。

2026-06-16 已完成 slot1 生产灰度：`image_to_video`、`video_insert`、`video_edit` 均由临时 agent `lan_aio_prod_gpu002_gpu1_image_to_video_01` 接单并以 canonical `image_to_video` 执行成功。灰度结束后必须恢复 `cloud_prod_worker_07`，停止 AIO 容器，保留原 `comfy1` / `8189` 作为生产基线。

2026-06-16 已将 gpu-002 slot0/slot1 切到生产 AIO 接新单：`cloud_prod_worker_06/07` 先 drain 并等待自然空闲，再 disable legacy worker、enable `lan_aio_prod_gpu002_gpu0_img2img_lora_01` 与 `lan_aio_prod_gpu002_gpu1_image_to_video_01`。切换时原 `comfy0/comfy1` 容器继续运行在 `8188/8189`，本地主服务器 `cloud-prod-comfy-agent-6/7` 也继续保留，作为热回滚基线；AIO 观察到 slot0 多单成功、slot1 视频单成功后，已执行 `docker stop comfy0 comfy1` 与 `docker stop cloud-prod-comfy-agent-6 cloud-prod-comfy-agent-7` 释放资源，容器未删除。回滚顺序是先 `docker start comfy0 comfy1`，确认 `8188/8189` `/system_stats` 与 `/queue` 正常，再启动 `cloud-prod-comfy-agent-6/7`，最后用 helper `restore --slot slot0|slot1 --execute` 恢复 `cloud_prod_worker_06/07`。

SCAIL-2 正式 slot0 接管会牺牲原 slot0 `img2img_lora` AIO 产能，但不影响 slot1 `image_to_video` AIO。入口是 `scripts/lan_scail2_aio_prod.sh`，默认 dry-run，真实执行必须加 `--execute`。`start-disabled --execute` 只 drain 旧 slot0 AIO agent `lan_aio_prod_gpu002_gpu0_img2img_lora_01` 并等待自然空闲，停止旧 slot0 容器 `allbot-lan-aio-gpu-002-gpu0-img2img_lora-canary` 后启动 `allbot-lan-aio-gpu-002-gpu0-scail2-prod`，先保持 `lan_aio_prod_gpu002_gpu0_scail2_01` 为 disabled heartbeat。验收时必须确认 `http://192.168.1.2:8190/system_stats`、`/queue`、`/object_info` 中的 `WanSCAILToVideo` / `SCAIL2ColoredMask` / `SAM3_VideoTrack` / `WanContextWindowsManual` / `VHS_LoadVideo` / `VHS_VideoCombine`，并确认主模型、SAM、CLIP Vision、Wan VAE、UMT5 和 LightX2V LoRA 枚举齐全，以及 compose/env 中只有 `cloud-prod`、正式 Central 和 `user-data-prod`。回滚执行 `scripts/lan_scail2_aio_prod.sh rollback --execute`，只恢复旧 slot0 img2img_lora AIO，不删除 SCAIL-2 workspace、模型缓存、旧 img2img workspace、slot1 或其它 GPU 节点。

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
scripts/cleanup_lan_comfy_artifacts.sh --host allbot-gpu-177
scripts/cleanup_lan_comfy_artifacts.sh --execute
```

脚本默认：
- 不带 `--execute` 只扫描不删除。
- `output/temp` 删除 60 分钟以前文件。
- `input` 删除 24 小时以前文件。
- `input` 保留窗口短于 360 分钟时必须显式加 `--force-short-input`，生产环境一般不要这么做。
- `allbot-gpu-226` 走宿主机路径 `/home/ubantu/comfyui/{input,output,temp}`。
- `allbot-gpu-177/252/002` 通过对应 `comfy0/comfy1` 容器内部 `/root/ComfyUI/{input,output,temp}` 清理，避免宿主权限导致 root-owned 文件残留。

手工清理前后必须验证：

```bash
for base in \
  http://192.168.1.226:8188 \
  http://192.168.1.177:8188 \
  http://192.168.1.177:8189 \
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

更新某个 GPU 节点上的单个 Comfy 容器时：

```bash
ssh allbot-gpu-177
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -fsS http://127.0.0.1:8189/queue
docker logs --since 5m comfy1
docker restart comfy1
curl -fsS http://127.0.0.1:8189/system_stats
```

注意：
- 上例只适合 `192.168.1.177:8189` / `comfy1`。
- 如果该 ComfyUI 正在执行任务，重启会中断当前任务。
- 如果 Central 中对应 worker 仍健康，优先等任务自然完成；紧急恢复时再中断。
- 对 `comfy0`/`comfy1` 执行 Docker 操作前，先确认当前所在 SSH Host，避免在错误机器上操作同名容器。

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
  http://192.168.1.177:8188 \
  http://192.168.1.177:8189 \
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
ssh allbot-gpu-177 'docker inspect comfy0 comfy1 --format "{{.Name}} {{range .Mounts}}{{println .Source \"->\" .Destination}}{{end}}"'
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
