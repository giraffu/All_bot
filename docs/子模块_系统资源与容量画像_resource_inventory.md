# 子模块: 系统资源与容量画像 (Resource Inventory)

## 1. 目标与范围

本文档记录 AllBot 当前主服务器、本地 GPU 节点、网络出口、数据存储与运行负载的资源事实，用于容量规划、云化评估、灾备设计与运维排障。

本文档不是实时监控面板。除明确标注为固定事实的硬件配置外，数据库行数、队列积压、桶容量、活跃用户等都应视为快照数据；做迁移、采购或扩容决策前，必须重新采集。

最近一次结构性更新时间：2026-06-18 03:06，Asia/Shanghai。表内容量数字若未单独标注，仍是历史快照，扩容或迁移决策前必须重新采集。
最近一次局域网 GPU ComfyUI 素材清理：2026-06-08，Asia/Shanghai。
最近一次云正式只读负载/数据巡检：2026-06-18 03:06，Asia/Shanghai。
最近一次云测试控制面核对：2026-06-18 03:06，Asia/Shanghai。
最近一次 gpu-252/worker05 LAN AIO 接管更新：2026-07-04，Asia/Shanghai；同日 19:19 已改为返修卡 Xid 隔离禁用口径，19:41 改由 8191 PornMaster Flux2 edit 低负载接单。
最近一次本地云正式 shadow 同步能力更新：2026-06-25，Asia/Shanghai。

## 2. 主服务器

当前主服务器不再是正式公开控制面的主承载点。正式 Bot/Web/Payment/Central/Dashboard 已迁到云控制面；本机主要保留本地 GPU worker、ComfyUI 访问、legacy MinIO 数据、本地旧正式数据保留、云正式 shadow DB/MinIO 副本、测试/开发辅助容器和运维工具。

| 项目 | 当前事实 |
| :--- | :--- |
| 主机名 | `hfy-FAEX9` |
| 内网地址 | `192.168.1.115` |
| 操作系统 | Ubuntu 24.04.4 LTS |
| 内核 | Linux 6.17.0-1020-oem |
| 硬件型号 | FEVM FAEX9 |
| CPU | AMD RYZEN AI MAX+ 395 w/ Radeon 8060S |
| CPU 规格 | 16 核 / 32 线程，最高约 5.19GHz |
| 内存 | 62GiB |
| 系统盘 | 3.6T NVMe，ext4 |
| Docker/Compose | Docker 29.1.3，`docker-compose` 1.29.2 |
| 主网卡 | `eno1`，1GbE，内网 `192.168.1.115/24` |
| 远程组网 | `tailscale0` 已存在，用于跨节点/边缘访问 |

最新磁盘快照：

| 挂载点 | 容量 | 已用 | 可用 | 备注 |
| :--- | ---: | ---: | ---: | :--- |
| `/` | 3.6T | 1.6T | 1.9T | 主系统盘与 Docker 数据共盘 |
| `/mnt/remote_data/192.168.1.226/ubantu` | 1.8T | 738G | 1001G | 远端 GPU 节点 SSHFS |
| `/mnt/remote_data/192.168.1.177/data` | 915G | 626G | 243G | 远端 GPU 节点 SSHFS，当前使用率约 73%，模型下载/视频压测前重点复查 |
| `/mnt/remote_data/192.168.1.252/user` | 937G | 243G | 647G | 远端 GPU 节点 SSHFS |
| `/mnt/remote_data/192.168.1.2/data` | 936G | 455G | 442G | 远端 GPU 节点 SSHFS |

## 2.1 云控制面 Droplet

云控制面 Droplet 已于 2026-06-06 创建，并于 2026-06-07 晚间承接正式生产控制面。

| 项目 | 当前事实 |
| :--- | :--- |
| 云厂商 | DigitalOcean |
| 区域 | Singapore `SGP1` |
| Droplet 名称 | `allbot-do-sgp1-control-01` |
| 公网 IPv4 | `159.223.39.217` |
| VPC/私网 IPv4 | `10.104.0.2` |
| 操作系统 | Ubuntu 24.04.3 LTS |
| 规格 | Basic Regular `$96/mo`，8 vCPU / 16GB RAM / 320GB SSD / 6TB transfer |
| 实测 CPU | 8 vCPU |
| 实测内存 | 约 15GiB |
| 实测系统盘 | 约 309G 总量；当前约 125G 已用、185G 可用，使用率约 41% |
| SSH 日常入口 | `ssh allbot-do-sgp1-control`，默认 `deploy` 用户 |
| SSH root 入口 | `ssh allbot-do-sgp1-control-root`，仅初始化/救援使用 |

使用边界：

- `$96/mo` Droplet 当前作为正式生产控制面；生产 Postgres、Valkey 与对象存储不在该 Droplet 上长期自托管。
- 2026-06-16 原地扩容后，系统盘事实容量已从约 160GB 扩到约 320GB；后续缩容不能再按“保留 160GB 磁盘”的旧口径假设。
- 公开媒体与新生成对象走 Cloudflare R2 `user-data-prod`；本地 MinIO 保留为 legacy 迁移补齐、人工回滚、旧外链排障与本地热数据保留，不再是正式 Web/Dashboard 运行时 fallback。
- 本地主服务器可每日维护云正式 shadow 副本：PostgreSQL `bot_db_prod_shadow`、R2 纯镜像 MinIO `user-data-prod-shadow`、完整合并桶 `user-data-complete-shadow` 与 `user-data-prod-shadow-quarantine/<timestamp>/`。数据库 dump 默认由 `allbot-do-sgp1-control` 在云机执行并经 R2 临时前缀 HTTPS 中转回本地，不依赖本地主公网/VPN 出口作为托管数据库 trusted source。完整桶每日只从本地 R2 shadow 非破坏式 copy；legacy MinIO 旧桶只做一次性手动导入。该副本用于灾备预热和只读分析，不是云正式服务运行时 fallback，也不会自动接管本地正式写入口。
- 本地 7 张 GPU 和 ComfyUI 不迁移；本地 `cloud-prod-comfy-agent-*` compose、LAN AIO、`remote_workers` 与手动 RunPod 都通过 Central worker 协议接入。当前可用容量必须以 `/system/workers` 为准。
- 后续如继续增长，优先单独评估 Dashboard/后台任务拆分、PostgreSQL 规格或连接池预算；不要同时放大 Web worker 数和 DB 连接池。

### 2.2 云测试控制面 Droplet

云测试控制面 Droplet 于 2026-06-09 创建，用于替代旧本地常驻测试入口，降低正式与测试环境交叉风险。

| 项目 | 当前事实 |
| :--- | :--- |
| 云厂商 | DigitalOcean |
| 区域 | Singapore `SGP1` |
| Droplet 名称 | `allbot-do-sgp1-test-control` |
| 公网 IPv4 | `168.144.128.133` |
| VPC/私网 IPv4 | `10.104.0.5` |
| Tailscale IPv4 | `100.82.124.91` |
| 操作系统 | Ubuntu 24.04 LTS x64 |
| 规格 | Basic Regular `$12/mo`，1 vCPU / 2GB RAM / 50GB SSD / 2TB transfer |
| 实测 CPU / 内存 | 1 vCPU；约 1.9GiB RAM，当前 available 约 751MiB |
| 实测系统盘 | 约 48G 总量；当前约 16G 已用、33G 可用，使用率约 32% |
| SSH 日常入口 | `ssh allbot-do-sgp1-test-control`，默认 `deploy` 用户 |
| 运行服务 | `cloud-postgres-test`、`cloud-redis-test`、`cloud-central-api-test`、`cloud-web-api-test`、`cloud-imgproxy-test`、`cloud-tg-bot-test`；管理面已移除，`cloud-qqcc-bot-test` 是可选 `qqcc-bot` profile |
| 公网保护 | 服务端口绑定 `100.82.124.91`；`allbot-cloud-test-firewall.service` 继续保护测试 API 端口；已移除的管理端口不再提供服务 |

使用边界：

- 测试 PostgreSQL 与 Redis 均为同机容器，只服务云测试栈，不连接正式托管 PostgreSQL/Valkey。
- 测试对象存储事实源为 R2 `user-data-test`，公网读取域名 `https://r2-test.aivison.it.com`。
- 本地主服务器运行 `cloud-comfy-agent-test-1..8`，通过 `CLOUD_TEST_CONTROL_HOST=100.82.124.91` 访问云测试 Central `8004`；`cloud_worker_test_08` 指向 gpu-002 SCAIL-2 LAN AIO runtime。
- 公网测试 Web 入口是 `web-test.aivison.it.com`，由 Web/Nginx VPS 静态站 `/root/dist-test` 反代到云测试 Web API `100.82.124.91:8001`。

### 2.3 云正式负载巡检快照

2026-06-18 03:06 Asia/Shanghai 的只读巡检显示，云正式控制面 CPU、内存、磁盘、Redis/Valkey 与 PostgreSQL 体量都不是第一瓶颈；用户等待更主要来自 GPU 任务吞吐、任务类型分布、R2/媒体链路和公网路径。

| 指标 | 快照 | 判断 |
| :--- | :--- | :--- |
| 云 Droplet CPU/内存 | `nproc=8`，内存约 15GiB，available 约 10GiB | 控制面 CPU/RAM 未打满 |
| 云 Droplet 磁盘 | 309G 总量，约 125G 已用，185G 可用 | 使用率约 41%，仍有余量 |
| 云控制面容器 | Central/Web/Payment/Dashboard/QQCC Config/imgproxy/Bot 均 `Up` 且关键服务健康；`visible-hotset-input-backfill-cloud` 为一次性补齐任务容器 | 控制面主服务正常，临时任务不写成长期常驻服务 |
| Central 队列 | `queue_size=49`，`active_workers=13`，`healthy_workers=13`，`error_workers=0`，`quarantined_workers=0` | 容量由本地 worker、LAN AIO、remote workers 与手动 RunPod 混合构成，不按固定 7 个判断 |
| 队列类型分布 | `img2img=19`、`img2img_lora=15`、`face_swap=8`、`scail2_video_replacement=2`、`t2i-pornmaster-turbo=2`、`face_video=1`、`i2i_pro=1`、`wan22_video_v2=1` | 排队主要受任务类型和对应 worker 数影响 |
| 托管 PostgreSQL 连接池预算 | 可用连接按 `100 - 3 reserved = 97` 估算；本轮配置目标峰值约 `73` | 保留约 24 条给迁移、排障、后台任务和抖动 |
| 托管 Valkey/Redis | used_memory 约 61.95MB，connected_clients 约 91，blocked/rejected/evicted 均为 0 | 暂未见 Redis 打满 |

本轮云正式 DB 连接池预算：

| 服务 | 进程/worker 口径 | 池配置 | 峰值预算 |
| :--- | :--- | :--- | ---: |
| `cloud-web-api-prod` | `uvicorn --workers 4` | `DB_POOL_SIZE=6`、`DB_MAX_OVERFLOW=6` | 48 |
| `cloud-dashboard-backend-prod` | `gunicorn -w 1` | `DB_POOL_SIZE=6`、`DB_MAX_OVERFLOW=4` | 10 |
| `cloud-qqcc-config-backend-prod` | `gunicorn -w 1` | `DB_POOL_SIZE=2`、`DB_MAX_OVERFLOW=2` | 4 |
| `cloud-payment-api-prod` | 单进程 | `DB_POOL_SIZE=4`、`DB_MAX_OVERFLOW=3` | 7 |
| `cloud-tg-bot-prod` | 单进程 | `DB_POOL_SIZE=4`、`DB_MAX_OVERFLOW=4` | 8 |
| `cloud-qqcc-bot-prod` | 单进程，仅启用 `qqcc-bot` profile 时 | `DB_POOL_SIZE=4`、`DB_MAX_OVERFLOW=4` | 8 |
| 基线合计 | - | 未启用 QQCC profile | 73 |
| 启用 QQCC 后合计 | - | QQCC Bot 与主 Bot 同时运行 | 81 |

延迟拆分基线：

- 云机内部访问 `100.107.220.127:8000/8003/8043/8045` 通常为 5-40ms。
- Web 边缘 VPS 到云 Web API 约 0.51-0.55s；该基线主要用于 `assets`/回滚/`web-test` 排障，不代表当前正式 Pages 主路径。
- 本地主服务器经公网访问 `api.aivison.it.com` API 约 0.3-0.7s；旧 `web.aivison.it.com/api` 不再作为 API 健康检查入口。
- 本地主服务器到云 Central Tailscale 约 0.7-2.1s。

云测试控制面 2026-06-18 03:06 快照：

- 云测试 Droplet 为 1 vCPU / 约 1.9GiB RAM / 48G 根盘，当前约 16G 已用、33G 可用。
- 当时测试控制面容器快照曾包含 Dashboard/QQCC Config；自 2026-07-16 起这四个管理服务已从目标测试契约移除，不应再启动。当前目标集合为 Postgres、Redis、Central API、Web API、imgproxy 和按需 Bot。
- Central 测试队列 `queue_size=0`，`active_workers=8`，`healthy_workers=5`，`error_workers=3`，`quarantined_workers=0`。`error` worker 是运行态快照，做测试验收前必须重新查 `/system/workers`，不要把它写成永久故障。

## 3. 服务与容器分布

正式控制面当前在云端，本地主服务器保留本地 GPU worker 与旧数据。测试/开发服务仍可能在本地或云测试控制面运行，必须按 compose、端口、环境变量、数据库与 Valkey/Redis DB 隔离。

当前正式生产常驻类型：

- 云端正式入口：`cloud-tg-bot-prod`、`cloud-web-api-prod`、`cloud-payment-api-prod`；`cloud-qqcc-bot-prod` 是可选 `qqcc-bot` profile 入口，正式启动需单独确认
- 云端正式执行面：`cloud-central-api-prod`，Tailscale `100.107.220.127:8003`
- 云端正式管理面：`cloud-dashboard-backend-prod`、`cloud-dashboard-frontend-prod`、`cloud-qqcc-config-backend-prod`、`cloud-qqcc-config-frontend-prod`、`cloud-imgproxy-prod`
- 本地正式 worker compose：`cloud-prod-worker-relay` 与 `cloud-prod-comfy-agent-1` 至 `cloud-prod-comfy-agent-7`；这是本地 compose 声明，不等于每个容器都必须长期运行
- 正式弹性/灰度算力：LAN AIO agent、`remote_workers` 与手动 RunPod worker 可按运维目标接入 Central；2026-06-18 快照中 Central 看到 13 个 healthy active workers
- 本地 legacy 与 shadow 数据：原 PostgreSQL/Redis/MinIO 只作为保留或 fallback；`bot_db_prod_shadow`、`user-data-prod-shadow`、`user-data-complete-shadow` 是云正式每日 shadow/备份副本，不应继续作为正式写入事实源，除非进入本地正式灾备并人工停同步、确认 RPO 后切写入口

测试/辅助服务类型：

- 云测试入口：`cloud-tg-bot-test`、`cloud-web-api-test`、`cloud-imgproxy-test`；Dashboard/QQCC Config 管理面不再部署，`cloud-qqcc-bot-test` 为可选 QQCC 测试入口，必须使用独立 `QQCC_BOT_TOKEN_TEST`
- 云测试执行面：`cloud-central-api-test`，Tailscale `100.82.124.91:8004`
- 云测试数据面：`cloud-postgres-test`、`cloud-redis-test`，仅 Docker 内网可达
- 本地云测试 worker：`cloud-comfy-agent-test-1` 至 `cloud-comfy-agent-test-8`，其中 `test-8` 是 SCAIL-2 测试接单层
- 本地旧测试栈：不再作为受支持测试或回滚环境；仅作为历史取证材料，默认应停止并保留数据
- 本地运维与历史数据：`postgres-server`、`redis-server`、`minio-server`、`pgadmin-server`、`filebrowser`、`portainer_agent`

重要运行约束：

- `web-api`、Dashboard、Payment API 等 COPY 型服务改代码后必须重建镜像，不能只 `restart`。
- 云测试研发验证优先按变更影响快速重建对应模块容器，不默认进入维护或排空队列；`scripts/update_cloud_test_with_maintenance.sh --execute` 仅用于整栈联动、迁移、排空验证或用户明确要求维护窗口，远端控制面重建子步骤为 `scripts/safe_deploy_cloud_test.sh`。
- 云正式生产发布优先走 `scripts/update_cloud_prod_with_maintenance.sh --execute --confirm-prod`、`scripts/safe_deploy_cloud_prod.sh` 子步骤或 cloud-prod compose 单服务重建；只有云正式整体故障、本地主服务器临时接管正式服务时才使用 `safe_deploy.sh`。
- 生产单服务重建时不得使用 `--remove-orphans` 或无 service 名的批量 compose 操作。
- 本地云正式 worker 使用旧版 `docker-compose` 时，遇到 `ContainerConfig` 兼容错误只能清理目标 worker 容器和同 service label 残留。

## 4. 本地 GPU 算力池

本地算力池由 4 台 GPU 服务器组成，共 7 张 GPU。项目容量口径以 GPU 监控截图与用户确认的硬件事实为准：3 张 RTX 5090 32G，4 张 RTX 4090 48G，总名义显存约 288GB。详细容器、模型挂载和安全运维边界见 `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md`。

> 注意：部分 ComfyUI 进程通过设备隔离启动，`/system_stats` 中会统一显示为 `cuda:0`。判断真实 GPU 数量时，不要把 Comfy 端口数、`cuda:0` 文本和物理 GPU 数混为一谈。

| GPU 服务器 | 物理 GPU | ComfyUI 端口 | 生产 Agent | 主要支持任务 |
| :--- | :--- | :--- | :--- | :--- |
| `192.168.1.226` | 1 x RTX 5090 32G | `8188` | `cloud_prod_worker_01` | `face_swap`、`i2i_pro`、`i2i_draw`、`face_video`、`video_edit`、`image_to_video`、`t2i-pornmaster-turbo` |
| `192.168.1.177` | 2 x RTX 5090 32G | AIO `8190`、`8191` only；旧 `8188`/`8189` 已退役删除 | `lan_aio_prod_gpu177_gpu0_image_to_video_01`、`lan_aio_prod_gpu177_gpu1_ltx_video_01` | `wan22_video_v2`、`ltx_video` |
| `192.168.1.252` | 2 x RTX 4090 48G | AIO `8192` i2i_pro active；AIO `8191` PornMaster Flux2 edit active；旧 `8188`/`8189` stopped rollback | `lan_aio_prod_gpu252_gpu0_i2i_pro_01`；`lan_aio_prod_gpu252_gpu1_pornmaster_flux2_edit_01` | `i2i_pro`、`t2i-pornmaster-turbo`、`face_swap`；`pornmaster_flux2_single_edit`、`pornmaster_flux2_multi_edit`；返修卡 SCAIL-2/Wan22 不计入当前容量 |
| `192.168.1.2` | 2 x RTX 4090 48G | AIO `8190`、`8191`；旧 `8188`/`8189` stopped rollback | `lan_aio_prod_gpu002_gpu0_scail2_01`、`lan_aio_prod_gpu002_gpu1_pornmaster_flux2_edit_01` | `scail2_action_transfer`、`scail2_video_replacement`、`pornmaster_flux2_single_edit`、`pornmaster_flux2_multi_edit` |

表中 `video_insert` / `video_edit` 仅表示生产 worker 仍声明的兼容 alias；canonical 执行面类型是 `image_to_video`，不再代表独立模型或独立 workflow。

同一批 ComfyUI 节点也可能被测试 agent 使用。正式 agent 连接云 Central API `100.107.220.127:8003`；测试 agent 连接测试 Central。测试与生产共享物理 GPU 时，要避免把测试任务当成免费容量；大模型/视频任务压测会直接影响生产排队。

本地主服务器已配置局域网 GPU 节点 SSH 别名：`allbot-gpu-226`、`allbot-gpu-177`、`allbot-gpu-252`、`allbot-gpu-002`。密钥、权限边界与验证命令见 `docs/子模块_局域网GPU节点SSH管理_lan_gpu_ssh_access.md`。

GPU 节点运行方式与模型挂载快照：

| GPU 服务器 | ComfyUI 运行方式 | 模型目录 | 实例隔离 | 运维注意 |
| :--- | :--- | :--- | :--- | :--- |
| `192.168.1.226` | 宿主机进程，cwd `/home/ubantu/comfyui`，端口 `8188` | `/home/ubantu/comfyui/models`，约 325G | 单实例 | 不是 Comfy Docker 容器；重启前先确认进程管理方式 |
| `192.168.1.177` | 正式 AIO `allbot-lan-aio-gpu-177-gpu0-image_to_video-prod`/`allbot-lan-aio-gpu-177-gpu1-ltx_video-prod`，host `8190`/`8191` | AIO workspace `/workspace/ComfyUI/models`；旧 `/data/comfy` 已删除 | AIO 使用 `/workspace/allbot-state` 隔离 input/output/temp；旧 `inst0/inst1` 已删除 | 2026-06-20 清理后根分区可用约 680G，使用率约 22%；旧 `comfy0/comfy1` 和旧 agent 2/3 已删除，`cloud_prod_worker_02/03` control 为 `disabled` |
| `192.168.1.252` | 正式 AIO `allbot-lan-aio-gpu-252-gpu0-i2i_pro-prod` host `8192`；正式 AIO `allbot-lan-aio-gpu-252-gpu1-pornmaster_flux2_edit-prod` host `8191`；旧 `comfy0`/`comfy1` stopped rollback | AIO workspace `/workspace/ComfyUI/models` 由 manifest 同步；旧 `/home/user/APP/data/models` 保留回滚 | AIO 使用 `/workspace/allbot-state` 隔离 input/output/temp；旧 `inst0`/`inst1` 保留回滚 | 2026-07-04 根分区可用约 413G；GPU0 i2i_pro 固定健康 UUID `GPU-09b7ea85-23df-a9b8-19d9-703534e47666`；GPU1 返修 UUID `GPU-33de1af6-ca27-7eeb-ae46-6a9f4f89523e` 只按 PornMaster Flux2 edit 低负载计入容量，真实 SCAIL-2 workload 曾复现 Xid 119/154，SCAIL-2/Wan22 仍 maintenance-disabled |
| `192.168.1.2` | 正式 AIO `allbot-lan-aio-gpu-002-gpu0-scail2-prod`/`allbot-lan-aio-gpu-002-gpu1-i2i_pro-prod`，host `8190`/`8191`；`image_to_video` 与 PornMaster AIO 为 stopped rollback | AIO workspace `/workspace/ComfyUI/models`；旧共享目录 `/data/comfy/models` 保留回滚 | AIO 使用 `/workspace/allbot-state` 隔离 input/output/temp；旧 `inst0/inst1` 保留 | 2026-07-17 GPU1 i2i_pro 六文件模型缓存与单卡 takeover 门禁通过；旧 `comfy0/comfy1` 和旧 agent 6/7 stopped，不得与 AIO 同卡并跑 |

双卡节点的重要边界：`gpu-177` 日常只按 AIO 容器和 `8190/8191` 端口操作，旧本地回滚链路已删除；`gpu-002` 日常按 AIO 容器和 `8190/8191` 端口操作，旧 `comfy0/comfy1` 仍只作为 stopped rollback baseline；`gpu-252` 当前 `8192` 健康卡接 `i2i_pro,t2i-pornmaster-turbo,face_swap`，`8191` 返修卡只接 PornMaster Flux2 edit 低负载图片编辑，不得误算为 SCAIL-2/Wan22 视频容量，旧 `comfy0/comfy1` 只作 stopped rollback。处理某个 worker 或某个 ComfyUI 的问题时，只操作对应 worker 容器、AIO 容器或对应 GPU 节点上的单个 `comfy0/comfy1`；不要使用整机 reboot、无 service 名 `docker compose down/up` 或批量 `docker rm`。

ComfyUI 素材清理口径：

- 2026-06-08 检查确认 GPU 节点没有项目级 ComfyUI 素材自动清理机制，只有系统默认 tmp/log 清理。
- 已执行一次安全清理：`output/temp` 删除 60 分钟以前文件，`input` 只删除 24 小时以前文件。
- 长期清理脚本为 `scripts/cleanup_lan_comfy_artifacts.sh`，默认 dry-run，必须显式 `--execute` 才删除。
- 不要把“只保留最近 1 小时”套到 `input` 目录；已进入 ComfyUI 队列的任务可能仍引用输入文件。

ComfyUI 版本快照：

| ComfyUI URL | ComfyUI | PyTorch | 运行时识别显存 |
| :--- | :--- | :--- | :--- |
| `http://192.168.1.226:8188` | 0.17.0 | 2.10.0+cu130 | RTX 5090，约 31.36GiB |
| `http://192.168.1.177:8190` | 0.21.1 | 2.11.0+cu128 | RTX 5090，约 31.36GiB，`--disable-dynamic-vram` |
| `http://192.168.1.177:8191` | 0.19.5 | 2.11.0+cu128 | RTX 5090，约 31.36GiB，LTX AIO |
| `http://192.168.1.252:8192` | 0.17.0 | 2.11.0+cu128 | RTX 4090，约 47.37GiB，i2i_pro AIO |
| `http://192.168.1.252:8191` | 0.17.0 | 2.11.0+cu128 | RTX 4090，约 47.37GiB，PornMaster Flux2 edit AIO |
| `http://192.168.1.252:8188` / `:8189` | 旧 runtime | 旧 runtime | stopped rollback，非当前接单入口 |
| `http://192.168.1.2:8190` | 0.25.0 | 2.11.0+cu128 | RTX 4090，约 47.62GiB，SCAIL-2 AIO |
| `http://192.168.1.2:8191` | 0.21.1 | 2.11.0+cu128 | RTX 4090，约 47.62GiB，image_to_video AIO |

## 5. 网络与外部依赖

现实网络条件：

- 主服务器位于中国武汉，电信家庭千兆内网环境。
- 主服务器主网卡为 1GbE；本地 GPU 节点通过 `192.168.1.0/24` 内网访问。
- ComfyUI 内网探测多数在几十毫秒内返回，但仍可能出现单节点端口瞬时慢响应。
- 公网入口依赖 Cloudflare、海外 VPS、Tailscale/Cloudflare Tunnel/FRP 等链路，不应把武汉家庭宽带作为唯一公网入口。
- Telegram API 访问通过代理/海外节点链路，HTTPS 可达但链路延迟明显高于普通内网 API。

当前云侧与边缘事实：

- 前端静态资源、部分公开分发能力与域名解析依赖 Cloudflare。
- 正式 Web 静态站由 Cloudflare Pages 承接；正式 Web API 与 RMB 支付入口由 Cloudflare Tunnel 回源云控制面。
- R2 `user-data-prod` 是正式新对象写入与公开媒体分发事实源。
- MinIO 不再承接正式新写入公开事实源；`assets.aivison.it.com` 仅作为 legacy 旧外链、人工回滚和迁移排障入口，正式应用不再生成该域名 URL。
- Web/API 的海外访问路径详见 [网络暴露与代理穿透](./子模块_网络暴露与代理穿透_network_proxy.md) 与 [边缘节点运维指南](./子模块_边缘节点运维指南_edge_node_ops.md)。

### 边缘 VPS

当前海外边缘层至少包含两台 VPS。详细运维 SOP 见 `docs/子模块_边缘节点运维指南_edge_node_ops.md`。

| 节点 | 入口 | 资源快照 | 当前职责 | 风险 |
| :--- | :--- | :--- | :--- | :--- |
| Web/Nginx 边缘 VPS `web` | Tailscale `100.88.57.122`，公网 `154.17.30.113`，SSH `root@100.88.57.122` 使用 `frontend/ssh_key/id_rsa.pem` | Ubuntu 24.04，2 vCPU，1.9GiB RAM，40G 根盘；2026-06-18 快照约 32G 已用、6.2G 可用，使用率约 84% | `web-test.aivison.it.com` 测试静态站与 `/api/` 反代，`assets.aivison.it.com` legacy MinIO 代理，`/root/dist` 正式 Web 回滚副本；`nginx` 与 `tailscaled` active | 根盘仍低于 20% 可用；`docker` 命令未安装，不要声称已检查容器状态；不再承接正式 `web.aivison.it.com` 主流量 |
| Telegram Local API VPS | 公网 `69.63.220.115` | 本轮 SSH key 未打通，CPU/内存/磁盘待补采；公网 `8081/8082` 可达 | Telegram Local Bot API `8081` 与文件服务 `8082`，支撑大文件下载/上传 | 当前主服务器未纳入 SSH 免密管理，资源与容器状态不可远程只读确认 |

边缘容量判断：

- Web 边缘根盘低于 10% 可用时，不建议发布新静态资源、扩大 Nginx cache 或新增大日志调试。
- `assets.aivison.it.com` 根路径返回 403 不代表具体旧外链/人工回滚对象不可读；验收该链路必须测试真实 object URL。正式 Web/Dashboard 响应不应再返回该域名。
- Telegram Local API 节点如果 SSH 不可用，发生 8081/8082 故障时只能做公网端口判断，无法快速查看容器日志和挂载目录，应优先补齐 SSH key 管理。

## 6. 数据存储快照

### PostgreSQL

2026-06-18 03:06 生产数据库 `bot_db` 约 3444MB。生产库主要体积来自历史与日志表；迁移、归档或索引决策前必须重新采集。

2026-06-25 起，本地主服务器云正式 shadow 同步的数据库获取路径正式切为 `CLOUD_PROD_DB_DUMP_MODE=remote_r2`：`scripts/sync_cloud_prod_to_local_shadow.py --execute` 通过 SSH 让 `allbot-do-sgp1-control` 在云机执行 PostgreSQL dump，临时上传 dump/sha256 到 R2 `user-data-prod/__shadow-transfer/<timestamp>`，本地主服务器经 HTTPS/rclone 下载校验后恢复为本地 `bot_db_prod_shadow`；中间库为 `bot_db_prod_shadow_next`，旧版本保留为带时间戳的 `bot_db_prod_shadow_previous_<timestamp>`；dump、sha256 与 manifest 位于 ignored 的 `backups/cloud-prod-shadow/<timestamp>/`。`R2_BUCKET_SYNC_ENABLED=false` 时每日任务只保留数据库 dump/restore 与 Redis 摘要，不镜像生产媒体桶；该开关不影响 `remote_r2` 的 `__shadow-transfer` 临时 dump 传输。Redis/Valkey 摘要采集仍可通过 `CLOUD_PROD_DB_TUNNEL_SSH_HOST=allbot-do-sgp1-control` 经云正式控制面 SSH tunnel 访问托管服务；旧 `local_tunnel` dump 模式仅作为 fallback/专项诊断。该库可供灾备预热和后续只读分析；业务分析表、BI、Notebook、脱敏访问边界尚未定义，不应默认扩大访问权限。

| 表 | 近似行数 | 总体积 |
| :--- | ---: | ---: |
| `history` | 1,979,345 | 2284MB |
| `user_logs` | 2,861,963 | 475MB |
| `worker_logs` | 1,758,668 | 447MB |
| `users` | 138,584 | 101MB |
| `checkin_history` | 525,608 | 51MB |
| `user_interactions` | 205,857 | 43MB |
| `referrals` | 124,166 | 15MB |
| `gallery_posts` | 20,894 | 8664kB |
| `orders` | 9,278 | 4776kB |

用户与生成量快照：

| 指标 | 数量 |
| :--- | ---: |
| 注册用户 | 138,584 |
| 近 1 天活跃用户 | 9,729 |
| 近 7 天活跃用户 | 22,055 |
| 近 30 天活跃用户 | 44,195 |
| 历史记录总数 | 约 1,979,345 |
| 近 1 天历史记录 | 31,926 |
| 近 7 天历史记录 | 179,627 |
| 近 30 天历史记录 | 760,273 |
| active Gallery 投稿 | 19,076 |
| 成功订单 | 5,474 |

### Redis

正式运行态当前由云侧 Valkey/Redis 承载，用于 Bot/Web 运行态、Central API 队列、worker 心跳、并发锁、pending finalizer、限流等短生命周期数据。下表为 2026-06-18 03:06 云正式聚合快照；不同 URL 可能指向同一托管 Valkey 实例的不同逻辑用途。

| 入口 | used_memory | clients | blocked | rejected | evicted | dbsize |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `REDIS_URL` | 61.95MB | 91 | 0 | 0 | 0 | 42,979 |
| `WORKER_REDIS_URL` | 61.95MB | 91 | 0 | 0 | 0 | 23,096 |

shadow 同步只记录 Redis/Valkey `INFO memory` 与 `DBSIZE` 摘要，不恢复队列、锁、heartbeat 或其它运行态 key。灾备切本地时 Redis 视为运行态重建/人工对账问题，不把 shadow 摘要当作可恢复数据源。

### MinIO

MinIO 本地数据目录：`/home/hfy/APP/minio-deploy/data`，迁移前快照总量约 453GB。当前正式新数据写入 R2；本地 MinIO 保留 legacy 历史媒体、旧输入和本地热数据，不应作为新生成结果公开事实源。2026-06-24 起新增可选 R2 shadow 同步：`R2_BUCKET_SYNC_ENABLED=true` 时，`user-data-prod-shadow` 保存 R2 `user-data-prod` 的本地增量副本，`user-data-prod-shadow-quarantine/<timestamp>/` 保存云端覆盖或删除导致的旧本地对象，禁止硬删替代 quarantine；数据库-only timer 可设 `R2_BUCKET_SYNC_ENABLED=false` 跳过该媒体桶镜像。2026-06-25 起可启用 `user-data-complete-shadow` 作为完整合并备份桶：每日从本地 `user-data-prod-shadow` 非破坏式 copy，不重复从 R2 拉取；`bot-data` / `comfyui-temp` 只在一次性手动补齐时用 `--ignore-existing` 导入，避免每日任务重复扫描 legacy 大桶。

| 桶/目录 | 当前体积 | 备注 |
| :--- | ---: | :--- |
| `bot-data` | 268GB | 生产输入/用户数据热桶 |
| `comfyui-temp` | 182GB | 生产生成结果热桶 |
| `bot-template` | 2.5GB | 模板资源 |
| `comfyui-temp-test` | 717MB | 测试结果桶 |
| `bot-data-test` | 266MB | 测试输入桶 |
| `comfyui-input` | 17MB | 旧/兼容输入目录 |
| `user-data-prod-shadow` | 待首次同步后采集 | R2 `user-data-prod` 的本地 shadow 副本 |
| `user-data-complete-shadow` | 待首次合并后采集 | R2 shadow + legacy MinIO 的完整合并备份桶；日常只 copy shadow，legacy 只手动首导 |
| `user-data-prod-shadow-quarantine` | 待首次同步后采集 | rclone `--backup-dir` quarantine 桶，按 timestamp 保留旧对象 |

MinIO 是主服务器历史数据与内存占用大户之一。规划清理时应先确认 R2 命中率、可见热集补齐状态和 legacy 旧外链/人工回滚访问量，再逐步缩短本地热数据生命周期。

## 7. 当前容量判断

当前系统瓶颈顺序大致为：

1. GPU 任务吞吐与视频任务长尾耗时。
2. 公网/Cloudflare/Web 边缘到云控制面的链路延迟，以及前端多接口串行等待。
3. R2 result URL 探测、R2 公开域名/短签耗时，以及 legacy `assets.aivison.it.com` 旧外链/人工回滚链路的边缘缓存/磁盘压力。
4. 云控制面到本地 GPU/ComfyUI 的 Tailscale/内网链路稳定性，以及本地 GPU 节点短暂停顿。
5. Dashboard stats/外部接口熔断与托管 Valkey/PostgreSQL 连接池压力。
6. ComfyUI 本地 `input/output/temp` 会继续随视频任务快速增长，若缺少定期巡检，远端 GPU 节点仍可能再次磁盘吃紧。

当前 CPU、Redis、Postgres 数据体积都不是第一瓶颈。若做云化，优先迁移控制面、公开对象分发与数据库备份；GPU 侧优先按任务类型增减 LAN AIO / RunPod / remote worker，而不是默认全量替换本地 7 张物理 GPU。

推荐容量策略：

- 控制面云化：Bot/Web/Payment/Central/Dashboard 已迁到云 VM，后续重点是规格升级、拆分 Dashboard 或引入第二控制面节点。
- 数据面分层：Postgres/Valkey 已采用云侧口径；R2 承接公开媒体分发和新对象写入。
- 本地 shadow 副本：每日同步只用于灾备预热和只读分析，不改变正式服务事实源；灾备写入前必须停 shadow timer 并确认 manifest/RPO。
- 本地 GPU 保留：4 台 GPU 服务器继续作为主算力池，本地 worker/relay、LAN AIO 与远程 worker 通过 Central worker 协议接入。
- 云 GPU 弹性：手动 RunPod 只在队列积压或单类任务爆发时临时拉起，不建议 24/7 常驻替代本地 GPU；具体 profile/slot 数只进入运维日志，不写成长期容量事实。
- MinIO 生命周期：生产热结果保留有限天数，长期公开访问走 R2，定期清理测试桶和临时桶。
- Web 体验优化：优先减少首屏/结果页串行 API 等待，R2 result 探测失败时快速返回 `pending_result` 或缓存快照，降低用户端 499。

## 8. 重新采集 Checklist

做采购、迁移或扩容决策前，至少重新采集：

- `hostnamectl`、`lscpu`、`free -h`、`df -hT`
- `docker ps`、`docker stats --no-stream`
- 云内、Web 边缘到云、公网域名三段 API 延迟
- Postgres 数据库大小、表大小、近 1/7/30 天活跃与历史量
- 本地 `bot_db_prod_shadow` 最新 manifest、dump sha256、Alembic 版本和关键表行数
- Redis `INFO memory`、`INFO keyspace`、Central pending/running/heartbeat
- Central pending 最老等待时间、`queue_by_type`、`healthy/error/quarantined` worker 数
- MinIO 桶大小与最近 7 天出入站量
- MinIO `user-data-prod-shadow` 与 `user-data-prod-shadow-quarantine` 桶大小、最近一次 rclone 同步日志和抽样对象 size/etag
- 所有 ComfyUI `/system_stats` 与 Dashboard GPU 监控
- Cloudflare/R2 命中率、R2 result timeout、MinIO 回源量、边缘 VPS 499/502/504 错误率
- 各 GPU 节点磁盘剩余空间，尤其是 `192.168.1.177`
- GPU 节点上 `comfy0`/`comfy1` 的 GPU 绑定、模型目录和 `inst0`/`inst1` 挂载是否仍与 `docs/子模块_局域网GPU节点资源与运维_lan_gpu_resource_ops.md` 一致

采集结果必须标注具体日期和时区，避免把实时队列或短期活动峰值写成长期容量。
